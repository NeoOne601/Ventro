# Ventro — Auditable AI Reconciliation Engine

Multi-Agent System for Visually-Grounded Financial Reconciliation (MAS-VGFR).

Automates three-way match auditing (PO ↔ GRN ↔ Invoice) with pixel-perfect evidence
tracing and SAMR™ hallucination detection.

## Quick Start

```bash
cd infra && docker compose up -d
```

## Architecture

- **FastAPI** backend with LangGraph orchestrator
- **PostgreSQL** for session metadata and audit log
- **MongoDB** for parsed document storage and version history
- **Qdrant** vector store for semantic search
- **Redis** for caching and Celery task queue
- **Celery** workers for reconciliation and batch processing

## Features

- Three-way document matching (PO + GRN + Invoice)
- SAMR™ hallucination detection with adaptive thresholds
- Document version history
- Confidence interval bands per extracted field
- Bulk upload with automatic batch reconciliation
- MASTER cross-organisation admin panel
- SOC 2 compliance evidence pack generation
