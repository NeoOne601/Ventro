"""
WebSocket Handler for Real-time Agent Progress Streaming
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


@router.websocket("/ws/reconciliation/{session_id}")
async def reconciliation_progress_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint for streaming real-time agent progress events.
    The frontend subscribes to this to display the agent pipeline visualization.
    """
    await websocket.accept()
    publisher = get_publisher()
    logger.info("websocket_connected", session_id=session_id)

    # Send existing events (catch up)
    existing = publisher.get_events(session_id)
    for event in existing:
        try:
            await websocket.send_json(event)
        except Exception:
            break

    # Subscribe to new events
    async def send_event(event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    publisher.subscribe(session_id, send_event)

    try:
        while True:
            # Keep connection alive with ping
            await asyncio.sleep(15)
            await websocket.send_json({"event": "ping", "session_id": session_id})
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
    finally:
        publisher.unsubscribe(session_id, send_event)
