"""
Qdrant Vector Store Adapter
Implements IVectorStore for dense + sparse hybrid search with metadata filtering.
Preserves bounding box spatial coordinates as searchable payload.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from ...domain.interfaces import IVectorStore

logger = structlog.get_logger(__name__)


class QdrantAdapter(IVectorStore):
    """
    Qdrant vector database adapter with hybrid search capabilities.
    Stores document chunks with spatial metadata (bounding boxes) for visual grounding.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "mas_vgfr_docs",
        embedding_dim: int = 384,
    ) -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(host=self.host, port=self.port)
        return self._client

    async def ensure_collection(self, collection_name: str | None = None) -> None:
        """Create collection if it doesn't exist."""
        name = collection_name or self.collection_name
        client = await self._get_client()
        try:
            await client.get_collection(name)
            logger.debug("qdrant_collection_exists", collection=name)
        except (UnexpectedResponse, Exception):
            logger.info("qdrant_creating_collection", collection=name, dim=self.embedding_dim)
            await client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=self.embedding_dim,
                    distance=qmodels.Distance.COSINE,
                    on_disk=False,
                ),
                optimizers_config=qmodels.OptimizersConfigDiff(
                    indexing_threshold=0,
                ),
                hnsw_config=qmodels.HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=10000,
                ),
            )
            # Create payload indices for fast filtering
            for field in ["document_id", "document_type", "session_id", "page"]:
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )

    async def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> list[str]:
        """
        Upsert document chunks into the vector store.
        Each chunk must have: 'vector', 'payload' (with text, bbox, page, document_id, etc.)
        """
        if not chunks:
            return []

        await self.ensure_collection(collection_name)
        client = await self._get_client()

        points = []
        point_ids = []
        for chunk in chunks:
            point_id = chunk.get("id") or str(uuid.uuid4())
            point_ids.append(point_id)
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=chunk["vector"],
                    payload=chunk["payload"],
                )
            )

        # Batch upsert
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            await client.upsert(collection_name=collection_name, points=batch)

        logger.info("qdrant_upserted", collection=collection_name, count=len(points))
        return point_ids

    async def search(
        self,
        query_vector: list[float],
        collection_name: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Dense vector similarity search with optional metadata filtering."""
        await self.ensure_collection(collection_name)
        client = await self._get_client()

        qdrant_filter = None
        if filters:
            conditions = [
                qmodels.FieldCondition(
                    key=k,
                    match=qmodels.MatchValue(value=v),
                )
                for k, v in filters.items()
                if v is not None
            ]
            if conditions:
                qdrant_filter = qmodels.Filter(must=conditions)

        results = await client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
            score_threshold=0.3,
        )

        return [
            {"id": str(r.id), "score": r.score, "payload": r.payload or {}}
            for r in results
        ]

    async def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        collection_name: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Hybrid dense + sparse BM25 search for improved recall.
        Falls back to dense-only if sparse not available.
        """
        # For now, use dense search (Qdrant sparse requires ColBERT/SPLADE setup)
        # TODO: Add sparse search with FastEmbed BM25 for production
        results = await self.search(query_vector, collection_name, filters, top_k * 2)

        # Apply basic keyword boosting (sparse signal approximation)
        query_terms = set(query_text.lower().split())
        for result in results:
            text = result.get("payload", {}).get("text", "").lower()
            term_hits = sum(1 for term in query_terms if term in text)
            boost = term_hits * 0.05
            result["score"] = min(1.0, result["score"] + boost)

        # Re-sort after boosting
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete_by_document_id(self, document_id: str, collection_name: str) -> None:
        """Delete all vectors associated with a document."""
        client = await self._get_client()
        await client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    )]
                )
            ),
        )
        logger.info("qdrant_deleted", document_id=document_id, collection=collection_name)

    async def get_collection_stats(self, collection_name: str | None = None) -> dict[str, Any]:
        """Get collection statistics for monitoring."""
        name = collection_name or self.collection_name
        client = await self._get_client()
        try:
            info = await client.get_collection(name)
            return {
                "name": name,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception as e:
            return {"error": str(e)}
