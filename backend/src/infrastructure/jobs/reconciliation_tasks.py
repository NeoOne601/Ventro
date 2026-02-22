"""
Reconciliation Celery Tasks — with Redis pub/sub progress events
Each agent stage emits a real-time event → WebSocket → browser.
"""
from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from .celery_app import celery_app

logger = structlog.get_logger(__name__)

# Agent stage metadata: name, display label, progress %
_STAGES = [
    ("initializing",         "Initialising pipeline",   0),
    ("extracting_documents", "Extracting documents",    15),
    ("quantitative_check",   "Verifying arithmetic",    35),
    ("compliance_check",     "Compliance rules",        50),
    ("confidence_assurance", "Confidence assurance",    65),
    ("reconciliation",       "Three-way match",         80),
    ("drafting_workpaper",   "Drafting workpaper",      92),
    ("completed",            "Complete",               100),
]


def _emit(session_id: str, event: str, stage: str, label: str,
          progress: int, data: dict | None = None) -> None:
    """
    Synchronous helper: publish a progress event from inside a Celery task.
    Celery workers are synchronous, so we spin up a minimal event loop just
    for the publish call (fire-and-forget).
    """
    from ...presentation.websocket.progress import publish_pipeline_event
    payload = {
        "event":      event,
        "session_id": session_id,
        "stage":      stage,
        "label":      label,
        "progress":   progress,
        "ts":         datetime.now(timezone.utc).isoformat(),
        "data":       data or {},
    }
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(publish_pipeline_event(session_id, payload))
        loop.close()
    except Exception as e:
        logger.warning("progress_emit_failed", stage=stage, error=str(e))


class ReconciliationTask(Task):
    abstract = True

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        logger.info(
            "task_completed",
            task_id=task_id, status=status,
            session_id=kwargs.get("session_id"),
        )


@celery_app.task(
    bind=True,
    base=ReconciliationTask,
    name="reconciliation.run_pipeline",
    queue="reconciliation",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError),
)
def run_reconciliation_pipeline(
    self,
    session_id: str,
    document_paths: dict[str, str],
    user_id: str,
    org_id: str,
) -> dict:
    """Durable multi-agent reconciliation pipeline task, with Redis progress relay."""
    logger.info(
        "reconciliation_task_started",
        task_id=self.request.id,
        session_id=session_id, user_id=user_id, org_id=org_id,
    )

    _emit(session_id, "agent_start", "initializing",
          "Initialising pipeline", 0)
    self.update_state(state="PROCESSING", meta={
        "session_id": session_id, "stage": "initializing",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        result = asyncio.run(
            _run_pipeline_async(
                task=self,
                session_id=session_id,
                document_paths=document_paths,
                user_id=user_id,
                org_id=org_id,
            )
        )
        _emit(session_id, "done", "completed", "Complete", 100, result)
        return result

    except SoftTimeLimitExceeded:
        logger.error("task_soft_time_limit_exceeded", session_id=session_id)
        err = {"status": "timeout", "error": "Pipeline exceeded the 5-minute time limit"}
        _emit(session_id, "error", "timeout", "Time limit exceeded", 0, err)
        return {"session_id": session_id, "partial": True, **err}

    except Exception as exc:
        logger.error("reconciliation_task_failed", session_id=session_id,
                     error=str(exc), traceback=traceback.format_exc())
        _emit(session_id, "error", "failed", f"Pipeline error: {exc}", 0)
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_pipeline_async(
    task: Task,
    session_id: str,
    document_paths: dict[str, str],
    user_id: str,
    org_id: str,
) -> dict:
    from ...application.config import get_settings
    settings = get_settings()

    def _stage(stage: str, label: str, progress: int) -> None:
        task.update_state(state="PROCESSING",
                          meta={"session_id": session_id, "stage": stage})
        _emit(session_id, "agent_start", stage, label, progress)

    _stage("extracting_documents", "Extracting documents", 15)

    from ...application.agents.orchestrator import VentroOrchestrator

    orchestrator = VentroOrchestrator()

    # We hook into the orchestrator's stage callbacks if available
    # Otherwise fall through with manual milestones
    if hasattr(orchestrator, "on_stage_complete"):
        async def _relay(stage: str, label: str, progress: int, data: dict):
            _emit(session_id, "agent_complete", stage, label, progress, data)
        orchestrator.on_stage_complete = _relay  # type: ignore

    _stage("quantitative_check", "Verifying arithmetic", 35)
    _stage("compliance_check",   "Running compliance rules", 50)
    _stage("confidence_assurance", "Confidence assurance layer", 65)
    _stage("reconciliation",     "Three-way match in progress", 80)

    result = await orchestrator.run(
        session_id=session_id,
        po_path=document_paths.get("po"),
        grn_path=document_paths.get("grn"),
        invoice_path=document_paths.get("invoice"),
        user_id=user_id,
        org_id=org_id,
    )

    _stage("drafting_workpaper", "Drafting workpaper", 92)

    return {
        "session_id":         session_id,
        "status":             "completed",
        "workpaper_id":       result.get("workpaper_id"),
        "samr_score":         result.get("samr_score"),
        "discrepancies_found": result.get("discrepancy_count", 0),
        "completed_at":       datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="reconciliation.cleanup_temp_files", queue="celery")
def cleanup_temp_files(file_paths: list[str]) -> int:
    import os
    cleaned = 0
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                cleaned += 1
        except Exception as e:
            logger.warning("temp_file_cleanup_failed", path=path, error=str(e))
    logger.info("temp_files_cleaned", count=cleaned)
    return cleaned
