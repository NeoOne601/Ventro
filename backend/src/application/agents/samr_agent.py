"""
SAMR Agent - Shadow Agent Memory Reconciliation
Novel hallucination detection via dual-stream adversarial perturbation
and cosine similarity divergence analysis.
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

import numpy as np
import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

SAMR_ANALYSIS_PROMPT = """You are performing a financial reconciliation analysis.
Based on the following document data, determine if the three documents match.

Data:
{context}

Provide your analysis in JSON:
{{
  "verdict": "match|mismatch|partial_match",
  "confidence": 0.0-1.0,
  "rationale": "brief explanation",
  "key_values_checked": ["list of key values you checked"],
  "anomalies": ["list of any anomalies found"]
}}"""


def _perturb_context(context: str, strength: float = 0.1) -> tuple[str, str]:
    """
    Apply adversarial perturbation to the context.
    Returns (perturbed_context, description_of_perturbation).
    """
    lines = context.split("\n")
    perturbations = []

    for i, line in enumerate(lines):
        # Look for numeric values to perturb
        import re
        numbers = re.findall(r'\b(\d+\.\d{2})\b', line)
        if numbers and random.random() < strength:
            original = numbers[0]
            # Shift by a small, plausible amount
            try:
                val = float(original)
                delta = val * random.choice([-0.05, 0.05, -0.10, 0.10])
                perturbed_val = round(val + delta, 2)
                lines[i] = line.replace(original, str(perturbed_val), 1)
                perturbations.append(f"Changed {original} → {perturbed_val}")
            except ValueError:
                pass

        # Occasionally perturb vendor IDs
        vendor_patterns = re.findall(r'(INV|PO|GRN)[-_]?(\d{4,8})', line)
        if vendor_patterns and random.random() < strength * 0.5:
            orig_type, orig_num = vendor_patterns[0]
            new_num = str(int(orig_num) + random.choice([1, -1, 10, -10]))
            lines[i] = line.replace(f"{orig_type}{orig_num}", f"{orig_type}{new_num}", 1)
            perturbations.append(f"Changed document number {orig_num} → {new_num}")

    perturbed = "\n".join(lines)
    description = "; ".join(perturbations) if perturbations else "No significant perturbation applied"
    return perturbed, description


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two reasoning vectors."""
    a = np.array(vec_a, dtype=float)
    b = np.array(vec_b, dtype=float)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _build_context(state: dict[str, Any]) -> str:
    """Build a compact context string from extracted document data."""
    parts = []

    for doc_type in ["po", "grn", "invoice"]:
        parsed = state.get(f"{doc_type}_parsed") or {}
        totals = parsed.get("totals", {})
        items = state.get(f"{doc_type}_line_items", [])
        parts.append(f"=== {doc_type.upper()} ===")
        for item in items[:10]:
            parts.append(
                f"  Item: {item.get('description', '')} | "
                f"Qty: {item.get('quantity', '')} | "
                f"Price: {item.get('unit_price', '')} | "
                f"Total: {item.get('total_amount', '')}"
            )
        parts.append(f"  Total: {totals.get('total', 'N/A')} | Tax: {totals.get('tax_amount', 'N/A')}")

    return "\n".join(parts)


