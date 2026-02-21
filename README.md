# MAS-VGFR — Multi-Agent System for Visually-Grounded Financial Reconciliation

> **Benchmark-setting AI for automated three-way match auditing.** Pixel-perfect evidence tracing. Self-hosted LLMs. Zero hallucination tolerance.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange.svg)](https://github.com/langchain-ai/langgraph)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What Is MAS-VGFR?

MAS-VGFR automates the financial audit process known as **three-way matching** — comparing a **Purchase Order (PO)**, **Goods Receipt Note (GRN)**, and **Supplier Invoice** to detect discrepancies, overcharges, and fraud.

Traditional RPA tools fail because they can't handle variation in document layout, vendor terminology, or partial deliveries. MAS-VGFR solves this with a pipeline of six specialized AI agents.

### Core Innovation: Visual Grounding
Every AI conclusion is linked back to the **exact pixel location** in the source PDF where the data was found. Auditors click a finding and the source document jumps to that bounding box — no more "trust the AI."

### Core Innovation: SAMR™
**Shadow Agent Memory Reconciliation** — a novel hallucination detection mechanism. Every LLM query runs through two parallel streams (one with adversarially perturbed context). Cosine similarity between the reasoning vectors detects divergence before it causes an audit error.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     React Frontend (Vite + TS)                    │
│   Glassmorphism UI · PDF Viewer · Real-time WebSocket Pipeline   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP + WebSocket
┌────────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Presentation Layer                      │
│        /api/v1/documents  ·  /api/v1/reconciliation  ·  /ws      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│              LangGraph Multi-Agent Orchestrator                    │
│                                                                    │
│  [Supervisor] → [Extraction] → [Quantitative] → [Compliance]      │
│             → [SAMR] → [Reconciliation] → [Drafting]             │
└──────┬──────────────┬───────────────┬────────────────────────────┘
       │              │               │
  Ollama LLM     Qdrant VDB      PostgreSQL + MongoDB
  (Mistral-7B)  (Vector Search)  (Sessions + Workpapers)
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Agents** | LangGraph 0.2, LangChain |
| **LLM** | Ollama + Mistral-7B-Instruct (self-hosted) |
| **Embeddings** | sentence-transformers (`all-MiniLM-L6-v2`) |
| **Vector DB** | Qdrant (hybrid dense + sparse search) |
| **CV Pipeline** | PyMuPDF (layout + bounding box + tables) |
| **Backend** | Python 3.11, FastAPI, asyncpg, Motor |
| **Databases** | PostgreSQL 16 (audit trail), MongoDB 7 (documents) |
| **Cache/Queue** | Redis 7, Celery |
| **Frontend** | React 18, TypeScript, Vite, Zustand, Framer Motion |
| **Charts** | Recharts |
| **Deploy** | Docker Compose (dev), Kubernetes (prod) |

---

## The Six Agents

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | **Extraction** | RAG retrieval from Qdrant with bounding-box-aware cross-encoder reranking |
| 2 | **Quantitative** | Deterministic math re-computation using Python `Decimal` (zero float error) |
| 3 | **Compliance** | Rule evaluation: duplicate invoices, tax compliance, vendor verification |
| 4 | **SAMR** | Dual-stream hallucination detection via cosine similarity divergence |
| 5 | **Reconciliation** | Three-way match with `rapidfuzz` entity resolution |
| 6 | **Drafting** | Interactive HTML audit workpaper with clickable citation links |

---

## Quick Start

### Prerequisites
- **Docker Desktop** (running)
- **Ollama** installed and running locally
- **Python 3.11+** and **Node.js 20+** (for local dev)

### 1. Pull the LLM
```bash
ollama pull mistral:7b-instruct
```

### 2. Configure environment
```bash
cd mas-vgfr/backend
cp .env.example .env
# Edit .env with your settings
```

### 3. Start with Docker Compose
```bash
cd mas-vgfr/infra
docker compose up -d
```

Services started:
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/api/docs
- **Frontend**: http://localhost:5173
- **Qdrant Dashboard**: http://localhost:6333/dashboard

### 4. Local development (no Docker)
```bash
# Backend
cd backend
pip install -e ".[dev]"
uvicorn src.presentation.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## Usage

### Via UI
1. Navigate to http://localhost:5173
2. Go to **Upload Documents** → drop your PO, GRN, and Invoice PDFs
3. Click **Start AI Reconciliation**
4. Watch the **6-agent pipeline** stream in real time
5. View the interactive **Audit Workpaper** with clickable evidence links

### Via API
```bash
# Upload PO
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@purchase_order.pdf"
# → {"document_id": "abc123", "document_type": "purchase_order", ...}

# Create session + run
curl -X POST http://localhost:8000/api/v1/reconciliation/sessions \
  -H "Content-Type: application/json" \
  -d '{"po_document_id": "abc123", "grn_document_id": "def456", "invoice_document_id": "ghi789"}'

curl -X POST http://localhost:8000/api/v1/reconciliation/sessions/{id}/run

# Poll result
curl http://localhost:8000/api/v1/reconciliation/sessions/{id}/result
```

---

## Project Structure

```
mas-vgfr/
├── backend/
│   ├── src/
│   │   ├── domain/          # Entities, interfaces (no dependencies)
│   │   ├── application/
│   │   │   ├── agents/      # 6 specialized agents + LangGraph orchestrator
│   │   │   └── config.py    # Pydantic-Settings centralized config
│   │   ├── infrastructure/  # DB adapters, LLM clients, CV pipeline, Qdrant
│   │   └── presentation/    # FastAPI routes, WebSocket, schemas
│   ├── tests/
│   │   ├── unit/            # Agent & CV pipeline unit tests
│   │   └── integration/     # API endpoint integration tests
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/           # Dashboard, Upload, Reconciliation, Sessions, Analytics
│   │   ├── components/      # Sidebar, layout components
│   │   ├── services/        # API client + WebSocket factory
│   │   └── store/           # Zustand global state
│   ├── index.css            # Glassmorphism design system
│   └── Dockerfile
├── infra/
│   └── docker-compose.yml   # Full-stack local orchestration
└── .gitignore
```

---

## Running Tests

```bash
cd backend
pytest tests/unit/ -v
pytest tests/ --cov=src --cov-report=html
```

---

## Key Design Decisions

- **Clean Architecture**: Domain layer has zero external dependencies. Infrastructure implements domain interfaces (Dependency Inversion).
- **Self-hosted LLMs only**: Ollama + Mistral-7B. No data leaves your infrastructure.
- **Decimal arithmetic**: All financial calculations use Python's `decimal.Decimal` — never `float`.
- **Bounding-box-first**: Every extracted value is linked to its PDF coordinates so auditors can verify the source.
- **SAMR hallucination guard**: Automatic human-review escalation when cosine similarity diverges below threshold.

---

## License

MIT © 2026 MAS-VGFR Contributors
