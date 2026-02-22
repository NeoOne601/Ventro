"""
Bulk / Batch Celery Tasks

Provides two task types:
  1. process_document_in_batch(file_id, batch_id) — processes a single uploaded file,
     publishes progress to WebSocket channel batch:{batch_id}
  2. batch_match_and_dispatch(results, batch_id) — the chord callback; receives all
     processed doc metadata, runs BatchMatchingService, creates ReconciliationSession
     records, and enqueues individual reconciliation tasks via the existing
     run_reconciliation task
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog

from ..celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="batch.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_document_in_batch(self, file_id: str, batch_id: str) -> dict[str, Any]:
    """
    Process a single file from a bulk upload.
    Returns document metadata dict consumed by batch_match_and_dispatch.
    """
    import asyncio
    from ...infrastructure.database.postgres_adapter import PostgresAdapter
    from ...infrastructure.database.mongodb_adapter import MongoDBAdapter
    from ...infrastructure.cv.document_processor import DocumentProcessor
    from ...infrastructure.llm.embedding_model import EmbeddingModel
    from ...infrastructure.vector_store.qdrant_adapter import QdrantAdapter
    from ...application.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, Any]:
        # Import here to avoid circular dependency at module load time
        from ...infrastructure.cache.progress_publisher import ProgressPublisher

        publisher = ProgressPublisher(settings.redis_url)
        await publisher.publish(
            f"batch:{batch_id}",
            {"event": "processing", "file_id": file_id, "batch_id": batch_id},
        )

        try:
            processor = DocumentProcessor(settings)
            embedder = EmbeddingModel(settings)
            mongo = MongoDBAdapter(settings.mongo_url)

            parsed_doc = await processor.process_pdf_by_id(file_id)
            await mongo.save_parsed_document(parsed_doc)

            # Generate embeddings for batch matching
            chunks = await processor.chunk_document_for_embedding(parsed_doc)
            doc_embedding: list[float] = []
            if chunks:
                texts = [c["payload"]["text"] for c in chunks[:3]]  # first 3 chunks for batch vector
                vectors = await embedder.embed_texts(texts)
                if vectors:
                    import numpy as np
                    doc_embedding = np.mean(vectors, axis=0).tolist()

            await publisher.publish(
                f"batch:{batch_id}",
                {
                    "event": "processed",
                    "file_id": file_id,
                    "doc_type": parsed_doc.metadata.document_type.value,
                    "vendor_name": parsed_doc.metadata.vendor_name,
                    "doc_number": parsed_doc.metadata.document_number,
                },
            )

            return {
                "doc_id": parsed_doc.id,
                "doc_type": parsed_doc.metadata.document_type.value,
                "vendor_name": parsed_doc.metadata.vendor_name,
                "doc_number": parsed_doc.metadata.document_number,
                "embedding": doc_embedding,
                "filename": parsed_doc.metadata.filename,
                "status": "success",
            }

        except Exception as exc:
            await publisher.publish(
                f"batch:{batch_id}",
                {"event": "error", "file_id": file_id, "error": str(exc)},
            )
            raise self.retry(exc=exc)

    return asyncio.get_event_loop().run_until_complete(_run())


@celery_app.task(
    name="batch.match_and_dispatch",
    bind=True,
)
def batch_match_and_dispatch(self, results: list[dict[str, Any]], batch_id: str) -> dict[str, Any]:
    """
    Chord callback: receives all processed document metadata.
    Runs BatchMatchingService, creates sessions, and enqueues reconciliation tasks.
    """
    import asyncio
    from ...application.services.batch_matching import BatchMatchingService, DocumentSlot
    from ...application.config import get_settings
    from ...infrastructure.cache.progress_publisher import ProgressPublisher

    settings = get_settings()

    async def _run() -> dict[str, Any]:
        publisher = ProgressPublisher(settings.redis_url)

        # Build DocumentSlot list from results
        slots = [
            DocumentSlot(
                doc_id=r["doc_id"],
                doc_type=r["doc_type"],
                vendor_name=r.get("vendor_name"),
                doc_number=r.get("doc_number"),
                embedding=r.get("embedding"),
                filename=r.get("filename", ""),
            )
            for r in results if r.get("status") == "success"
        ]

        matcher = BatchMatchingService()
        match_result = matcher.match(slots)

        # Enqueue individual reconciliation tasks for each matched triplet
        from .reconciliation_tasks import run_reconciliation

        session_ids = []
        for triplet in match_result.triplets:
            session_id = str(uuid.uuid4())
            session_ids.append(session_id)
            run_reconciliation.apply_async(
                kwargs={
                    "session_id": session_id,
                    "po_id": triplet.po_id,
                    "grn_id": triplet.grn_id,
                    "invoice_id": triplet.invoice_id,
                },
                queue="reconciliation",
            )

        await publisher.publish(
            f"batch:{batch_id}",
            {
                "event": "batch_complete",
                "batch_id": batch_id,
                "triplets_found": len(match_result.triplets),
                "sessions_queued": session_ids,
                "unmatched_docs": match_result.unmatched,
                "stats": match_result.stats,
            },
        )

        logger.info(
            "batch_dispatch_complete",
            batch_id=batch_id,
            sessions=len(session_ids),
            unmatched=len(match_result.unmatched),
        )

        return {
            "batch_id": batch_id,
            "sessions": session_ids,
            "triplets": [
                {"po": t.po_id, "grn": t.grn_id, "invoice": t.invoice_id,
                 "method": t.match_method, "score": t.match_score}
                for t in match_result.triplets
            ],
            "unmatched": match_result.unmatched,
            "stats": match_result.stats,
        }

    return asyncio.get_event_loop().run_until_complete(_run())