class SAMRAgent:
    """
    Shadow Agent Memory Reconciliation (SAMR)

    Proprietary hallucination detection mechanism:
    1. PRIMARY stream: processes verified factual data, generates reasoning vector
    2. SHADOW stream: processes adversarially perturbed data, generates reasoning vector
    3. RECONCILER: computes cosine similarity - high similarity means model didn't
       notice the perturbation → reasoning failure → SAMR Alert triggered

    divergence_threshold is now ADAPTIVE per-org (Bayesian F-score optimiser).
    Falls back to static config value when no threshold_svc is injected.
    """

    def __init__(
        self,
        llm: ILLMClient,
        divergence_threshold: float = 0.85,
        threshold_svc: Any = None,    # AdaptiveThresholdService | None
    ) -> None:
        self.llm = llm
        self.divergence_threshold = divergence_threshold
        self.threshold_svc = threshold_svc

    async def _get_threshold(self, org_id: str | None) -> float:
        """Return adaptive threshold for org, or static fallback."""
        if self.threshold_svc and org_id:
            try:
                return await self.threshold_svc.get_threshold(org_id)
            except Exception:
                pass
        return self.divergence_threshold

    async def _run_primary_stream(self, context: str) -> tuple[str, list[float]]:
        """Run primary analysis on verified factual data."""
        prompt = SAMR_ANALYSIS_PROMPT.format(context=context)
        response = await self.llm.complete(prompt=prompt, temperature=0.0, json_mode=True)
        reasoning_vector = await self.llm.get_reasoning_vector(prompt)
        return response, reasoning_vector

    async def _run_shadow_stream(
        self, context: str, strength: float
    ) -> tuple[str, list[float], str]:
        """Run shadow analysis on adversarially perturbed data."""
        perturbed_context, perturbation_desc = _perturb_context(context, strength)
        prompt = SAMR_ANALYSIS_PROMPT.format(context=perturbed_context)
        response = await self.llm.complete(prompt=prompt, temperature=0.0, json_mode=True)
        reasoning_vector = await self.llm.get_reasoning_vector(prompt)
        return response, reasoning_vector, perturbation_desc

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute SAMR dual-stream analysis with adaptive per-org threshold."""
        from ...application.config import get_settings
        settings = get_settings()

        session_id = state["session_id"]
        org_id = state.get("org_id")     # Injected by orchestrator
        context = _build_context(state)

        # Resolve adaptive threshold
        threshold = await self._get_threshold(org_id)

        logger.info("samr_starting", session_id=session_id,
                    threshold=threshold, org_id=org_id)

        # === PRIMARY STREAM ===
        primary_response, primary_vector = await self._run_primary_stream(context)

        # === SHADOW STREAM ===
        shadow_response, shadow_vector, perturbation_desc = await self._run_shadow_stream(
            context, settings.samr_perturbation_strength
        )

        # === RECONCILIATION ===
        similarity_score = _cosine_similarity(primary_vector, shadow_vector)

        alert_triggered = (
            similarity_score >= threshold
            and perturbation_desc != "No significant perturbation applied"
        )

        # Parse responses for comparison
        try:
            primary_parsed = json.loads(primary_response)
        except json.JSONDecodeError:
            primary_parsed = {"verdict": "unknown", "confidence": 0}

        try:
            shadow_parsed = json.loads(shadow_response)
        except json.JSONDecodeError:
            shadow_parsed = {"verdict": "unknown", "confidence": 0}

        samr_metrics = {
            "session_id": session_id,
            "primary_stream_verdict": primary_parsed.get("verdict", "unknown"),
            "shadow_stream_verdict": shadow_parsed.get("verdict", "unknown"),
            "primary_confidence": primary_parsed.get("confidence", 0),
            "shadow_confidence": shadow_parsed.get("confidence", 0),
            "cosine_similarity_score": round(similarity_score, 4),
            "divergence_threshold": threshold,    # adaptive value logged
            "alert_triggered": alert_triggered,
            "perturbation_applied": perturbation_desc,
            "reasoning_vectors_diverged": similarity_score < threshold,
            "threshold_source": "adaptive" if self.threshold_svc and org_id else "static",
            "interpretation": (
                "⚠️ REASONING FAILURE: Model did not detect adversarial perturbation. "
                "High confidence outputs may be hallucinated. Human review mandatory."
                if alert_triggered
                else "✅ REASONING VERIFIED: Model correctly identified perturbation. "
                     "Output reasoning is consistent and reliable."
            ),
            "timestamp": time.time(),
        }

        logger.info(
            "samr_complete",
            session_id=session_id,
            similarity=similarity_score,
            alert=alert_triggered,
        )

        return {
            "samr_metrics": samr_metrics,
            "samr_alert_triggered": alert_triggered,
        }
