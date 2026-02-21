"""
MAS-VGFR Domain Interfaces
Abstract interfaces for the infrastructure layer (Dependency Inversion Principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .entities import (
    AuditWorkpaper,
    DocumentMetadata,
    DocumentType,
    ParsedDocument,
    ReconciliationSession,
    ReconciliationVerdict,
    SAMRMetrics,
)


class IDocumentRepository(ABC):
    """Abstract repository for document metadata (PostgreSQL)."""

    @abstractmethod
    async def save(self, metadata: DocumentMetadata) -> DocumentMetadata:
        ...

    @abstractmethod
    async def get_by_id(self, document_id: str) -> DocumentMetadata | None:
        ...

    @abstractmethod
    async def list_by_type(self, doc_type: DocumentType, limit: int = 50) -> list[DocumentMetadata]:
        ...

    @abstractmethod
    async def update(self, metadata: DocumentMetadata) -> DocumentMetadata:
        ...


class IDocumentStore(ABC):
    """Abstract store for complex document data (MongoDB)."""

    @abstractmethod
    async def save_parsed_document(self, doc: ParsedDocument) -> str:
        ...

    @abstractmethod
    async def get_parsed_document(self, document_id: str) -> ParsedDocument | None:
        ...

    @abstractmethod
    async def save_workpaper(self, workpaper: AuditWorkpaper) -> str:
        ...

    @abstractmethod
    async def get_workpaper(self, workpaper_id: str) -> AuditWorkpaper | None:
        ...


class IReconciliationRepository(ABC):
    """Abstract repository for reconciliation sessions."""

    @abstractmethod
    async def create_session(self, session: ReconciliationSession) -> ReconciliationSession:
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> ReconciliationSession | None:
        ...

    @abstractmethod
    async def update_session(self, session: ReconciliationSession) -> ReconciliationSession:
        ...

    @abstractmethod
    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[ReconciliationSession]:
        ...

    @abstractmethod
    async def save_samr_metrics(self, metrics: SAMRMetrics) -> None:
        ...

    @abstractmethod
    async def get_samr_metrics(self, session_id: str) -> list[SAMRMetrics]:
        ...


class IVectorStore(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    async def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> list[str]:
        ...

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        collection_name: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        collection_name: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def delete_by_document_id(self, document_id: str, collection_name: str) -> None:
        ...


class IEmbeddingModel(ABC):
    """Abstract interface for embedding generation."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


class ILLMClient(ABC):
    """Abstract interface for LLM interactions."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        ...

    @abstractmethod
    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        ...


class IVisionModel(ABC):
    """Abstract interface for document vision/layout models."""

    @abstractmethod
    async def analyze_document(self, image_paths: list[str]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def classify_document(self, image_path: str) -> tuple[DocumentType, float]:
        ...


class ICacheClient(ABC):
    """Abstract interface for caching."""

    @abstractmethod
    async def get(self, key: str) -> Any:
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...


class IProgressPublisher(ABC):
    """Abstract interface for publishing real-time progress events."""

    @abstractmethod
    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        ...
