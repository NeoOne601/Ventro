# FAANG Resume Guide: Ventro Multi-Agent System

This document provides high-impact, FAANG-formatted resume points and architectural summaries for the **Ventro** project. FAANG recruiters look for the **XYZ formula** ("Accomplished [X] as measured by [Y], by doing [Z]") and indicators of **scale, complexity, and ownership**.

## Project Synopsis
**Ventro (Visual GenAI Financial Reconciliation System)** 
*A real-time Multi-Agent System (MAS) that automates three-way financial matching (Purchase Orders, Goods Receipts, Invoices) using Large Language Models, semantic search, and deterministic validation.*

**Tech Stack:** Python, FastAPI, React/TypeScript, PostgreSQL, MongoDB, Redis, Qdrant (Vector DB), Celery, Docker, LangGraph, Groq (Llama 3.3).

---

## 🚀 Resume Bullet Points (Pick 3-4)

### 1. Multi-Agent Orchestration & Core Architecture
* **Architected and deployed a multi-agent orchestration pipeline** using LangGraph and FastAPI, decoupling document extraction, quantitative validation, and compliance checks into isolated, scalable state machines.
* **Reduced manual financial auditing time by an estimated 80%** by engineering an automated three-way matching engine that cross-references unstructured Purchase Orders, Receipts, and Invoices using deterministic logic and LLM-powered fuzzy entity resolution.
* **Designed a hybrid multi-tenant data architecture** utilizing PostgreSQL for relational session state (isolated via organization-scoped JWTs) and MongoDB for append-only, version-controlled document history.

### 2. Applied AI & Vector Search (RAG)
* **Pioneered a micro-fragment bounding box embedding strategy** using PyMuPDF and sentence-transformers, slicing raw text into semantic chunks while retaining granular spatial coordinates in a Qdrant vector database.
* **Improved LLM extraction accuracy and auditability** by implementing a custom precision RAG pipeline; built an `ExtractionAgent` that links generated financial conclusions directly back to strict Cartesian coordinates (x,y) on the original PDF source document.
* **Mitigated LLM hallucinations (SAMR framework)** by designing a deterministic isolation state machine within the LangGraph orchestrator, forcing the AI agents to mathematically defend extracted values against a unified Cartesian truth array before granting final reconciliation approval.

### 3. Distributed Systems, Frontend & Concurrency
* **Resolved fatal concurrent authentication "thundering herd" bottlenecks** by engineering a React `AuthContext` with cross-tab LocalStorage synchronization and randomized jitter backoffs, preventing race conditions during rapid multi-tab session instantiation.
* **Built a real-time, event-driven React frontend** utilizing WebSocket streaming and React Query polling, providing users with live, granular progress updates (e.g., "Agent running...", "Mathematical mismatch found") streamed via Redis Pub/Sub.
* **Implemented an asynchronous batch processing engine** utilizing Celery chords and Redis message brokering, allowing users to bulk-upload and dispatch 50+ concurrent reconciliation workflows without blocking the main event loop.

---

## 🎤 Interview "Elevator Pitch" (Behavioral & Technical)

### The Problem (Situation)
"In financial operations, accounts payable teams spend countless hours manually cross-referencing Purchase Orders against Goods Receipts and Invoices (the '3-way match'). Existing OCR tools were too rigid for varied vendor templates, and raw LLMs hallucinated numbers or lost the audit trail of *where* the data came from."

### The Solution (Action)
"I built Ventro, a Multi-Agent GenAI system. Instead of one massive prompt, I decoupled the problem into a LangGraph state machine with specialized agents (Classification, Extraction, Quantitative, Compliance). 
To solve the audit trail problem, I built a custom chunking algorithm that embeds spatial micro-bounding-boxes alongside the text vectors in Qdrant. When the LLM extracts an item, my algorithm traces it back to the exact (x,y) coordinate on the page."

### The Complexity (Task/Result)
"A major challenge was managing state and concurrency. The backend relies on async Celery workers and Redis Pub/Sub to broadcast real-time status to the React frontend via Websockets. When I encountered a 'thundering herd' bug—where opening multiple browser tabs triggered simultaneous auth refresh requests that rotated the token and logged the user out—I engineered a sophisticated cross-tab synchronization mechanism utilizing LocalStorage with a randomized jitter backoff to enforce serialized, polite token renewals."
