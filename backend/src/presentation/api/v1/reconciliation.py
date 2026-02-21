"""
Reconciliation Session API Routes
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import HTMLResponse

from ..dependencies import DBDep, MongoDep, OllamaDep, PublisherDep, QdrantDep, EmbedderDep
from ..schemas import (
    CreateSessionRequest,
    ReconciliationResultResponse,
    SessionResponse,
)
from ...application.agents.langgraph_orchestrator import LangGraphOrchestrator
from ...domain.entities import ReconciliationSession, ReconciliationStatus

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


async def _run_reconciliation_background(
    session_id: str,
    db: DBDep,
    mongo: MongoDep,
    qdrant: QdrantDep,
    ollama: OllamaDep,
    embedder: EmbedderDep,
    publisher: PublisherDep,
) -> None:
    """Background task: run the full multi-agent reconciliation workflow."""
    try:
        session = await db.get_session(session_id)
        if not session:
            logger.error("session_not_found_for_reconciliation", session_id=session_id)
            return

        # Mark as processing
        session.status = ReconciliationStatus.PROCESSING
        session.started_at = datetime.utcnow()
        await db.update_session(session)

        # Build orchestrator
        orchestrator = LangGraphOrchestrator(
            llm_client=ollama,
            vector_store=qdrant,
            document_store=mongo,
            reconciliation_repo=db,
            progress_publisher=publisher,
        )

        # Run the LangGraph state machine
        final_state = await orchestrator.run_reconciliation(session)

        # Persist results
        verdict = final_state.get("reconciliation_verdict") or {}
        workpaper_data = final_state.get("workpaper") or {}
        samr_data = final_state.get("samr_metrics") or {}

        # Determine final status
        overall_status = verdict.get("overall_status", "exception")
        status_map = {
            "full_match": ReconciliationStatus.MATCHED,
            "partial_match": ReconciliationStatus.DISCREPANCY_FOUND,
            "mismatch": ReconciliationStatus.DISCREPANCY_FOUND,
            "exception": ReconciliationStatus.EXCEPTION,
        }
        session.status = status_map.get(overall_status, ReconciliationStatus.COMPLETED)
        if final_state.get("samr_alert_triggered"):
            session.status = ReconciliationStatus.SAMR_ALERT
        session.completed_at = datetime.utcnow()
        session.agent_trace = final_state.get("agent_trace", [])
        await db.update_session(session)

        # Save workpaper to MongoDB
        if workpaper_data:
            from ...domain.entities import AuditWorkpaper, WorkpaperSection
            wp = AuditWorkpaper(
                id=workpaper_data.get("id", ""),
                session_id=session_id,
                title=workpaper_data.get("title", "Audit Workpaper"),
                verdict_summary=workpaper_data.get("verdict_summary", ""),
                html_content=workpaper_data.get("html_content", ""),
            )
            await mongo.save_workpaper(wp)

        logger.info("reconciliation_completed", session_id=session_id, status=session.status.value)

    except Exception as e:
        logger.error("reconciliation_background_error", session_id=session_id, error=str(e))
        try:
            session = await db.get_session(session_id)
            if session:
                session.status = ReconciliationStatus.FAILED
                session.error_message = str(e)
                session.completed_at = datetime.utcnow()
                await db.update_session(session)
        except Exception:
            pass


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    db: DBDep = None,
) -> SessionResponse:
    """Create a new three-way match reconciliation session."""
    # Validate documents exist
    for doc_id in [request.po_document_id, request.grn_document_id, request.invoice_document_id]:
        doc = await db.get_by_id(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {doc_id}",
            )

    session = ReconciliationSession(
        po_document_id=request.po_document_id,
        grn_document_id=request.grn_document_id,
        invoice_document_id=request.invoice_document_id,
    )
    created = await db.create_session(session)
    logger.info("session_created", session_id=session.id)

    return SessionResponse(
        id=session.id,
        po_document_id=session.po_document_id,
        grn_document_id=session.grn_document_id,
        invoice_document_id=session.invoice_document_id,
        status=session.status.value,
        created_at=session.created_at,
    )


@router.post("/sessions/{session_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_reconciliation(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: DBDep = None,
    mongo: MongoDep = None,
    qdrant: QdrantDep = None,
    ollama: OllamaDep = None,
    embedder: EmbedderDep = None,
    publisher: PublisherDep = None,
) -> dict[str, str]:
    """Trigger the multi-agent reconciliation workflow asynchronously."""
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status in (ReconciliationStatus.PROCESSING, ReconciliationStatus.COMPLETED,
                          ReconciliationStatus.MATCHED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already in state: {session.status.value}",
        )

    background_tasks.add_task(
        _run_reconciliation_background,
        session_id, db, mongo, qdrant, ollama, embedder, publisher,
    )

    return {
        "message": "Reconciliation workflow started",
        "session_id": session_id,
        "ws_endpoint": f"/ws/reconciliation/{session_id}",
    }


@router.get("/sessions/{session_id}/status", response_model=SessionResponse)
async def get_session_status(session_id: str, db: DBDep = None) -> SessionResponse:
    """Poll the current status of a reconciliation session."""
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionResponse(
        id=session.id,
        po_document_id=session.po_document_id,
        grn_document_id=session.grn_document_id,
        invoice_document_id=session.invoice_document_id,
        status=session.status.value,
        created_at=session.created_at,
    )


@router.get("/sessions/{session_id}/result", response_model=ReconciliationResultResponse)
async def get_reconciliation_result(
    session_id: str,
    db: DBDep = None,
    mongo: MongoDep = None,
) -> ReconciliationResultResponse:
    """Retrieve the full reconciliation result and workpaper."""
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    workpaper = None
    samr = None

    if mongo:
        workpaper = await mongo.get_workpaper_by_session(session_id)

    # Get SAMR metrics
    samr_metrics_list = await db.get_samr_metrics(session_id)
    if samr_metrics_list:
        m = samr_metrics_list[-1]
        samr = {
            "cosine_similarity_score": m.cosine_similarity_score,
            "alert_triggered": m.alert_triggered,
            "interpretation": "Alert" if m.alert_triggered else "Clear",
        }

    return ReconciliationResultResponse(
        session_id=session_id,
        status=session.status.value,
        verdict=session.verdict.__dict__ if session.verdict else None,
        workpaper=workpaper,
        samr_metrics=samr,
        agent_trace=session.agent_trace or [],
        completed_at=session.completed_at,
    )


@router.get("/sessions/{session_id}/workpaper", response_class=HTMLResponse)
async def get_workpaper_html(
    session_id: str,
    mongo: MongoDep = None,
) -> HTMLResponse:
    """Retrieve the interactive HTML audit workpaper."""
    workpaper = await mongo.get_workpaper_by_session(session_id)
    if not workpaper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workpaper not found")

    html = workpaper.get("html_content", "<p>Workpaper content not available.</p>")
    return HTMLResponse(content=html)


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    db: DBDep = None,
) -> list[dict[str, Any]]:
    """List all reconciliation sessions with pagination."""
    sessions = await db.list_sessions(limit=limit, offset=offset)
    return [
        {
            "id": s.id,
            "status": s.status.value,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sessions
    ]
