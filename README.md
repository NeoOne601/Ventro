# Ventro — AI-Native Financial Reconciliation Platform

> **Automate three-way match auditing with explainable AI. Every conclusion is traceable to its source. Every number is verified twice.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What Is Ventro?

Ventro automates the most time-consuming step in accounts payable: **three-way matching** — confirming that a Purchase Order (PO), Goods Receipt Note (GRN), and Supplier Invoice all agree before approving payment.

Where traditional software fails on template changes, multilingual documents, or partial deliveries, Ventro uses a coordinated system of AI agents that read and reason across all three documents simultaneously — the same way a senior auditor would, but in seconds rather than hours.

### Who Is It For?

| Team | How Ventro Helps |
|------|-----------------|
| **Accounts Payable** | Eliminate manual matching; catch overcharges automatically |
| **Internal Audit** | Every finding links back to the exact document line that triggered it |
| **Finance Directors** | Full analytics dashboard; exportable signed workpapers |
| **External Auditors** | Read-only access to sessions and findings; PDF workpaper download |
| **Compliance / Legal** | Immutable, cryptographically chained audit trail |

---

## What Makes Ventro Different

### Explainable Evidence — Not a Black Box

Every number Ventro surfaces is anchored to the exact position in the source document where it was found. Auditors can click any finding and be taken directly to the relevant line in the original PDF. There is no "trust the AI" — every conclusion has a citation.

### Confidence Assurance Technology

Ventro includes a proprietary confidence layer that monitors AI reasoning quality in real time. When the system detects that an AI answer may be unreliable — for any reason — it automatically escalates the finding for human review instead of silently passing it through. This means the error rate does not depend on AI model quality alone; the system is self-correcting by design.

> **This mechanism is core IP. It is not documented beyond this description.**

### Resilient AI — Always Running

Ventro operates across a configured chain of AI providers. If the primary provider is unavailable or slow, the system automatically retries through secondary options and, as a last resort, falls back to a deterministic rule-based extractor that always returns a result. From the user's perspective, the pipeline finishes — even during an AI outage.

### Parallel Processing

All three documents (PO, GRN, Invoice) are processed simultaneously, not sequentially. End-to-end reconciliation typically completes in under 90 seconds regardless of document length.

---

## Security & Compliance

Ventro is built to the same standards expected of financial software in regulated environments.

### Authentication & Access Control

- **Seven-tier role model** — from read-only External Auditor through to Master Administrator. Every API call is authorised against the caller's role before any data is returned.
- **JWT-based sessions** — short-lived access tokens, rotating refresh tokens. Tokens are individually revocable: logout is instantaneous, not eventual.
- **Logout all devices** — a single call invalidates every active session for a user across all browsers and devices simultaneously.
- **Organisation isolation** — every data record is scoped to its organisation. No user can read another organisation's data, regardless of their role.

| Role | Access Level |
|------|-------------|
| External Auditor | Read-only: sessions, workpapers |
| AP Analyst | Upload documents, create and run reconciliations |
| AP Manager | All above + approve findings, sign workpapers |
| Finance Director | All above + analytics, billing, audit log |
| Administrator | All above + user management within organisation |
| Developer | Platform access: diagnostics, API keys, logs (no financial writes) |
| Master | Full system access across all organisations |

### Input Integrity

- All uploaded documents are validated for file type, size, and safe content before being processed.
- User-controlled text that enters AI reasoning pipelines is cleaned and screened before use, preventing a class of attacks where malicious content embedded in a document attempts to manipulate AI behaviour.

### Audit Trail

- Every action that changes data — login, document upload, session creation, finding override — is recorded in an append-only, cryptographically chained log. No record can be modified or deleted without breaking the chain.
- Audit log entries are accessible to Finance Director and above.

### Workpaper Integrity

- Exported PDF workpapers embed a cryptographic fingerprint and session identifier in the document. Any modification to the exported file invalidates the fingerprint, making tampering detectable.

---

## Rate Limiting

Every API endpoint is protected by configurable rate limiting to prevent abuse. Administrators choose the limiting strategy without code changes:

| Strategy | Description |
|----------|-------------|
| `per_ip` | One limit per source IP address — default |
| `per_user` | One limit per authenticated user |
| `per_org` | Shared limit across all users in an organisation |
| `per_ip_and_user` | Both IP and user limits must be within quota — strictest |
| `global` | Single counter for the entire API — useful for development |

