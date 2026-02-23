"""
Dependency Injection Container
Provides shared infrastructure instances across routes.
Automatically selects Groq (cloud) or Ollama (local) based on env.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from ..application.config import get_settings, Settings
from ..domain.interfaces import ILLMClient
from ..infrastructure.cv.document_processor import DocumentProcessor
from ..infrastructure.database.mongodb_adapter import MongoDBAdapter
from ..infrastructure.database.postgres_adapter import PostgreSQLAdapter
from ..infrastructure.llm.embedding_model import SentenceTransformerEmbedding
from ..infrastructure.vector_store.qdrant_adapter import QdrantAdapter
from ..infrastructure.cache.progress_publisher import InMemoryProgressPublisher

import asyncpg
import structlog
logger = structlog.get_logger(__name__)

# Singletons
_pg: PostgreSQLAdapter | None = None
_pg_pool: asyncpg.Pool | None = None
_mongo: MongoDBAdapter | None = None
_qdrant: QdrantAdapter | None = None
_llm: ILLMClient | None = None
_embedder: SentenceTransformerEmbedding | None = None
_publisher: InMemoryProgressPublisher | None = None
_doc_processor: DocumentProcessor | None = None


def get_db() -> PostgreSQLAdapter:
    global _pg
    if _pg is None:
        settings = get_settings()
        _pg = PostgreSQLAdapter(settings.database_url)
    return _pg


async def get_pg_pool() -> asyncpg.Pool:
    global _pg_pool
    if _pg_pool is None:
        settings = get_settings()
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pg_pool = await asyncpg.create_pool(dsn)
    return _pg_pool


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
        # Support Qdrant Cloud (URL + API key) or local (host + port)
        qdrant_url = getattr(settings, "qdrant_url", None)
        qdrant_api_key = getattr(settings, "qdrant_api_key", None)
        _qdrant = QdrantAdapter(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection_name,
            embedding_dim=settings.embedding_dimension,
            url=qdrant_url or None,
            api_key=qdrant_api_key or None,
        )
    return _qdrant


def get_llm() -> ILLMClient:
    """
    Build an LLMRouter backed by the admin-configured fallback chain.

    Chain order from settings.llm_fallback_chain (default: groq → ollama → rule_based).
    Each provider has an independent circuit breaker.  "rule_based" is appended
    automatically if not already present — it must always be the final fallback.
    """
    global _llm
    if _llm is None:
        settings = get_settings()
        from ..infrastructure.llm.llm_router import LLMRouter, RuleBasedExtractor

        chain_names: list[str] = list(settings.llm_fallback_chain)
        # Guarantee rule_based is always reachable as the last resort
        if "rule_based" not in chain_names:
            chain_names.append("rule_based")

        providers: list[tuple[str, ILLMClient]] = []
        for name in chain_names:
            try:
                if name == "groq" and settings.groq_api_key:
                    from ..infrastructure.llm.groq_client import GroqClient
                    providers.append(("groq", GroqClient(
                        api_key=settings.groq_api_key,
                        model=settings.groq_model,
                    )))
                    logger.info("llm_chain_provider_added", provider="groq", model=settings.groq_model)

                elif name == "groq" and not settings.groq_api_key:
                    logger.info("llm_chain_provider_skipped", provider="groq", reason="no_api_key")

                elif name == "ollama":
                    from ..infrastructure.llm.ollama_client import OllamaClient
                    providers.append(("ollama", OllamaClient(
                        base_url=settings.ollama_base_url,
                        primary_model=settings.ollama_primary_model,
                    )))
                    logger.info("llm_chain_provider_added", provider="ollama", model=settings.ollama_primary_model)

                elif name == "rule_based":
                    providers.append(("rule_based", RuleBasedExtractor()))
                    logger.info("llm_chain_provider_added", provider="rule_based")

                else:
                    logger.warning("llm_chain_unknown_provider", name=name)

            except Exception as exc:
                logger.error("llm_chain_provider_init_failed", provider=name, error=str(exc))

        if not providers:
            # Absolute safety net — should never happen in a properly configured env
            providers = [("rule_based", RuleBasedExtractor())]
            logger.error("llm_chain_fallback_to_rule_based_only")

        _llm = LLMRouter(
            providers=providers,
            timeout_seconds=settings.llm_provider_timeout_seconds,
            max_failures=settings.llm_max_failures_before_circuit_break,
            recovery_seconds=settings.llm_circuit_break_recovery_seconds,
        )
    return _llm


# Backward-compat alias (agents import get_ollama — we re-route to get_llm)
def get_ollama() -> ILLMClient:
    return get_llm()


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
        vlm = None
        if getattr(settings, "vlm_enabled", False):
            from ..infrastructure.cv.vlm_processor import VLMProcessor
            vlm_url = getattr(settings, "vlm_ollama_base_url", "") or settings.ollama_base_url
            vlm = VLMProcessor(
                ollama_base_url=vlm_url,
                model=getattr(settings, "vlm_model", "qwen2-vl:7b-instruct"),
            )
        _doc_processor = DocumentProcessor(
            temp_dir=settings.temp_upload_dir,
            ocr_lang=getattr(settings, "ocr_language", "eng+ara+hin+chi_sim+jpn+kor+rus"),
            vlm_processor=vlm,
            enable_vlm=getattr(settings, "vlm_enabled", False),
            ocr_dpi=getattr(settings, "ocr_dpi", 300),
        )
    return _doc_processor



# FastAPI dependency type aliases
DBDep = Annotated[PostgreSQLAdapter, Depends(get_db)]
PgPoolDep = Annotated[asyncpg.Pool, Depends(get_pg_pool)]
MongoDep = Annotated[MongoDBAdapter, Depends(get_mongo)]
QdrantDep = Annotated[QdrantAdapter, Depends(get_qdrant)]
LLMDep = Annotated[ILLMClient, Depends(get_llm)]
EmbedderDep = Annotated[SentenceTransformerEmbedding, Depends(get_embedder)]
PublisherDep = Annotated[InMemoryProgressPublisher, Depends(get_publisher)]
DocProcessorDep = Annotated[DocumentProcessor, Depends(get_doc_processor)]
