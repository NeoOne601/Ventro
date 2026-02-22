"""
Secrets Management — Abstract provider with Vault, AWS SSM, and env fallback

Priority order at startup:
  1. HashiCorp Vault (if VAULT_ADDR + VAULT_TOKEN are set)
  2. AWS SSM Parameter Store (if AWS_REGION + AWS_SECRET_NAME are set)
  3. Environment variables (always available — used in dev)

Usage:
  Call `resolve_secrets(settings)` once at startup.
  Returns a new Settings instance with secrets populated from the provider.

Secrets fetched from vault/AWS (keys map to Settings field names):
  SECRET_KEY, DATABASE_URL, MONGO_URL, GROQ_API_KEY, FILE_ENCRYPTION_KEY,
  LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Which settings fields are considered "secrets" (fetched from Vault/AWS)
_SECRET_FIELDS = {
    "secret_key",
    "database_url",
    "mongo_url",
    "groq_api_key",
    "file_encryption_key",
    "langfuse_public_key",
    "langfuse_secret_key",
    "webhook_signing_key",
}


class SecretsProvider(ABC):
    @abstractmethod
    def get_secrets(self) -> dict[str, str]:
        """Return a flat dict of secret_name → value."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and reachable."""
        ...


class EnvSecretsProvider(SecretsProvider):
    """Read secrets from environment variables (dev / CI fallback)."""

    def is_available(self) -> bool:
        return True

    def get_secrets(self) -> dict[str, str]:
        secrets = {}
        for field in _SECRET_FIELDS:
            val = os.environ.get(field.upper(), "")
            if val:
                secrets[field] = val
        logger.debug("secrets_loaded_from_env", count=len(secrets))
        return secrets


class VaultSecretsProvider(SecretsProvider):
    """
    HashiCorp Vault — KV v2 secrets engine.
    Requires: VAULT_ADDR, VAULT_TOKEN (or VAULT_ROLE_ID + VAULT_SECRET_ID for AppRole)
    """

    def __init__(self, addr: str, token: str, secret_path: str) -> None:
        self._addr = addr.rstrip("/")
        self._token = token
        self._path = secret_path  # e.g. "secret/data/ventro/production"

    def is_available(self) -> bool:
        return bool(self._addr and self._token)

    def get_secrets(self) -> dict[str, str]:
        try:
            import httpx
            resp = httpx.get(
                f"{self._addr}/v1/{self._path}",
                headers={"X-Vault-Token": self._token},
                timeout=5.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json().get("data", {}).get("data", {})
            secrets = {
                k.lower(): str(v)
                for k, v in data.items()
                if k.lower() in _SECRET_FIELDS
            }
            logger.info("secrets_loaded_from_vault", count=len(secrets), path=self._path)
            return secrets
        except Exception as e:
            logger.error("vault_secrets_failed", error=str(e))
            raise


class AWSSecretsProvider(SecretsProvider):
    """
    AWS Secrets Manager — fetches a single JSON secret.
    Requires: AWS_REGION, AWS_SECRET_NAME (+ IAM role / env creds)
    """

    def __init__(self, region: str, secret_name: str) -> None:
        self._region = region
        self._name = secret_name

    def is_available(self) -> bool:
        return bool(self._region and self._name)

    def get_secrets(self) -> dict[str, str]:
        try:
            import boto3
            client = boto3.client("secretsmanager", region_name=self._region)
            resp = client.get_secret_value(SecretId=self._name)
            raw = resp.get("SecretString", "{}")
            data = json.loads(raw)
            secrets = {
                k.lower(): str(v)
                for k, v in data.items()
                if k.lower() in _SECRET_FIELDS
            }
            logger.info("secrets_loaded_from_aws", count=len(secrets), name=self._name)
            return secrets
        except Exception as e:
            logger.error("aws_secrets_failed", error=str(e))
            raise


def resolve_secrets(settings: Any) -> Any:
    """
    Attempt each configured provider in priority order.
    Merge fetched secrets into the settings object and return it.

    Called once at application startup in main.py lifespan.
    """
    provider_name = getattr(settings, "secrets_provider", "env")

    providers: list[SecretsProvider] = []

    if provider_name in ("vault", "auto") and getattr(settings, "vault_addr", ""):
        providers.append(VaultSecretsProvider(
            addr=settings.vault_addr,
            token=settings.vault_token,
            secret_path=settings.vault_secret_path,
        ))

    if provider_name in ("aws", "auto") and getattr(settings, "aws_region", ""):
        providers.append(AWSSecretsProvider(
            region=settings.aws_region,
            secret_name=settings.aws_secret_name,
        ))

    # Env provider is always the final fallback
    providers.append(EnvSecretsProvider())

    secrets: dict[str, str] = {}
    for provider in providers:
        if not provider.is_available():
            continue
        try:
            secrets = provider.get_secrets()
            break  # First successful provider wins
        except Exception:
            logger.warning("secrets_provider_failed_trying_next",
                           provider=type(provider).__name__)
            continue

    # Overlay secrets onto the settings object
    for field, value in secrets.items():
        if hasattr(settings, field) and value:
            object.__setattr__(settings, field, value)

    return settings
