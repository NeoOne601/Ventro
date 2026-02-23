"""
MAS-VGFR Domain Entities
Core domain objects with no framework dependencies.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DocumentType(str, Enum):
    PURCHASE_ORDER = "purchase_order"
    GOODS_RECEIPT_NOTE = "goods_receipt_note"
    INVOICE = "invoice"
    UNKNOWN = "unknown"


class ReconciliationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    MATCHED = "matched"
    DISCREPANCY_FOUND = "discrepancy_found"
    EXCEPTION = "exception"
    SAMR_ALERT = "samr_alert"
    COMPLETED = "completed"
    FAILED = "failed"


class MatchStatus(str, Enum):
    FULL_MATCH = "full_match"
    PARTIAL_MATCH = "partial_match"
    MISMATCH = "mismatch"
    MISSING = "missing"


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    REQUIRES_REVIEW = "requires_review"


@dataclass(frozen=True)
class BoundingBox:
    """Pixel-precise spatial coordinates for visual grounding."""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def to_dict(self) -> dict[str, float | int]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1, "page": self.page}

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def from_list(cls, coords: list[float], page: int = 0) -> "BoundingBox":
        return cls(x0=coords[0], y0=coords[1], x1=coords[2], y1=coords[3], page=page)


@dataclass(frozen=True)
class MonetaryAmount:
    """Value object for monetary values with currency."""
    amount: float
    currency: str = "USD"

    def __add__(self, other: "MonetaryAmount") -> "MonetaryAmount":
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return MonetaryAmount(self.amount + other.amount, self.currency)

    def __sub__(self, other: "MonetaryAmount") -> "MonetaryAmount":
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return MonetaryAmount(self.amount - other.amount, self.currency)

    def is_within_tolerance(self, other: "MonetaryAmount", tolerance: float = 0.01) -> bool:
        return abs(self.amount - other.amount) <= tolerance

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:.2f}"


@dataclass
class TextFragment:
    """A piece of text with its spatial location."""
    text: str
    bbox: BoundingBox
    confidence: float = 1.0
    font_size: float | None = None
    is_bold: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextFragment":
        return cls(
            text=data["text"],
            bbox=BoundingBox(**data["bbox"]),
            confidence=data.get("confidence", 1.0),
            font_size=data.get("font_size"),
            is_bold=data.get("is_bold", False),
        )


@dataclass
class LineItem:
    """A single line item extracted from a financial document."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    quantity: float = 0.0
    unit_price: MonetaryAmount = field(default_factory=lambda: MonetaryAmount(0.0))
    total_amount: MonetaryAmount = field(default_factory=lambda: MonetaryAmount(0.0))
    unit_of_measure: str = ""
    part_number: str | None = None
    bbox: BoundingBox | None = None
    row_index: int = 0
    raw_text: str = ""
    confidence: float = 1.0

    def computed_total(self) -> MonetaryAmount:
        """Recompute total from quantity * unit_price."""
        return MonetaryAmount(
            round(self.quantity * self.unit_price.amount, 2),
            self.unit_price.currency,
        )

    def has_total_discrepancy(self, tolerance: float = 0.01) -> bool:
        return not self.total_amount.is_within_tolerance(self.computed_total(), tolerance)


@dataclass
class DocumentMetadata:
    """Metadata for a processed financial document."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    document_type: DocumentType = DocumentType.UNKNOWN
    total_pages: int = 0
    file_size_bytes: int = 0
    mime_type: str = ""
    uploaded_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: datetime | None = None
    vendor_name: str | None = None
    document_number: str | None = None
    document_date: str | None = None
    currency: str = "USD"
    classification_confidence: float = 0.0


@dataclass
class ParsedDocument:
    """A fully parsed and spatially-aware financial document."""
    metadata: DocumentMetadata
    line_items: list[LineItem] = field(default_factory=list)
    text_fragments: list[TextFragment] = field(default_factory=list)
    raw_text_by_page: dict[int, str] = field(default_factory=dict)
    subtotal: MonetaryAmount | None = None
    tax_amount: MonetaryAmount | None = None
    total_amount: MonetaryAmount | None = None
    additional_fields: dict[str, Any] = field(default_factory=dict)
    vector_ids: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.metadata.id


@dataclass
class LineItemMatch:
    """Result of matching a single line item across documents."""
    po_item: LineItem | None
    grn_item: LineItem | None
    invoice_item: LineItem | None
    status: MatchStatus = MatchStatus.MISSING
    quantity_variance: float = 0.0
    price_variance: MonetaryAmount = field(default_factory=lambda: MonetaryAmount(0.0))
    similarity_score: float = 0.0
    resolution_notes: str = ""


@dataclass
class QuantitativeValidation:
    """Mathematical validation results."""
    po_total: MonetaryAmount
    grn_total: MonetaryAmount
    invoice_total: MonetaryAmount
    computed_invoice_total: MonetaryAmount
    tax_validated: bool
    subtotal_validated: bool
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    is_mathematically_consistent: bool = True
    validation_details: str = ""


@dataclass
class ComplianceCheck:
    """Compliance validation results."""
    status: ComplianceStatus
    flags: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    notes: str = ""


@dataclass
class SAMRMetrics:
    """Shadow Agent Memory Reconciliation metrics."""
    session_id: str
    primary_stream_conclusion: str
    shadow_stream_conclusion: str
    cosine_similarity_score: float
    divergence_threshold: float
    alert_triggered: bool
    perturbation_applied: str
    reasoning_vectors_diverged: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_suspicious(self) -> bool:
        return self.cosine_similarity_score >= self.divergence_threshold and not self.reasoning_vectors_diverged


@dataclass
class ReconciliationVerdict:
    """Final verdict of the three-way match reconciliation."""
    session_id: str
    po_document_id: str
    grn_document_id: str
    invoice_document_id: str
    status: ReconciliationStatus
    line_item_matches: list[LineItemMatch] = field(default_factory=list)
    quantitative_validation: QuantitativeValidation | None = None
    compliance_check: ComplianceCheck | None = None
    samr_metrics: SAMRMetrics | None = None
    overall_confidence: float = 0.0
    discrepancy_summary: list[str] = field(default_factory=list)
    recommendation: str = ""
    classification_errors: list[str] = field(default_factory=list)
    completed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Citation:
    """An interactive citation linking text to its source location."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    document_id: str = ""
    document_type: DocumentType = DocumentType.UNKNOWN
    page: int = 0
    bbox: BoundingBox | None = None
    value: str = ""


@dataclass
class WorkpaperSection:
    """A section of the automated audit workpaper."""
    title: str
    content: str
    citations: list[Citation] = field(default_factory=list)
    order: int = 0


@dataclass
class AuditWorkpaper:
    """Complete automated audit workpaper."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    title: str = "Three-Way Match Audit Workpaper"
    generated_at: datetime = field(default_factory=datetime.utcnow)
    sections: list[WorkpaperSection] = field(default_factory=list)
    verdict_summary: str = ""
    materiality_analysis: str = ""
    evidence_map: dict[str, list[Citation]] = field(default_factory=dict)
    html_content: str = ""


@dataclass
class ReconciliationSession:
    """A complete reconciliation session."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    po_document_id: str = ""
    grn_document_id: str = ""
    invoice_document_id: str = ""
    status: ReconciliationStatus = ReconciliationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    verdict: ReconciliationVerdict | None = None
    workpaper: AuditWorkpaper | None = None
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    created_by: str = "system"
