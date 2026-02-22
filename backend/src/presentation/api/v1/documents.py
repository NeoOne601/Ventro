"""
FastAPI Document Upload and Management Routes
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from ..dependencies import DBDep, DocProcessorDep, EmbedderDep, MongoDep, QdrantDep
from ..schemas import DocumentInfoResponse, DocumentUploadResponse
from ...application.config import get_settings
from ...domain.entities import DocumentType

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])
settings = get_settings()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/tiff": "tiff",
}


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: DBDep = None,
    mongo: MongoDep = None,
    qdrant: QdrantDep = None,
    embedder: EmbedderDep = None,
    processor: DocProcessorDep = None,
) -> DocumentUploadResponse:
    """
    Upload and process a financial document (PO, GRN, or Invoice).
    - Validates file type and size
    - Runs the CV pipeline (layout analysis + bounding box extraction)
    - Generates embeddings and indexes in Qdrant
    - Returns document ID for subsequent reconciliation
    """
    content_type = file.content_type or ""

    # Validate file type
    if not any(allowed in content_type for allowed in ALLOWED_TYPES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, PNG, JPEG, TIFF",
        )

    # Read content
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
        )

    # Save to temp
    doc_id = str(uuid.uuid4())
    ext = ALLOWED_TYPES.get(content_type, "pdf")
    temp_path = Path(settings.temp_upload_dir) / f"{doc_id}.{ext}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(temp_path, "wb") as f:
        await f.write(content)

    logger.info("document_uploaded", doc_id=doc_id, filename=file.filename, size=len(content))

    try:
        # Process with CV pipeline
        parsed_doc = await processor.process_pdf(str(temp_path), document_id=doc_id)

        # Save metadata to PostgreSQL
        parsed_doc.metadata.processed_at = datetime.utcnow()
        await db.save(parsed_doc.metadata)

        # Save full parsed data to MongoDB
        await mongo.save_parsed_document(parsed_doc)

        # Generate embeddings and index in Qdrant
        chunks = await processor.chunk_document_for_embedding(parsed_doc)
        if chunks:
            texts = [c["payload"]["text"] for c in chunks]
            vectors = await embedder.embed_texts(texts)
            for chunk, vector in zip(chunks, vectors):
                chunk["vector"] = vector

            await qdrant.upsert_chunks(chunks, settings.qdrant_collection_name)

        # Update parsed_doc.vector_ids
        logger.info("document_indexed",
                    doc_id=doc_id,
                    doc_type=parsed_doc.metadata.document_type.value,
                    chunks=len(chunks))

        return DocumentUploadResponse(
            document_id=doc_id,
            filename=file.filename or "unknown",
            document_type=parsed_doc.metadata.document_type.value,
            total_pages=parsed_doc.metadata.total_pages,
            classification_confidence=parsed_doc.metadata.classification_confidence,
            message=f"Document processed successfully. {len(chunks)} chunks indexed.",
        )

    except Exception as e:
        logger.error("document_processing_failed", doc_id=doc_id, error=str(e))
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}",
        )


@router.get("/{document_id}", response_model=DocumentInfoResponse)
async def get_document(document_id: str, db: DBDep = None) -> DocumentInfoResponse:
    """Retrieve document metadata by ID."""
    metadata = await db.get_by_id(document_id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return DocumentInfoResponse(
        id=metadata.id,
        filename=metadata.filename,
        document_type=metadata.document_type.value,
        total_pages=metadata.total_pages,
        file_size_bytes=metadata.file_size_bytes,
        uploaded_at=metadata.uploaded_at,
        vendor_name=metadata.vendor_name,
        document_number=metadata.document_number,
        classification_confidence=metadata.classification_confidence,
    )


@router.get("/{document_id}/parsed")
async def get_parsed_document(document_id: str, mongo: MongoDep = None) -> JSONResponse:
    """Retrieve full parsed document data including line items and bounding boxes."""
    data = await mongo.get_parsed_document_raw(document_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parsed document not found")
    return JSONResponse(content=data)


# ── Version History ──────────────────────────────────────────────────────────

@router.get("/{document_id}/history")
async def get_document_history(document_id: str, mongo: MongoDep = None) -> JSONResponse:
    """
    Return all upload versions for a document, newest first.
    Each entry includes metadata summary + line item count — no full data.
    """
    history = await mongo.get_document_history(document_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No history found for document (may not exist or was never re-uploaded)"
        )
    return JSONResponse(content=history)


@router.get("/{document_id}/diff/{v1}/{v2}")
async def get_document_diff(
    document_id: str,
    v1: int,
    v2: int,
    mongo: MongoDep = None,
) -> JSONResponse:
    """
    Structured diff between two document versions.
    Returns: metadata_changes (field-level), line_item_changes (added/removed/changed).
    """
    if v1 == v2:
        raise HTTPException(status_code=400, detail="v1 and v2 must be different")
    diff = await mongo.get_document_diff(document_id, v1, v2)
    if "error" in diff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=diff["error"])
    return JSONResponse(content=diff)


# ── Bulk Upload ──────────────────────────────────────────────────────────────

MAX_BULK_FILES = 50


@router.post("/bulk", status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_documents(
    files: list[UploadFile] = File(...),
    db: DBDep = None,
    mongo: MongoDep = None,
    processor: DocProcessorDep = None,
) -> JSONResponse:
    """
    Upload up to 50 files for bulk batch reconciliation.

    Processing pipeline:
      1. Validate + save each file to temp storage
      2. Fire a Celery chord: N×process_document_in_batch tasks
      3. Chord callback: batch_match_and_dispatch groups docs into PO+GRN+Invoice
         triplets and enqueues reconciliation sessions automatically
      4. Connect to WebSocket /ws/batch/{batch_id} for real-time progress

    Returns: batch_id + per-file initial status list
    """
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Too many files. Maximum is {MAX_BULK_FILES}.",
        )

    from celery import chord as celery_chord
    from ...infrastructure.jobs.batch_tasks import (
        process_document_in_batch,
        batch_match_and_dispatch,
    )

    batch_id = str(uuid.uuid4())
    tasks_info = []

    for file in files:
        content_type = file.content_type or ""
        if not any(a in content_type for a in ALLOWED_TYPES):
            tasks_info.append({
                "filename": file.filename,
                "status": "rejected",
                "reason": f"Unsupported type: {content_type}",
                "file_id": None,
            })
            continue

        content = await file.read()
        if len(content) > settings.max_upload_size_bytes:
            tasks_info.append({
                "filename": file.filename,
                "status": "rejected",
                "reason": "File exceeds size limit",
                "file_id": None,
            })
            continue

        file_id = str(uuid.uuid4())
        ext = ALLOWED_TYPES.get(content_type, "pdf")
        temp_path = Path(settings.temp_upload_dir) / f"{file_id}.{ext}"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        import aiofiles as _aiofiles
        async with _aiofiles.open(temp_path, "wb") as f:
            await f.write(content)

        tasks_info.append({
            "filename": file.filename,
            "file_id": file_id,
            "status": "queued",
        })

    # Build Celery chord for accepted files
    accepted = [t for t in tasks_info if t["status"] == "queued"]
    if accepted:
        chord_header = [
            process_document_in_batch.s(t["file_id"], batch_id)
            for t in accepted
        ]
        celery_chord(chord_header)(
            batch_match_and_dispatch.s(batch_id)
        )

    logger.info("bulk_upload_accepted", batch_id=batch_id, files=len(accepted))

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "batch_id": batch_id,
            "accepted": len(accepted),
            "rejected": len(tasks_info) - len(accepted),
            "files": tasks_info,
            "ws_channel": f"/ws/batch/{batch_id}",
            "message": (
                f"Processing {len(accepted)} files. Connect to ws_channel for live progress. "
                f"Sessions will be queued automatically once triplets are matched."
            ),
        },
    )
