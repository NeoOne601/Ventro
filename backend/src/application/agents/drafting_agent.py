"""
Drafting Agent - Automated Audit Workpaper Generation
Synthesizes findings into professional, citation-linked audit documentation.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

WORKPAPER_NARRATIVE_PROMPT = """You are a Senior Audit Partner drafting a formal audit workpaper.

Reconciliation Data:
Verdict: {verdict_status}
Confidence: {confidence}
Math Discrepancies: {discrepancies}
Compliance Status: {compliance_status}
Risk Score: {risk_score}
SAMR Alert: {samr_alert}
Key Discrepancy Summary:
{discrepancy_summary}

Audit Narrative from Reconciliation Agent:
{audit_narrative}

Write a professionally formatted audit workpaper narrative. Include:
1. Objective and Scope (1-2 sentences)
2. Substantive Testing Procedure (what was checked)
3. Findings and Analysis (specific findings with professional language)
4. Materiality Assessment
5. Conclusion and Recommendation

Use auditor-style language. Reference document types (Purchase Order, Goods Receipt Note, Invoice).
Be precise about quantities and amounts where known.
Keep total length under 600 words."""


def _build_workpaper_html(
    session_id: str,
    verdict: dict[str, Any],
    quant_report: dict[str, Any],
    compliance: dict[str, Any],
    samr: dict[str, Any],
    narrative: str,
    citations: list[dict[str, Any]],
) -> str:
    """Build interactive HTML workpaper with embedded citation links."""
    status = verdict.get("overall_status", "unknown")
    status_class = {
        "full_match": "status-match",
        "partial_match": "status-partial",
        "mismatch": "status-mismatch",
        "exception": "status-exception",
    }.get(status, "status-unknown")

    status_icon = {
        "full_match": "✅",
        "partial_match": "⚠️",
        "mismatch": "❌",
        "exception": "🚨",
    }.get(status, "❓")

    # Build citation map for inline references
    citation_html = ""
    for cit in citations[:20]:
        cit_id = cit.get("id", str(uuid.uuid4()))
        bbox = cit.get("bbox") or {}
        citation_html += f"""
        <span class="citation-link" 
              data-doc-id="{cit.get('document_id', '')}"
              data-page="{cit.get('page', 0)}"
              data-x0="{bbox.get('x0', 0)}"
              data-y0="{bbox.get('y0', 0)}"  
              data-x1="{bbox.get('x1', 0)}"
              data-y1="{bbox.get('y1', 0)}"
              data-citation-id="{cit_id}"
              onclick="window.openCitation(this)"
              title="Click to view source document">
            {cit.get('text', '')}: <strong>{cit.get('value', '')}</strong> 📎
        </span>"""

    line_items_html = ""
    for match in verdict.get("line_item_matches", []):
        match_status = match.get("match_status", "unknown")
        match_icon = "✅" if match_status == "full_match" else "⚠️" if match_status == "partial_match" else "❌"
        line_items_html += f"""
        <tr class="match-row match-{match_status}">
            <td>{match_icon} {match.get('po_description', 'N/A')}</td>
            <td>{match.get('grn_description', 'N/A')}</td>
            <td>{match.get('invoice_description', 'N/A')}</td>
            <td><span class="badge badge-{match_status}">{match_status.replace('_', ' ').title()}</span></td>
            <td>{match.get('similarity_score', 0):.0%}</td>
        </tr>"""

    compliance_flags_html = ""
    for flag in compliance.get("flags", []):
        flag_status = flag.get("status", "unknown")
        flag_icon = "✅" if flag_status == "pass" else "⚠️" if flag_status == "warning" else "❌"
        compliance_flags_html += f"""
        <div class="compliance-flag flag-{flag_status}">
            {flag_icon} <strong>{flag.get('rule', '')}</strong>: {flag.get('detail', '')}
        </div>"""

    samr_class = "samr-alert" if samr.get("alert_triggered") else "samr-clear"
    samr_icon = "🚨" if samr.get("alert_triggered") else "✅"

    narrative_paragraphs = "".join(
        f"<p>{para}</p>" for para in narrative.strip().split("\n\n") if para.strip()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Audit Workpaper - Session {session_id[:8]}</title>
<style>
  body {{ font-family: 'Inter', system-ui, sans-serif; background: #0a0a1a; color: #e2e8f0; padding: 2rem; }}
  .workpaper {{ max-width: 1000px; margin: 0 auto; background: rgba(255,255,255,0.05); border-radius: 1rem; 
                border: 1px solid rgba(255,255,255,0.1); padding: 2rem; backdrop-filter: blur(10px); }}
  .header {{ border-bottom: 2px solid rgba(99,102,241,0.5); padding-bottom: 1.5rem; margin-bottom: 2rem; }}
  .header h1 {{ font-size: 1.5rem; color: #a5b4fc; }}
  .status-badge {{ display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1.2rem;
                   border-radius: 2rem; font-weight: 600; font-size: 0.9rem; }}
  .status-match {{ background: rgba(34,197,94,0.2); color: #86efac; border: 1px solid rgba(34,197,94,0.4); }}
  .status-partial {{ background: rgba(234,179,8,0.2); color: #fde047; border: 1px solid rgba(234,179,8,0.4); }}
  .status-mismatch {{ background: rgba(239,68,68,0.2); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); }}
  .status-exception {{ background: rgba(168,85,247,0.2); color: #d8b4fe; border: 1px solid rgba(168,85,247,0.4); }}
  .section {{ margin-bottom: 2rem; }}
  .section h2 {{ font-size: 1.1rem; color: #a5b4fc; margin-bottom: 1rem; padding-bottom: 0.5rem;
                 border-bottom: 1px solid rgba(99,102,241,0.3); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ background: rgba(99,102,241,0.2); color: #a5b4fc; padding: 0.75rem; text-align: left; }}
  td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); }}
  .match-full_match {{ background: rgba(34,197,94,0.05); }}
  .match-partial_match {{ background: rgba(234,179,8,0.05); }}
  .match-mismatch {{ background: rgba(239,68,68,0.05); }}
  .badge {{ padding: 0.2rem 0.6rem; border-radius: 1rem; font-size: 0.75rem; font-weight: 600; }}
  .badge-full_match {{ background: rgba(34,197,94,0.2); color: #86efac; }}
  .badge-partial_match {{ background: rgba(234,179,8,0.2); color: #fde047; }}
  .badge-mismatch {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
  .citation-link {{ cursor: pointer; color: #67e8f9; text-decoration: underline;
                    border-radius: 4px; padding: 1px 4px; transition: background 0.2s; display: inline-block; }}
  .citation-link:hover {{ background: rgba(103,232,249,0.15); }}
  .compliance-flag {{ padding: 0.6rem 1rem; margin-bottom: 0.5rem; border-radius: 0.5rem;
                      background: rgba(255,255,255,0.03); border-left: 3px solid rgba(99,102,241,0.5); }}
  .flag-fail {{ border-left-color: #ef4444; }}
  .flag-warning {{ border-left-color: #eab308; }}
  .flag-pass {{ border-left-color: #22c55e; }}
  .samr-alert {{ background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.4); 
                 padding: 1rem; border-radius: 0.75rem; }}
  .samr-clear {{ background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.4);
                 padding: 1rem; border-radius: 0.75rem; }}
  .narrative {{ line-height: 1.8; color: #cbd5e1; }}
  .narrative p {{ margin-bottom: 1rem; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }}
  .metric-card {{ background: rgba(255,255,255,0.03); border-radius: 0.75rem; padding: 1rem; 
                  border: 1px solid rgba(255,255,255,0.07); text-align: center; }}
  .metric-value {{ font-size: 1.8rem; font-weight: 700; color: #a5b4fc; }}
  .metric-label {{ font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }}
  .footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);
             font-size: 0.75rem; color: #64748b; }}
</style>
</head>
<body>
<div class="workpaper">
  <div class="header">
    <h1>📋 Three-Way Match Audit Workpaper</h1>
    <p style="color:#64748b; font-size:0.85rem;">Session: {session_id} | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    <div style="margin-top:1rem;">
      <span class="status-badge {status_class}">{status_icon} {status.replace('_', ' ').title()}</span>
      <span style="margin-left:1rem; color:#94a3b8; font-size:0.85rem;">
        Confidence: {verdict.get('confidence', 0):.0%} | 
        Recommendation: <strong style="color:#a5b4fc;">{verdict.get('recommendation', 'N/A').replace('_', ' ').title()}</strong>
      </span>
    </div>
  </div>

  <div class="section">
    <h2>📊 Summary Metrics</h2>
    <div class="metric-grid">
      <div class="metric-card">
        <div class="metric-value">{quant_report.get('total_discrepancies', 0)}</div>
        <div class="metric-label">Mathematical Discrepancies</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{len(verdict.get('line_item_matches', []))}</div>
        <div class="metric-label">Line Items Reconciled</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{compliance.get('risk_score', 0):.1f}/10</div>
        <div class="metric-label">Compliance Risk Score</div>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>🔍 Substantive Testing Narrative</h2>
    <div class="narrative">{narrative_paragraphs}</div>
  </div>

  <div class="section">
    <h2>📑 Line Item Reconciliation Detail</h2>
    <table>
      <thead><tr>
        <th>Purchase Order</th><th>GRN</th><th>Invoice</th><th>Status</th><th>Similarity</th>
      </tr></thead>
      <tbody>{line_items_html}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>✅ Compliance Evaluation</h2>
    {compliance_flags_html if compliance_flags_html else '<p style="color:#64748b;">No compliance flags generated.</p>'}
    {"<div style='margin-top:0.75rem; padding:0.75rem; background:rgba(239,68,68,0.1); border-radius:0.5rem;'><strong>Policy Violations:</strong> " + "; ".join(compliance.get('policy_violations', [])) + "</div>" if compliance.get('policy_violations') else ""}
  </div>

  <div class="section">
    <h2>🛡️ SAMR Hallucination Detection Report</h2>
    <div class="{samr_class}">
      <div style="font-size:1.1rem; margin-bottom:0.5rem;">{samr_icon} {samr.get('interpretation', 'SAMR check not performed.')}</div>
      <div style="font-size:0.8rem; color:#94a3b8;">
        Cosine Similarity Score: <strong>{samr.get('cosine_similarity_score', 'N/A')}</strong> | 
        Threshold: {samr.get('divergence_threshold', 0.85)} | 
        Perturbation: {samr.get('perturbation_applied', 'N/A')}
      </div>
    </div>
  </div>

  <div class="section">
    <h2>🔗 Interactive Evidence Map</h2>
    <p style="color:#64748b; font-size:0.85rem; margin-bottom:1rem;">
      Click any citation below to jump to the exact location in the source document.
    </p>
    <div style="display:flex; flex-wrap:wrap; gap:0.75rem;">
      {citation_html if citation_html else '<p style="color:#64748b;">No spatial citations captured.</p>'}
    </div>
  </div>

  <div class="footer">
    <p>Generated by MAS-VGFR v1.0.0 | Multi-Agent System for Visually-Grounded Financial Reconciliation</p>
    <p>⚠️ This workpaper was generated autonomously. Review agent conclusions before final sign-off.</p>
  </div>
</div>
<script>
window.openCitation = function(el) {{
  const docId = el.dataset.docId;
  const page = parseInt(el.dataset.page);
  const bbox = {{ x0: parseFloat(el.dataset.x0), y0: parseFloat(el.dataset.y0),
                   x1: parseFloat(el.dataset.x1), y1: parseFloat(el.dataset.y1) }};
  window.parent.postMessage({{ type: 'CITATION_CLICK', docId, page, bbox }}, '*');
}};
</script>
</body>
</html>"""


