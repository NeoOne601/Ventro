"""
Analytics API Routes - System metrics, session history, and SAMR stats.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter

from ...dependencies import DBDep, QdrantDep
from ...schemas import AnalyticsResponse

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/metrics", response_model=AnalyticsResponse)
async def get_metrics(db: DBDep = None, qdrant: QdrantDep = None) -> AnalyticsResponse:
    """Get system-wide performance and quality metrics."""
    from src.application.config import get_settings
    settings = get_settings()

    sessions = await db.list_sessions(limit=1000)
    total = len(sessions)
    matched = sum(1 for s in sessions if s.status.value == "matched")
    discrepancy = sum(1 for s in sessions if s.status.value in ("discrepancy_found", "exception"))

    # Get SAMR alerts
    samr_alerts = 0
    for s in sessions:
        metrics = await db.get_samr_metrics(s.id)
        samr_alerts += sum(1 for m in metrics if m.alert_triggered)

    # Calculate average processing time
    completed = [s for s in sessions if s.completed_at and s.started_at]
    avg_time = 0.0
    if completed:
        times = [(s.completed_at - s.started_at).total_seconds() for s in completed]
        avg_time = sum(times) / len(times)

    # Hallucination rate from SAMR
    hall_rate = samr_alerts / total if total > 0 else 0.0

    # Vector store stats
    qdrant_stats = await qdrant.get_collection_stats(settings.qdrant_collection_name)

    return AnalyticsResponse(
        total_sessions=total,
        matched_sessions=matched,
        discrepancy_sessions=discrepancy,
        samr_alerts=samr_alerts,
        avg_processing_time_seconds=round(avg_time, 2),
        hallucination_rate=round(hall_rate, 4),
        sessions=[
            {
                "id": s.id,
                "status": s.status.value,
                "created_at": s.created_at.isoformat(),
                "processing_time": (
                    (s.completed_at - s.started_at).total_seconds()
                    if s.completed_at and s.started_at else None
                ),
            }
            for s in sessions[:50]
        ],
    )


@router.get("/health")
async def detailed_health(
    db: DBDep = None,
    qdrant: QdrantDep = None,
) -> dict[str, Any]:
    """Detailed health check of all subsystems."""
    from src.application.config import get_settings
    settings = get_settings()
    from ...dependencies import get_ollama
    ollama = get_ollama()

    services: dict[str, str] = {}

    # Check PostgreSQL
    try:
        await db.list_sessions(limit=1)
        services["postgresql"] = "healthy"
    except Exception as e:
        services["postgresql"] = f"unhealthy: {str(e)[:50]}"

    # Check Qdrant
    try:
        await qdrant.get_collection_stats()
        services["qdrant"] = "healthy"
    except Exception as e:
        services["qdrant"] = f"unhealthy: {str(e)[:50]}"

    # Check Ollama
    try:
        is_alive = await ollama.health_check()
        services["ollama"] = "healthy" if is_alive else "model_not_loaded"
    except Exception as e:
        services["ollama"] = f"unhealthy: {str(e)[:50]}"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return {
        "status": overall,
        "version": settings.app_version,
        "services": services,
        "timestamp": datetime.utcnow().isoformat(),
    }
