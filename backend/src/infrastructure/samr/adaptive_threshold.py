"""
Adaptive SAMR Threshold Service

Replaces the static config threshold with a per-org, self-improving value.

Algorithm (Bayesian F-score optimiser):
  1. Collect last 30 sessions of feedback for the org (cosine_score + label)
  2. Walk candidate thresholds [0.70 … 0.99] step 0.01
  3. For each candidate: simulate TP, FP, FN counts
  4. Maximise F-beta (beta=0.5 → precision-weighted: false alarms hurt 4× more)
  5. Apply Bayesian shrinkage toward global prior (alpha=0.3):
       threshold = alpha * computed + (1 - alpha) * prior
  6. Cache in Redis for 1 hour; apply to next session

Why precision-weighted?
  AP teams trust the system more when alerts are less frequent but highly accurate.
  A false alarm on a matched invoice costs auditor time and erodes confidence faster
  than a missed mismatch that the analyst would catch on review.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ALPHA = 0.30          # Shrinkage toward global prior
BETA = 0.5            # F-beta weight (< 1 = precision-weighted)
WINDOW_SIZE = 30      # Sessions used for optimisation
MIN_SAMPLES = 5       # Need at least this many before adapting
CANDIDATE_STEP = 0.01
REDIS_TTL = 3600      # 1 hour


def _f_beta(tp: int, fp: int, fn: int, beta: float) -> float:
    """F-beta score. Returns 0 if denominator is zero."""
    denom = (1 + beta ** 2) * tp + beta ** 2 * fn + fp
    return ((1 + beta ** 2) * tp / denom) if denom > 0 else 0.0


def _optimise_threshold(
    feedback_rows: list[dict[str, Any]],
    prior: float,
) -> float:
    """
    Find the threshold that maximises F-beta on historical feedback.
    Falls back to prior if not enough data.
    """
    n = len(feedback_rows)
    if n < MIN_SAMPLES:
        return prior

    best_threshold = prior
    best_score = -1.0

    candidates = [round(0.70 + i * CANDIDATE_STEP, 2) for i in range(30)]
    for t in candidates:
        tp = fp = fn = 0
        for row in feedback_rows:
            predicted_alert = row["cosine_score"] >= t
            true_alert = row["feedback"] == "correct" and row["samr_triggered"]
            if predicted_alert and true_alert:
                tp += 1
            elif predicted_alert and not true_alert:
                fp += 1
            elif not predicted_alert and row["feedback"] == "false_negative":
                fn += 1

        score = _f_beta(tp, fp, fn, BETA)
        if score > best_score:
            best_score = score
            best_threshold = t

    # Bayesian shrinkage toward prior
    adapted = ALPHA * best_threshold + (1 - ALPHA) * prior
    return round(adapted, 4)


class AdaptiveThresholdService:
    """
    Computes and caches a per-org SAMR divergence threshold.
    Injected into SAMRAgent at runtime.
    """

    def __init__(self, pool: Any, redis_url: str, global_prior: float = 0.85) -> None:
        self._pool = pool
        self._redis_url = redis_url
        self._prior = global_prior
        self._redis: Any = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _cache_key(self, org_id: str) -> str:
        return f"ventro:samr:threshold:{org_id}"

    async def get_threshold(self, org_id: str) -> float:
        """Return per-org threshold, computing from feedback if cache is stale."""
        try:
            r = await self._get_redis()
            cached = await r.get(self._cache_key(org_id))
            if cached is not None:
                return float(cached)
        except Exception:
            pass  # Redis unavailable — fall through to DB

        threshold = await self._recompute(org_id)
        try:
            r = await self._get_redis()
            await r.setex(self._cache_key(org_id), REDIS_TTL, str(threshold))
        except Exception:
            pass
        return threshold

    async def _recompute(self, org_id: str) -> float:
        """Query DB, compute optimal threshold, return result."""
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT cosine_score, feedback, samr_triggered
                    FROM samr_feedback
                    WHERE org_id = $1
                    ORDER BY submitted_at DESC
                    LIMIT $2
                    """,
                    org_id, WINDOW_SIZE,
                )
            data = [dict(r) for r in rows]
            threshold = _optimise_threshold(data, self._prior)
            logger.info(
                "samr_threshold_recomputed",
                org_id=org_id, threshold=threshold,
                samples=len(data),
            )
            return threshold
        except Exception as e:
            logger.warning("samr_threshold_recompute_failed", error=str(e))
            return self._prior

    async def record_feedback(
        self,
        session_id: str,
        org_id: str,
        samr_triggered: bool,
        cosine_score: float,
        threshold_used: float,
        feedback: str,           # 'correct' | 'false_positive' | 'false_negative'
        submitted_by: str | None = None,
    ) -> None:
        """Persist analyst feedback and invalidate the org's threshold cache."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO samr_feedback
                  (session_id, org_id, samr_triggered, cosine_score,
                   threshold_used, feedback, submitted_by)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7::uuid)
                """,
                session_id, org_id, samr_triggered, cosine_score,
                threshold_used, feedback, submitted_by,
            )
        # Invalidate cache so next session uses updated threshold
        try:
            r = await self._get_redis()
            await r.delete(self._cache_key(org_id))
        except Exception:
            pass

        logger.info(
            "samr_feedback_recorded",
            session_id=session_id, org_id=org_id, feedback=feedback,
        )

    async def get_analytics(self, org_id: str) -> dict:
        """Return threshold trend and TP/FP/FN counts for analytics panel."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT feedback, COUNT(*) as count,
                       AVG(cosine_score) as avg_score,
                       AVG(threshold_used) as avg_threshold
                FROM samr_feedback
                WHERE org_id = $1 AND submitted_at > NOW() - INTERVAL '90 days'
                GROUP BY feedback
                """,
                org_id,
            )
            daily = await conn.fetch(
                """
                SELECT DATE(submitted_at) as day,
                       COUNT(*) FILTER (WHERE feedback = 'correct') as correct,
                       COUNT(*) FILTER (WHERE feedback = 'false_positive') as false_pos,
                       COUNT(*) FILTER (WHERE feedback = 'false_negative') as false_neg
                FROM samr_feedback
                WHERE org_id = $1 AND submitted_at > NOW() - INTERVAL '30 days'
                GROUP BY day ORDER BY day
                """,
                org_id,
            )
        current_threshold = await self.get_threshold(org_id)
        return {
            "current_threshold": current_threshold,
            "global_prior": self._prior,
            "summary": [dict(r) for r in rows],
            "daily_trend": [dict(r) for r in daily],
        }