class DraftingAgent:
    """
    Generates the final audit workpaper with interactive visual citations.
    Synthesizes all agent outputs into a professional, review-ready document.
    """

    def __init__(self, llm: ILLMClient) -> None:
        self.llm = llm

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        verdict = state.get("reconciliation_verdict") or {}
        quant_report = state.get("quantitative_report") or {}
        compliance = state.get("compliance_report") or {}
        samr = state.get("samr_metrics") or {}
        citations = state.get("extracted_citations") or []

        # Generate professional narrative
        prompt = WORKPAPER_NARRATIVE_PROMPT.format(
            verdict_status=verdict.get("overall_status", "unknown"),
            confidence=f"{verdict.get('confidence', 0):.0%}",
            discrepancies=quant_report.get("total_discrepancies", 0),
            compliance_status=compliance.get("compliance_status", "unknown"),
            risk_score=compliance.get("risk_score", 0),
            samr_alert="YES - Requires Immediate Review" if samr.get("alert_triggered") else "CLEAR",
            discrepancy_summary=json.dumps(verdict.get("discrepancy_summary", []), indent=2),
            audit_narrative=verdict.get("audit_narrative", "No narrative generated."),
        )

        try:
            narrative = await self.llm.complete(prompt=prompt, temperature=0.2, max_tokens=2000)
        except Exception as e:
            logger.error("drafting_narrative_failed", error=str(e))
            narrative = verdict.get("audit_narrative", "Automated narrative generation failed. Manual review required.")

        # Build the interactive HTML workpaper
        html_content = _build_workpaper_html(
            session_id=state["session_id"],
            verdict=verdict,
            quant_report=quant_report,
            compliance=compliance,
            samr=samr,
            narrative=narrative,
            citations=citations,
        )

        workpaper = {
            "id": str(uuid.uuid4()),
            "session_id": state["session_id"],
            "title": f"Three-Way Match Audit Workpaper — {datetime.utcnow().strftime('%Y-%m-%d')}",
            "generated_at": datetime.utcnow().isoformat(),
            "verdict_summary": verdict.get("overall_status", "unknown"),
            "narrative": narrative,
            "html_content": html_content,
            "citations": citations,
            "sections": [
                {"title": "Summary", "content": f"Overall status: {verdict.get('overall_status', 'unknown')}"},
                {"title": "Substantive Testing", "content": narrative},
                {"title": "Compliance", "content": json.dumps(compliance, indent=2)},
                {"title": "SAMR", "content": json.dumps(samr, indent=2)},
            ],
        }

        logger.info("workpaper_generated", session_id=state["session_id"],
                    has_citations=len(citations) > 0)

        return {"workpaper": workpaper}
