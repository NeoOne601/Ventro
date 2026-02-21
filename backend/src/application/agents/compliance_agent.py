"""
Compliance Agent - Regulatory and Policy Evaluation
Uses prompts encoding business rules, policy templates, and risk scoring.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

COMPLIANCE_PROMPT = """You are a senior financial compliance auditor evaluating a transaction.

Transaction Data:
{context}

Mathematical Discrepancies Found: {discrepancies}

Evaluate the following compliance criteria:
1. DUPLICATE INVOICE CHECK: Is the invoice number unique / not previously processed?
2. VENDOR VERIFICATION: Does the vendor name on the Invoice match the PO?
3. AUTHORIZATION: Is the PO amount within standard procurement authorization limits?
4. PAYMENT TERMS: Do payment terms comply with corporate policy (max Net-90)?
5. TAX COMPLIANCE: Is the tax rate applied correctly for the jurisdiction?
6. BENFORD'S LAW: Do the leading digits of amounts follow expected distributions?
7. ROUND NUMBER ANOMALY: Are there suspiciously round numbers that may indicate fraud?
8. SPLIT TRANSACTION: Does this appear to be a transaction split to avoid approval thresholds?

Respond with valid JSON:
{{
  "compliance_status": "compliant|non_compliant|requires_review",
  "risk_score": 0.0-10.0,
  "flags": [
    {{"rule": "rule_name", "status": "pass|fail|warning", "detail": "explanation"}}
  ],
  "policy_violations": ["list of specific violations"],
  "fraud_indicators": ["list of potential fraud patterns detected"],
  "recommended_action": "approve|reject|escalate|flag_for_review",
  "notes": "overall assessment"
}}"""


class ComplianceAgent:
    """
    Evaluates reconciled transactions against corporate procurement policies,
    regulatory requirements, and historical audit patterns.
    """

    def __init__(self, llm: ILLMClient) -> None:
        self.llm = llm

    def _build_context(self, state: dict[str, Any]) -> str:
        po_parsed = state.get("po_parsed") or {}
        inv_parsed = state.get("invoice_parsed") or {}
        po_meta = po_parsed.get("metadata", {})
        inv_meta = inv_parsed.get("metadata", {})
        po_totals = po_parsed.get("totals", {})
        inv_totals = inv_parsed.get("totals", {})

        return json.dumps({
            "po_number": po_meta.get("document_number", "N/A"),
            "po_date": po_meta.get("document_date", "N/A"),
            "po_total": po_totals.get("total", 0),
            "invoice_number": inv_meta.get("document_number", "N/A"),
            "invoice_date": inv_meta.get("document_date", "N/A"),
            "invoice_total": inv_totals.get("total", 0),
            "vendor_on_po": po_meta.get("vendor_name", "N/A"),
            "vendor_on_invoice": inv_meta.get("vendor_name", "N/A"),
            "payment_terms": inv_meta.get("payment_terms", "N/A"),
            "tax_rate": inv_totals.get("tax_rate", 0),
            "line_item_count": len(state.get("po_line_items", [])),
        }, indent=2)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        context = self._build_context(state)
        discrepancies = state.get("math_discrepancies", [])
        disc_summary = json.dumps([d["type"] for d in discrepancies]) if discrepancies else "None"

        prompt = COMPLIANCE_PROMPT.format(context=context, discrepancies=disc_summary)

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.1,
                json_mode=True,
                max_tokens=2048,
            )
            report = json.loads(response)
        except Exception as e:
            logger.error("compliance_llm_failed", error=str(e))
            report = {
                "compliance_status": "requires_review",
                "risk_score": 5.0,
                "flags": [],
                "policy_violations": [f"Compliance evaluation failed: {e}"],
                "fraud_indicators": [],
                "recommended_action": "escalate",
                "notes": "Automated compliance check encountered an error.",
            }

        logger.info("compliance_check_complete",
                    status=report.get("compliance_status"),
                    risk_score=report.get("risk_score"))

        return {"compliance_report": report}
