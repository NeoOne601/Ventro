"""
Authentication API Router
POST /api/v1/auth/register  — Create account
POST /api/v1/auth/login     — Obtain token pair
POST /api/v1/auth/refresh   — Rotate refresh token
POST /api/v1/auth/logout    — Revoke refresh token
GET  /api/v1/auth/me        — Get current user profile
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from ...domain.auth_entities import Role, TokenPair, User
from ...infrastructure.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    verify_access_token,
)
from ...infrastructure.auth.password_handler import (
    hash_password,
    password_strength_ok,
    verify_password,
)
from ...infrastructure.database.user_repository import UserRepository
from ..dependencies import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ─── Request / Response schemas ───────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12)
    org_slug: str = Field(min_length=2, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user_id: str
    role: str
    full_name: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organisation_id: str
    permissions: list[str]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db=Depends(get_db),
) -> dict:
    """
    Register a new user under an existing organisation.
    The organisation must already exist (created by admin or onboarding flow).
    """
    repo = UserRepository(db.pool)

    # Validate password strength
    ok, reason = password_strength_ok(body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Resolve organisation
    org = await repo.get_org_by_slug(body.org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organisation '{body.org_slug}' not found")

    # Check for existing user
    existing = await repo.get_user_by_email(body.email.lower(), org.id)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email.lower(),
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=Role.AP_ANALYST,   # Default role; admin can upgrade
        organisation_id=org.id,
    )
    created = await repo.create_user(user)

    await repo.append_audit_log(
        action="user.registered",
        user_id=created.id,
        org_id=org.id,
        resource_type="user",
        resource_id=created.id,
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "Account created", "user_id": created.id, "role": created.role.value}


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db=Depends(get_db),
) -> LoginResponse:
    """
    Authenticate with email + password.
    Returns JWT access token (1h) + refresh token (7d).
    org_slug is passed in the `client_id` field of OAuth2 form.
    """
    repo = UserRepository(db.pool)

    org_slug = form_data.client_id or "dev"
    org = await repo.get_org_by_slug(org_slug)
    if not org:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = await repo.get_user_by_email(form_data.username.lower(), org.id)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Issue tokens
    access_token = create_access_token(
        subject=user.id, role=user.role.value, org_id=user.organisation_id
    )
    raw_refresh, refresh_hash = create_refresh_token()

    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None

    await repo.store_refresh_token(user.id, refresh_hash, user_agent=ua, ip_address=ip)
    await repo.update_last_login(user.id)
    await repo.append_audit_log(
        action="user.login",
        user_id=user.id,
        org_id=org.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=ip,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role.value,
        full_name=user.full_name,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    db=Depends(get_db),
) -> LoginResponse:
    """Rotate refresh token — revokes the old one and issues a new pair."""
    repo = UserRepository(db.pool)
    token_hash = hash_refresh_token(body.refresh_token)
    record = await repo.get_refresh_token(token_hash)

    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await repo.get_user_by_id(str(record["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate: revoke old, issue new
    await repo.revoke_refresh_token(token_hash)
    access_token = create_access_token(
        subject=user.id, role=user.role.value, org_id=user.organisation_id
    )
    raw_refresh, refresh_hash = create_refresh_token()
    await repo.store_refresh_token(user.id, refresh_hash,
                                   user_agent=request.headers.get("user-agent"),
                                   ip_address=request.client.host if request.client else None)

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role.value,
        full_name=user.full_name,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db=Depends(get_db)) -> None:
    """Revoke refresh token (client should also discard the access token)."""
    repo = UserRepository(db.pool)
    await repo.revoke_refresh_token(hash_refresh_token(body.refresh_token))


@router.get("/me", response_model=UserProfile)
async def get_me(request: Request) -> UserProfile:
    """Get current user profile from the JWT in the Authorization header."""
    token = _extract_bearer(request)
    payload = verify_access_token(token)
    return UserProfile(
        id=payload["sub"],
        email="",   # Fetch from DB if needed
        full_name="",
        role=payload["role"],
        organisation_id=payload["org"],
        permissions=[p.value for p in _permissions_from_role(payload["role"])],
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth[7:]


def _permissions_from_role(role_str: str) -> set:
    from ...domain.auth_entities import Role, get_permissions
    try:
        return get_permissions(Role(role_str))
    except ValueError:
        return set()
