"""
Authentication Middleware + FastAPI Dependencies
Validates JWT on every protected request, checks the denylist, and injects User.

Role hierarchy for require_role():
  external_auditor < ap_analyst < ap_manager < finance_director < admin < developer < master
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from ...domain.auth_entities import Permission, Role, User, get_permissions
from ...infrastructure.auth.jwt_handler import verify_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Full role hierarchy (lowest → highest)
_ROLE_HIERARCHY = [
    Role.EXTERNAL_AUDITOR,
    Role.AP_ANALYST,
    Role.AP_MANAGER,
    Role.FINANCE_DIRECTOR,
    Role.ADMIN,
    Role.DEVELOPER,
    Role.MASTER,
]


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """
    FastAPI dependency: validates JWT + checks Redis denylist.
    Populates User from JWT claims (no DB round-trip on each request).
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

    # ── Denylist check — revoked tokens are rejected here ────────────────────
    jti = payload.get("jti")
    if jti:
        try:
            from ...infrastructure.auth.token_denylist import get_denylist
            denylist = get_denylist()
            if await denylist.is_revoked(jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Also check user-level global revocation (logout-all-devices)
            iat = payload.get("iat", 0)
            if await denylist.is_user_globally_revoked(payload["sub"], float(iat)):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="All sessions have been revoked. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Fail-open if denylist is unreachable

    user = User(
        id=payload["sub"],
        role=Role(payload.get("role", "ap_analyst")),
        organisation_id=payload.get("org", ""),
    )
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
    """Dependency factory: enforces a specific permission."""
    async def _check(user: Annotated[User, Depends(get_current_active_user)]) -> User:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return user
    return _check


def require_role(minimum_role: Role):
    """
    Dependency factory: enforces minimum role level.
    MASTER and DEVELOPER are at the top of the hierarchy.
    """
    async def _check(user: Annotated[User, Depends(get_current_active_user)]) -> User:
        try:
            user_level = _ROLE_HIERARCHY.index(user.role)
            required_level = _ROLE_HIERARCHY.index(minimum_role)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid role configuration")

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role.value}' or higher required",
            )
        return user
    return _check


# Convenience annotation aliases for route signatures
CurrentUser      = Annotated[User, Depends(get_current_active_user)]
AnalystOrAbove   = Annotated[User, Depends(require_role(Role.AP_ANALYST))]
ManagerOrAbove   = Annotated[User, Depends(require_role(Role.AP_MANAGER))]
DirectorOrAbove  = Annotated[User, Depends(require_role(Role.FINANCE_DIRECTOR))]
AdminOrAbove   = Annotated[User, Depends(require_role(Role.ADMIN))]
DeveloperOrAbove = Annotated[User, Depends(require_role(Role.DEVELOPER))]
MasterOnly       = Annotated[User, Depends(require_role(Role.MASTER))]
