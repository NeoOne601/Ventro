"""
User Repository
Async PostgreSQL CRUD for users, refresh tokens, and organisations.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import structlog

from ...domain.auth_entities import Organisation, Role, User

logger = structlog.get_logger(__name__)


class UserRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ─── Users ────────────────────────────────────────────────────────────────

    async def create_user(self, user: User) -> User:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (id, organisation_id, email, full_name, hashed_password, role)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                user.id, user.organisation_id, user.email,
                user.full_name, user.hashed_password, user.role.value,
            )
        return _row_to_user(row)

    async def get_user_by_email(self, email: str, org_id: str) -> User | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1 AND organisation_id = $2 AND is_active = TRUE",
                email.lower(), org_id,
            )
        return _row_to_user(row) if row else None

    async def get_user_by_id(self, user_id: str) -> User | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1 AND is_active = TRUE", user_id
            )
        return _row_to_user(row) if row else None

    async def update_last_login(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = $1", user_id
            )

    # ─── Refresh Tokens ────────────────────────────────────────────────────────

    async def store_refresh_token(
        self,
        user_id: str,
        token_hash: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
        expires_days: int = 7,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent, ip_address)
                VALUES ($1, $2, $3, $4, $5::inet)
                """,
                user_id, token_hash, expires_at, user_agent, ip_address,
            )

    async def get_refresh_token(self, token_hash: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT rt.*, u.id as user_id_check FROM refresh_tokens rt
                JOIN users u ON rt.user_id = u.id
                WHERE rt.token_hash = $1
                  AND rt.revoked = FALSE
                  AND rt.expires_at > NOW()
                  AND u.is_active = TRUE
                """,
                token_hash,
            )
        return dict(row) if row else None

    async def revoke_refresh_token(self, token_hash: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
                token_hash,
            )

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        """Force logout from all devices (legacy name)."""
        await self.revoke_all_refresh_tokens(user_id)

    async def revoke_all_refresh_tokens(self, user_id: str) -> None:
        """
        Revoke every active refresh token for a user.
        Called by /auth/logout-all to invalidate all device sessions.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1", user_id
            )

    # ─── Organisations ─────────────────────────────────────────────────────────

    async def get_org_by_slug(self, slug: str) -> Organisation | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM organisations WHERE slug = $1 AND is_active = TRUE", slug
            )
        if not row:
            return None
        return Organisation(
            id=str(row["id"]),
            name=row["name"],
            slug=row["slug"],
            plan=row["plan"],
            is_active=row["is_active"],
            created_at=row["created_at"],
        )

    # ─── Audit Log ─────────────────────────────────────────────────────────────

    async def append_audit_log(
        self,
        action: str,
        user_id: str | None = None,
        org_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        import json
        async with self._pool.acquire() as conn:
            # Get hash of the last row for chain integrity
            prev = await conn.fetchrow(
                "SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1"
            )
            prev_hash: str | None = prev["row_hash"] if prev else None

            # Compute this row's hash
            raw = f"{action}|{user_id}|{org_id}|{resource_type}|{resource_id}|{json.dumps(details, default=str)}|{prev_hash}"
            row_hash = hashlib.sha256(raw.encode()).hexdigest()

            await conn.execute(
                """
                INSERT INTO audit_log
                  (organisation_id, user_id, action, resource_type, resource_id,
                   details, ip_address, prev_hash, row_hash)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6, $7::inet, $8, $9)
                """,
                org_id, user_id, action, resource_type, resource_id,
                json.dumps(details, default=str) if details else None,
                ip_address, prev_hash, row_hash,
            )


def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=str(row["id"]),
        organisation_id=str(row["organisation_id"]),
        email=row["email"],
        full_name=row["full_name"],
        hashed_password=row["hashed_password"],
        role=Role(row["role"]),
        is_active=row["is_active"],
        is_verified=row["is_verified"],
        created_at=row["created_at"],
        last_login_at=row.get("last_login_at"),
    )
