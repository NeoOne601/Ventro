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
from .routes.auth_router import router as auth_router
from .routes.admin_router import router as admin_router
from .routes.samr_router import router as samr_router
from .websocket.progress import router as ws_router
from .dependencies import get_db, get_mongo, get_qdrant, get_publisher, get_llm
from .middleware.rate_limit_middleware import RateLimitMiddleware
from ..application.config import get_settings
from ..infrastructure.telemetry.otel_setup import setup_telemetry

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("mas_vgfr_starting", version=settings.app_version, env=settings.app_env)

    # Initialize OpenTelemetry tracing
    setup_telemetry(service_name="ventro-backend")

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
        title="Ventro — Auditable AI Reconciliation Engine",
        description=(
            "Multi-Agent System for Visually-Grounded Financial Reconciliation. "
            "Automates three-way match auditing with pixel-perfect evidence tracing "
            "and SAMR™ hallucination detection."
        ),
        version=settings.app_version,
        docs_url="/api/docs" if not settings.is_production else None,   # Disable Swagger in production
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ─── Middleware ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Configurable Rate Limiting (strategy, limits, CIDR whitelist all from settings)
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.redis_url,
        strategy=settings.rate_limit_strategy,
        window_seconds=settings.rate_limit_window_seconds,
        auth_limit=settings.rate_limit_auth_requests,
        api_limit=settings.rate_limit_api_requests,
        upload_limit=settings.rate_limit_upload_requests,
        burst_multiplier=settings.rate_limit_burst_multiplier,
        whitelist_cidrs=settings.rate_limit_whitelist_cidrs,
        key_prefix=settings.rate_limit_redis_prefix,
        enabled=settings.rate_limit_enabled,
    )

    # Request ID + timing middleware
    import uuid
    @app.middleware("http")
    async def request_id_and_timing(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.time()
        response = await call_next(request)
        elapsed = round((time.time() - start) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(elapsed)
        response.headers["X-Request-ID"] = request_id
        if elapsed > 5000:  # Warn on slow requests
            logger.warning("slow_request", path=request.url.path, elapsed_ms=elapsed, request_id=request_id)
        return response

    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    # ─── Routers ─────────────────────────────────────────────────────────────
    app.include_router(auth_router,      prefix="/api/v1")
    app.include_router(documents.router,  prefix="/api/v1")
    app.include_router(reconciliation.router, prefix="/api/v1")
    app.include_router(analytics.router,  prefix="/api/v1")
    app.include_router(admin_router,      prefix="/api/v1")   # /api/v1/admin/*
    app.include_router(samr_router,       prefix="/api/v1")   # /api/v1/samr/*
    app.include_router(ws_router)

    # ─── Health Endpoints ─────────────────────────────────────────────────────
    # Separate liveness and readiness for Kubernetes probes
    @app.get("/health/live", tags=["Health"], summary="Liveness probe")
    async def liveness():
        """Returns 200 if the process is alive. Used by K8s to decide restart."""
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe")
    async def readiness():
        """Returns 200 if all dependencies are reachable. Used by K8s to route traffic."""
        checks = {}
        try:
            db = get_db()
            await db.pool.fetchval("SELECT 1")
            checks["postgresql"] = "ok"
        except Exception as e:
            checks["postgresql"] = f"error: {e}"

        try:
            mongo = get_mongo()
            await mongo.client.admin.command("ping")
            checks["mongodb"] = "ok"
        except Exception as e:
            checks["mongodb"] = f"error: {e}"

        all_ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "ready" if all_ok else "degraded", "checks": checks}
        )

    @app.get("/health", tags=["Health"])   # Legacy alias
    async def health():
        return {"status": "healthy", "service": "Ventro", "version": settings.app_version,
                "timestamp": datetime.utcnow().isoformat()}

    # ─── Admin Endpoints ─────────────────────────────────────────────────────
    @app.get("/admin/llm-status", tags=["Admin"], summary="LLM provider circuit breaker status")
    async def llm_router_status():
        """
        Returns the health of each LLM provider in the fallback chain.
        Circuit breaker state: CLOSED (healthy) | OPEN (tripped) | recovering...
        Requires: AP_MANAGER+ (enforced via middleware in production).
        """
        try:
            llm = get_llm()
            from ..infrastructure.llm.llm_router import LLMRouter
            if isinstance(llm, LLMRouter):
                return {
                    "strategy": "fallback_chain",
                    "configured_chain": settings.llm_fallback_chain,
                    "providers": llm.provider_status(),
                    "timeout_seconds": settings.llm_provider_timeout_seconds,
                    "circuit_break_after_failures": settings.llm_max_failures_before_circuit_break,
                    "circuit_recovery_seconds": settings.llm_circuit_break_recovery_seconds,
                }
            return {"strategy": "single_provider", "provider": str(type(llm).__name__)}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/admin/rate-limit-config", tags=["Admin"], summary="Current rate limiting configuration")
    async def rate_limit_config():
        """Returns the active rate limiting configuration for admin inspection."""
        return {
            "enabled": settings.rate_limit_enabled,
            "strategy": settings.rate_limit_strategy,
            "window_seconds": settings.rate_limit_window_seconds,
            "limits": {
                "auth_requests": settings.rate_limit_auth_requests,
                "api_requests": settings.rate_limit_api_requests,
                "upload_requests": settings.rate_limit_upload_requests,
            },
            "burst_multiplier": settings.rate_limit_burst_multiplier,
            "whitelist_cidrs": settings.rate_limit_whitelist_cidrs or "(none)",
            "redis_prefix": settings.rate_limit_redis_prefix,
        }

    return app


app = create_app()
