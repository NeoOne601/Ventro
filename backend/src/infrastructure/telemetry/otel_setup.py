"""
OpenTelemetry Setup
Distributed tracing across the multi-agent pipeline.
Instruments: FastAPI routes, LLM calls, DB queries, agent transitions.
"""
from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_tracer = None


def setup_telemetry(service_name: str = "ventro-backend") -> None:
    """
    Initialize OpenTelemetry with OTLP exporter.
    Falls back to no-op tracing if otel packages not installed.

    Set OTEL_EXPORTER_OTLP_ENDPOINT env var to point to your Jaeger/Grafana Tempo.
    e.g. OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    """
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("otel_configured", endpoint=endpoint)
        else:
            # Console exporter — good for development
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("otel_configured_console_fallback")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)

        # Auto-instrument FastAPI + asyncpg
        _auto_instrument()

    except ImportError:
        logger.warning(
            "otel_packages_not_installed",
            hint="pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc "
                 "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-asyncpg"
        )
        _tracer = _NoOpTracer()


def get_tracer():
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = _NoOpTracer()
    return _tracer


def _auto_instrument() -> None:
    """Auto-instrument FastAPI and asyncpg if packages available."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
        logger.debug("otel_fastapi_instrumented")
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        AsyncPGInstrumentor().instrument()
        logger.debug("otel_asyncpg_instrumented")
    except ImportError:
        pass


def agent_span(agent_name: str, session_id: str, **attributes):
    """
    Context manager for tracing individual agent invocations.
    Usage:
        with agent_span("ExtractionAgent", session_id, doc_type="invoice"):
            ...
    """
    tracer = get_tracer()
    return tracer.start_as_current_span(
        f"agent.{agent_name}",
        attributes={"session.id": session_id, "agent.name": agent_name, **attributes}
    )


def llm_span(model: str, prompt_tokens: int = 0):
    """Context manager for tracing individual LLM calls."""
    tracer = get_tracer()
    return tracer.start_as_current_span(
        "llm.generate",
        attributes={"llm.model": model, "llm.prompt_tokens": prompt_tokens}
    )


class _NoOpTracer:
    """Fallback when OTel is not installed — all calls are no-ops."""
    def start_as_current_span(self, name: str, **kwargs):
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()

    def start_span(self, name: str, **kwargs):
        return _NoOpSpan()


class _NoOpSpan:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def set_attribute(self, *args): pass
    def record_exception(self, *args): pass
    def end(self): pass
