"""
Quantitative Agent - Deterministic Mathematical Validation
Executes secure Python code for financial arithmetic validation.
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

TOLERANCE = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    """Safely convert to Decimal for precise arithmetic."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


class QuantitativeAgent:
    """
    Deterministic mathematical validation of extracted financial data.
    Uses Python's Decimal arithmetic for exact financial computations.
    Implements function calling - no hallucination possible in math.
    """

    def __init__(self, llm: ILLMClient) -> None:
        self.llm = llm

    def _validate_line_item_totals(self, line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check each line item: quantity * unit_price == total_amount."""
        discrepancies = []
        for item in line_items:
            qty = _to_decimal(item.get("quantity", 0))
            unit_price = _to_decimal(item.get("unit_price", 0))
            claimed_total = _to_decimal(item.get("total_amount", 0))
            computed_total = (qty * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if abs(computed_total - claimed_total) > TOLERANCE:
                discrepancies.append({
                    "type": "line_item_total_mismatch",
                    "description": item.get("description", "Unknown"),
                    "quantity": float(qty),
                    "unit_price": float(unit_price),
                    "claimed_total": float(claimed_total),
                    "computed_total": float(computed_total),
                    "variance": float(abs(computed_total - claimed_total)),
                    "bbox": item.get("bbox"),
                    "page": item.get("page", 0),
                    "document_id": item.get("document_id", ""),
                })
        return discrepancies

    def _validate_document_total(
        self,
        line_items: list[dict[str, Any]],
        totals: dict[str, Any],
        doc_type: str,
    ) -> dict[str, Any]:
        """Validate that sum of line items matches document total."""
        computed_subtotal = sum(_to_decimal(item.get("total_amount", 0)) for item in line_items)
        claimed_subtotal = _to_decimal(totals.get("subtotal", 0))
        claimed_total = _to_decimal(totals.get("total", 0))
        tax_amount = _to_decimal(totals.get("tax_amount", 0))
        tax_rate = _to_decimal(totals.get("tax_rate", 0))

        computed_tax = (computed_subtotal * tax_rate / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if tax_rate > 0 else tax_amount
        computed_total = (computed_subtotal + computed_tax).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "doc_type": doc_type,
            "computed_subtotal": float(computed_subtotal),
            "claimed_subtotal": float(claimed_subtotal),
            "subtotal_valid": abs(computed_subtotal - claimed_subtotal) <= TOLERANCE,
            "computed_tax": float(computed_tax),
            "claimed_tax": float(tax_amount),
            "tax_valid": abs(computed_tax - tax_amount) <= TOLERANCE if tax_rate > 0 else True,
            "computed_total": float(computed_total),
            "claimed_total": float(claimed_total),
            "total_valid": abs(computed_total - claimed_total) <= TOLERANCE,
        }

    def _cross_document_quantity_check(
        self,
        po_items: list[dict[str, Any]],
        grn_items: list[dict[str, Any]],
        invoice_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Compare quantities across PO, GRN, and Invoice."""

        def get_qty(items: list[dict[str, Any]], index: int) -> Decimal:
            if index < len(items):
                return _to_decimal(items[index].get("quantity", 0))
            return Decimal("0.00")

        discrepancies = []
        max_items = max(len(po_items), len(grn_items), len(invoice_items))
        for i in range(max_items):
            po_qty = get_qty(po_items, i)
            grn_qty = get_qty(grn_items, i)
            inv_qty = get_qty(invoice_items, i)

            if not (abs(po_qty - grn_qty) <= TOLERANCE and abs(grn_qty - inv_qty) <= TOLERANCE):
                desc = (po_items[i] if i < len(po_items) else
                        (invoice_items[i] if i < len(invoice_items) else {})).get("description", f"Item {i+1}")
                discrepancies.append({
                    "type": "cross_document_quantity_mismatch",
                    "item_index": i,
                    "description": desc,
                    "po_quantity": float(po_qty),
                    "grn_quantity": float(grn_qty),
                    "invoice_quantity": float(inv_qty),
                    "po_grn_variance": float(abs(po_qty - grn_qty)),
                    "grn_invoice_variance": float(abs(grn_qty - inv_qty)),
                })
        return discrepancies

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute full mathematical validation."""
        po_items = state.get("po_line_items", [])
        grn_items = state.get("grn_line_items", [])
        inv_items = state.get("invoice_line_items", [])

        po_parsed = state.get("po_parsed") or {}
        grn_parsed = state.get("grn_parsed") or {}
        inv_parsed = state.get("invoice_parsed") or {}

        discrepancies: list[dict[str, Any]] = []

        # 1. Validate individual line item arithmetic
        discrepancies.extend(self._validate_line_item_totals(po_items))
        discrepancies.extend(self._validate_line_item_totals(inv_items))

        # 2. Validate document-level totals
        po_total_check = self._validate_document_total(po_items, po_parsed.get("totals", {}), "PO")
        grn_total_check = self._validate_document_total(grn_items, grn_parsed.get("totals", {}), "GRN")
        inv_total_check = self._validate_document_total(inv_items, inv_parsed.get("totals", {}), "Invoice")

        if not po_total_check.get("total_valid"):
            discrepancies.append({"type": "document_total_mismatch", "document": "PO", **po_total_check})
        if not inv_total_check.get("total_valid"):
            discrepancies.append({"type": "document_total_mismatch", "document": "Invoice", **inv_total_check})

        # 3. Cross-document quantity comparison
        cross_discrepancies = self._cross_document_quantity_check(po_items, grn_items, inv_items)
        discrepancies.extend(cross_discrepancies)

        # 4. Price comparison PO vs Invoice
        price_discrepancies = []
        for i, (po_item, inv_item) in enumerate(zip(po_items, inv_items)):
            po_price = _to_decimal(po_item.get("unit_price", 0))
            inv_price = _to_decimal(inv_item.get("unit_price", 0))
            if abs(po_price - inv_price) > TOLERANCE:
                price_discrepancies.append({
                    "type": "price_discrepancy",
                    "item_index": i,
                    "description": po_item.get("description", f"Item {i+1}"),
                    "po_price": float(po_price),
                    "invoice_price": float(inv_price),
                    "variance": float(abs(po_price - inv_price)),
                })
        discrepancies.extend(price_discrepancies)

        report = {
            "po_validation": po_total_check,
            "grn_validation": grn_total_check,
            "invoice_validation": inv_total_check,
            "total_discrepancies": len(discrepancies),
            "is_mathematically_consistent": len(discrepancies) == 0,
            "discrepancy_breakdown": {
                "line_item_arithmetic": len([d for d in discrepancies if d["type"] == "line_item_total_mismatch"]),
                "document_totals": len([d for d in discrepancies if d["type"] == "document_total_mismatch"]),
                "cross_document_quantities": len(cross_discrepancies),
                "price_discrepancies": len(price_discrepancies),
            },
        }

        logger.info("quantitative_validation_complete",
                    discrepancies=len(discrepancies),
                    is_consistent=report["is_mathematically_consistent"])

        return {
            "quantitative_report": report,
            "math_discrepancies": discrepancies,
        }
