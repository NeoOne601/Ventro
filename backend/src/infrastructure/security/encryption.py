"""
File & Field Encryption Service — AES-256-GCM envelope encryption

Two-tier design:
  Tier 1: Master Key (MEK) — loaded from Vault/env at startup, never stored
  Tier 2: Per-file Data Encryption Key (DEK) — random 32 bytes per file,
           stored alongside the ciphertext encrypted with the MEK (envelope pattern)

File encryption format on disk:
  [4 bytes: DEK ciphertext length][DEK ciphertext][nonce][tag][ciphertext]

Field encryption (for MongoDB sensitive fields):
  base64(nonce + tag + ciphertext) — compact, roundtrip-safe

Why AES-256-GCM?
  AEAD — provides both confidentiality and authenticity in one pass.
  Standard for data-at-rest in SOC 2 / ISO 27001 workloads.
"""
from __future__ import annotations

import base64
import os
import struct
from pathlib import Path

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = structlog.get_logger(__name__)

_NONCE_BYTES = 12   # 96-bit nonce — NIST recommendation for GCM
_TAG_BYTES   = 16   # 128-bit authentication tag
_KEY_BYTES   = 32   # 256-bit key


def _load_master_key(raw: str) -> bytes:
    """
    Accept key as hex (64 chars) or base64 (44 chars).
    Raises ValueError if key is wrong length.
    """
    raw = raw.strip()
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        key = base64.b64decode(raw)
    if len(key) != _KEY_BYTES:
        raise ValueError(
            f"FILE_ENCRYPTION_KEY must be 32 bytes (64 hex chars or 44 base64 chars), "
            f"got {len(key)} bytes"
        )
    return key


class FileEncryptionService:
    """
    AES-256-GCM envelope encryption for files and individual fields.

    Instantiated once at startup from settings.file_encryption_key.
    If key is empty and app_env != production, encryption is skipped
    with a WARNING. In production mode, missing key raises RuntimeError.
    """

    def __init__(self, master_key_hex: str, is_production: bool = False) -> None:
        if not master_key_hex:
            if is_production:
                raise RuntimeError(
                    "FILE_ENCRYPTION_KEY must be set in production. "
                    "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            logger.warning(
                "encryption_disabled_no_key",
                msg="FILE_ENCRYPTION_KEY is not set — encryption skipped (dev mode only)",
            )
            self._mek: bytes | None = None
        else:
            self._mek = _load_master_key(master_key_hex)
            logger.info("file_encryption_service_ready")

    @property
    def enabled(self) -> bool:
        return self._mek is not None

    # ── File encryption (envelope pattern) ────────────────────────────────────

    def encrypt_file(self, plaintext_path: str | Path) -> Path:
        """
        Encrypt the file at *plaintext_path* in-place (overwrites).
        Returns the path (for chaining).

        Format: [4B: dek_enc_len][dek_enc][12B: nonce][plaintext_enc_with_tag]
        """
        if not self.enabled:
            return Path(plaintext_path)

        path = Path(plaintext_path)
        data = path.read_bytes()

        # Generate a per-file DEK
        dek = os.urandom(_KEY_BYTES)
        nonce = os.urandom(_NONCE_BYTES)

        # Encrypt the file content with the DEK
        aesgcm = AESGCM(dek)
        ct = aesgcm.encrypt(nonce, data, None)  # ct includes 16-byte GCM tag

        # Encrypt the DEK with the master key (envelope)
        mek_aesgcm = AESGCM(self._mek)          # type: ignore[arg-type]
        dek_nonce = os.urandom(_NONCE_BYTES)
        dek_enc = dek_nonce + mek_aesgcm.encrypt(dek_nonce, dek, None)

        # Write: header(dek) + nonce + ciphertext(+tag)
        payload = struct.pack(">I", len(dek_enc)) + dek_enc + nonce + ct
        path.write_bytes(payload)

        logger.debug("file_encrypted", path=str(path), size=len(data))
        return path

    def decrypt_file(self, encrypted_path: str | Path) -> bytes:
        """
        Decrypt a file previously encrypted by encrypt_file().
        Returns plaintext bytes (does NOT modify the file).
        """
        if not self.enabled:
            return Path(encrypted_path).read_bytes()

        path = Path(encrypted_path)
        payload = path.read_bytes()

        # Parse header
        (dek_enc_len,) = struct.unpack_from(">I", payload, 0)
        offset = 4
        dek_enc = payload[offset: offset + dek_enc_len]
        offset += dek_enc_len
        nonce = payload[offset: offset + _NONCE_BYTES]
        offset += _NONCE_BYTES
        ct = payload[offset:]

        # Decrypt DEK with master key
        dek_nonce = dek_enc[:_NONCE_BYTES]
        dek_ct    = dek_enc[_NONCE_BYTES:]
        mek_aesgcm = AESGCM(self._mek)           # type: ignore[arg-type]
        dek = mek_aesgcm.decrypt(dek_nonce, dek_ct, None)

        # Decrypt file content with DEK
        aesgcm = AESGCM(dek)
        return aesgcm.decrypt(nonce, ct, None)

    # ── Field encryption (for MongoDB sensitive values) ────────────────────────

    def encrypt_field(self, plaintext: str) -> str:
        """
        Encrypt a string field. Returns compact base64 string safe for MongoDB storage.
        Format: base64(nonce + ciphertext_with_tag)
        """
        if not self.enabled:
            return plaintext
        nonce = os.urandom(_NONCE_BYTES)
        aesgcm = AESGCM(self._mek)               # type: ignore[arg-type]
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt_field(self, ciphertext_b64: str) -> str:
        """
        Decrypt a field encrypted by encrypt_field().
        If encryption is disabled, returns the value as-is.
        """
        if not self.enabled:
            return ciphertext_b64
        raw = base64.b64decode(ciphertext_b64)
        nonce = raw[:_NONCE_BYTES]
        ct    = raw[_NONCE_BYTES:]
        aesgcm = AESGCM(self._mek)               # type: ignore[arg-type]
        return aesgcm.decrypt(nonce, ct, None).decode()

    # ── Utility ────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_key() -> str:
        """Generate a new 256-bit master key as a hex string. Use once at setup."""
        return os.urandom(_KEY_BYTES).hex()


# Module-level singleton — initialised in main.py lifespan
_service: FileEncryptionService | None = None


def get_encryption_service() -> FileEncryptionService:
    global _service
    if _service is None:
        from ...application.config import get_settings
        s = get_settings()
        _service = FileEncryptionService(
            master_key_hex=s.file_encryption_key,
            is_production=s.is_production,
        )
    return _service
