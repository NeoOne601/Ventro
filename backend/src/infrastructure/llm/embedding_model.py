"""
Sentence Transformer Embedding Model
Produces dense vector embeddings for semantic search in Qdrant.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import structlog
from sentence_transformers import SentenceTransformer

from ...domain.interfaces import IEmbeddingModel

logger = structlog.get_logger(__name__)

_embedding_model_instance: "SentenceTransformerEmbedding | None" = None


class SentenceTransformerEmbedding(IEmbeddingModel):
    """
    Local sentence-transformers embedding model.
    Default: all-MiniLM-L6-v2 (384 dimensions, ~80MB, very fast).
    Upgrade to: BAAI/bge-large-en-v1.5 (1024 dimensions) for production.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        logger.info("embedding_model_loading", model=model_name)

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
            logger.info("embedding_model_loaded", model=self.model_name, dim=self._model.get_sentence_embedding_dimension())
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        loop = asyncio.get_event_loop()
        model = self._get_model()

        def _encode() -> Any:
            return model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)

        embeddings = await loop.run_in_executor(None, _encode)
        return embeddings.tolist()

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query string."""
        results = await self.embed_texts([query])
        return results[0]

    @property
    def dimension(self) -> int:
        return self._get_model().get_sentence_embedding_dimension() or 384


async def get_embedding_model() -> SentenceTransformerEmbedding:
    """Get singleton embedding model instance."""
    global _embedding_model_instance
    if _embedding_model_instance is None:
        from ...application.config import get_settings
        settings = get_settings()
        _embedding_model_instance = SentenceTransformerEmbedding(settings.embedding_model)
    return _embedding_model_instance
