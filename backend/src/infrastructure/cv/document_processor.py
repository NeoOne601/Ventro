"""
Document Computer Vision Pipeline
Multimodal ingestion: PDF parsing, layout analysis, table extraction, 
bounding box extraction, and text OCR with spatial metadata preservation.
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

logger = structlog.get_logger(__name__)

# Document type keywords for classification
DOC_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.PURCHASE_ORDER: [
        "purchase order", "p.o.", "po number", "order number", "procurement",
        "buyer", "ship to", "vendor", "requisition",
    ],
    DocumentType.GOODS_RECEIPT_NOTE: [
        "goods receipt", "grn", "delivery note", "received", "receiving",
        "warehouse", "goods received", "delivery receipt", "packing slip",
    ],
    DocumentType.INVOICE: [
        "invoice", "bill to", "tax invoice", "invoice number", "amount due",
        "payment due", "remit to", "statement", "invoice date",
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
    Multimodal document processing pipeline.
    Extracts text, tables, and bounding boxes from PDFs.
    Classifies documents and produces ParsedDocument with full spatial metadata.
    """

    def __init__(self, temp_dir: str = "/tmp/mas_vgfr_uploads") -> None:
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def process_pdf(
        self, file_path: str, document_id: str | None = None
    ) -> ParsedDocument:
        """
        Process a PDF file through the full CV pipeline.
        Returns ParsedDocument with spatial metadata.
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

        for page_num in range(len(pdf_doc)):
            blocks, page_text = _extract_bounding_boxes_from_pdf(pdf_doc, page_num)
            tables = _extract_tables_from_pdf(pdf_doc, page_num)

            all_blocks.extend(blocks)
            all_tables.extend(tables)
            text_by_page[page_num] = page_text

        full_text = "\n".join(text_by_page.values())
        doc_type, classification_confidence = _classify_document(full_text)

        # Extract line items from tables
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
                bbox=BoundingBox(**block["bbox"], page=block["page"]),
                confidence=1.0,
            )
            for block in all_blocks
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
            pages=len(pdf_doc),
            line_items=len(line_items),
            text_blocks=len(all_blocks),
            tables=len(all_tables),
        )

        return ParsedDocument(
            metadata=metadata,
            line_items=line_items,
            text_fragments=text_fragments,
            raw_text_by_page=text_by_page,
            additional_fields={"tables_raw": all_tables, "blocks_raw": all_blocks},
        )

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
                        "chunk_type": "text_block",
                    },
                })
                current_chunk_text = text + " "
                current_chunk_bbox = fragment.bbox.to_dict() if fragment.bbox else None
                current_page = fragment.bbox.page if fragment.bbox else 0
            else:
                current_chunk_text += text + " "
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
