"""
Webhook Outbound Notification Service

Delivers HMAC-SHA256 signed payloads to registered org endpoints.
Retries 3× with exponential backoff (1s → 4s → 16s).
All deliveries logged to the webhook_deliveries table.

Security:
  - Each endpoint has its own HMAC secret (stored encrypted at rest)
  - Delivery includes X-Ventro-Signature: sha256=<hmac>
  - Receivers verify with their secret — prevents replay from 3rd parties

Events fired by default:
  reconciliation.completed  — pipeline finished (with results summary)
  finding.discrepancy       — one or more discrepancies found
  session.failed            — pipeline errored
  test.ping                 — manual test from admin UI
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# All supported event types
WEBHOOK_EVENTS = [
    "reconciliation.completed",
    "finding.discrepancy",
    "session.failed",
    "user.created",
    "user.role_changed",
    "test.ping",
]


class WebhookService:
    """
    Sends signed webhook payloads to registered endpoints for an organisation.
    Uses httpx async client for non-blocking delivery.
    """

    def __init__(
        self,
        db_pool: Any,        # asyncpg Pool
        signing_key: str,    # global fallback HMAC key (from settings)
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self._pool = db_pool
        self._global_key = signing_key
        self._timeout = timeout
        self._max_retries = max_retries

    # ── Public API ─────────────────────────────────────────────────────────────

    async def fire(
        self,
        event: str,
        org_id: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Fetch all active endpoints for org + event, then deliver asynchronously.
        Does NOT block the calling code — spawns background tasks.
        """
        endpoints = await self._get_endpoints(org_id, event)
        if not endpoints:
            return

        full_payload = {
            "id":       str(uuid.uuid4()),
            "event":    event,
            "org_id":   org_id,
            "ts":       datetime.now(timezone.utc).isoformat(),
            "data":     payload,
        }

        # Deliver concurrently, don't wait
        for ep in endpoints:
            asyncio.create_task(
                self._deliver_with_retry(ep, event, full_payload)
            )

    async def test_endpoint(self, endpoint_id: str, org_id: str) -> dict[str, Any]:
        """Send a test.ping to one specific endpoint. Returns delivery result."""
        async with self._pool.acquire() as conn:
            ep = await conn.fetchrow(
                "SELECT * FROM webhook_endpoints WHERE id = $1 AND org_id = $2",
                uuid.UUID(endpoint_id), uuid.UUID(org_id),
            )
        if not ep:
            return {"success": False, "error": "Endpoint not found"}

        payload = {
            "id":    str(uuid.uuid4()),
            "event": "test.ping",
            "org_id": org_id,
            "ts":    datetime.now(timezone.utc).isoformat(),
            "data":  {"message": "Ventro webhook test — this is a test.ping event"},
        }
        result = await self._deliver_once(dict(ep), payload)
        return result

    # ── Internal delivery mechanics ────────────────────────────────────────────

    async def _get_endpoints(
        self, org_id: str, event: str
    ) -> list[dict[str, Any]]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM webhook_endpoints
                    WHERE org_id = $1
                      AND is_active = TRUE
                      AND $2 = ANY(events)
                    """,
                    uuid.UUID(org_id), event,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("webhook_endpoint_fetch_failed", error=str(e))
            return []

    def _sign(self, secret: str, body: bytes) -> str:
        """Compute HMAC-SHA256 signature. Returns 'sha256=<hex>'."""
        key = (secret or self._global_key).encode()
        sig = hmac.new(key, body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    async def _deliver_once(
        self, endpoint: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = json.dumps(payload, default=str).encode()
        signature = self._sign(endpoint.get("secret", ""), body)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    endpoint["url"],
                    content=body,
                    headers={
                        "Content-Type":       "application/json",
                        "X-Ventro-Signature": signature,
                        "X-Ventro-Event":     payload["event"],
                        "X-Ventro-Delivery":  payload["id"],
                    },
                )
            return {"success": resp.is_success, "status_code": resp.status_code}
        except Exception as e:
            return {"success": False, "status_code": None, "error": str(e)}

    async def _deliver_with_retry(
        self,
        endpoint: dict[str, Any],
        event: str,
        payload: dict[str, Any],
    ) -> None:
        backoffs = [0, 1, 4, 16]  # immediate + backoffs between retries
        result: dict[str, Any] = {}

        for attempt in range(1, self._max_retries + 2):  # +2 = initial + retries
            if attempt > 1:
                delay = backoffs[min(attempt - 1, len(backoffs) - 1)]
                await asyncio.sleep(delay)

            result = await self._deliver_once(endpoint, payload)
            await self._log_delivery(endpoint, event, payload, result, attempt)

            if result.get("success"):
                logger.info(
                    "webhook_delivered",
                    endpoint=endpoint["url"], event=event, attempt=attempt,
                )
                return

            logger.warning(
                "webhook_delivery_failed",
                endpoint=endpoint["url"], event=event,
                attempt=attempt, error=result.get("error"),
                status_code=result.get("status_code"),
            )

        logger.error(
            "webhook_all_retries_exhausted",
            endpoint=endpoint["url"], event=event,
            max_retries=self._max_retries,
        )

    async def _log_delivery(
        self,
        endpoint: dict[str, Any],
        event: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        attempt: int,
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO webhook_deliveries
                      (endpoint_id, event, payload, status_code, attempt, delivered_at, error)
                    VALUES ($1, $2, $3, $4, $5, NOW(), $6)
                    """,
                    endpoint["id"],
                    event,
                    json.dumps(payload, default=str),
                    result.get("status_code"),
                    attempt,
                    result.get("error"),
                )
        except Exception as e:
            logger.error("webhook_delivery_log_failed", error=str(e))
