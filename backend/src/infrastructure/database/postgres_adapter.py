"""
SQLAlchemy ORM Models and PostgreSQL Adapter
For audit logs, reconciliation sessions, SAMR metrics.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, Boolean
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from ...domain.entities import (
    DocumentMetadata,
    DocumentType,
    ReconciliationSession,
    ReconciliationStatus,
    SAMRMetrics,
)
from ...domain.interfaces import IDocumentRepository, IReconciliationRepository

logger = structlog.get_logger(__name__)

Base = declarative_base()


class DocumentMetadataORM(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    document_type = Column(String, nullable=False)
    total_pages = Column(Integer, default=0)
    file_size_bytes = Column(Integer, default=0)
    mime_type = Column(String, default="application/pdf")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    vendor_name = Column(String, nullable=True)
    document_number = Column(String, nullable=True)
    document_date = Column(String, nullable=True)
    currency = Column(String, default="USD")
    classification_confidence = Column(Float, default=0.0)


class ReconciliationSessionORM(Base):
    __tablename__ = "reconciliation_sessions"

    id = Column(String, primary_key=True)
    po_document_id = Column(String, nullable=False)
    grn_document_id = Column(String, nullable=False)
    invoice_document_id = Column(String, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    verdict_json = Column(JSON, nullable=True)
    agent_trace_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String, default="system")
    organisation_id = Column(String, nullable=True, index=True)


class SAMRMetricsORM(Base):
    __tablename__ = "samr_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    primary_stream_conclusion = Column(Text)
    shadow_stream_conclusion = Column(Text)
    cosine_similarity_score = Column(Float)
    divergence_threshold = Column(Float)
    alert_triggered = Column(Boolean, default=False)
    perturbation_applied = Column(Text)
    reasoning_vectors_diverged = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class PostgreSQLAdapter(IDocumentRepository, IReconciliationRepository):
    """
    Async PostgreSQL adapter via SQLAlchemy 2.0 with asyncpg driver.
    Implements both IDocumentRepository and IReconciliationRepository.
    """

    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url, echo=False, pool_size=10, max_overflow=20)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def init_db(self) -> None:
        """Create all tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("postgresql_tables_created")

    def _orm_to_metadata(self, orm: DocumentMetadataORM) -> DocumentMetadata:
        return DocumentMetadata(
            id=orm.id,
            filename=orm.filename,
            document_type=DocumentType(orm.document_type),
            total_pages=orm.total_pages,
            file_size_bytes=orm.file_size_bytes,
            mime_type=orm.mime_type,
            uploaded_at=orm.uploaded_at,
            processed_at=orm.processed_at,
            vendor_name=orm.vendor_name,
            document_number=orm.document_number,
            document_date=orm.document_date,
            currency=orm.currency,
            classification_confidence=orm.classification_confidence,
        )

    def _orm_to_session(self, orm: ReconciliationSessionORM) -> ReconciliationSession:
        session = ReconciliationSession(
            id=orm.id,
            po_document_id=orm.po_document_id,
            grn_document_id=orm.grn_document_id,
            invoice_document_id=orm.invoice_document_id,
            status=ReconciliationStatus(orm.status),
            created_at=orm.created_at,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
            error_message=orm.error_message,
            created_by=orm.created_by,
            organisation_id=orm.organisation_id,
        )
        if getattr(orm, 'verdict_json', None):
            try:
                from src.domain.entities import ReconciliationVerdict
                v = ReconciliationVerdict(
                    session_id=session.id,
                    po_document_id=session.po_document_id,
                    grn_document_id=session.grn_document_id,
                    invoice_document_id=session.invoice_document_id,
                    status=session.status
                )
                v.__dict__.update(orm.verdict_json)
                session.verdict = v
            except Exception:
                pass
        
        if getattr(orm, 'agent_trace_json', None):
            session.agent_trace = orm.agent_trace_json

        return session

    # ---- IDocumentRepository ----

    async def save(self, metadata: DocumentMetadata) -> DocumentMetadata:
        async with self.async_session() as session:
            orm = DocumentMetadataORM(
                id=metadata.id,
                filename=metadata.filename,
                document_type=metadata.document_type.value,
                total_pages=metadata.total_pages,
                file_size_bytes=metadata.file_size_bytes,
                mime_type=metadata.mime_type,
                uploaded_at=metadata.uploaded_at,
                processed_at=metadata.processed_at,
                vendor_name=metadata.vendor_name,
                document_number=metadata.document_number,
                document_date=metadata.document_date,
                currency=metadata.currency,
                classification_confidence=metadata.classification_confidence,
            )
            session.add(orm)
            await session.commit()
            return metadata

    async def get_by_id(self, document_id: str) -> DocumentMetadata | None:
        async with self.async_session() as session:
            result = await session.execute(
                select(DocumentMetadataORM).where(DocumentMetadataORM.id == document_id)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_metadata(orm) if orm else None

    async def list_by_type(self, doc_type: DocumentType, limit: int = 50) -> list[DocumentMetadata]:
        async with self.async_session() as session:
            result = await session.execute(
                select(DocumentMetadataORM)
                .where(DocumentMetadataORM.document_type == doc_type.value)
                .limit(limit)
            )
            return [self._orm_to_metadata(row) for row in result.scalars()]

    async def update(self, metadata: DocumentMetadata) -> DocumentMetadata:
        async with self.async_session() as session:
            result = await session.execute(
                select(DocumentMetadataORM).where(DocumentMetadataORM.id == metadata.id)
            )
            orm = result.scalar_one_or_none()
            if orm:
                orm.document_type = metadata.document_type.value
                orm.processed_at = metadata.processed_at
                orm.vendor_name = metadata.vendor_name
                orm.document_number = metadata.document_number
                orm.classification_confidence = metadata.classification_confidence
                await session.commit()
        return metadata

    # ---- IReconciliationRepository ----

    async def create_session(self, session: ReconciliationSession) -> ReconciliationSession:
        async with self.async_session() as db:
            orm = ReconciliationSessionORM(
                id=session.id,
                po_document_id=session.po_document_id,
                grn_document_id=session.grn_document_id,
                invoice_document_id=session.invoice_document_id,
                status=session.status.value,
                created_at=session.created_at,
                created_by=session.created_by,
                organisation_id=session.organisation_id,
            )
            db.add(orm)
            await db.commit()
        return session

    async def get_session(self, session_id: str) -> ReconciliationSession | None:
        async with self.async_session() as db:
            result = await db.execute(
                select(ReconciliationSessionORM).where(ReconciliationSessionORM.id == session_id)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_session(orm) if orm else None

    async def update_session(self, session: ReconciliationSession) -> ReconciliationSession:
        async with self.async_session() as db:
            result = await db.execute(
                select(ReconciliationSessionORM).where(ReconciliationSessionORM.id == session.id)
            )
            orm = result.scalar_one_or_none()
            if orm:
                orm.status = session.status.value
                orm.started_at = session.started_at
                orm.completed_at = session.completed_at
                orm.error_message = session.error_message
                if session.verdict:
                    orm.verdict_json = json.loads(json.dumps(session.verdict.__dict__, default=str))
                if session.agent_trace:
                    orm.agent_trace_json = session.agent_trace
                await db.commit()
        return session

    async def list_sessions(self, limit: int = 50, offset: int = 0, org_id: str | None = None) -> list[ReconciliationSession]:
        async with self.async_session() as db:
            query = select(ReconciliationSessionORM)
            if org_id:
                query = query.where(ReconciliationSessionORM.organisation_id == org_id)
            
            result = await db.execute(
                query.order_by(ReconciliationSessionORM.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._orm_to_session(row) for row in result.scalars()]

    async def save_samr_metrics(self, metrics: SAMRMetrics) -> None:
        async with self.async_session() as db:
            orm = SAMRMetricsORM(
                session_id=metrics.session_id,
                primary_stream_conclusion=metrics.primary_stream_conclusion,
                shadow_stream_conclusion=metrics.shadow_stream_conclusion,
                cosine_similarity_score=metrics.cosine_similarity_score,
                divergence_threshold=metrics.divergence_threshold,
                alert_triggered=metrics.alert_triggered,
                perturbation_applied=metrics.perturbation_applied,
                reasoning_vectors_diverged=metrics.reasoning_vectors_diverged,
                timestamp=metrics.timestamp,
            )
            db.add(orm)
            await db.commit()

    async def get_samr_metrics(self, session_id: str) -> list[SAMRMetrics]:
        async with self.async_session() as db:
            result = await db.execute(
                select(SAMRMetricsORM).where(SAMRMetricsORM.session_id == session_id)
            )
            return [
                SAMRMetrics(
                    session_id=row.session_id,
                    primary_stream_conclusion=row.primary_stream_conclusion or "",
                    shadow_stream_conclusion=row.shadow_stream_conclusion or "",
                    cosine_similarity_score=row.cosine_similarity_score or 0.0,
                    divergence_threshold=row.divergence_threshold or 0.85,
                    alert_triggered=row.alert_triggered or False,
                    perturbation_applied=row.perturbation_applied or "",
                    reasoning_vectors_diverged=row.reasoning_vectors_diverged or True,
                    timestamp=row.timestamp or datetime.utcnow(),
                )
                for row in result.scalars()
            ]
