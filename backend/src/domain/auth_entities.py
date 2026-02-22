"""
Authentication Domain Entities
Users, Roles, and Permissions for RBAC.

Role hierarchy (lowest → highest privilege):
  EXTERNAL_AUDITOR → AP_ANALYST → AP_MANAGER → FINANCE_DIRECTOR
                    → ADMIN → DEVELOPER → MASTER

MASTER           — Super-admin. Cross-org. All permissions. System config.
DEVELOPER        — Platform engineering. Debug/API/log access. No financial writes.
ADMIN            — Full org access, user management within org.
FINANCE_DIRECTOR — Business operations + analytics + audit log + billing.
AP_MANAGER       — Business approval, override SAMR findings, sign workpapers.
AP_ANALYST       — Day-to-day reconciliation (upload, create, view).
EXTERNAL_AUDITOR — Read-only access to sessions, findings, workpapers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    EXTERNAL_AUDITOR = "external_auditor"
    AP_ANALYST       = "ap_analyst"
    AP_MANAGER       = "ap_manager"
    FINANCE_DIRECTOR = "finance_director"
    ADMIN            = "admin"
    DEVELOPER        = "developer"    # Platform engineering
    MASTER           = "master"       # Super-admin; cross-org; all permissions


class Permission(str, Enum):
    # Document
    DOCUMENT_UPLOAD  = "document:upload"
    DOCUMENT_READ    = "document:read"
    DOCUMENT_DELETE  = "document:delete"

    # Session
    SESSION_CREATE   = "session:create"
    SESSION_READ     = "session:read"
    SESSION_DELETE   = "session:delete"

    # Finding
    FINDING_READ     = "finding:read"
    FINDING_OVERRIDE = "finding:override"

    # Workpaper
    WORKPAPER_READ   = "workpaper:read"
    WORKPAPER_EXPORT = "workpaper:export"
    WORKPAPER_SIGN   = "workpaper:sign"

    # Analytics
    ANALYTICS_READ   = "analytics:read"

    # Admin / User Management
    USER_MANAGE      = "user:manage"
    AUDIT_LOG_READ   = "audit_log:read"

    # Organisation
    ORG_MANAGE       = "org:manage"          # Create/modify orgs — MASTER only
    BILLING_READ     = "billing:read"

    # Developer
    DEBUG_ACCESS     = "debug:access"
    API_KEY_MANAGE   = "api_key:manage"

    # System
    SYSTEM_CONFIG    = "system:config"       # System-wide config — MASTER only


# Built incrementally to avoid forward-reference errors
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
    Permission.BILLING_READ,
}

ROLE_PERMISSIONS[Role.ADMIN] = {
    *ROLE_PERMISSIONS[Role.FINANCE_DIRECTOR],
    Permission.USER_MANAGE,
}

ROLE_PERMISSIONS[Role.DEVELOPER] = {
    # Developers can read all business data for debugging/support
    # but CANNOT perform financial writes (upload, create, sign, override)
    Permission.SESSION_READ,
    Permission.FINDING_READ,
    Permission.WORKPAPER_READ,
    Permission.ANALYTICS_READ,
    Permission.AUDIT_LOG_READ,
    Permission.DEBUG_ACCESS,
    Permission.API_KEY_MANAGE,
    Permission.USER_MANAGE,
}

ROLE_PERMISSIONS[Role.MASTER] = set(Permission)   # All permissions


def get_permissions(role: Role) -> set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    full_name: str = ""
    hashed_password: str = ""
    role: Role = Role.AP_ANALYST
    organisation_id: str = ""
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
        """MASTER and ADMIN bypass org scoping; all others are scoped to their org."""
        if self.role in (Role.MASTER, Role.ADMIN):
            return True
        return self.organisation_id == org_id


@dataclass
class Organisation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    slug: str = ""
    plan: str = "enterprise"
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
