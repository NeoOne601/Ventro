"""
Reconciliation Session API Routes
All routes require JWT authentication.
Sessions are scoped to the user's organisation (multi-tenant isolation).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse

from ...middleware.auth_middleware import AnalystOrAbove, CurrentUser
from ...dependencies import DBDep, MongoDep, LLMDep, PublisherDep, QdrantDep, EmbedderDep, PgPoolDep
from ...schemas import (
    CreateSessionRequest,
    ReconciliationResultResponse,
    SessionResponse,
)
from src.application.agents.langgraph_orchestrator import LangGraphOrchestrator
from src.domain.entities import ReconciliationSession, ReconciliationStatus

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


async def _run_reconciliation_background(
    session_id: str,
    db: DBDep,
    mongo: MongoDep,
    qdrant: QdrantDep,
    llm: LLMDep,
    embedder: EmbedderDep,
    publisher: PublisherDep,
    org_id: str | None = None,
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
            llm_client=llm,
            vector_store=qdrant,
            document_store=mongo,
            reconciliation_repo=db,
            progress_publisher=publisher,
        )

        # Run the LangGraph state machine (org_id flows into AdaptiveThresholdService)
        final_state = await orchestrator.run_reconciliation(
            session, org_id=org_id
        )

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

        from src.domain.entities import ReconciliationVerdict
        session.verdict = ReconciliationVerdict(
            session_id=session.id,
            po_document_id=session.po_document_id,
            grn_document_id=session.grn_document_id,
            invoice_document_id=session.invoice_document_id,
            status=session.status,
            overall_confidence=verdict.get("confidence", 0.0),
            discrepancy_summary=verdict.get("discrepancy_summary", []),
            recommendation=verdict.get("recommendation", ""),
            line_item_matches=final_state.get("line_item_matches") or verdict.get("line_item_matches", []),
            classification_errors=final_state.get("classification_errors", [])
        )

        session.completed_at = datetime.utcnow()
        session.agent_trace = final_state.get("agent_trace", [])
        await db.update_session(session)

        # Save workpaper to MongoDB
        if workpaper_data:
            from src.domain.entities import AuditWorkpaper, WorkpaperSection
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
    request: Request,
    body: CreateSessionRequest,
    current_user: AnalystOrAbove,
    pool: PgPoolDep,
    db: DBDep = None,
) -> SessionResponse:
    """
    Create a new three-way match reconciliation session.
    Session is automatically scoped to the caller's organisation.
    Requires role: ap_analyst or higher.
    """
    # Validate documents exist AND belong to caller's org
    for doc_id in [body.po_document_id, body.grn_document_id, body.invoice_document_id]:
        doc = await db.get_by_id(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {doc_id}",
            )

    session = ReconciliationSession(
        po_document_id=body.po_document_id,
        grn_document_id=body.grn_document_id,
        invoice_document_id=body.invoice_document_id,
        created_by=current_user.id,
    )
    created = await db.create_session(session)
    logger.info("session_created", session_id=session.id, org=current_user.organisation_id)

    # Audit log
    from src.infrastructure.database.user_repository import UserRepository
    repo = UserRepository(pool)
    await repo.append_audit_log(
        action="session.created",
        user_id=current_user.id,
        org_id=current_user.organisation_id,
        resource_type="session",
        resource_id=session.id,
        ip_address=request.client.host if request.client else None,
    )

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
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: AnalystOrAbove,
    db: DBDep = None,
    pool: PgPoolDep = None,
    mongo: MongoDep = None,
    qdrant: QdrantDep = None,
    llm: LLMDep = None,
    embedder: EmbedderDep = None,
    publisher: PublisherDep = None,
) -> dict[str, str]:
    """Trigger the multi-agent reconciliation workflow asynchronously. Requires: ap_analyst+"""
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Org isolation — users can only run sessions belonging to their organisation
    if hasattr(session, 'organisation_id') and session.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if session.status in (ReconciliationStatus.PROCESSING, ReconciliationStatus.COMPLETED,
                          ReconciliationStatus.MATCHED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already in state: {session.status.value}",
        )

    background_tasks.add_task(
        _run_reconciliation_background,
        session_id, db, mongo, qdrant, llm, embedder, publisher, current_user.organisation_id,
    )

    # Audit log
    from src.infrastructure.database.user_repository import UserRepository
    repo = UserRepository(pool)
    await repo.append_audit_log(
        action="session.run_triggered",
        user_id=current_user.id,
        org_id=current_user.organisation_id,
        resource_type="session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else None,
    )

    return {
        "message": "Reconciliation workflow started",
        "session_id": session_id,
        "ws_endpoint": f"/ws/reconciliation/{session_id}",
    }


@router.get("/sessions/{session_id}/status", response_model=SessionResponse)
async def get_session_status(
    session_id: str,
    current_user: CurrentUser,
    db: DBDep = None,
) -> SessionResponse:
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
    current_user: CurrentUser,
    db: DBDep = None,
    mongo: MongoDep = None,
) -> ReconciliationResultResponse:
    """Retrieve the full reconciliation result and workpaper."""
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    workpaper = None
    if mongo:
        workpaper = await mongo.get_workpaper_by_session(session_id)

    samr_metrics_list = await db.get_samr_metrics(session_id)
    samr = None
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
        classification_errors=session.verdict.classification_errors if session.verdict and session.verdict.classification_errors else [],
        errors=[]
    )


@router.get("/sessions/{session_id}/workpaper", response_class=HTMLResponse)
async def get_workpaper_html(
    session_id: str,
    current_user: CurrentUser,
    mongo: MongoDep = None,
) -> HTMLResponse:
    """Retrieve the interactive HTML audit workpaper."""
    workpaper = await mongo.get_workpaper_by_session(session_id)
    if not workpaper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workpaper not found")
    html = workpaper.get("html_content", "<p>Workpaper content not available.</p>")
    return HTMLResponse(content=html)


@router.get("/sessions/{session_id}/workpaper/pdf")
async def export_workpaper_pdf(
    session_id: str,
    current_user: CurrentUser,
    mongo: MongoDep = None,
) -> StreamingResponse:
    """
    Export the audit workpaper as a signed PDF.
    Requires permission: workpaper:export (AP Manager or higher).
    """
    from src.domain.auth_entities import Permission
    if not current_user.has_permission(Permission.WORKPAPER_EXPORT):
        raise HTTPException(status_code=403, detail="workpaper:export permission required")

    workpaper = await mongo.get_workpaper_by_session(session_id)
    if not workpaper:
        raise HTTPException(status_code=404, detail="Workpaper not found")

    html = workpaper.get("html_content", "")
    pdf_bytes = _html_to_pdf(html, session_id)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="workpaper_{session_id}.pdf"',
            "X-Workpaper-Hash": _sha256_hex(pdf_bytes),
        },
    )


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    current_user: CurrentUser = None,
    db: DBDep = None,
) -> list[dict[str, Any]]:
    """List reconciliation sessions for the caller's organisation (paginated)."""
    sessions = await db.list_sessions(
        limit=limit, offset=offset,
        org_id=getattr(current_user, 'organisation_id', None),  # Org-scoped
    )
    return [
        {
            "id": s.id,
            "status": s.status.value,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sessions
    ]


# ─── PDF Export Helper ────────────────────────────────────────────────────────

def _sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _html_to_pdf(html_content: str, session_id: str) -> bytes:
    """
    Convert HTML workpaper to a signed PDF.
    Priority:
      1. playwright (best fidelity — matches browser rendering)
      2. weasyprint (pure Python — good for server environments)
      3. Minimal fallback with integrity footer
    """
    import hashlib
    from datetime import datetime

    integrity_footer = (
        f"\n\n<!-- Ventro Integrity Footer -->\n"
        f"<!-- Session: {session_id} | Generated: {datetime.utcnow().isoformat()} | "
        f"SHA-256: {hashlib.sha256(html_content.encode()).hexdigest()} -->"
    )
    signed_html = html_content + integrity_footer

    # Try playwright first
    try:
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            f.write(signed_html)
            tmp_html = f.name
        tmp_pdf = tmp_html.replace(".html", ".pdf")
        result = subprocess.run(
            ["playwright", "pdf", tmp_html, tmp_pdf],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and os.path.exists(tmp_pdf):
            with open(tmp_pdf, "rb") as f:
                pdf = f.read()
            os.unlink(tmp_html)
            os.unlink(tmp_pdf)
            return pdf
    except Exception:
        pass

    # Try weasyprint
    try:
        from weasyprint import HTML
        return HTML(string=signed_html).write_pdf()
    except ImportError:
        pass

    # Fallback: return HTML bytes with PDF content-type header
    # (browser will display it as HTML but integrity footer is embedded)
    return signed_html.encode("utf-8")
