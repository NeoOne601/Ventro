"""
SAMR Analytics & Feedback Router

Endpoints:
  POST /samr/feedback          — analyst marks verdict correct/false_positive/false_negative
  GET  /samr/threshold         — view current adaptive threshold for caller's org
  GET  /samr/analytics         — 30-day TP/FP/FN trend + F-score trajectory
"""
from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..middleware.auth_middleware import CurrentUser
from ...application.config import get_settings
import asyncpg

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/samr", tags=["SAMR"])

settings = get_settings()


# ── Lazy singleton ─────────────────────────────────────────────────────────
_threshold_svc = None  # type: ignore[assignment]


async def _get_svc() -> "AdaptiveThresholdService":  # noqa: F821
    global _threshold_svc
    if _threshold_svc is None:
        from ...infrastructure.samr.adaptive_threshold import AdaptiveThresholdService
        import asyncpg
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        pool = await asyncpg.create_pool(dsn)
        _threshold_svc = AdaptiveThresholdService(
            pool=pool,
            redis_url=settings.redis_url,
            global_prior=settings.samr_divergence_threshold,
        )
    return _threshold_svc


# ── Schemas ────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    feedback: Literal["correct", "false_positive", "false_negative"]
    # These are filled server-side from session record, but client can hint:
    samr_triggered: bool | None = None
    cosine_score: float | None = None
    threshold_used: float | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def submit_samr_feedback(
    body: FeedbackRequest,
    current_user: CurrentUser,
) -> None:
    """
    Record analyst feedback on a SAMR verdict.
    - 'correct'        → alert was real, threshold was right
    - 'false_positive' → alert fired but no real issue (too sensitive)
    - 'false_negative' → no alert but there was a real issue (not sensitive enough)

    Invalidates the org's Redis-cached threshold so the next session recomputes.
    """
    try:
        import asyncpg
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        row = await conn.fetchrow(
            """
            SELECT samr_cosine_score, samr_threshold_used, samr_alert_triggered
            FROM reconciliation_sessions WHERE id = $1::uuid AND organisation_id = $2::uuid
            """,
            body.session_id, str(current_user.organisation_id),
        )
        await conn.close()
    except Exception:
        row = None

    cosine = (row["samr_cosine_score"] if row else None) or body.cosine_score or 0.85
    threshold = (row["samr_threshold_used"] if row else None) or body.threshold_used or settings.samr_divergence_threshold
    triggered = (row["samr_alert_triggered"] if row else None) if body.samr_triggered is None else body.samr_triggered

    await svc.record_feedback(
        session_id=body.session_id,
        org_id=str(current_user.organisation_id),
        samr_triggered=bool(triggered),
        cosine_score=float(cosine),
        threshold_used=float(threshold),
        feedback=body.feedback,
        submitted_by=str(current_user.id),
    )


@router.get("/threshold")
async def get_threshold(current_user: CurrentUser) -> dict:
    """Current adaptive threshold for the caller's organisation."""
    svc = await _get_svc()
    threshold = await svc.get_threshold(str(current_user.organisation_id))
    return {
        "org_id": str(current_user.organisation_id),
        "threshold": threshold,
        "global_prior": settings.samr_divergence_threshold,
        "description": (
            "Adaptive threshold computed from your org's last 30 SAMR feedback submissions. "
            "Optimised to maximise precision (fewer false alarms)."
        ),
    }


@router.get("/analytics")
async def get_samr_analytics(current_user: CurrentUser) -> dict:
    """30-day feedback trend: TP/FP/FN counts and per-day breakdown."""
    svc = await _get_svc()
    return await svc.get_analytics(str(current_user.organisation_id))
