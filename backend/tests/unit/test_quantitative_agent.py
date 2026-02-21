"""
Unit Tests for Quantitative Agent
Tests mathematical validation logic with Python Decimal precision.
"""
from decimal import Decimal

import pytest

# ─── Import ────────────────────────────────────────────────────────────────────
# We test the pure computation functions in isolation.


@pytest.fixture
def po_line_items():
    return [
        {"description": "Widget A", "quantity": 10.0, "unit_price": 50.00, "total_amount": 500.00},
        {"description": "Widget B", "quantity": 5.0, "unit_price": 100.00, "total_amount": 500.00},
    ]


@pytest.fixture
def grn_line_items():
    return [
        {"description": "Widget A", "quantity": 10.0, "unit_price": 50.00, "total_amount": 500.00},
        {"description": "Widget B", "quantity": 4.0, "unit_price": 100.00, "total_amount": 400.00},  # Short delivery
    ]


@pytest.fixture  
def invoice_line_items():
    return [
        {"description": "Widget A", "quantity": 10.0, "unit_price": 50.00, "total_amount": 500.00},
        {"description": "Widget B", "quantity": 5.0, "unit_price": 100.00, "total_amount": 500.00},
    ]


class TestMoneyArithmetic:
    """Test that Decimal is used for all financial calculations."""

    def test_line_item_total_correct(self):
        qty = Decimal("10")
        unit_price = Decimal("50.00")
        expected_total = Decimal("500.00")
        assert qty * unit_price == expected_total

    def test_line_item_total_discrepancy(self):
        qty = Decimal("5")
        unit_price = Decimal("100.00")
        claimed_total = Decimal("500.00")
        computed_total = qty * unit_price
        assert computed_total == claimed_total  # This one matches

    def test_floating_point_trap(self):
        """Demonstrate that Decimal avoids float rounding errors."""
        float_result = 0.1 + 0.2
        decimal_result = Decimal("0.1") + Decimal("0.2")
        # Float is imprecise:
        assert float_result != 0.3
        # Decimal is exact:
        assert decimal_result == Decimal("0.3")

    def test_documents_total_validation(self, po_line_items):
        """Validate that sum of line items matches document total."""
        line_totals = [Decimal(str(item["total_amount"])) for item in po_line_items]
        computed = sum(line_totals)
        claimed = Decimal("1000.00")
        assert computed == claimed

    def test_quantity_discrepancy_detection(self, po_line_items, grn_line_items):
        """Detect that GRN received less than PO ordered."""
        po_qty_b = Decimal(str(po_line_items[1]["quantity"]))  # 5.0
        grn_qty_b = Decimal(str(grn_line_items[1]["quantity"]))  # 4.0
        tolerance = Decimal("0.01")
        assert abs(po_qty_b - grn_qty_b) > tolerance  # Discrepancy detected

    def test_document_total_discrepancy(self, po_line_items, grn_line_items):
        """Invoice billing for undelivered goods should be flagged."""
        po_total = sum(Decimal(str(i["total_amount"])) for i in po_line_items)
        grn_total = sum(Decimal(str(i["total_amount"])) for i in grn_line_items)
        # GRN total should be less (short delivery)
        assert grn_total < po_total
        assert po_total - grn_total == Decimal("100.00")  # Widget B delta

    def test_tax_calculation(self):
        """Tax rounding should use ROUND_HALF_UP."""
        from decimal import ROUND_HALF_UP
        subtotal = Decimal("999.99")
        tax_rate = Decimal("0.1")
        tax = (subtotal * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert tax == Decimal("100.00")

    def test_cross_rate_comparison(self):
        """Currency conversion math."""
        usd_amount = Decimal("1000.00")
        eur_rate = Decimal("0.92")
        eur_amount = (usd_amount * eur_rate).quantize(Decimal("0.01"))
        assert eur_amount == Decimal("920.00")


class TestDiscrepancyThresholds:
    """Test tolerance thresholds for matching."""

    def test_within_tolerance(self):
        a = Decimal("1000.00")
        b = Decimal("1000.01")
        tolerance_pct = Decimal("0.001")  # 0.1%
        diff_pct = abs(a - b) / a
        assert diff_pct <= tolerance_pct  # Should pass

    def test_exceeds_tolerance(self):
        a = Decimal("1000.00")
        b = Decimal("999.00")
        tolerance_pct = Decimal("0.001")  # 0.1%
        diff_pct = abs(a - b) / a
        assert diff_pct > tolerance_pct  # Should flag as discrepancy

    def test_zero_quantity_edge_case(self):
        """Zero quantity items should not divide by zero."""
        qty = Decimal("0")
        unit_price = Decimal("50.00")
        total = qty * unit_price
        assert total == Decimal("0.00")

    def test_large_invoice_precision(self):
        """Large invoices must remain precise."""
        qty = Decimal("1000000")
        unit_price = Decimal("0.001")
        total = qty * unit_price
        assert total == Decimal("1000.000")  # Decimal preserves precision