Limits for authentication, file upload, and general API calls are independently configurable. Internal services can be whitelisted by CIDR range.

---

## The Six AI Agents

Each agent has a single, well-defined job. They run in sequence, passing structured results to the next stage.

| Agent | What It Does |
|-------|-------------|
| **Extraction** | Reads PO, GRN, and Invoice in parallel; pulls out every line item, total, date, and reference number |
| **Quantitative** | Re-computes all arithmetic from first principles — subtotals, tax, totals — using exact arithmetic, not floating point |
| **Compliance** | Checks for duplicate invoices, missing references, tax rule violations, and vendor verification |
| **Confidence Assurance** | Proprietary mechanism that validates AI reasoning quality before results are committed |
| **Reconciliation** | Runs the three-way match; identifies every discrepancy by amount, description, and quantity |
| **Drafting** | Produces an interactive HTML audit workpaper with inline citations and a signed PDF export |

---

## Technology

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11, FastAPI, asyncpg, Motor |
| **AI Orchestration** | LangGraph, LangChain |
| **AI Providers** | Groq (cloud), Ollama (self-hosted) — with automatic failover |
| **Embeddings** | Multilingual sentence-transformers (100+ languages) |
| **Vector Search** | Qdrant |
| **Document Processing** | PyMuPDF (bounding-box-aware), Tesseract OCR, VLM for scanned pages |
| **Databases** | PostgreSQL 16 (sessions, audit trail), MongoDB 7 (documents, workpapers) |
| **Cache / Queue** | Redis 7, Celery (async job processing) |
| **Frontend** | React 18, TypeScript, Vite |
| **Observability** | OpenTelemetry distributed tracing, Prometheus metrics, structured JSON logging |
| **Deployment** | Docker Compose (development), Kubernetes (production) |

**Multilingual support:** document extraction and entity matching work across Latin, Arabic, Hindi, Chinese, Japanese, Korean, Cyrillic, and 90+ additional scripts out of the box.

---

## Quick Start

### Prerequisites
- Docker Desktop (running)
- Python 3.11+ and Node.js 20+ (for local development without Docker)

### With Docker Compose

```bash
cd mas-vgfr/infra
cp ../backend/.env.example ../backend/.env
# Configure at minimum: SECRET_KEY, GROQ_API_KEY or OLLAMA_BASE_URL
docker compose up -d
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (dev only) | http://localhost:8000/api/docs |
| Qdrant Dashboard | http://localhost:6333/dashboard |

### Local Development (no Docker)

```bash
# Backend
cd mas-vgfr/backend
pip install -e ".[dev]"
uvicorn src.presentation.main:app --reload --port 8000

# Frontend (separate terminal)
cd mas-vgfr/frontend
npm install
npm run dev
```

---

## Usage

### Via the Web Interface

1. Open **http://localhost:5173** — log in with your organisation credentials
2. Go to **Upload Documents** → drop your PO, GRN, and Invoice files (PDF, XLSX, CSV, or scanned images)
3. Click **Start Reconciliation** → the six-agent pipeline runs with live progress updates
4. Review findings in the **Reconciliation** view — each finding shows its source location in the document
5. Export a signed **PDF Workpaper** for your audit file

### Via the API

All API calls require a Bearer token obtained from `POST /api/v1/auth/login`.

```bash
# Upload a document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@purchase_order.pdf"
# → { "document_id": "abc123", "document_type": "purchase_order" }

# Create a reconciliation session
curl -X POST http://localhost:8000/api/v1/reconciliation/sessions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{ "po_document_id": "abc123", "grn_document_id": "def456", "invoice_document_id": "ghi789" }'

# Run the pipeline
curl -X POST http://localhost:8000/api/v1/reconciliation/sessions/{id}/run \
  -H "Authorization: Bearer <token>"

# Get results
curl http://localhost:8000/api/v1/reconciliation/sessions/{id}/result \
  -H "Authorization: Bearer <token>"

# Export signed workpaper PDF (Finance Director+ only)
curl http://localhost:8000/api/v1/reconciliation/sessions/{id}/workpaper/pdf \
  -H "Authorization: Bearer <token>" -o workpaper.pdf
