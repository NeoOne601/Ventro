"""
Password Handler
Secure bcrypt password hashing and verification.
"""
from __future__ import annotations

from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost factor 12)."""
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return _ctx.verify(plain, hashed)


def password_strength_ok(password: str) -> tuple[bool, str]:
    """
    Basic password strength validation.
    Returns (is_valid, reason).
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password):
        return False, "Password must contain at least one special character"
    return True, "ok"
