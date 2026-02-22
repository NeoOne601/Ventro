"""
Confidence Interval Service

Computes per-field, 3-level (90/95/99%) confidence intervals for every
extracted value in a reconciliation session.

Method: Gaussian error propagation
  σ_field = value × (1 - min_ocr_confidence) × correction_factor
  correction_factor = 1 + SAMR_divergence_weight

  CI bounds:
    90%  → μ ± 1.645σ
    95%  → μ ± 1.960σ
    99%  → μ ± 2.576σ

Grade:
  green  → 95% CI width < 1% of value
  amber  → 1% ≤ CI width < 5%
  red    → CI width ≥ 5%

Design notes:
  - Propagates both extraction uncertainty (OCR confidence) and model
    uncertainty (SAMR divergence penalty when alert was triggered)
  - Does NOT use bootstrap sampling (too slow in real-time API path);
    closed-form Gaussian approximation is sufficient for bounded monetary values
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# z-scores for 90 / 95 / 99% two-sided intervals
_Z = {90: 1.645, 95: 1.960, 99: 2.576}

# When SAMR alert fires, inflate σ by this factor (model is less trustworthy)
SAMR_ALERT_PENALTY = 0.20


@dataclass
class FieldCI:
    """Confidence interval for a single extracted field."""
    field_name: str
    value: float
    lower_90: float
    upper_90: float
    lower_95: float
    upper_95: float
    lower_99: float
    upper_99: float
    sigma: float
    grade: str        # 'green' | 'amber' | 'red'
    ocr_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "value": round(self.value, 4),
            "ci": {
                "90": [round(self.lower_90, 4), round(self.upper_90, 4)],
                "95": [round(self.lower_95, 4), round(self.upper_95, 4)],
                "99": [round(self.lower_99, 4), round(self.upper_99, 4)],
            },
            "sigma": round(self.sigma, 6),
            "grade": self.grade,
            "ocr_confidence": round(self.ocr_confidence, 4),
        }


def _grade(value: float, sigma_95: float) -> str:
    if value == 0:
        return "green"
    width_pct = (2 * sigma_95) / abs(value) * 100
    if width_pct < 1.0:
        return "green"
    elif width_pct < 5.0:
        return "amber"
    return "red"


def _compute_ci(value: float, ocr_confidence: float, samr_penalty: float, field: str) -> FieldCI:
    """Propagate uncertainty into a FieldCI object."""
    # Base σ: fraction of value that could be wrong given OCR confidence
    base_sigma = abs(value) * max(0.001, 1.0 - ocr_confidence)
    # Inflate if SAMR indicated model uncertainty
    sigma = base_sigma * (1.0 + samr_penalty)

    bounds = {level: z * sigma for level, z in _Z.items()}
    return FieldCI(
        field_name=field,
        value=value,
        lower_90=value - bounds[90], upper_90=value + bounds[90],
        lower_95=value - bounds[95], upper_95=value + bounds[95],
        lower_99=value - bounds[99], upper_99=value + bounds[99],
        sigma=sigma,
        grade=_grade(value, bounds[95]),
        ocr_confidence=ocr_confidence,
    )


class ConfidenceIntervalService:
    """
    Computes confidence intervals for all monetary and quantity fields
    in a completed reconciliation session.
    """

    def compute_for_session(
        self,
        session_state: dict[str, Any],
        samr_alert_triggered: bool = False,
        samr_cosine_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Main entry point. Returns a list of FieldCI.to_dict() for all fields.

        session_state: the Celery task state dict (keys: po_parsed, grn_parsed, etc.)
        """
        samr_penalty = SAMR_ALERT_PENALTY if samr_alert_triggered else 0.0
        results: list[dict] = []

        for doc_type in ("po", "grn", "invoice"):
            parsed = session_state.get(f"{doc_type}_parsed") or {}
            line_items = session_state.get(f"{doc_type}_line_items", [])

            # Document-level totals
            totals = parsed.get("totals", {})
            total_val = float(totals.get("total") or 0.0)
            doc_conf = float(parsed.get("classification_confidence") or 0.8)

            if total_val:
                ci = _compute_ci(total_val, doc_conf, samr_penalty, f"{doc_type}.total")
                ci_dict = ci.to_dict()
                ci_dict["doc_type"] = doc_type
                ci_dict["item_index"] = None
                results.append(ci_dict)

            # Per-line-item fields
            for idx, item in enumerate(line_items):
                item_conf = float(item.get("confidence") or 0.8)
                effective_conf = min(item_conf, doc_conf)

                for field_name, raw_val in [
                    ("unit_price", item.get("unit_price")),
                    ("total_amount", item.get("total_amount")),
                    ("quantity", item.get("quantity")),
                ]:
                    val = float(raw_val or 0.0)
                    if val == 0.0:
                        continue
                    ci = _compute_ci(val, effective_conf, samr_penalty,
                                     f"{doc_type}.items[{idx}].{field_name}")
                    ci_dict = ci.to_dict()
                    ci_dict["doc_type"] = doc_type
                    ci_dict["item_index"] = idx
                    ci_dict["item_description"] = item.get("description", "")
                    results.append(ci_dict)

        return results

    def summary_grade(self, confidence_bands: list[dict]) -> str:
        """Overall session CI grade: worst grade across all fields."""
        if not confidence_bands:
            return "green"
        grades = {"red": 3, "amber": 2, "green": 1}
        worst = max(grades.get(b.get("grade", "green"), 1) for b in confidence_bands)
        return {3: "red", 2: "amber", 1: "green"}[worst]
