"""
Dependency Injection Container
Provides shared infrastructure instances across routes.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, AsyncGenerator

from fastapi import Depends

from ..application.config import get_settings, Settings
from ..infrastructure.cv.document_processor import DocumentProcessor
from ..infrastructure.database.mongodb_adapter import MongoDBAdapter
from ..infrastructure.database.postgres_adapter import PostgreSQLAdapter
from ..infrastructure.llm.embedding_model import SentenceTransformerEmbedding
from ..infrastructure.llm.ollama_client import OllamaClient
from ..infrastructure.vector_store.qdrant_adapter import QdrantAdapter
from ..infrastructure.cache.progress_publisher import InMemoryProgressPublisher

# Singletons
_pg: PostgreSQLAdapter | None = None
_mongo: MongoDBAdapter | None = None
_qdrant: QdrantAdapter | None = None
_ollama: OllamaClient | None = None
_embedder: SentenceTransformerEmbedding | None = None
_publisher: InMemoryProgressPublisher | None = None
_doc_processor: DocumentProcessor | None = None


def get_db() -> PostgreSQLAdapter:
    global _pg
    if _pg is None:
        settings = get_settings()
        _pg = PostgreSQLAdapter(settings.database_url)
    return _pg


def get_mongo() -> MongoDBAdapter:
    global _mongo
    if _mongo is None:
        settings = get_settings()
        _mongo = MongoDBAdapter(settings.mongo_url, settings.mongo_db)
    return _mongo


def get_qdrant() -> QdrantAdapter:
    global _qdrant
    if _qdrant is None:
        settings = get_settings()
        _qdrant = QdrantAdapter(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection_name,
            embedding_dim=settings.embedding_dimension,
        )
    return _qdrant


def get_ollama() -> OllamaClient:
    global _ollama
    if _ollama is None:
        settings = get_settings()
        _ollama = OllamaClient(
            base_url=settings.ollama_base_url,
            primary_model=settings.ollama_primary_model,
        )
    return _ollama


def get_embedder() -> SentenceTransformerEmbedding:
    global _embedder
    if _embedder is None:
        settings = get_settings()
        _embedder = SentenceTransformerEmbedding(settings.embedding_model)
    return _embedder


def get_publisher() -> InMemoryProgressPublisher:
    global _publisher
    if _publisher is None:
        _publisher = InMemoryProgressPublisher()
    return _publisher


def get_doc_processor() -> DocumentProcessor:
    global _doc_processor
    if _doc_processor is None:
        settings = get_settings()
        _doc_processor = DocumentProcessor(temp_dir=settings.temp_upload_dir)
    return _doc_processor


# FastAPI dependency type aliases
DBDep = Annotated[PostgreSQLAdapter, Depends(get_db)]
MongoDep = Annotated[MongoDBAdapter, Depends(get_mongo)]
QdrantDep = Annotated[QdrantAdapter, Depends(get_qdrant)]
OllamaDep = Annotated[OllamaClient, Depends(get_ollama)]
EmbedderDep = Annotated[SentenceTransformerEmbedding, Depends(get_embedder)]
PublisherDep = Annotated[InMemoryProgressPublisher, Depends(get_publisher)]
DocProcessorDep = Annotated[DocumentProcessor, Depends(get_doc_processor)]
