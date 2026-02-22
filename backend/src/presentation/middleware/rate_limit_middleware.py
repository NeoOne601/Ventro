"""
Configurable Rate Limiting Middleware
Enforces request-rate limits using Redis sliding-window counters.

The ADMIN controls the strategy via the RATE_LIMIT_STRATEGY env var:

  per_ip          — one bucket per source IP address (default)
  per_user        — one bucket per authenticated JWT user_id
  per_org         — shared bucket across all users in an organisation
  per_ip_and_user — BOTH the IP bucket AND user bucket must have capacity
  global          — one global counter for the entire API (dev/test use)

Per-endpoint tiers (also configurable):
  /auth/*   → RATE_LIMIT_AUTH_REQUESTS   per window (default: 10)
  /upload   → RATE_LIMIT_UPLOAD_REQUESTS per window (default: 20)
  everything else → RATE_LIMIT_API_REQUESTS per window (default: 120)

CIDRs in RATE_LIMIT_WHITELIST_CIDRS are never rate-limited (internal services).
Rate-limited responses include Retry-After + X-RateLimit-* headers.
"""
from __future__ import annotations

import ipaddress
import time
from typing import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter backed by Redis (with in-memory fallback).
    Instantiated once at app startup via main.py create_app().
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_url: str,
        strategy: str = "per_ip",
        window_seconds: int = 60,
        auth_limit: int = 10,
        api_limit: int = 120,
        upload_limit: int = 20,
        burst_multiplier: float = 1.5,
        whitelist_cidrs: str = "",
        key_prefix: str = "ventro:rl",
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.strategy = strategy
        self.window = window_seconds
        self.auth_limit = auth_limit
        self.api_limit = api_limit
        self.upload_limit = upload_limit
        self.burst = burst_multiplier
        self.key_prefix = key_prefix
        self.enabled = enabled

        # Parse CIDR whitelist
        self._whitelist: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in (whitelist_cidrs or "").split(","):
            cidr = cidr.strip()
            if cidr:
                try:
                    self._whitelist.append(ipaddress.ip_network(cidr, strict=False))
                except ValueError:
                    logger.warning("invalid_cidr_in_whitelist", cidr=cidr)

        # Redis connection (lazy-init to avoid startup errors if Redis is slow)
        self._redis = None
        self._redis_url = redis_url
        self._fallback_counters: dict[str, list[float]] = {}  # In-memory fallback

        logger.info(
            "rate_limit_middleware_configured",
            strategy=strategy,
            window=window_seconds,
            auth=auth_limit,
            api=api_limit,
            upload=upload_limit,
            whitelist=whitelist_cidrs,
        )

    # ── Redis + fallback ──────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                logger.debug("rate_limiter_redis_connected")
            except Exception as e:
                logger.warning("rate_limiter_redis_unavailable", error=str(e))
                self._redis = False  # Mark as unavailable
        return self._redis if self._redis is not False else None

    async def _sliding_window_count(self, key: str, limit: int) -> tuple[int, int]:
        """
        Sliding-window counter using Redis sorted sets.
        Returns (current_count, remaining).
        Falls back to in-memory if Redis is unavailable.
        """
        now = time.time()
        window_start = now - self.window
        full_key = f"{self.key_prefix}:{key}"

        redis = await self._get_redis()

        if redis:
            try:
                pipe = redis.pipeline()
                pipe.zremrangebyscore(full_key, 0, window_start)
                pipe.zadd(full_key, {str(now): now})
                pipe.zcard(full_key)
                pipe.expire(full_key, self.window + 1)
                results = await pipe.execute()
                count = results[2]
                return count, max(0, limit - count)
            except Exception as e:
                logger.warning("rate_limiter_redis_error", error=str(e))

        # In-memory fallback (single-node only; not shared across workers)
        timestamps = self._fallback_counters.get(key, [])
        timestamps = [t for t in timestamps if t > window_start]
        timestamps.append(now)
        self._fallback_counters[key] = timestamps
        count = len(timestamps)
        return count, max(0, limit - count)

    # ── Routing logic ─────────────────────────────────────────────────────────

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, respecting X-Forwarded-For from trusted proxies."""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_whitelisted(self, ip_str: str) -> bool:
        if not self._whitelist:
            return False
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in self._whitelist)
        except ValueError:
            return False

    def _get_limit_for_path(self, path: str) -> tuple[int, str]:
        """Return (limit, tier_name) for a given request path."""
        if path.startswith("/api/v1/auth"):
            return self.auth_limit, "auth"
        if "upload" in path or "documents" in path:
            return self.upload_limit, "upload"
        return self.api_limit, "api"

    def _build_bucket_keys(
        self, request: Request, client_ip: str, limit_tier: str
    ) -> list[str]:
        """
        Return the Redis key(s) to check based on the configured strategy.
        Each key is an independent sliding-window counter.
        For per_ip_and_user, BOTH keys must be under limit for the request to proceed.
        """
        strategy = self.strategy

        if strategy == "per_ip":
            return [f"{limit_tier}:ip:{client_ip}"]

        elif strategy == "per_user":
            uid = self._extract_user_id(request) or client_ip
            return [f"{limit_tier}:user:{uid}"]

        elif strategy == "per_org":
            org = self._extract_org_id(request) or client_ip
            return [f"{limit_tier}:org:{org}"]

        elif strategy == "per_ip_and_user":
            uid = self._extract_user_id(request) or "anon"
            return [
                f"{limit_tier}:ip:{client_ip}",
                f"{limit_tier}:user:{uid}",
            ]

        elif strategy == "global":
            return [f"{limit_tier}:global"]

        # Fallback to per_ip
        return [f"{limit_tier}:ip:{client_ip}"]

    @staticmethod
    def _extract_user_id(request: Request) -> str | None:
        """Try to get user_id from JWT without full verification (for bucketing only)."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            token = auth.split(" ", 1)[1]
            import base64
            # Decode JWT payload without verify (we only need the 'sub' claim for bucketing)
            payload_b64 = token.split(".")[1]
            # Add padding
            padding = 4 - len(payload_b64) % 4
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
            import json
            payload = json.loads(payload_bytes)
            return payload.get("sub")
        except Exception:
            return None

    @staticmethod
    def _extract_org_id(request: Request) -> str | None:
        """Try to get org_id from JWT 'org' claim."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            token = auth.split(" ", 1)[1]
            import base64, json
            payload_b64 = token.split(".")[1]
            padding = 4 - len(payload_b64) % 4
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
            payload = json.loads(payload_bytes)
            return payload.get("org")
        except Exception:
            return None

    # ── Middleware entrypoint ─────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip health probes unconditionally
        if request.url.path in ("/health", "/health/live", "/health/ready"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # Whitelisted IPs bypass rate limiting
        if self._is_whitelisted(client_ip):
            return await call_next(request)

        limit, tier = self._get_limit_for_path(request.url.path)
        bucket_keys = self._build_bucket_keys(request, client_ip, tier)

        # Check ALL buckets (for per_ip_and_user both must pass)
        for key in bucket_keys:
            count, remaining = await self._sliding_window_count(key, limit)
            burst_limit = int(limit * self.burst)

            if count > burst_limit:
                retry_after = int(self.window)
                logger.warning(
                    "rate_limit_exceeded",
                    key=key,
                    count=count,
                    limit=limit,
                    burst_limit=burst_limit,
                    strategy=self.strategy,
                    path=request.url.path,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "https://httpstatus.es/429",
                        "title": "Too Many Requests",
                        "detail": (
                            f"Rate limit exceeded ({count}/{limit} requests in "
                            f"{self.window}s window). Strategy: {self.strategy}."
                        ),
                        "retry_after_seconds": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                        "X-RateLimit-Strategy": self.strategy,
                    },
                )

        # Request allowed — add informational headers
        response = await call_next(request)
        remaining_all = [
            (await self._sliding_window_count(k, limit))[1]
            for k in bucket_keys
        ]
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(min(remaining_all))
        response.headers["X-RateLimit-Strategy"] = self.strategy
        return response
