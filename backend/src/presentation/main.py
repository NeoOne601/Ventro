"""
MAS-VGFR FastAPI Application Factory
Main entrypoint with lifespan events, CORS, and router registration.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import documents, reconciliation, analytics
from .websocket.progress import router as ws_router
from .dependencies import get_db, get_mongo, get_qdrant, get_publisher
from ..application.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("mas_vgfr_starting", version=settings.app_version, env=settings.app_env)

    # Initialize databases
    db = get_db()
    await db.init_db()
    logger.info("postgresql_initialized")

    mongo = get_mongo()
    await mongo.ensure_indexes()
    logger.info("mongodb_initialized")

    # Ensure Qdrant collection
    qdrant = get_qdrant()
    await qdrant.ensure_collection()
    logger.info("qdrant_collection_ready")

    logger.info("mas_vgfr_ready", host=settings.api_host, port=settings.api_port)

    yield  # Application runs

    logger.info("mas_vgfr_shutting_down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MAS-VGFR API",
        description=(
            "Multi-Agent System for Visually-Grounded Financial Reconciliation. "
            "Automates three-way match auditing with pixel-perfect evidence tracing."
        ),
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Request timing middleware
    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        response.headers["X-Process-Time-Ms"] = str(round((time.time() - start) * 1000, 2))
        return response

    # Routers
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(reconciliation.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")
    app.include_router(ws_router)

    # Root health check
    @app.get("/health", tags=["Health"])
    async def health():
        return {
            "status": "healthy",
            "service": "MAS-VGFR",
            "version": settings.app_version,
            "timestamp": datetime.utcnow().isoformat(),
        }

    return app


app = create_app()