```

---

## Configuration Reference

All settings are read from environment variables (or a `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | JWT signing key — **must be set in production** |
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `GROQ_API_KEY` | — | If set, Groq is the primary AI provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Fallback self-hosted LLM |
| `LLM_FALLBACK_CHAIN` | `groq,ollama,rule_based` | Ordered AI provider failover list |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `MONGO_URL` | — | MongoDB connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis (rate limiting + denylist + cache) |
| `RATE_LIMIT_STRATEGY` | `per_ip` | Rate limiting strategy (see above) |
| `RATE_LIMIT_AUTH_REQUESTS` | `10` | Max auth requests per window |
| `RATE_LIMIT_API_REQUESTS` | `120` | Max general API requests per window |
| `RATE_LIMIT_WHITELIST_CIDRS` | — | Comma-separated CIDRs exempt from limits |
| `SAMR_DIVERGENCE_THRESHOLD` | `0.85` | Confidence threshold — findings below escalate to human review |
| `MAX_UPLOAD_SIZE_MB` | `50` | Per-file upload size limit |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |

---

## Project Structure

```
mas-vgfr/
├── backend/
│   ├── src/
│   │   ├── domain/             # Entities, interfaces, RBAC definitions
│   │   ├── application/
│   │   │   ├── agents/         # Six reconciliation agents + LangGraph orchestrator
│   │   │   └── config.py       # Centralised configuration (pydantic-settings)
│   │   ├── infrastructure/
│   │   │   ├── llm/            # AI provider clients + fallback router
│   │   │   ├── auth/           # JWT handler, password hashing, token denylist
│   │   │   ├── security/       # Input sanitization
│   │   │   ├── cv/             # Document processing pipeline
│   │   │   ├── database/       # PostgreSQL and MongoDB adapters
│   │   │   ├── vector_store/   # Qdrant adapter
│   │   │   ├── jobs/           # Celery task definitions
│   │   │   └── workpaper/      # PDF export utilities
│   │   └── presentation/
│   │       ├── api/v1/         # REST endpoints (documents, reconciliation, analytics)
│   │       ├── routes/         # Authentication router
│   │       ├── middleware/     # Rate limiting, auth, security headers
│   │       └── websocket/      # Real-time pipeline progress
│   ├── tests/
│   │   ├── unit/               # Agent and component unit tests
│   │   ├── integration/        # API endpoint integration tests
│   │   └── test_production_hardening.py  # Security and reliability test suite
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── contexts/           # AuthContext — authentication state and RBAC helpers
│   │   ├── pages/              # Dashboard, Upload, Sessions, Reconciliation, Analytics, Login
│   │   ├── components/
│   │   │   ├── auth/           # ProtectedRoute — role and permission guards
│   │   │   └── layout/         # Sidebar (role-aware navigation)
│   │   ├── services/           # API client
│   │   └── styles/             # Auth page and component styles
│   └── Dockerfile
├── infra/
│   └── docker-compose.yml      # Full-stack local orchestration (includes Celery workers)
└── docs/
    ├── DeploymentGuide.md
    └── CommercialStrategy.md
```

---

## Running Tests

```bash
cd mas-vgfr/backend

# Full test suite
pytest tests/ -v --tb=short

# With coverage
pytest tests/ --cov=src --cov-report=html

# Security and production-hardening tests only
pytest tests/test_production_hardening.py -v
```

The production hardening suite covers JWT authentication, password security, role-based access control, document sanitization, audit log integrity, workpaper export, and AI resilience — 38 tests, all passing.

---

## Deployment

See [DeploymentGuide.md](docs/DeploymentGuide.md) for:
- Docker Compose production configuration
- Kubernetes manifest deployment
- Environment variable reference
- Database migration steps
- TLS / reverse proxy setup

---

## Design Principles

- **Zero trust at every layer** — every API call is authenticated and authorised, regardless of origin
- **Data never leaves your infrastructure** — the self-hosted AI path (Ollama) keeps all document content on-premises
- **Exact arithmetic** — all financial calculations use Python's `decimal.Decimal`; floating-point is never used for money
- **Evidence-first** — every extracted value is stored with its document coordinates; no finding exists without a source reference
- **Resilience by default** — the AI pipeline degrades gracefully; a partial result with a warning is always preferable to a silent failure
- **Clean Architecture** — the domain layer has no external dependencies; infrastructure implements domain interfaces

---

## License

MIT © 2026 Ventro Contributors
