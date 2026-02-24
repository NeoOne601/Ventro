"""
Document Computer Vision Pipeline
Multimodal ingestion: PDF, XLSX/CSV parsing, layout analysis, table extraction,
bounding box extraction, and multilingual OCR with spatial metadata preservation.

Processing tiers:
  Tier 1 — PyMuPDF (native text, all digital PDFs)
  Tier 2 — Tesseract OCR (scanned pages, 100+ languages)
  Tier 3 — Qwen2-VL (complex layouts, handwriting, mixed-script docs)
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import structlog
from PIL import Image

from ...domain.entities import (
    BoundingBox,
    DocumentMetadata,
    DocumentType,
    LineItem,
    MonetaryAmount,
    ParsedDocument,
    TextFragment,
)
from .ocr_processor import (
    TESSERACT_LANG_PACKS,
    is_page_scanned,
    ocr_page_with_tesseract,
    render_page_to_image,
)

logger = structlog.get_logger(__name__)

# Document type keywords for classification (English + key multilingual terms)
DOC_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.PURCHASE_ORDER: [
        # English
        "purchase order", "p.o.", "po number", "order number", "procurement",
        "buyer", "ship to", "vendor", "requisition",
        # Arabic
        "أمر الشراء", "طلب شراء",
        # Hindi
        "क्रय आदेश", "खरीद आदेश",
        # Chinese
        "采购订单", "订购单",
        # Japanese
        "発注書", "購買注文",
        # German
        "bestellung", "kaufvertrag",
        # French
        "bon de commande",
    ],
    DocumentType.GOODS_RECEIPT_NOTE: [
        # English
        "goods receipt", "grn", "delivery note", "received", "receiving",
        "warehouse", "goods received", "delivery receipt", "packing slip",
        # Arabic
        "استلام البضائع", "سند استلام",
        # Hindi
        "माल प्राप्ति",
        # Chinese
        "收货单", "入库单",
        # Japanese
        "納品書", "受領書",
        # German
        "wareneingangsschein", "lieferschein",
        # French
        "bon de réception", "bon de livraison",
    ],
    DocumentType.INVOICE: [
        # English
        "invoice", "bill to", "tax invoice", "invoice number", "amount due",
        "payment due", "remit to", "statement", "invoice date",
        # Arabic
        "فاتورة", "فاتورة ضريبية",
        # Hindi
        "चालान", "बिल",
        # Chinese
        "发票", "税务发票",
        # Japanese
        "請求書", "インボイス",
        # German
        "rechnung", "steuerrechnung",
        # French
        "facture", "facture fiscale",
    ],
}


def _classify_document(text: str) -> tuple[DocumentType, float]:
    """Classify document type based on keyword presence."""
    text_lower = text.lower()
    scores: dict[DocumentType, int] = {}

    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        scores[doc_type] = score

    if not scores or max(scores.values()) == 0:
        return DocumentType.UNKNOWN, 0.0

    best_type = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    confidence = scores[best_type] / total if total > 0 else 0.0
    return best_type, min(confidence, 1.0)


def _extract_bounding_boxes_from_pdf(
    doc: fitz.Document, page_num: int
) -> tuple[list[dict[str, Any]], str]:
    """
    Extract text blocks with bounding boxes from a PDF page.
    Returns (blocks_with_bbox, full_page_text).
    """
    page = doc[page_num]
    blocks = []
    full_text_parts = []

    # Get detailed text with coordinates
    text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    page_width = page.rect.width
    page_height = page.rect.height

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue

        block_text_parts = []
        block_bbox = block.get("bbox", [0, 0, 0, 0])

        for line in block.get("lines", []):
            line_text = ""
            for span in line.get("spans", []):
                span_text = span.get("text", "").strip()
                if span_text:
                    line_text += span_text + " "

            if line_text.strip():
                block_text_parts.append(line_text.strip())

        block_text = "\n".join(block_text_parts)
        if block_text.strip():
            full_text_parts.append(block_text)
            blocks.append({
                "text": block_text,
                "bbox": {
                    "x0": round(block_bbox[0] / page_width, 4),
                    "y0": round(block_bbox[1] / page_height, 4),
                    "x1": round(block_bbox[2] / page_width, 4),
                    "y1": round(block_bbox[3] / page_height, 4),
                },
                "bbox_pixels": {"x0": block_bbox[0], "y0": block_bbox[1],
                                "x1": block_bbox[2], "y1": block_bbox[3]},
                "page": page_num,
                "page_width": page_width,
                "page_height": page_height,
            })

    return blocks, "\n".join(full_text_parts)


def _extract_tables_from_pdf(doc: fitz.Document, page_num: int) -> list[dict[str, Any]]:
    """
    Extract table structures from PDF using PyMuPDF's table finder.
    Returns list of tables with cell data and bounding boxes.
    """
    page = doc[page_num]
    tables = []

    try:
        page_tables = page.find_tables()
        for table_obj in page_tables:
            table_data = table_obj.extract()
            table_bbox = table_obj.bbox
            page_width = page.rect.width
            page_height = page.rect.height

            rows = []
            for row in table_data:
                cells = []
                for cell in row:
                    cells.append(str(cell) if cell is not None else "")
                rows.append(cells)

            if rows:
                tables.append({
                    "rows": rows,
                    "bbox": {
                        "x0": round(table_bbox[0] / page_width, 4),
                        "y0": round(table_bbox[1] / page_height, 4),
                        "x1": round(table_bbox[2] / page_width, 4),
                        "y1": round(table_bbox[3] / page_height, 4),
                    },
                    "page": page_num,
                    "num_rows": len(rows),
                    "num_cols": max(len(r) for r in rows) if rows else 0,
                })
    except Exception as e:
        logger.warning("table_extraction_failed", page=page_num, error=str(e))

    return tables


def _parse_table_to_line_items(
    table: dict[str, Any],
    document_id: str,
    doc_type: DocumentType,
) -> list[dict[str, Any]]:
    """
    Convert a raw table structure to structured line items.
    Handles header detection and value extraction.
    """
    rows = table.get("rows", [])
    if len(rows) < 2:
        return []

    # Detect header row
    header = [str(h).lower().strip() for h in rows[0]]

    # Map columns to semantic fields
    col_map: dict[str, int] = {}
    for i, h in enumerate(header):
        if any(kw in h for kw in ["desc", "item", "product", "service", "particulars"]):
            col_map["description"] = i
        elif any(kw in h for kw in ["qty", "quantity", "units", "nos"]):
            col_map["quantity"] = i
        elif any(kw in h for kw in ["unit price", "rate", "price", "unit cost"]):
            col_map["unit_price"] = i
        elif any(kw in h for kw in ["amount", "total", "value", "line total"]):
            col_map["total_amount"] = i
        elif any(kw in h for kw in ["uom", "unit", "measure"]):
            col_map["unit_of_measure"] = i
        elif any(kw in h for kw in ["part", "sku", "code", "reference"]):
            col_map["part_number"] = i

    items = []
    for row_idx, row in enumerate(rows[1:], start=1):
        if not any(str(cell).strip() for cell in row):
            continue

        def get_cell(key: str, default: str = "") -> str:
            idx = col_map.get(key, -1)
            if idx >= 0 and idx < len(row):
                return str(row[idx]).strip()
            return default

        def parse_float(val: str) -> float:
            import re
            cleaned = re.sub(r"[^\d.]", "", val.replace(",", ""))
            try:
                return float(cleaned)
            except ValueError:
                return 0.0

        desc = get_cell("description")
        if not desc or desc.lower() in {"", "n/a", "-", "none"}:
            continue

        item = {
            "description": desc,
            "quantity": parse_float(get_cell("quantity", "1")),
            "unit_price": parse_float(get_cell("unit_price")),
            "total_amount": parse_float(get_cell("total_amount")),
            "unit_of_measure": get_cell("unit_of_measure", "each"),
            "part_number": get_cell("part_number") or None,
            "raw_text": " | ".join(str(c) for c in row),
            "row_index": row_idx,
            "confidence": 0.85,
            "bbox": table.get("bbox"),
            "page": table.get("page", 0),
            "document_id": document_id,
        }
        items.append(item)

    return items


class DocumentProcessor:
    """
    Multimodal document processing pipeline — Tier 1/2/3 routing.

    Tier 1 (PyMuPDF):   Digital PDFs — direct text + table extraction, full bbox
    Tier 2 (Tesseract): Scanned pages — OCR with 100+ language packs
    Tier 3 (Qwen2-VL):  Complex layouts — VLM structured extraction (optional)
    """

    def __init__(
        self,
        temp_dir: str = "/tmp/mas_vgfr_uploads",
        ocr_lang: str = TESSERACT_LANG_PACKS["default"],
        vlm_processor=None,   # Optional[VLMProcessor]
        enable_vlm: bool = False,
        ocr_dpi: int = 300,
    ) -> None:
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_lang = ocr_lang
        self.vlm_processor = vlm_processor
        self.enable_vlm = enable_vlm and vlm_processor is not None
        self.ocr_dpi = ocr_dpi
        logger.info(
            "document_processor_initialized",
            ocr_lang=ocr_lang,
            vlm_enabled=self.enable_vlm,
            ocr_dpi=ocr_dpi,
        )

    async def process_pdf(
        self, file_path: str, document_id: str | None = None
    ) -> ParsedDocument:
        """
        Process a PDF file through the full multi-tier CV pipeline.
        Automatically detects scanned pages and routes to Tesseract OCR.
        Returns ParsedDocument with spatial metadata and OCR provenance flags.
        """
        doc_id = document_id or str(uuid.uuid4())
        file_path_obj = Path(file_path)

        logger.info("processing_pdf", path=str(file_path_obj), doc_id=doc_id)

        try:
            pdf_doc = fitz.open(str(file_path_obj))
        except Exception as e:
            raise ValueError(f"Failed to open PDF: {e}") from e

        all_blocks: list[dict[str, Any]] = []
        all_tables: list[dict[str, Any]] = []
        text_by_page: dict[int, str] = {}
        ocr_applied_pages: list[int] = []
        detected_language: str | None = None

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            if is_page_scanned(page):
                # ── Tier 2: Tesseract OCR ──────────────────────────────────
                logger.info("routing_to_ocr", page=page_num, doc_id=doc_id)
                ocr_applied_pages.append(page_num)
                image_bytes = render_page_to_image(page, dpi=self.ocr_dpi)

                # Detect language on first scanned page via VLM if available
                if self.enable_vlm and detected_language is None:
                    detected_language = await self.vlm_processor.detect_language(image_bytes)
                    logger.info("language_detected_by_vlm", lang=detected_language)

                page_text, ocr_bboxes = ocr_page_with_tesseract(
                    image_bytes, lang=self.ocr_lang
                )
                text_by_page[page_num] = page_text

                # Convert OCR bboxes to block format
                for bbox_item in ocr_bboxes:
                    all_blocks.append({
                        "text": bbox_item["text"],
                        "bbox": {
                            "x0": bbox_item["x0"], "y0": bbox_item["y0"],
                            "x1": bbox_item["x1"], "y1": bbox_item["y1"],
                        },
                        "bbox_pixels": {},
                        "page": page_num,
                        "page_width": page.rect.width,
                        "page_height": page.rect.height,
                        "source": "ocr",
                        "ocr_confidence": bbox_item.get("confidence", 0.9),
                    })

                # ── Tier 3: VLM structured extraction (optional) ───────────
                if self.enable_vlm:
                    logger.info("routing_to_vlm", page=page_num, doc_id=doc_id)
                    vlm_result = await self.vlm_processor.extract_financial_data(
                        image_bytes, language_hint=detected_language
                    )
                    if vlm_result.get("line_items"):
                        # Inject VLM-extracted line items as synthetic blocks
                        for item in vlm_result["line_items"]:
                            all_blocks.append({
                                "text": (
                                    f"{item.get('description','')} | "
                                    f"qty:{item.get('quantity','')} | "
                                    f"price:{item.get('unit_price','')} | "
                                    f"total:{item.get('total','')} "
                                    f"[{vlm_result.get('currency','USD')}]"
                                ),
                                "bbox": None,
                                "page": page_num,
                                "source": "vlm",
                                "vlm_data": item,
                                "currency": vlm_result.get("currency", "USD"),
                            })
            else:
                # ── Tier 1: PyMuPDF native extraction ─────────────────────
                blocks, page_text = _extract_bounding_boxes_from_pdf(pdf_doc, page_num)
                tables = _extract_tables_from_pdf(pdf_doc, page_num)
                all_blocks.extend(blocks)
                all_tables.extend(tables)
                text_by_page[page_num] = page_text

        full_text = "\n".join(text_by_page.values())
        doc_type, classification_confidence = _classify_document(full_text)

        # Extract line items from tables (Tier 1 path)
        line_items_raw: list[dict[str, Any]] = []
        for table in all_tables:
            items = _parse_table_to_line_items(table, doc_id, doc_type)
            line_items_raw.extend(items)

        # Build domain entities
        line_items = [
            LineItem(
                id=str(uuid.uuid4()),
                description=item["description"],
                quantity=item["quantity"],
                unit_price=MonetaryAmount(item["unit_price"]),
                total_amount=MonetaryAmount(item["total_amount"]),
                unit_of_measure=item.get("unit_of_measure", "each"),
                part_number=item.get("part_number"),
                bbox=BoundingBox(**item["bbox"], page=item.get("page", 0)) if item.get("bbox") else None,
                row_index=item["row_index"],
                raw_text=item["raw_text"],
                confidence=item["confidence"],
            )
            for item in line_items_raw
        ]

        text_fragments = [
            TextFragment(
                text=block["text"],
                bbox=BoundingBox(**block["bbox"], page=block["page"]) if block.get("bbox") else None,
                confidence=block.get("ocr_confidence", 1.0),
            )
            for block in all_blocks
            if block.get("text")
        ]

        metadata = DocumentMetadata(
            id=doc_id,
            filename=file_path_obj.name,
            document_type=doc_type,
            total_pages=len(pdf_doc),
            file_size_bytes=file_path_obj.stat().st_size,
            mime_type="application/pdf",
            classification_confidence=classification_confidence,
        )

        pdf_doc.close()

        logger.info(
            "pdf_processed",
            doc_id=doc_id,
            doc_type=doc_type.value,
            pages=metadata.total_pages,
            line_items=len(line_items),
            text_blocks=len(all_blocks),
            tables=len(all_tables),
            ocr_pages=ocr_applied_pages,
            detected_language=detected_language,
        )

        return ParsedDocument(
            metadata=metadata,
            line_items=line_items,
            text_fragments=text_fragments,
            raw_text_by_page=text_by_page,
            additional_fields={
                "tables_raw": all_tables,
                "blocks_raw": all_blocks,
                "ocr_applied_pages": ocr_applied_pages,
                "detected_language": detected_language,
            },
        )

    async def process_spreadsheet(
        self, file_path: str, document_id: str | None = None
    ) -> ParsedDocument:
        """
        Process XLSX or CSV files as structured financial documents.
        Treats each sheet / CSV as a table of line items.
        """
        import csv
        doc_id = document_id or str(uuid.uuid4())
        file_path_obj = Path(file_path)
        suffix = file_path_obj.suffix.lower()

        all_rows: list[list[str]] = []

        if suffix == ".csv":
            with open(file_path_obj, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                all_rows = [row for row in reader]

        elif suffix in (".xlsx", ".xls"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path_obj, read_only=True, data_only=True)
                sheet = wb.active  # Use active (first) sheet
                for row in sheet.iter_rows(values_only=True):
                    all_rows.append([str(c) if c is not None else "" for c in row])
                wb.close()
            except ImportError:
                raise ImportError("Install openpyxl for XLSX support: pip install openpyxl")
        else:
            raise ValueError(f"Unsupported spreadsheet format: {suffix}")

        full_text = "\n".join(" | ".join(r) for r in all_rows)
        doc_type, confidence = _classify_document(full_text)

        synthetic_table = {"rows": all_rows, "bbox": None, "page": 0,
                           "num_rows": len(all_rows),
                           "num_cols": max((len(r) for r in all_rows), default=0)}
        line_items_raw = _parse_table_to_line_items(synthetic_table, doc_id, doc_type)

        line_items = [
            LineItem(
                id=str(uuid.uuid4()),
                description=item["description"],
                quantity=item["quantity"],
                unit_price=MonetaryAmount(item["unit_price"]),
                total_amount=MonetaryAmount(item["total_amount"]),
                unit_of_measure=item.get("unit_of_measure", "each"),
                part_number=item.get("part_number"),
                bbox=None,
                row_index=item["row_index"],
                raw_text=item["raw_text"],
                confidence=0.95,
            )
            for item in line_items_raw
        ]

        metadata = DocumentMetadata(
            id=doc_id,
            filename=file_path_obj.name,
            document_type=doc_type,
            total_pages=1,
            file_size_bytes=file_path_obj.stat().st_size,
            mime_type="text/csv" if suffix == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            classification_confidence=confidence,
        )

        logger.info(
            "spreadsheet_processed",
            doc_id=doc_id,
            format=suffix,
            rows=len(all_rows),
            line_items=len(line_items),
        )

        return ParsedDocument(
            metadata=metadata,
            line_items=line_items,
            text_fragments=[],
            raw_text_by_page={0: full_text},
            additional_fields={"spreadsheet_format": suffix},
        )

    async def process_document(
        self, file_path: str, document_id: str | None = None
    ) -> ParsedDocument:
        """
        Auto-routing entry point — detects format and dispatches to correct processor.
        Supported: PDF, XLSX, XLS, CSV.
        """
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            return await self.process_pdf(file_path, document_id)
        elif suffix in (".xlsx", ".xls", ".csv"):
            return await self.process_spreadsheet(file_path, document_id)
        else:
            raise ValueError(f"Unsupported document format: {suffix}. Supported: pdf, xlsx, xls, csv")

    async def chunk_document_for_embedding(
        self, parsed_doc: ParsedDocument, chunk_size: int = 512, overlap: int = 50
    ) -> list[dict[str, Any]]:
        """
        Chunk the parsed document into embeddable pieces with bounding box metadata.
        Each chunk preserves spatial coordinates for visual grounding.
        """
        chunks = []

        # Chunk by text blocks (each block becomes a chunk, merged if too small)
        current_chunk_text = ""
        current_chunk_bbox: dict[str, float] | None = None
        current_chunk_fragments: list[dict[str, Any]] = []
        current_page = 0

        for fragment in parsed_doc.text_fragments:
            text = fragment.text.strip()
            if not text:
                continue

            if len(current_chunk_text) + len(text) > chunk_size and current_chunk_text:
                # Save current chunk
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "payload": {
                        "text": current_chunk_text.strip(),
                        "document_id": parsed_doc.id,
                        "document_type": parsed_doc.metadata.document_type.value,
                        "page": current_page,
                        "bbox": current_chunk_bbox,
                        "fragments": current_chunk_fragments,
                        "chunk_type": "text_block",
                    },
                })
                current_chunk_text = text + " "
                current_chunk_bbox = fragment.bbox.to_dict() if fragment.bbox else None
                current_chunk_fragments = [{"text": text, "bbox": current_chunk_bbox}] if current_chunk_bbox else []
                current_page = fragment.bbox.page if fragment.bbox else 0
            else:
                current_chunk_text += text + " "
                frag_dict = fragment.bbox.to_dict() if fragment.bbox else None
                if frag_dict:
                    current_chunk_fragments.append({"text": text, "bbox": frag_dict})
                if current_chunk_bbox is None and fragment.bbox:
                    current_chunk_bbox = fragment.bbox.to_dict()
                    current_page = fragment.bbox.page

        # Don't forget the last chunk
        if current_chunk_text.strip():
            chunks.append({
                "id": str(uuid.uuid4()),
                "payload": {
                    "text": current_chunk_text.strip(),
                    "document_id": parsed_doc.id,
                    "document_type": parsed_doc.metadata.document_type.value,
                    "page": current_page,
                    "bbox": current_chunk_bbox,
                    "fragments": current_chunk_fragments,
                    "chunk_type": "text_block",
                },
            })

        # Add line items as individual semantic chunks
        for item in parsed_doc.line_items:
            chunk_text = (
                f"{item.description} | qty: {item.quantity} | "
                f"unit price: {item.unit_price.amount} | total: {item.total_amount.amount}"
            )
            chunks.append({
                "id": str(uuid.uuid4()),
                "payload": {
                    "text": chunk_text,
                    "document_id": parsed_doc.id,
                    "document_type": parsed_doc.metadata.document_type.value,
                    "page": item.bbox.page if item.bbox else 0,
                    "bbox": item.bbox.to_dict() if item.bbox else None,
                    "chunk_type": "line_item",
                    "line_item": {
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price.amount,
                        "total_amount": item.total_amount.amount,
                        "part_number": item.part_number,
                    },
                },
            })

        logger.info("document_chunked", doc_id=parsed_doc.id, chunks=len(chunks))
        return chunks
