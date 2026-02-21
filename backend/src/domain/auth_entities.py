"""
Authentication Domain Entities
Users, Roles, and Permissions for RBAC.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """Role hierarchy — each level inherits the permissions of levels below it."""
    EXTERNAL_AUDITOR = "external_auditor"   # Read-only: workpapers, sessions
    AP_ANALYST       = "ap_analyst"         # Upload docs, create sessions, view results
    AP_MANAGER       = "ap_manager"         # All analyst perms + approve/override findings
    FINANCE_DIRECTOR = "finance_director"   # All manager perms + analytics, exports
    ADMIN            = "admin"              # Full access, user management


class Permission(str, Enum):
    # Document permissions
    DOCUMENT_UPLOAD  = "document:upload"
    DOCUMENT_READ    = "document:read"
    DOCUMENT_DELETE  = "document:delete"

    # Session permissions
    SESSION_CREATE   = "session:create"
    SESSION_READ     = "session:read"
    SESSION_DELETE   = "session:delete"

    # Finding permissions
    FINDING_READ     = "finding:read"
    FINDING_OVERRIDE = "finding:override"   # AP Manager can override SAMR flags

    # Workpaper permissions
    WORKPAPER_READ   = "workpaper:read"
    WORKPAPER_EXPORT = "workpaper:export"
    WORKPAPER_SIGN   = "workpaper:sign"     # Digital attestation

    # Analytics
    ANALYTICS_READ   = "analytics:read"

    # Admin
    USER_MANAGE      = "user:manage"        # Create/disable users
    AUDIT_LOG_READ   = "audit_log:read"     # Read immutable audit trail


# Role → Permission mapping — built incrementally to avoid forward-reference errors
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {}

ROLE_PERMISSIONS[Role.EXTERNAL_AUDITOR] = {
    Permission.SESSION_READ,
    Permission.FINDING_READ,
    Permission.WORKPAPER_READ,
    Permission.WORKPAPER_EXPORT,
}

ROLE_PERMISSIONS[Role.AP_ANALYST] = {
    Permission.DOCUMENT_UPLOAD,
    Permission.DOCUMENT_READ,
    Permission.SESSION_CREATE,
    Permission.SESSION_READ,
    Permission.FINDING_READ,
    Permission.WORKPAPER_READ,
    Permission.ANALYTICS_READ,
}

ROLE_PERMISSIONS[Role.AP_MANAGER] = {
    *ROLE_PERMISSIONS[Role.AP_ANALYST],
    Permission.DOCUMENT_DELETE,
    Permission.SESSION_DELETE,
    Permission.FINDING_OVERRIDE,
    Permission.WORKPAPER_EXPORT,
    Permission.WORKPAPER_SIGN,
}

ROLE_PERMISSIONS[Role.FINANCE_DIRECTOR] = {
    *ROLE_PERMISSIONS[Role.AP_MANAGER],
    Permission.AUDIT_LOG_READ,
}

ROLE_PERMISSIONS[Role.ADMIN] = set(Permission)   # All permissions



def get_permissions(role: Role) -> set[Permission]:
    """Get all permissions for a given role."""
    return ROLE_PERMISSIONS.get(role, set())


@dataclass
class User:
    """Domain model for an authenticated user."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    full_name: str = ""
    hashed_password: str = ""
    role: Role = Role.AP_ANALYST
    organisation_id: str = ""     # Multi-tenancy: all data scoped to org
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login_at: datetime | None = None

    @property
    def permissions(self) -> set[Permission]:
        return get_permissions(self.role)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    def can_access_org(self, org_id: str) -> bool:
        return self.organisation_id == org_id or self.role == Role.ADMIN


@dataclass
class Organisation:
    """Multi-tenant organisation entity."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    slug: str = ""                # URL-safe identifier
    plan: str = "enterprise"
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TokenPair:
    """JWT access + refresh token pair returned on login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600        # seconds
