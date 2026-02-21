"""
Authentication Middleware + FastAPI Dependency
Validates JWT on every protected request and injects the current user.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from ...domain.auth_entities import Permission, Role, User, get_permissions
from ...infrastructure.auth.jwt_handler import verify_access_token

# FastAPI security scheme — points to our login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """
    FastAPI dependency: extracts and validates the JWT, returns a lightweight
    User object (populated from claims — no DB round-trip on every request).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        payload = verify_access_token(token)
    except JWTError:
        raise credentials_exception

    user = User(
        id=payload["sub"],
        role=Role(payload.get("role", "ap_analyst")),
        organisation_id=payload.get("org", ""),
    )
    # Attach org_id to request state for downstream use
    request.state.org_id = user.organisation_id
    request.state.user_id = user.id
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return current_user


def require_permission(permission: Permission):
    """
    FastAPI dependency factory: enforces a specific permission.
    Usage: Depends(require_permission(Permission.SESSION_CREATE))
    """
    async def _check(
        user: Annotated[User, Depends(get_current_active_user)]
    ) -> User:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return user
    return _check


def require_role(minimum_role: Role):
    """
    FastAPI dependency factory: enforces a minimum role level.
    Role hierarchy: external_auditor < ap_analyst < ap_manager < finance_director < admin
    """
    _hierarchy = [
        Role.EXTERNAL_AUDITOR,
        Role.AP_ANALYST,
        Role.AP_MANAGER,
        Role.FINANCE_DIRECTOR,
        Role.ADMIN,
    ]

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)]
    ) -> User:
        try:
            user_level = _hierarchy.index(user.role)
            required_level = _hierarchy.index(minimum_role)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid role configuration")

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {minimum_role.value} or higher required",
            )
        return user
    return _check


# Convenience type aliases for route signatures
CurrentUser = Annotated[User, Depends(get_current_active_user)]
AnalystOrAbove = Annotated[User, Depends(require_role(Role.AP_ANALYST))]
ManagerOrAbove = Annotated[User, Depends(require_role(Role.AP_MANAGER))]
DirectorOrAbove = Annotated[User, Depends(require_role(Role.FINANCE_DIRECTOR))]
AdminOnly = Annotated[User, Depends(require_role(Role.ADMIN))]
