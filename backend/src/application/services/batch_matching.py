"""
Batch Matching Service — Smart Triplet Grouper

Given N uploaded documents from a bulk upload, finds optimal PO+GRN+Invoice triplets.

Algorithm:
  Phase 1: Group by exact vendor_name + document_number_prefix (e.g. "ACME-2025")
  Phase 2: For unresolved documents, use embedding cosine similarity to find
           the closest cross-type pair (e.g. best-matching PO for each orphan Invoice)
  Phase 3: Any document that can't be matched is returned in an 'unmatched' list
           for manual linking in the UI

This gives enterprise clients one-click "Run All" for an entire monthly batch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DocumentSlot:
    """A document that has been uploaded and classified."""
    doc_id: str
    doc_type: str        # 'purchase_order' | 'goods_receipt_note' | 'invoice'
    vendor_name: str | None
    doc_number: str | None
    embedding: list[float] | None = None
    filename: str = ""


@dataclass
class MatchedTriplet:
    """A validated PO + GRN + Invoice triplet ready for reconciliation."""
    triplet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    po_id: str = ""
    grn_id: str = ""
    invoice_id: str = ""
    match_method: str = ""    # 'exact' | 'embedding' | 'manual'
    match_score: float = 1.0


@dataclass
class BatchMatchResult:
    """Result of batch matching for one batch upload."""
    batch_id: str
    triplets: list[MatchedTriplet]
    unmatched: list[str]      # doc_ids that couldn't be grouped
    stats: dict[str, Any] = field(default_factory=dict)


def _vendor_key(doc: DocumentSlot) -> str:
    """Normalised group key from vendor + doc number."""
    vendor = (doc.vendor_name or "").strip().lower()[:30]
    # Strip trailing numeric suffix for grouping (INV-2025-001 → INV-2025)
    number = (doc.doc_number or "").strip().upper()
    prefix = "-".join(number.split("-")[:2]) if "-" in number else number[:8]
    return f"{vendor}|{prefix}" if vendor or prefix else ""


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    return float(np.dot(va, vb) / (na * nb)) if na > 0 and nb > 0 else 0.0


class BatchMatchingService:
    """Groups uploaded documents into PO+GRN+Invoice triplets."""

    def match(self, documents: list[DocumentSlot]) -> BatchMatchResult:
        batch_id = str(uuid.uuid4())

        by_type: dict[str, list[DocumentSlot]] = {
            "purchase_order": [],
            "goods_receipt_note": [],
            "invoice": [],
        }
        misc = []
        for doc in documents:
            if doc.doc_type in by_type:
                by_type[doc.doc_type].append(doc)
            else:
                misc.append(doc.doc_id)

        triplets: list[MatchedTriplet] = []
        unmatched_ids: set[str] = set()

        # ── Phase 1: exact match by vendor+doc_number ──────────────────────
        used: set[str] = set()
        groups: dict[str, dict[str, DocumentSlot]] = {}

        for dt, docs in by_type.items():
            for doc in docs:
                key = _vendor_key(doc)
                if key:
                    if key not in groups:
                        groups[key] = {}
                    # Keep first seen of each type
                    if dt not in groups[key]:
                        groups[key][dt] = doc

        for key, slot_map in groups.items():
            if all(t in slot_map for t in ("purchase_order", "goods_receipt_note", "invoice")):
                po = slot_map["purchase_order"]
                grn = slot_map["goods_receipt_note"]
                inv = slot_map["invoice"]
                triplets.append(MatchedTriplet(
                    po_id=po.doc_id, grn_id=grn.doc_id, invoice_id=inv.doc_id,
                    match_method="exact", match_score=1.0,
                ))
                used |= {po.doc_id, grn.doc_id, inv.doc_id}

        # ── Phase 2: embedding similarity for unmatched docs ──────────────
        remaining = {
            dt: [d for d in docs if d.doc_id not in used]
            for dt, docs in by_type.items()
        }

        has_embeddings = all(
            any(d.embedding for d in remaining[t])
            for t in ("purchase_order", "goods_receipt_note", "invoice")
            if remaining[t]
        )

        if has_embeddings:
            pos = [d for d in remaining["purchase_order"] if d.embedding]
            grns = [d for d in remaining["goods_receipt_note"] if d.embedding]
            invs = [d for d in remaining["invoice"] if d.embedding]

            # Greedy matching: for each PO, find best GRN + best Invoice
            available_grns = list(grns)
            available_invs = list(invs)

            for po in pos:
                if not available_grns or not available_invs:
                    break

                best_grn = max(available_grns, key=lambda g: _cosine(po.embedding, g.embedding))  # type: ignore[arg-type]
                best_inv = max(available_invs, key=lambda i: _cosine(po.embedding, i.embedding))  # type: ignore[arg-type]

                score = (_cosine(po.embedding, best_grn.embedding) +  # type: ignore[arg-type]
                         _cosine(po.embedding, best_inv.embedding)) / 2  # type: ignore[arg-type]

                if score >= 0.75:
                    triplets.append(MatchedTriplet(
                        po_id=po.doc_id, grn_id=best_grn.doc_id, invoice_id=best_inv.doc_id,
                        match_method="embedding", match_score=round(score, 4),
                    ))
                    available_grns.remove(best_grn)
                    available_invs.remove(best_inv)

        # ── Phase 3: collect unmatched ─────────────────────────────────────
        matched_ids = {id_ for t in triplets for id_ in [t.po_id, t.grn_id, t.invoice_id]}
        for dt, docs in by_type.items():
            for d in docs:
                if d.doc_id not in matched_ids:
                    unmatched_ids.add(d.doc_id)
        unmatched_ids |= set(misc)

        logger.info(
            "batch_matching_complete",
            batch_id=batch_id,
            triplets=len(triplets),
            unmatched=len(unmatched_ids),
        )

        return BatchMatchResult(
            batch_id=batch_id,
            triplets=triplets,
            unmatched=list(unmatched_ids),
            stats={
                "total_documents": len(documents),
                "exact_matches": sum(1 for t in triplets if t.match_method == "exact"),
                "embedding_matches": sum(1 for t in triplets if t.match_method == "embedding"),
                "unmatched_count": len(unmatched_ids),
            },
        )
