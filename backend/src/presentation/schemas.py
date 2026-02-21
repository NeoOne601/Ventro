"""
Pydantic API Schemas for Request/Response validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class BBoxSchema(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    document_type: str
    total_pages: int
    classification_confidence: float
    message: str


class DocumentInfoResponse(BaseModel):
    id: str
    filename: str
    document_type: str
    total_pages: int
    file_size_bytes: int
    uploaded_at: datetime
    vendor_name: Optional[str] = None
    document_number: Optional[str] = None
    classification_confidence: float


class CreateSessionRequest(BaseModel):
    po_document_id: str = Field(..., description="Document ID of the Purchase Order")
    grn_document_id: str = Field(..., description="Document ID of the Goods Receipt Note")
    invoice_document_id: str = Field(..., description="Document ID of the Invoice")


class SessionResponse(BaseModel):
    id: str
    po_document_id: str
    grn_document_id: str
    invoice_document_id: str
    status: str
    created_at: datetime


class ReconciliationResultResponse(BaseModel):
    session_id: str
    status: str
    verdict: Optional[dict[str, Any]] = None
    workpaper: Optional[dict[str, Any]] = None
    samr_metrics: Optional[dict[str, Any]] = None
    agent_trace: list[dict[str, Any]] = []
    completed_at: Optional[datetime] = None
    errors: list[str] = []


class AnalyticsResponse(BaseModel):
    total_sessions: int
    matched_sessions: int
    discrepancy_sessions: int
    samr_alerts: int
    avg_processing_time_seconds: float
    hallucination_rate: float
    sessions: list[dict[str, Any]] = []


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]
    timestamp: datetime
