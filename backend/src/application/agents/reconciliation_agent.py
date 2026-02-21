"""
Reconciliation Agent - Three-Way Match with Semantic Entity Resolution
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from rapidfuzz import fuzz

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

RECONCILIATION_PROMPT = """You are performing a three-way financial document reconciliation.

Purchase Order Items:
{po_items}

Goods Receipt Note Items:
{grn_items}

Invoice Items:
{invoice_items}

Mathematical Validation:
{quant_report}

Compliance Status:
{compliance_status}

SAMR Hallucination Check:
{samr_status}

Perform a comprehensive three-way match. For each matched set of items, determine:
1. Whether descriptions refer to the same product (accounting for abbreviations/naming variations)
2. Whether quantities match across all three documents
3. Whether prices match between PO and Invoice

Respond with valid JSON:
{{
  "overall_status": "full_match|partial_match|mismatch|exception",
  "confidence": 0.0-1.0,
  "line_item_matches": [
    {{
      "match_id": "uuid",
      "po_description": "...",
      "grn_description": "...",
      "invoice_description": "...",
      "match_status": "full_match|partial_match|mismatch|missing",
      "quantity_consistent": true,
      "price_consistent": true,
      "similarity_score": 0.95,
      "resolution_notes": "..."
    }}
  ],
  "discrepancy_summary": ["list of key discrepancies"],
  "recommendation": "approve|reject|investigate|partial_approve",
  "audit_narrative": "Professional narrative for audit workpaper"
}}"""


def _fuzzy_match_items(
    po_items: list[dict[str, Any]],
    target_items: list[dict[str, Any]],
    threshold: float = 60.0,
) -> list[tuple[dict[str, Any], dict[str, Any] | None, float]]:
    """
    Match PO items to target items using fuzzy string matching.
    Returns list of (po_item, matched_target_item, score).
    """
    matches = []
    used_indices: set[int] = set()

    for po_item in po_items:
        po_desc = po_item.get("description", "").lower().strip()
        best_score = 0.0
        best_match = None
        best_idx = -1

        for i, target_item in enumerate(target_items):
            if i in used_indices:
                continue
            target_desc = target_item.get("description", "").lower().strip()

            # Use token_set_ratio for better handling of reordered words
            score = fuzz.token_set_ratio(po_desc, target_desc)

            # Also check part numbers if available
            po_pn = po_item.get("part_number", "")
            target_pn = target_item.get("part_number", "")
            if po_pn and target_pn and po_pn.strip() == target_pn.strip():
                score = max(score, 100.0)  # Exact part number match trumps description

            if score > best_score:
                best_score = score
                best_match = target_item
                best_idx = i

        if best_score >= threshold and best_match is not None:
            used_indices.add(best_idx)
            matches.append((po_item, best_match, best_score / 100.0))
        else:
            matches.append((po_item, None, 0.0))

    return matches


class ReconciliationAgent:
    """
    Performs the three-way match reconciliation between PO, GRN, and Invoice.
    Uses fuzzy entity resolution for nomenclature variance and LLM synthesis.
    """

    def __init__(self, llm: ILLMClient) -> None:
        self.llm = llm

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        po_items = state.get("po_line_items", [])
        grn_items = state.get("grn_line_items", [])
        inv_items = state.get("invoice_line_items", [])

        # Pre-match using fuzzy entity resolution
        po_grn_matches = _fuzzy_match_items(po_items, grn_items)
        po_inv_matches = _fuzzy_match_items(po_items, inv_items)

        # Build a combined match picture
        pre_matches = []
        for i, (po_item, grn_item, grn_score) in enumerate(po_grn_matches):
            _, inv_item, inv_score = po_inv_matches[i] if i < len(po_inv_matches) else (po_item, None, 0.0)
            pre_matches.append({
                "po": po_item,
                "grn": grn_item,
                "invoice": inv_item,
                "grn_similarity": grn_score,
                "inv_similarity": inv_score,
            })

        quant_report = state.get("quantitative_report") or {}
        compliance = state.get("compliance_report") or {}
        samr = state.get("samr_metrics") or {}

        prompt = RECONCILIATION_PROMPT.format(
            po_items=json.dumps(po_items[:20], indent=2),
            grn_items=json.dumps(grn_items[:20], indent=2),
            invoice_items=json.dumps(inv_items[:20], indent=2),
            quant_report=json.dumps({
                "is_consistent": quant_report.get("is_mathematically_consistent"),
                "discrepancies": quant_report.get("total_discrepancies", 0),
            }),
            compliance_status=compliance.get("compliance_status", "unknown"),
            samr_status=f"Alert Triggered: {samr.get('alert_triggered', False)}, "
                        f"Score: {samr.get('cosine_similarity_score', 'N/A')}",
        )

        try:
            response = await self.llm.complete(prompt=prompt, temperature=0.1, json_mode=True, max_tokens=3000)
            verdict = json.loads(response)
        except Exception as e:
            logger.error("reconciliation_llm_failed", error=str(e))
            verdict = {
                "overall_status": "exception",
                "confidence": 0.0,
                "line_item_matches": [],
                "discrepancy_summary": [f"Reconciliation analysis failed: {e}"],
                "recommendation": "investigate",
                "audit_narrative": "Automated reconciliation encountered an error requiring manual review.",
            }

        # Ensure match IDs exist
        for match in verdict.get("line_item_matches", []):
            if not match.get("match_id"):
                match["match_id"] = str(uuid.uuid4())

        logger.info("reconciliation_complete",
                    status=verdict.get("overall_status"),
                    confidence=verdict.get("confidence"))

        return {
            "line_item_matches": verdict.get("line_item_matches", []),
            "reconciliation_verdict": verdict,
        }
