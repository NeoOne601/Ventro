"""
Password Handler
Secure bcrypt password hashing and verification.
Uses SHA-256 pre-hashing before bcrypt to avoid the 72-byte truncation bug
(bcrypt silently ignores bytes beyond position 72 — SHA-256 converts any
password to a 64-char hex digest, well within bcrypt's limit).
"""
from __future__ import annotations

import hashlib

import bcrypt


def _prehash(plain: str) -> str:
    """SHA-256 pre-hash to avoid bcrypt's 72-byte silent truncation."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost factor 12)."""
    return bcrypt.hashpw(_prehash(plain).encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(_prehash(plain).encode(), hashed.encode())
    except Exception:
        return False




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
