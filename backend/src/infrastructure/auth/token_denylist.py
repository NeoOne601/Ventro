"""
JWT Denylist — Redis-backed Access Token Revocation
Provides immediate revocation of access tokens on logout.

Problem: JWTs are stateless — even after logout, a stolen token remains valid
until its expiry (up to 60 minutes). The denylist fixes this by checking a
Redis sorted set on every authenticated request.

Implementation:
  - Each JWT contains a unique `jti` (JWT ID) claim
  - On logout, the jti is written to Redis with TTL = remaining token lifetime
  - get_current_user() checks the denylist before accepting any token
  - Redis sorted set allows O(log N) lookup and automatic expiry cleanup
  - Falls back gracefully if Redis is unavailable (logs warning, allows token)

Usage:
    from src.infrastructure.auth.token_denylist import TokenDenylist

    denylist = TokenDenylist(redis_url)
    await denylist.revoke(jti, expires_at_unix_timestamp)
    is_revoked = await denylist.is_revoked(jti)
"""
from __future__ import annotations

import time
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Redis key for the denylist sorted set (score = expiry timestamp)
_DENYLIST_KEY = "ventro:auth:token_denylist"


class TokenDenylist:
    """
    Redis-backed JWT access token denylist.
    Thread-safe; one instance shared across the application.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                logger.debug("token_denylist_redis_connected")
            except Exception as e:
                logger.error("token_denylist_redis_failed", error=str(e))
                self._redis = False
        return self._redis if self._redis is not False else None

    async def revoke(self, jti: str, expires_at: float) -> bool:
        """
        Add a JTI to the denylist until its natural expiry.
        Score = Unix timestamp at which the entry can be pruned.
        Returns True on success, False if Redis unavailable.
        """
        redis = await self._get_redis()
        if redis is None:
            logger.warning("token_denylist_revoke_skipped_no_redis", jti=jti)
            return False
        try:
            now = time.time()
            ttl = max(1, int(expires_at - now))
            pipe = redis.pipeline()
            pipe.zadd(_DENYLIST_KEY, {jti: expires_at})
            # Remove already-expired entries while we're here (amortised cleanup)
            pipe.zremrangebyscore(_DENYLIST_KEY, 0, now)
            pipe.expire(_DENYLIST_KEY, ttl + 60)  # Safety margin
            await pipe.execute()
            logger.info("token_revoked", jti=jti, ttl_seconds=ttl)
            return True
        except Exception as e:
            logger.error("token_denylist_revoke_error", jti=jti, error=str(e))
            return False

    async def is_revoked(self, jti: str) -> bool:
        """
        Check if a JTI is in the denylist.
        Returns False if Redis is unavailable (fail-open for availability;
        short token expiry is the secondary defence line).
        """
        redis = await self._get_redis()
        if redis is None:
            logger.warning("token_denylist_check_skipped_no_redis", jti=jti)
            return False  # Fail-open; log + rely on short expiry
        try:
            score = await redis.zscore(_DENYLIST_KEY, jti)
            if score is None:
                return False             # Not in denylist
            if score < time.time():
                # Entry expired but not yet cleaned up — treat as not revoked
                return False
            logger.warning("token_denylist_hit", jti=jti)
            return True
        except Exception as e:
            logger.error("token_denylist_check_error", jti=jti, error=str(e))
            return False  # Fail-open

    async def revoke_all_for_user(self, user_id: str, current_expiry: float) -> None:
        """
        'Logout all devices' — stores a user-level revocation timestamp.
        Any token issued before this timestamp is considered revoked.
        """
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            key = f"ventro:auth:user_revoked_at:{user_id}"
            ttl = max(1, int(current_expiry - time.time()))
            await redis.set(key, str(time.time()), ex=ttl + 300)
            logger.info("all_tokens_revoked_for_user", user_id=user_id)
        except Exception as e:
            logger.error("token_revoke_all_error", user_id=user_id, error=str(e))

    async def is_user_globally_revoked(self, user_id: str, token_issued_at: float) -> bool:
        """Returns True if the token was issued before the user's global revocation time."""
        redis = await self._get_redis()
        if redis is None:
            return False
        try:
            key = f"ventro:auth:user_revoked_at:{user_id}"
            val = await redis.get(key)
            if val is None:
                return False
            revoked_at = float(val)
            return token_issued_at < revoked_at
        except Exception:
            return False


# Module-level singleton — initialised in main.py lifespan
_denylist: Optional[TokenDenylist] = None


def get_denylist() -> TokenDenylist:
    """Return the shared TokenDenylist instance."""
    global _denylist
    if _denylist is None:
        from ...application.config import get_settings
        _denylist = TokenDenylist(get_settings().redis_url)
    return _denylist
