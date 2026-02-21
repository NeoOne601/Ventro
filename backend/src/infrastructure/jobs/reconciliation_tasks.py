"""
Reconciliation Celery Tasks
Durable, resumable tasks for the multi-agent reconciliation pipeline.
If the worker dies mid-run, Redis ensures the job is re-queued automatically.
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


class ReconciliationTask(Task):
    """Base task class with DB connection management."""
    abstract = True
    _db_pool = None

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Called after every task completion — log the outcome."""
        logger.info(
            "task_completed",
            task_id=task_id,
            status=status,
            session_id=kwargs.get("session_id"),
        )


@celery_app.task(
    bind=True,
    base=ReconciliationTask,
    name="reconciliation.run_pipeline",
    queue="reconciliation",
    max_retries=3,
    default_retry_delay=30,          # 30 seconds between retries
    autoretry_for=(ConnectionError, TimeoutError),
)
def run_reconciliation_pipeline(
    self,
    session_id: str,
    document_paths: dict[str, str],  # {"po": path, "grn": path, "invoice": path}
    user_id: str,
    org_id: str,
) -> dict:
    """
    Durable multi-agent reconciliation pipeline task.
    Runs the full LangGraph pipeline in an asyncio event loop within Celery.
    
    Args:
        session_id: The reconciliation session UUID
        document_paths: Dict mapping document type to file path
        user_id: Requesting user (for audit log)
        org_id: Organisation ID (for multi-tenancy)
    
    Returns:
        Dict with reconciliation result summary and workpaper_id
    """
    logger.info(
        "reconciliation_task_started",
        task_id=self.request.id,
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
    )

    # Update task state so frontend can show "PROCESSING"
    self.update_state(
        state="PROCESSING",
        meta={
            "session_id": session_id,
            "stage": "initializing",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )

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
        return result

    except SoftTimeLimitExceeded:
        logger.error("task_soft_time_limit_exceeded", session_id=session_id)
        # Return partial result rather than crashing
        return {
            "session_id": session_id,
            "status": "timeout",
            "error": "Pipeline exceeded the 5-minute time limit",
            "partial": True,
        }
    except Exception as exc:
        logger.error(
            "reconciliation_task_failed",
            session_id=session_id,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        # Retry with exponential back-off (up to max_retries=3)
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_pipeline_async(
    task: Task,
    session_id: str,
    document_paths: dict[str, str],
    user_id: str,
    org_id: str,
) -> dict:
    """
    Async wrapper that runs the actual LangGraph pipeline.
    Separated so it can be properly awaited with asyncio.run().
    """
    from ...application.config import get_settings
    from ..database.postgres_adapter import PostgreSQLAdapter
    from ..database.mongodb_adapter import MongoDBAdapter

    settings = get_settings()

    # Update state: extracting
    task.update_state(
        state="PROCESSING",
        meta={"session_id": session_id, "stage": "extracting_documents"}
    )

    # Import here to avoid circular imports at module load time
    from ...application.agents.orchestrator import VentroOrchestrator

    orchestrator = VentroOrchestrator()

    # Update state: running agents
    task.update_state(
        state="PROCESSING",
        meta={"session_id": session_id, "stage": "running_agents"}
    )

    result = await orchestrator.run(
        session_id=session_id,
        po_path=document_paths.get("po"),
        grn_path=document_paths.get("grn"),
        invoice_path=document_paths.get("invoice"),
        user_id=user_id,
        org_id=org_id,
    )

    task.update_state(
        state="PROCESSING",
        meta={"session_id": session_id, "stage": "generating_workpaper"}
    )

    return {
        "session_id": session_id,
        "status": "completed",
        "workpaper_id": result.get("workpaper_id"),
        "samr_score": result.get("samr_score"),
        "discrepancies_found": result.get("discrepancy_count", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="reconciliation.cleanup_temp_files", queue="celery")
def cleanup_temp_files(file_paths: list[str]) -> int:
    """Clean up temporary uploaded files after pipeline completion."""
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
