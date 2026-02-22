"""
WebSocket Handler — Real-time Celery → Browser Pipeline Progress Relay

Architecture:
  Celery task → publish_pipeline_event() → Redis pub/sub channel
  WebSocket handler → subscribes to Redis → pushes JSON to browser

The Redis channel name is: ventro:pipeline:{session_id}

Why Redis pub/sub?
  Celery workers run in a separate process (or even separate machine).
  The WebSocket connection lives in the FastAPI process.
  Redis is the only shared communication layer between them.

Fallback:
  If Redis is unavailable, falls back to the in-memory publisher
  (works in single-process dev mode, breaks in multi-worker deploys).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..dependencies import get_publisher

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["WebSocket"])

# Redis channel prefix for pipeline events
_CHANNEL_PREFIX = "ventro:pipeline:"


def _channel(session_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{session_id}"


async def publish_pipeline_event(session_id: str, event: dict[str, Any]) -> None:
    """
    Publish a pipeline progress event to Redis pub/sub.
    Called from Celery tasks after each agent stage completes.

    Also pushes to the in-memory publisher so dev mode still works.
    """
    # In-memory publisher (always — works in dev, also picked up by WS handler)
    publisher = get_publisher()
    publisher.publish(session_id, event)

    # Redis pub/sub (production — crosses process boundaries)
    try:
        from ...application.config import get_settings
        import redis.asyncio as aioredis
        settings = get_settings()
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis.publish(_channel(session_id), json.dumps(event))
        await redis.aclose()
    except Exception as e:
        logger.debug("redis_publish_failed_fallback_only", error=str(e))


@router.websocket("/ws/reconciliation/{session_id}")
async def reconciliation_progress_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint — bridges Celery pipeline events to the browser.

    On connect:
      1. Sends all buffered events (catch-up for reconnects)
      2. Subscribes to Redis pub/sub channel for live events
      3. Also watches the in-memory publisher for dev mode

    Messages format:
      { "event": "agent_start"|"agent_complete"|"ping"|"done"|"error",
        "session_id": "...",
        "agent": "extraction"|"quantitative"|...,
        "stage": "...",
        "progress": 0-100,
        "data": {...} }
    """
    await websocket.accept()
    publisher = get_publisher()
    logger.info("websocket_connected", session_id=session_id)

    # ── 1. Send buffered events (catch-up) ────────────────────────────────────
    for event in publisher.get_events(session_id):
        try:
            await websocket.send_json(event)
        except Exception:
            await websocket.close()
            return

    # ── 2. In-memory callback (dev mode + same-process events) ────────────────
    async def send_event(event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    publisher.subscribe(session_id, send_event)

    # ── 3. Redis pub/sub listener (production) ────────────────────────────────
    redis_task: asyncio.Task | None = None
    try:
        from ...application.config import get_settings
        import redis.asyncio as aioredis

        settings = get_settings()
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(_channel(session_id))

        async def _redis_listener() -> None:
            """Read Redis pub/sub messages and push to the WebSocket."""
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        await websocket.send_json(data)
                        # Stop listening once pipeline is done
                        if data.get("event") in ("done", "error"):
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("redis_listener_exited", error=str(e))
            finally:
                try:
                    await pubsub.unsubscribe(_channel(session_id))
                    await redis.aclose()
                except Exception:
                    pass

        redis_task = asyncio.create_task(_redis_listener())
        logger.info("websocket_redis_relay_active", session_id=session_id)

    except Exception as e:
        logger.warning(
            "websocket_redis_unavailable_using_memory",
            session_id=session_id,
            error=str(e),
        )

    # ── 4. Keep-alive + disconnect handler ────────────────────────────────────
    try:
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"event": "ping", "session_id": session_id})
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
    finally:
        publisher.unsubscribe(session_id, send_event)
        if redis_task and not redis_task.done():
            redis_task.cancel()
