"""
JWT Handler — Access token creation, verification, and refresh token generation.
Each access token now embeds a unique `jti` (JWT ID) for denylist-based revocation.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from jose import JWTError, jwt

from ...application.config import get_settings

logger = structlog.get_logger(__name__)

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str,           # user_id
    role: str,
    org_id: str,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with a unique jti for denylist support."""
    settings = get_settings()
    now = _utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub":  subject,
        "role": role,
        "org":  org_id,
        "iat":  now,
        "exp":  expire,
        "type": "access",
        "jti":  str(uuid.uuid4()),   # Unique token ID — used for denylist revocation
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token() -> tuple[str, str]:
    """
    Create a refresh token.
    Returns (raw_token, token_hash).
    Store only the hash in the DB; send raw to client.
    """
    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def verify_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT access token.
    Raises JWTError on invalid/expired tokens.
    NOTE: denylist check is NOT done here — it's done in get_current_user()
    because we need the async Redis call for that.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("Token is not an access token")
        return payload
    except JWTError as e:
        logger.warning("jwt_verification_failed", error=str(e))
        raise


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
