# Ventro — System Journal
### Granular Architecture Reference: Problem → Objective → Task → Action → Result

*Version 1.0 · February 2026*

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Objectives](#2-objectives)
3. [High-Level Design (HLD)](#3-high-level-design)
   - 3.1 System Topology
   - 3.2 Component Responsibility Map
   - 3.3 Data Flow Overview
4. [Low-Level Design (LLD)](#4-low-level-design)
   - 4.1 Domain Layer
   - 4.2 Agent Pipeline Deep Dive
   - 4.3 CV & Embedding Pipeline
   - 4.4 Vector Store Strategy
   - 4.5 SAMR™ Mechanism
   - 4.6 Database Schema
   - 4.7 API Contract Detail
   - 4.8 WebSocket Event Protocol
   - 4.9 Frontend State Machine
5. [OTAR Framework](#5-otar-framework)
   - Objective → Task → Action → Result for every agent
6. [Failure Modes & Mitigations](#6-failure-modes--mitigations)
7. [Performance Characteristics](#7-performance-characteristics)
8. [Security Model](#8-security-model)

---

## 1. Problem Statement

### 1.1 The Core Pain

Financial auditors spend 60–80% of their time on **three-way match** — the process of cross-referencing three documents to verify a vendor payment is legitimate:

| Document | Owner | Contains |
|----------|-------|---------|
| **Purchase Order (PO)** | Buyer (internal) | What was ordered, at what agreed price |
| **Goods Receipt Note (GRN)** | Warehouse/Logistics | What was actually delivered |
| **Supplier Invoice** | Vendor (external) | What the vendor is billing for |

A payment should only be approved when all three align. In practice they almost never align perfectly:

- Vendor invoices for 10 units; only 8 were delivered (GRN shows 8)
- Vendor raises price by 3% above PO rate
- Item descriptions differ: PO says "Bolt M6 stainless", Invoice says "SS Fastener 6mm"
- GST/VAT line items don't add up correctly
- Duplicate invoices are re-submitted days apart with different invoice numbers

### 1.2 Why Existing Solutions Fail

| Approach | Failure Mode |
|----------|-------------|
| Manual auditor review | Slow (hours per PO set), error-prone, doesn't scale |
| Rule-based RPA (UiPath, Blue Prism) | Breaks on any layout variation; zero semantic understanding |
| Naive LLM prompting | **Hallucination** — LLMs confidently state wrong totals; no ground truth linking |
| OCR + regex | Cannot match "Bolt M6 stainless" to "SS Fastener 6mm"; no fuzzy entity resolution |

### 1.3 The Hallucination Problem (Critical)

When you ask an LLM "does the invoice total match the PO?", it may produce a plausible answer without actually comparing the numbers — a phenomenon called **confabulation**. In financial auditing, a hallucinated "MATCH" verdict authorising a fraudulent payment is a severe risk.

**No existing commercial product has a formally specified hallucination detection mechanism for financial document comparison.** This is the core differentiator Ventro addresses with SAMR™.

---

## 2. Objectives

| ID | Objective | Success Criterion |
|----|-----------|------------------|
| O-01 | Automate three-way match to < 2 minutes per document set | P95 processing time ≤ 120s |
| O-02 | Achieve zero hallucination in final match verdicts | SAMR cosine similarity threshold ≥ 0.85 |
| O-03 | Preserve pixel-level evidence traceability | Every finding linked to a bounding box in the source PDF |
| O-04 | Handle layout variation across vendors | Fuzzy match score ≥ 0.80 for equivalent items |
| O-05 | Run entirely on-premise | Zero data sent to external APIs |
| O-06 | Produce auditor-grade workpapers automatically | Workpaper passes internal review without manual editing |
| O-07 | Detect financial discrepancies to 2 decimal places | Decimal arithmetic with no float rounding errors |

---

## 3. High-Level Design

### 3.1 System Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT ZONE (Browser)                              │
│                                                                             │
│  React SPA (Vite + TypeScript)                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────────┐  │
│  │Dashboard │ │  Upload  │ │Reconciliation│ │ Sessions │ │  Analytics  │  │
│  │          │ │DropZone  │ │  + WS Feed   │ │  Table   │ │ Recharts    │  │
│  └──────────┘ └──────────┘ └──────────────┘ └──────────┘ └─────────────┘  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTPS / WSS
┌────────────────────────────────▼────────────────────────────────────────────┐
│                        PRESENTATION LAYER (FastAPI)                          │
│                                                                             │
│  /api/v1/documents/upload    ─────────────► CV Pipeline                    │
│  /api/v1/reconciliation/sessions  ────────► Session Manager                │
│  /api/v1/reconciliation/sessions/{id}/run ► LangGraph Orchestrator         │
│  /ws/reconciliation/{session_id}  ────────► InMemoryProgressPublisher      │
│  /api/v1/analytics/metrics   ─────────────► PostgreSQL read                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────────┐
│                    APPLICATION LAYER (LangGraph State Machine)               │
│                                                                             │
│   ┌────────────┐                                                            │
│   │ Supervisor │  Decides which agent runs next based on AgentState         │
│   └─────┬──────┘                                                           │
│         │ routes to                                                         │
│    ┌────▼───────────────────────────────────────────────────────────┐      │
│    │ Extraction → Quantitative → Compliance → SAMR → Reconciliation │      │
│    │                                               → Drafting       │      │
│    └────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
┌────────────────┬───────────────┼──────────────────┬────────────────────────┐
│                │               │                  │                        │
│   ┌────────────▼──┐  ┌─────────▼───────┐  ┌──────▼──────────┐            │
│   │   Ollama LLM  │  │  Qdrant VectorDB│  │  PostgreSQL     │            │
│   │  Mistral-7B   │  │  (dense search) │  │  (sessions,     │            │
│   │  port 11434   │  │  port 6333      │  │   SAMR metrics) │            │
│   └───────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                            │
│   ┌───────────────┐  ┌─────────────────┐                                  │
│   │   MongoDB     │  │   Redis         │                                   │
│   │  (parsed docs │  │  (WS pub/sub,   │                                   │
│   │   workpapers) │  │   task queue)   │                                   │
│   └───────────────┘  └─────────────────┘                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibility Map

| Component | Responsibility | Owns |
|-----------|---------------|------|
| **FastAPI** | API gateway, request validation, background task dispatch | HTTP routing, auth middleware |
| **LangGraph Orchestrator** | State machine — decides agent order and passes state | `AgentState` TypedDict |
| **Extraction Agent** | Pull relevant text chunks from Qdrant with spatial context | RAG logic, cross-encoder reranking |
| **Quantitative Agent** | Re-compute every number from raw extracted values | `Decimal` arithmetic, discrepancy flags |
| **Compliance Agent** | Evaluate business rules (duplicate check, tax validation) | Rule registry, risk scoring |
| **SAMR Agent** | Detect reasoning divergence between primary & shadow streams | Dual LLM calls, cosine similarity |
| **Reconciliation Agent** | Final three-way entity matching and verdict synthesis | `rapidfuzz`, match matrix |
| **Drafting Agent** | Generate interactive HTML workpaper | Narrative generation, citation rendering |
| **DocumentProcessor** | Parse PDFs → bounding boxes + tables + text | PyMuPDF, table finder |
| **QdrantAdapter** | Store and retrieve embedding vectors with metadata | Collection management, HNSW index |
| **OllamaClient** | Inference endpoint for Mistral-7B | HTTP calls, retry, JSON extraction |
| **PostgreSQL** | Durable audit trail for sessions and SAMR metrics | ACID transactions |
| **MongoDB** | Document-oriented store for parsed docs and workpapers | Schemaless JSON storage |

### 3.3 Data Flow Overview

```
PDF Upload
    │
    ▼
DocumentProcessor.process_pdf()
    ├── PyMuPDF extracts text blocks + bounding boxes (normalized 0-1 coords)
    ├── Table finder extracts structured rows → LineItem domain objects
    ├── Keyword classifier assigns DocumentType (PO | GRN | Invoice)
    └── chunk_document_for_embedding() → N chunks with spatial metadata
            │
            ▼
    SentenceTransformer.embed_texts(chunks)  →  384-dim dense vectors
            │
            ▼
    QdrantAdapter.upsert_chunks()  →  Indexed in Qdrant collection
            │
    DocumentMetadata → PostgreSQL
    ParsedDocument   → MongoDB
            │
    ◄───────────────────────── Upload complete, return document_id
            
[User creates session: po_id + grn_id + invoice_id]
            │
            ▼
    POST /reconciliation/sessions/{id}/run
            │
            ▼  (BackgroundTask)
    LangGraphOrchestrator.run_reconciliation(session)
            │
     ┌──────▼──────────────────────────────────────┐
     │          LangGraph State Machine             │
     │                                              │
     │  State: AgentState dict (shared memory)      │
     │                                              │
     │  supervisor → extraction → supervisor        │
     │            → quantitative → supervisor       │
     │            → compliance → supervisor         │
     │            → samr → supervisor               │
     │            → reconciliation → supervisor     │
     │            → drafting → END                 │
     └──────────────────────────────────────────────┘
            │
            ▼
    AuditWorkpaper (HTML) → MongoDB
    ReconciliationSession (verdict) → PostgreSQL
    WebSocket events stream → React frontend
```

---

## 4. Low-Level Design

### 4.1 Domain Layer

The domain layer has **zero imports from infrastructure or frameworks**. It defines pure Python dataclasses.

#### Core Entities

```python
# Value Objects (immutable, equality by value)
@dataclass(frozen=True)
class BoundingBox:
    x0: float   # normalized [0.0, 1.0] from left edge
    y0: float   # normalized [0.0, 1.0] from top edge  
    x1: float   # normalized right edge
    y1: float   # normalized bottom edge
    page: int   # 0-indexed page number

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1,
                "y1": self.y1, "page": self.page}

@dataclass(frozen=True)
class MonetaryAmount:
    amount: Decimal    # ALWAYS Decimal — never float
    currency: str = "USD"
```

#### Aggregate Root: ReconciliationSession
```
ReconciliationSession
├── id: UUID
├── po_document_id: str
├── grn_document_id: str
├── invoice_document_id: str
├── status: ReconciliationStatus (enum)
│   ├── PENDING | PROCESSING | COMPLETED
│   ├── MATCHED | DISCREPANCY_FOUND
│   ├── SAMR_ALERT | EXCEPTION | FAILED
├── verdict: ReconciliationVerdict | None
│   ├── overall_status: str
│   ├── confidence: float
│   ├── line_item_matches: list[dict]
│   ├── discrepancy_summary: list[str]
│   └── recommendation: str
├── agent_trace: list[dict]   ← complete audit log of every agent step
└── created_at / started_at / completed_at: datetime
```

#### Abstract Interfaces (Dependency Inversion)
Every infrastructure dependency is abstracted:

```python
class ILLMClient(ABC):
    async def complete(self, prompt, temperature, max_tokens) -> str: ...
    async def get_reasoning_vector(self, prompt) -> list[float]: ...

class IVectorStore(ABC):
    async def search(self, query_vector, collection_name, filters, top_k) -> list[dict]: ...
    async def upsert_chunks(self, chunks, collection_name) -> list[str]: ...

class IProgressPublisher(ABC):
    async def publish(self, session_id, event: dict) -> None: ...
```

This means: swapping Ollama for OpenAI, or Qdrant for Pinecone, requires **only** a new class implementing the interface — zero changes to agents.

---

### 4.2 Agent Pipeline Deep Dive

#### AgentState — the shared memory bus

```python
class AgentState(TypedDict):
    session_id: str
    po_document_id: str
    grn_document_id: str
    invoice_document_id: str

    # Populated by Extraction Agent
    extracted_data: dict          # {po: {...}, grn: {...}, invoice: {...}}
    extracted_citations: list     # [{doc_id, bbox, text, value}, ...]

    # Populated by Quantitative Agent
    quantitative_report: dict     # {discrepancies: [...], total_discrepancies: N}

    # Populated by Compliance Agent
    compliance_report: dict       # {compliance_status, risk_score, flags, violations}

    # Populated by SAMR Agent
    samr_metrics: dict            # {cosine_similarity_score, alert_triggered, ...}
    samr_alert_triggered: bool

    # Populated by Reconciliation Agent
    reconciliation_verdict: dict  # {overall_status, confidence, line_item_matches}

    # Populated by Drafting Agent
    workpaper: dict               # {html_content, narrative, citations}

    # Orchestration metadata
    current_agent: str
    agent_trace: list[dict]
    errors: list[str]
    next_action: str              # "extraction" | "quantitative" | ... | "end"
```

All agents READ from this dict and WRITE their output back. LangGraph handles the state transitions.

---

#### Extraction Agent — Internal Flow

```
Input:  AgentState with document IDs
Output: extracted_data (structured JSON) + extracted_citations (bboxes)

Step 1: For each document (PO, GRN, Invoice):
        ├── Embed a targeted query string
        │   e.g. "vendor name invoice number line items total amount"
        ├── QdrantAdapter.hybrid_search(query_vector, filters={"document_id": id})
        │   └── Returns top-10 chunks ranked by cosine similarity
        │       + keyword boost for query term overlap
        ├── CrossEncoder.predict([(query, chunk_text) for chunk in results])
        │   └── Re-ranks top-10 → top-5 by semantic relevance
        └── Concatenate top-5 chunks as "context"

Step 2: Build extraction prompt:
        "Given this context from a {doc_type}, extract:
         vendor_name, document_number, document_date,
         currency, line_items (description, qty, unit_price, total),
         subtotal, tax, grand_total.
         Return JSON only."

Step 3: LLM.complete(prompt, json_mode=True)
        └── OllamaClient._extract_json(response)
            └── Strips markdown fences, finds JSON boundaries

Step 4: Attach bounding boxes to extracted values:
        For each extracted field value, find the matching chunk
        and pull its payload.bbox → citation record

Step 5: Write to AgentState:
        extracted_data[doc_type] = parsed JSON
        extracted_citations.extend(citation_list)
```

---

#### Quantitative Agent — Internal Flow

```
Input:  extracted_data from Extraction Agent
Output: quantitative_report

Step 1: Load PO / GRN / Invoice line items as Decimal

Step 2: For each document independently:
        ├── For each line item: compute qty × unit_price using Decimal
        ├── Compare computed_total vs claimed_total
        │   tolerance = Decimal("0.01")  ← 1 cent
        ├── If |computed - claimed| > tolerance → flag DISCREPANCY
        └── Sum all line_totals → computed_doc_total
            Compare vs claimed grand_total

Step 3: Cross-document quantity checks:
        PO_qty vs GRN_qty for each matched item (by description fuzzy match)
        ├── If GRN_qty < PO_qty → SHORT_DELIVERY flag
        └── If Invoice_qty > GRN_qty → OVERBILLING flag

Step 4: Cross-document price checks:
        Invoice_unit_price vs PO_unit_price
        ├── tolerance_pct = Decimal("0.001")  ← 0.1%
        └── If exceeded → PRICE_DEVIATION flag

Step 5: Write to AgentState:
        quantitative_report = {
            discrepancies: [list of found issues],
            total_discrepancies: N,
            math_verified: bool,
            cross_doc_flags: [...]
        }
```

**Why Decimal?** Python's `float` cannot represent 0.1 exactly in IEEE-754 binary. `0.1 + 0.2 == 0.30000000000000004`. For financial arithmetic this is unacceptable. `Decimal("0.1") + Decimal("0.2") == Decimal("0.3")` — exact.

---

#### SAMR Agent — The Hallucination Detector

This is Ventro's most novel mechanism.

```
Objective: Detect if the LLM's current reasoning is reliable or hallucinated.

Mechanism: Run two parallel inference streams on the SAME question.
           Stream 2 has adversarially perturbed numerical context.
           If the LLM's conclusions diverge significantly, it was relying
           on shallow pattern matching rather than genuine document comparison.

Step 1: Prepare primary context
        context = [po_data, grn_data, invoice_data] concatenated as text

Step 2: Prepare shadow context (adversarial perturbation)
        _perturb_context(context, strength=0.15):
            ├── For each line: find regex pattern \b(\d+\.\d{2})\b
            ├── With probability=strength, shift value by ±5% or ±10%
            │   original=500.00 → perturbed=525.00 (shift +5%)
            └── Record perturbations applied

Step 3: Primary stream
        primary_prompt = "Analyze these documents for reconciliation...{context}"
        primary_response = await llm.complete(primary_prompt, temperature=0.0)
        primary_vector  = await llm.get_reasoning_vector(primary_prompt)
        # → 768-dim embedding of the reasoning chain

Step 4: Shadow stream
        shadow_prompt = same prompt but with perturbed_context
        shadow_response = await llm.complete(shadow_prompt, temperature=0.0)
        shadow_vector   = await llm.get_reasoning_vector(shadow_prompt)

Step 5: Compute cosine similarity
        similarity = dot(primary_vector, shadow_vector)
                     / (||primary_vector|| × ||shadow_vector||)

Step 6: Apply threshold
        if similarity < 0.85:
            alert_triggered = True   ← REASONING DIVERGED
        else:
            alert_triggered = False  ← REASONING STABLE

Step 7: Interpretation
        HIGH similarity (≥ 0.85):
            Both streams reached same conclusion → LLM reasoning is robust
            Even with corrupted numbers, the model identified discrepancies
            consistently → we can trust its analysis

        LOW similarity (< 0.85):
            Shadow stream produced different conclusion when numbers changed
            → LLM was NOT actually reading the numbers, just pattern-matching
            → SAMR_ALERT: mandatory human review before payment
```

**Why this works:** A genuinely reasoning model will reach the same *logical structure* of conclusion regardless of minor input perturbations (it will still detect discrepancies, just different ones). A hallucinating model that is fabricating responses will produce structurally different outputs when inputs change, because it has no coherent ground truth to anchor to.

---

#### Reconciliation Agent — Three-Way Match

```
Input:  extracted_data (PO, GRN, Invoice line items)
Output: reconciliation_verdict

Step 1: Build match matrix
        For each PO line item i:
            For each GRN line item j:
                score_ij = rapidfuzz.fuzz.token_set_ratio(
                    po_item[i].description,
                    grn_item[j].description
                )
                # token_set_ratio handles word reordering:
                # "M6 Stainless Bolt" ↔ "Bolt Stainless M6" → 100

                # Override with exact part number match if available:
                if po_item[i].part_number == grn_item[j].part_number:
                    score_ij = 100.0

        Best match per PO item = argmax over GRN items where score > 70

Step 2: Same process for PO ↔ Invoice matching

Step 3: For each matched triple (po_i, grn_j, inv_k):
        ├── Description match score
        ├── Quantity comparison: po_qty, grn_qty, inv_qty
        ├── Price comparison: po_price vs inv_price
        └── Assign match_status:
            full_match   → all three align within tolerance
            partial_match → 2 of 3 align or minor deviation
            mismatch      → significant deviation or no match found

Step 4: Build prompt for LLM synthesis:
        "Given these match results: {match_matrix_json}
         Quantitative report: {quant_report}
         Synthesize a verdict: overall_status, confidence (0-1),
         discrepancy_summary (max 5 bullet points),
         recommendation (approve|hold|reject|escalate)
         Return JSON."

Step 5: Parse LLM verdict, combine with deterministic match results
        → final reconciliation_verdict

Step 6: Write to AgentState
```

---

### 4.3 CV & Embedding Pipeline

```
PDF → PyMuPDF (fitz.open)
         │
         ├── page.get_text("dict")
         │   Extracts: blocks → lines → spans
         │   Each span has: text, bbox (absolute pixels), font, size
         │   Normalize: bbox_normalized.x0 = bbox_pixels.x0 / page.rect.width
         │
         ├── page.find_tables()
         │   Uses PyMuPDF's built-in table bounding detection
         │   Returns: rows × cols grid, each cell as text
         │   Maps to: LineItem domain objects via header detection
         │
         └── Document classification:
             keyword_score(PO_KEYWORDS, full_text)
             keyword_score(GRN_KEYWORDS, full_text)
             keyword_score(INVOICE_KEYWORDS, full_text)
             → winner = argmax; confidence = winner_score / total_score

Chunking Strategy:
   Text blocks → merged until chunk_size=512 chars
   Each chunk preserves: {text, document_id, document_type, page, bbox}
   Line items → individual chunks (description + qty + price for semantic search)

Embedding:
   SentenceTransformer("all-MiniLM-L6-v2")
   → 384-dimensional L2-normalized dense vectors
   → Batch size 32, runs in thread pool (not blocking event loop)
```

---

### 4.4 Vector Store Strategy

#### Collection Schema
```
Collection: "mas_vgfr_docs"
Vector: 384-dim, COSINE distance, HNSW index (m=16, ef_construct=100)

Payload per point:
{
    "text":          string,     # chunk content
    "document_id":  string,     # UUID of source document
    "document_type": string,    # "purchase_order" | "grn" | "invoice"
    "page":          integer,   # 0-indexed
    "bbox":          object,    # {x0, y0, x1, y1, page}
    "chunk_type":    string,    # "text_block" | "line_item"
    "line_item":     object     # only if chunk_type == "line_item"
}

Payload Indices (keyword):
    document_id, document_type, page, session_id
    → O(1) filter lookup before vector search
```

#### Search Flow
```
Query: "invoice line item total amount due"
    │
    ▼
embedder.embed_query(query) → [0.12, -0.45, ...] (384 floats)
    │
    ▼
qdrant.search(
    query_vector=vector,
    filter={"document_id": invoice_doc_id},  # restrict to ONE document
    top_k=10,
    score_threshold=0.3
)
    │
    ├── HNSW approximate nearest neighbor search
    ├── Results: [(id, score, payload), ...]
    └── Keyword boost: query_terms ∩ payload.text → score += 0.05/term
    │
    ▼
cross_encoder.predict([(query, r.payload.text) for r in results])
    │
    └── Re-ranks by true semantic similarity (more expensive, applied to top-10 only)
```

---

### 4.5 SAMR Metrics Database Schema

```sql
CREATE TABLE samr_metrics (
    id                          SERIAL PRIMARY KEY,
    session_id                  VARCHAR NOT NULL,
    primary_stream_conclusion   TEXT,
    shadow_stream_conclusion    TEXT,
    cosine_similarity_score     FLOAT,
    divergence_threshold        FLOAT DEFAULT 0.85,
    alert_triggered             BOOLEAN DEFAULT FALSE,
    perturbation_applied        TEXT,
    reasoning_vectors_diverged  BOOLEAN DEFAULT TRUE,
    timestamp                   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_samr_session ON samr_metrics(session_id);
```

---

### 4.6 Database Schema

#### PostgreSQL Tables

```sql
-- documents
CREATE TABLE documents (
    id                     VARCHAR PRIMARY KEY,
    filename               VARCHAR NOT NULL,
    document_type          VARCHAR NOT NULL,   -- purchase_order | grn | invoice
    total_pages            INTEGER DEFAULT 0,
    file_size_bytes        INTEGER DEFAULT 0,
    mime_type              VARCHAR DEFAULT 'application/pdf',
    uploaded_at            TIMESTAMP DEFAULT NOW(),
    processed_at           TIMESTAMP,
    vendor_name            VARCHAR,
    document_number        VARCHAR,
    document_date          VARCHAR,
    currency               VARCHAR DEFAULT 'USD',
    classification_confidence FLOAT DEFAULT 0.0
);

-- reconciliation_sessions
CREATE TABLE reconciliation_sessions (
    id                     VARCHAR PRIMARY KEY,
    po_document_id         VARCHAR NOT NULL REFERENCES documents(id),
    grn_document_id        VARCHAR NOT NULL REFERENCES documents(id),
    invoice_document_id    VARCHAR NOT NULL REFERENCES documents(id),
    status                 VARCHAR DEFAULT 'pending',
    created_at             TIMESTAMP DEFAULT NOW(),
    started_at             TIMESTAMP,
    completed_at           TIMESTAMP,
    verdict_json           JSONB,         -- full ReconciliationVerdict
    agent_trace_json       JSONB,         -- complete agent execution log
    error_message          TEXT,
    created_by             VARCHAR DEFAULT 'system'
);
```

#### MongoDB Collections

```javascript
// parsed_documents collection
{
    "metadata": {
        "id": "uuid",
        "filename": "PO_12345.pdf",
        "document_type": "purchase_order",
        "total_pages": 3,
        "classification_confidence": 0.92
    },
    "line_items": [
        {
            "id": "uuid",
            "description": "Widget A",
            "quantity": 10.0,
            "unit_price": 50.00,
            "total_amount": 500.00,
            "bbox": {"x0": 0.1, "y0": 0.42, "x1": 0.9, "y1": 0.48, "page": 1},
            "confidence": 0.85
        }
    ],
    "raw_text_by_page": {"0": "...", "1": "..."},
}

// workpapers collection
{
    "id": "uuid",
    "session_id": "uuid",
    "title": "Three-Way Match Audit Workpaper — 2026-02-21",
    "generated_at": "2026-02-21T04:51:00Z",
    "verdict_summary": "full_match",
    "html_content": "<!DOCTYPE html>...",  // full interactive HTML
    "sections": [...]
}
```

---

### 4.7 API Contract Detail

#### POST /api/v1/documents/upload

```
Request:  multipart/form-data
          file: File (PDF | PNG | JPG | TIFF, max 50MB)

Response 201:
{
    "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "filename": "PO_2024_001.pdf",
    "document_type": "purchase_order",
    "total_pages": 2,
    "classification_confidence": 0.91,
    "message": "Document processed successfully. 14 chunks indexed."
}

Errors:
    415: Unsupported file type
    413: File exceeds 50MB limit
    500: CV pipeline failure (with detail)
```

#### POST /api/v1/reconciliation/sessions

```
Request:  application/json
{
    "po_document_id":      "uuid",
    "grn_document_id":     "uuid",
    "invoice_document_id": "uuid"
}

Response 201:
{
    "id": "session-uuid",
    "po_document_id": "uuid",
    "grn_document_id": "uuid",
    "invoice_document_id": "uuid",
    "status": "pending",
    "created_at": "2026-02-21T04:51:00Z"
}
```

#### POST /api/v1/reconciliation/sessions/{id}/run

```
Response 202:
{
    "message": "Reconciliation workflow started",
    "session_id": "uuid",
    "ws_endpoint": "/ws/reconciliation/uuid"
}
```

#### GET /api/v1/reconciliation/sessions/{id}/result

```
Response 200:
{
    "session_id": "uuid",
    "status": "matched",
    "verdict": {
        "overall_status": "full_match",
        "confidence": 0.94,
        "recommendation": "approve",
        "line_item_matches": [...],
        "discrepancy_summary": []
    },
    "workpaper": { "html_content": "...", "title": "..." },
    "samr_metrics": {
        "cosine_similarity_score": 0.923,
        "alert_triggered": false,
        "interpretation": "Clear"
    },
    "agent_trace": [...],
    "completed_at": "2026-02-21T04:52:47Z"
}
```

---

### 4.8 WebSocket Event Protocol

Events published by `InMemoryProgressPublisher` and consumed by frontend:

```typescript
interface ProgressEvent {
    event:      string;       // event type (see below)
    session_id: string;
    timestamp:  number;       // Unix epoch float
    agent?:     string;       // which agent triggered this
    message?:   string;       // human-readable message
    data?:      any;          // event-specific payload
}

// Event types:
"workflow_started"   → { total_agents: 6 }
"agent_started"      → { agent: "extraction", message: "Retrieving spatial data..." }
"agent_progress"     → { agent: "quantitative", message: "Checking line item totals..." }
"agent_completed"    → { agent: "extraction", duration_ms: 3420 }
"samr_alert"         → { cosine_score: 0.71, threshold: 0.85, perturbation: "..." }
"samr_clear"         → { cosine_score: 0.93 }
"workflow_complete"  → { status: "matched", verdict_summary: "full_match" }
"workflow_error"     → { error: "...", agent: "compliance" }
"ping"               → {}   // keepalive every 15s
```

---

### 4.9 Frontend State Machine

```
Zustand AppState:

                    ┌─────────────────────────────────────────────────┐
                    │                  AppState                        │
                    │                                                  │
  Upload Page ────► │ poDoc | grnDoc | invoiceDoc                     │
                    │ setPoDoc() / setGrnDoc() / setInvoiceDoc()       │
                    │                                                  │
  /sessions/{id} ──► │ activeSessionId / setActiveSessionId()          │
                    │                                                  │
  WS events ──────► │ progressEvents[] / addProgressEvent()           │
                    │ clearProgressEvents()                            │
                    │                                                  │
  Citation click ──► │ pdfViewerDoc: {docId, page, bbox}              │
                    │ openPdfViewer() / closePdfViewer()               │
                    │                                                  │
  SAMR Agent ─────► │ samrAlertActive / setSamrAlert()               │
                    └─────────────────────────────────────────────────┘

React Query caches:
    "session-status"  → polls every 3s while processing
    "session-result"  → fetched once when status is terminal
    "analytics-metrics" → refetched every 30s
    "health"          → refetched every 60s
```

---

## 5. OTAR Framework

> **O**bjective → **T**ask → **A**ction → **R**esult for every system component.

---

### User: Upload Document

| | Detail |
|--|--------|
| **Objective** | Ingest a financial PDF and make it semantically searchable |
| **Task** | Validate, parse, classify, embed, and index the document |
| **Actions** | (1) Validate MIME type and size → (2) Save to tempdir → (3) `DocumentProcessor.process_pdf()` → PyMuPDF extracts text blocks + bounding boxes → table finder extracts rows → keyword classifier assigns type → (4) `chunk_document_for_embedding()` builds N chunks with spatial metadata → (5) `SentenceTransformerEmbedding.embed_texts()` produces vectors → (6) `QdrantAdapter.upsert_chunks()` indexes in Qdrant → (7) `PostgreSQLAdapter.save()` stores metadata → (8) `MongoDBAdapter.save_parsed_document()` stores full structure |
| **Result** | `document_id` returned; document is ready for semantic retrieval with bounding-box citations |

---

### Agent 1: Extraction Agent

| | Detail |
|--|--------|
| **Objective** | Retrieve the most relevant text from each document and extract structured fields |
| **Task** | RAG with spatial metadata, LLM-powered structured extraction |
| **Actions** | (1) Embed targeted queries per document type → (2) Qdrant hybrid search (dense + keyword boost) → (3) Cross-encoder reranking of top-10 → top-5 → (4) Prompt Mistral-7B to extract JSON (vendor, items, totals) → (5) Match extracted values to bounding boxes from chunk payloads → (6) Write to `AgentState.extracted_data` and `extracted_citations` |
| **Result** | Structured data from all three documents with pixel-level source citations |

---

### Agent 2: Quantitative Agent

| | Detail |
|--|--------|
| **Objective** | Independently verify every number without trusting LLM arithmetic |
| **Task** | Deterministic re-computation of all financial arithmetic |
| **Actions** | (1) Convert all extracted values to `Decimal` → (2) Re-compute `qty × unit_price` per line → compare to claimed total → (3) Sum line totals → compare to claimed grand total → (4) Cross-document: PO qty vs GRN qty (short delivery?), Invoice qty vs GRN qty (overbilling?) → (5) Cross-document: PO unit price vs Invoice unit price (price deviation?) → (6) Write flagged discrepancies to `AgentState.quantitative_report` |
| **Result** | A machine-verified, error-free discrepancy report with `Decimal` precision |

---

### Agent 3: Compliance Agent

| | Detail |
|--|--------|
| **Objective** | Evaluate the transaction against business rules and regulatory requirements |
| **Task** | Rule evaluation and risk scoring |
| **Actions** | (1) Build compliance prompt including all document data + rule definitions → (2) Mistral-7B evaluates: duplicate invoice check, vendor on approved list, tax calculation correctness, payment terms consistency, PO line count vs GRN line count → (3) Returns JSON: `{compliance_status, risk_score, flags, policy_violations}` → (4) Write to `AgentState.compliance_report` |
| **Result** | Risk score (0–10), list of rule passes/failures, policy violations flagged |

---

### Agent 4: SAMR Agent

| | Detail |
|--|--------|
| **Objective** | Detect if the LLM is hallucinating rather than genuinely reasoning |
| **Task** | Dual-stream adversarial inference with cosine divergence measurement |
| **Actions** | (1) Prepare primary context (full document data) → (2) Perturb context: shift ±5–10% of numeric values randomly → (3) Send both contexts to Mistral-7B simultaneously → (4) Extract reasoning vectors (768-dim embeddings of reasoning chain) → (5) Compute cosine similarity → (6) If similarity < 0.85: set `samr_alert_triggered=True`, publish `samr_alert` WebSocket event → (7) Write metrics to `AgentState.samr_metrics` and PostgreSQL |
| **Result** | Binary alert (clear/triggered) + similarity score; if alert, session status becomes SAMR_ALERT and human review is enforced |

---

### Agent 5: Reconciliation Agent

| | Detail |
|--|--------|
| **Objective** | Produce the definitive three-way match verdict |
| **Task** | Semantic entity resolution + LLM synthesis of final verdict |
| **Actions** | (1) Build match matrix: `rapidfuzz.token_set_ratio` for all PO×GRN and PO×Invoice item pairs → (2) Override with exact part number when available → (3) For each matched triple: compare qty, price, description → assign `full_match | partial_match | mismatch` → (4) Prompt Mistral-7B with match matrix + quant report to synthesize verdict JSON → (5) Write to `AgentState.reconciliation_verdict` |
| **Result** | `{overall_status, confidence, recommendation, line_item_matches[], discrepancy_summary[]}` |

---

### Agent 6: Drafting Agent

| | Detail |
|--|--------|
| **Objective** | Generate a professional, interactive audit workpaper |
| **Task** | LLM narrative generation + HTML workpaper with clickable citations |
| **Actions** | (1) Prompt Mistral-7B with all agent outputs → generate 500-word auditor-style narrative covering Objective, Procedure, Findings, Materiality, Conclusion → (2) Build `_build_workpaper_html()`: embeds narrative, line item reconciliation table, compliance flags, SAMR report, interactive citation map → (3) Each citation renders as `<span onclick="window.openCitation(this)">` with `data-doc-id`, `data-page`, `data-x0/y0/x1/y1` attributes → (4) Frontend intercepts `postMessage` from iframe and navigates PDF viewer to exact bounding box → (5) Write to `AgentState.workpaper`, save to MongoDB |
| **Result** | A self-contained HTML audit workpaper with professional narrative and pixel-precise, clickable evidence citations |

---

## 6. Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---------|-----------|-----------|
| Ollama model not loaded | `health_check()` returns False on startup | `pull_model_if_needed()` called at init; lifespan startup logs warning |
| LLM returns invalid JSON | `_extract_json()` fails to find brackets | Agent catches exception, writes `error` to state, supervisor routes to exception handler |
| PDF has no extractable text (scanned) | `all_blocks == []`, `full_text == ""` | Classification returns `UNKNOWN`; agent falls back to raw text; future: Tesseract OCR |
| Qdrant collection missing | `UnexpectedResponse` on search | `ensure_collection()` called before every search; idempotent creation |
| Cosine similarity NaN | Zero vectors from failed reasoning vector | Fallback: generate deterministic pseudo-vector from SHA-256 hash of prompt |
| WebSocket client disconnects | `WebSocketDisconnect` exception | `unsubscribe()` removes callback; no resource leak |
| PostgreSQL connection pool exhausted | `asyncpg` raises `TooManyConnectionsError` | Pool size 10 + overflow 20; Celery offloads heavy async work |
| Document misclassified | Low `classification_confidence` returned | Frontend displays confidence; user can manually override type |

---

## 7. Performance Characteristics

| Operation | Typical Duration | Bottleneck |
|-----------|-----------------|-----------|
| PDF upload + CV pipeline | 2–8s | PyMuPDF page iteration |
| Embedding 20 chunks | 0.3–1.5s | SentenceTransformer CPU inference |
| Qdrant HNSW search | 5–50ms | In-memory ANN |
| Ollama Mistral-7B inference | 5–30s | GPU/CPU LLM inference |
| SAMR dual-stream (2 × LLM) | 10–60s | Two sequential LLM calls |
| Full pipeline (6 agents) | 45–120s | LLM calls dominate |

**P95 target: ≤ 120 seconds** end-to-end, achievable on:
- M2 Mac (CPU): ~90s
- Linux + RTX 3090 (GPU Ollama): ~35s

---

## 8. Security Model

| Concern | Control |
|---------|---------|
| **Data residency** | All LLM inference via local Ollama; no data exits the network |
| **File upload safety** | MIME type validation + 50MB limit; files stored in `/tmp` with UUID names |
| **SQL injection** | SQLAlchemy ORM with parameterized queries only |
| **Secret management** | All credentials in `.env` file; `.gitignore` prevents commit |
| **CORS** | Configurable `allowed_origins` in Settings; production should lockdown to frontend domain |
| **Non-root container** | Backend runs as `appuser` (UID 1000) inside Docker |
| **PDF content safety** | PyMuPDF does not execute JavaScript in PDFs; safe for malicious uploads |
| **Future: Auth** | JWT middleware planned; current `IAuthClient` interface ready for implementation |
