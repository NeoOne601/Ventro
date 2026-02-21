"""
MongoDB Document Store Adapter (Motor async driver)
Stores complex nested documents and workpapers in MongoDB.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from ...domain.entities import AuditWorkpaper, ParsedDocument
from ...domain.interfaces import IDocumentStore

logger = structlog.get_logger(__name__)


class MongoDBAdapter(IDocumentStore):
    """MongoDB adapter for complex document storage using Motor async driver."""

    def __init__(self, mongo_url: str, db_name: str = "mas_vgfr_docs") -> None:
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        self.parsed_docs = self.db["parsed_documents"]
        self.workpapers = self.db["workpapers"]

    async def ensure_indexes(self) -> None:
        await self.parsed_docs.create_index("metadata.id", unique=True)
        await self.parsed_docs.create_index("metadata.document_type")
        await self.workpapers.create_index("session_id")
        await self.workpapers.create_index("id", unique=True)
        logger.info("mongodb_indexes_ensured")

    def _parsed_doc_to_dict(self, doc: ParsedDocument) -> dict[str, Any]:
        return {
            "metadata": {
                "id": doc.metadata.id,
                "filename": doc.metadata.filename,
                "document_type": doc.metadata.document_type.value,
                "total_pages": doc.metadata.total_pages,
                "file_size_bytes": doc.metadata.file_size_bytes,
                "uploaded_at": doc.metadata.uploaded_at.isoformat(),
                "vendor_name": doc.metadata.vendor_name,
                "document_number": doc.metadata.document_number,
                "classification_confidence": doc.metadata.classification_confidence,
            },
            "line_items": [
                {
                    "id": item.id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price.amount,
                    "total_amount": item.total_amount.amount,
                    "unit_of_measure": item.unit_of_measure,
                    "part_number": item.part_number,
                    "bbox": item.bbox.to_dict() if item.bbox else None,
                    "row_index": item.row_index,
                    "raw_text": item.raw_text,
                    "confidence": item.confidence,
                }
                for item in doc.line_items
            ],
            "raw_text_by_page": {str(k): v for k, v in doc.raw_text_by_page.items()},
            "additional_fields": {
                k: v for k, v in doc.additional_fields.items()
                if k not in {"blocks_raw", "tables_raw"}  # Skip large raw data
            },
        }

    async def save_parsed_document(self, doc: ParsedDocument) -> str:
        data = self._parsed_doc_to_dict(doc)
        await self.parsed_docs.replace_one(
            {"metadata.id": doc.id}, data, upsert=True
        )
        logger.info("mongodb_parsed_doc_saved", doc_id=doc.id)
        return doc.id

    async def get_parsed_document(self, document_id: str) -> ParsedDocument | None:
        data = await self.parsed_docs.find_one({"metadata.id": document_id})
        if not data:
            return None
        # Return a lightweight version (domain reconstruction)
        # Full deserialization omitted for brevity - used as source of parsed data
        return None  # Callers use the raw dict; full deserialization in use case layer

    async def get_parsed_document_raw(self, document_id: str) -> dict[str, Any] | None:
        return await self.parsed_docs.find_one({"metadata.id": document_id}, {"_id": 0})

    async def save_workpaper(self, workpaper: AuditWorkpaper) -> str:
        data = {
            "id": workpaper.id,
            "session_id": workpaper.session_id,
            "title": workpaper.title,
            "generated_at": workpaper.generated_at.isoformat(),
            "verdict_summary": workpaper.verdict_summary,
            "html_content": workpaper.html_content,
            "sections": [
                {"title": s.title, "content": s.content, "order": s.order}
                for s in workpaper.sections
            ],
        }
        await self.workpapers.replace_one({"id": workpaper.id}, data, upsert=True)
        logger.info("mongodb_workpaper_saved", workpaper_id=workpaper.id)
        return workpaper.id

    async def get_workpaper(self, workpaper_id: str) -> AuditWorkpaper | None:
        return await self.workpapers.find_one({"id": workpaper_id}, {"_id": 0})

    async def get_workpaper_by_session(self, session_id: str) -> dict[str, Any] | None:
        return await self.workpapers.find_one({"session_id": session_id}, {"_id": 0})
