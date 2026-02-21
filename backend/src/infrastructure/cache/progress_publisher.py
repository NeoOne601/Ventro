"""
Progress Publisher - WebSocket Real-time Event Broadcasting
Publishes agent progress events via Redis PubSub.
"""
from __future__ import annotations

import json
import time
from typing import Any

import structlog
from redis.asyncio import Redis

from ...domain.interfaces import IProgressPublisher

logger = structlog.get_logger(__name__)


class RedisProgressPublisher(IProgressPublisher):
    """
    Publishes real-time progress events to Redis channel.
    WebSocket handler subscribes and streams events to browser.
    """

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        """Publish an event to the session's Redis channel."""
        try:
            redis = await self._get_redis()
            channel = f"mas_vgfr:session:{session_id}"
            message = json.dumps({
                **event,
                "session_id": session_id,
                "timestamp": time.time(),
            })
            await redis.publish(channel, message)
        except Exception as e:
            logger.warning("progress_publish_failed", session_id=session_id, error=str(e))

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()


class InMemoryProgressPublisher(IProgressPublisher):
    """
    In-memory progress publisher for development/testing.
    Stores events in a dict, retrieved by WebSocket handler.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._callbacks: dict[str, list] = {}

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        if session_id not in self._events:
            self._events[session_id] = []
        enriched = {**event, "session_id": session_id, "timestamp": time.time()}
        self._events[session_id].append(enriched)
        logger.debug("progress_event", session_id=session_id, event_type=event.get("event"))

        # Notify callbacks (WebSocket connections)
        for callback in self._callbacks.get(session_id, []):
            try:
                await callback(enriched)
            except Exception:
                pass

    def subscribe(self, session_id: str, callback: Any) -> None:
        if session_id not in self._callbacks:
            self._callbacks[session_id] = []
        self._callbacks[session_id].append(callback)

    def unsubscribe(self, session_id: str, callback: Any) -> None:
        if session_id in self._callbacks:
            self._callbacks[session_id] = [c for c in self._callbacks[session_id] if c != callback]

    def get_events(self, session_id: str) -> list[dict[str, Any]]:
        return self._events.get(session_id, [])
