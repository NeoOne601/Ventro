"""
MongoDB Document Store Adapter (Motor async driver) — with Version History

Changes vs original:
  - save_parsed_document() now calls save_parsed_document_version() (append-only)
  - document_versions collection: immutable, one document per (document_id, version)
  - get_document_history()  → list of version summaries
  - get_document_diff()     → field-level diff between two versions
  - Original parsed_documents collection still used for latest-version fast access
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
        self.parsed_docs = self.db["parsed_documents"]       # latest version (fast reads)
        self.doc_versions = self.db["document_versions"]     # immutable history (append-only)
        self.workpapers = self.db["workpapers"]

    async def ensure_indexes(self) -> None:
        await self.parsed_docs.create_index("metadata.id", unique=True)
        await self.parsed_docs.create_index("metadata.document_type")
        await self.workpapers.create_index("session_id")
        await self.workpapers.create_index("id", unique=True)
        # Version history indexes
        await self.doc_versions.create_index(
            [("document_id", 1), ("version", -1)], unique=True
        )
        await self.doc_versions.create_index("document_id")
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
                if k not in {"blocks_raw", "tables_raw"}
            },
        }

    async def save_parsed_document(self, doc: ParsedDocument, replaced_reason: str = "upload") -> str:
        """Save (or replace) a document. Keeps history via versioned collection."""
        data = self._parsed_doc_to_dict(doc)

        # 1. Update the latest-version fast-access collection
        await self.parsed_docs.replace_one(
            {"metadata.id": doc.id}, data, upsert=True
        )

        # 2. Append to immutable version history
        await self.save_parsed_document_version(doc, replaced_reason)

        logger.info("mongodb_parsed_doc_saved", doc_id=doc.id)
        return doc.id

    async def save_parsed_document_version(
        self, doc: ParsedDocument, replaced_reason: str = "upload"
    ) -> int:
        """Append an immutable version snapshot. Returns the new version number."""
        # Find current max version
        last = await self.doc_versions.find_one(
            {"document_id": doc.id},
            sort=[("version", -1)],
        )
        version = (last["version"] + 1) if last else 1

        data = self._parsed_doc_to_dict(doc)
        data["document_id"] = doc.id
        data["version"] = version
        data["replaced_reason"] = replaced_reason
        data["created_at"] = doc.metadata.uploaded_at.isoformat()

        await self.doc_versions.insert_one(data)
        logger.info("mongodb_version_saved", doc_id=doc.id, version=version)
        return version

    async def get_parsed_document(self, document_id: str) -> ParsedDocument | None:
        return None  # Callers use raw dict

    async def get_parsed_document_raw(self, document_id: str) -> dict[str, Any] | None:
        return await self.parsed_docs.find_one({"metadata.id": document_id}, {"_id": 0})

    # ── Version History ───────────────────────────────────────────────────────

    async def get_document_history(self, document_id: str) -> list[dict[str, Any]]:
        """Return all version summaries (metadata only, no line items) for a document."""
        cursor = self.doc_versions.find(
            {"document_id": document_id},
            {
                "_id": 0,
                "document_id": 1,
                "version": 1,
                "created_at": 1,
                "replaced_reason": 1,
                "metadata": 1,
                # Summarise line_items instead of returning all
                "line_item_count": {"$size": {"$ifNull": ["$line_items", []]}},
            },
            sort=[("version", -1)],
        )
        results = []
        async for doc in cursor:
            # Compute line_item_count manually (projection $size not available in find easily)
            doc["line_item_count"] = len(doc.get("line_items", []))
            doc.pop("line_items", None)
            results.append(doc)
        return results

    async def get_document_version_raw(
        self, document_id: str, version: int
    ) -> dict[str, Any] | None:
        return await self.doc_versions.find_one(
            {"document_id": document_id, "version": version}, {"_id": 0}
        )

    async def get_document_diff(
        self, document_id: str, v1: int, v2: int
    ) -> dict[str, Any]:
        """
        Return a structured diff between two document versions.
        Covers: metadata fields, line item add/remove/change.
        """
        doc1 = await self.get_document_version_raw(document_id, v1)
        doc2 = await self.get_document_version_raw(document_id, v2)

        if not doc1 or not doc2:
            return {"error": "One or both versions not found"}

        def diff_meta(m1: dict, m2: dict) -> list[dict]:
            changes = []
            for key in set(list(m1.keys()) + list(m2.keys())):
                if m1.get(key) != m2.get(key):
                    changes.append({"field": key, "before": m1.get(key), "after": m2.get(key)})
            return changes

        def diff_items(items1: list, items2: list) -> dict:
            by_desc1 = {i["description"]: i for i in items1}
            by_desc2 = {i["description"]: i for i in items2}
            added = [i for d, i in by_desc2.items() if d not in by_desc1]
            removed = [i for d, i in by_desc1.items() if d not in by_desc2]
            changed = []
            for desc in set(by_desc1.keys()) & set(by_desc2.keys()):
                i1, i2 = by_desc1[desc], by_desc2[desc]
                field_diffs = {
                    k: {"before": i1.get(k), "after": i2.get(k)}
                    for k in ("quantity", "unit_price", "total_amount")
                    if i1.get(k) != i2.get(k)
                }
                if field_diffs:
                    changed.append({"description": desc, "changes": field_diffs})
            return {"added": added, "removed": removed, "changed": changed}

        return {
            "document_id": document_id,
            "v1": v1, "v2": v2,
            "metadata_changes": diff_meta(
                doc1.get("metadata", {}), doc2.get("metadata", {})
            ),
            "line_item_changes": diff_items(
                doc1.get("line_items", []), doc2.get("line_items", [])
            ),
        }

    # ─────────────────────────────────────────────────────────────────────────

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
