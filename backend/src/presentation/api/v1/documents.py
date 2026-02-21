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
