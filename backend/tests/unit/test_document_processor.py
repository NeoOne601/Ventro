"""
Unit Tests for Document Processor (CV Pipeline)
"""
import os
import tempfile
from pathlib import Path
import pytest


class TestDocumentClassification:
    """Test keyword-based document type classification."""

    def test_classifies_purchase_order(self):
        from backend.src.infrastructure.cv.document_processor import _classify_document
        from backend.src.domain.entities import DocumentType
        doc_type, conf = _classify_document(
            "PURCHASE ORDER\nPO Number: 12345\nVendor: Acme Corp\nBuyer: XYZ Inc\nShip to: Warehouse A"
        )
        assert doc_type == DocumentType.PURCHASE_ORDER
        assert conf > 0.3

    def test_classifies_invoice(self):
        from backend.src.infrastructure.cv.document_processor import _classify_document
        from backend.src.domain.entities import DocumentType
        doc_type, conf = _classify_document(
            "TAX INVOICE\nInvoice Number: INV-2024-001\nBill To: XYZ Inc\nAmount Due: $1500\nPayment Due: 30 days"
        )
        assert doc_type == DocumentType.INVOICE
        assert conf > 0.3

    def test_classifies_grn(self):
        from backend.src.infrastructure.cv.document_processor import _classify_document
        from backend.src.domain.entities import DocumentType
        doc_type, conf = _classify_document(
            "GOODS RECEIPT NOTE\nGRN Number: GRN-001\nReceived at Warehouse\nGoods received from supplier"
        )
        assert doc_type == DocumentType.GOODS_RECEIPT_NOTE
        assert conf > 0.3

    def test_unknown_for_blank(self):
        from backend.src.infrastructure.cv.document_processor import _classify_document
        from backend.src.domain.entities import DocumentType
        doc_type, conf = _classify_document("")
        assert doc_type == DocumentType.UNKNOWN
        assert conf == 0.0


class TestTableParsing:
    """Test line item extraction from table rows."""

    def test_parse_table_to_line_items(self):
        from backend.src.infrastructure.cv.document_processor import _parse_table_to_line_items
        from backend.src.domain.entities import DocumentType

        table = {
            "rows": [
                ["Description", "Qty", "Unit Price", "Amount"],
                ["Widget A", "10", "50.00", "500.00"],
                ["Widget B", "5", "100.00", "500.00"],
            ],
            "bbox": {"x0": 0.0, "y0": 0.2, "x1": 1.0, "y1": 0.5},
            "page": 0,
        }
        items = _parse_table_to_line_items(table, "doc-123", DocumentType.PURCHASE_ORDER)
        assert len(items) == 2
        assert items[0]["description"] == "Widget A"
        assert items[0]["quantity"] == 10.0
        assert items[0]["unit_price"] == 50.0
        assert items[0]["total_amount"] == 500.0

    def test_skips_empty_rows(self):
        from backend.src.infrastructure.cv.document_processor import _parse_table_to_line_items
        from backend.src.domain.entities import DocumentType

        table = {
            "rows": [
                ["Description", "Qty", "Amount"],
                ["", "", ""],  # Empty row
                ["Widget A", "5", "250.00"],
            ],
            "bbox": None, "page": 0,
        }
        items = _parse_table_to_line_items(table, "doc-456", DocumentType.INVOICE)
        assert len(items) == 1

    def test_handles_short_table(self):
        from backend.src.infrastructure.cv.document_processor import _parse_table_to_line_items
        from backend.src.domain.entities import DocumentType
        table = {"rows": [["Header"]], "bbox": None, "page": 0}
        items = _parse_table_to_line_items(table, "doc-789", DocumentType.INVOICE)
        assert items == []


class TestBoundingBoxNormalization:
    """Test bounding box coordinate normalization."""

    def test_bbox_within_unit_range(self):
        from backend.src.domain.entities import BoundingBox
        bbox = BoundingBox(x0=0.1, y0=0.2, x1=0.8, y1=0.9, page=0)
        assert 0 <= bbox.x0 <= 1
        assert 0 <= bbox.y0 <= 1
        assert 0 <= bbox.x1 <= 1
        assert 0 <= bbox.y1 <= 1
        assert bbox.x1 > bbox.x0
        assert bbox.y1 > bbox.y0

    def test_bbox_to_dict(self):
        from backend.src.domain.entities import BoundingBox
        bbox = BoundingBox(x0=0.1, y0=0.2, x1=0.8, y1=0.9, page=1)
        d = bbox.to_dict()
        assert d["x0"] == 0.1
        assert d["page"] == 1
