"""
MAS-VGFR Application Configuration
Centralized settings using pydantic-settings.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valid rate-limit strategy identifiers
RateLimitStrategy = Literal[
    "per_ip",          # One bucket per source IP (default, no auth needed)
    "per_user",        # One bucket per authenticated user_id (requires JWT)
    "per_org",         # One bucket per organisation_id (shared across all org users)
    "per_ip_and_user", # Both IP and user buckets must have capacity (strictest)
    "global",          # Single global counter — useful for dev/test
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "MAS-VGFR"
    app_version: str = "1.0.0"
    debug: bool = True
    secret_key: str = "change-me-in-production-must-be-32-chars-minimum"
    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://mas_vgfr_user:mas_vgfr_password@localhost:5432/mas_vgfr"

    # MongoDB
    mongo_url: str = "mongodb://mas_vgfr_user:mas_vgfr_password@localhost:27017/mas_vgfr_docs"
    mongo_db: str = "mas_vgfr_docs"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "mas_vgfr_docs"

    # Ollama (local self-hosted LLM)
    ollama_base_url: str = "http://localhost:11434"
    # qwen2.5 is multilingual (50+ langs) and near-equal to Mistral in English
    ollama_primary_model: str = "qwen2.5:7b-instruct"
    ollama_extraction_model: str = "qwen2.5:7b-instruct"
    ollama_drafting_model: str = "qwen2.5:7b-instruct"

    # Groq (cloud free-tier LLM — used when GROQ_API_KEY is set)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"  # best quality on Groq free tier

    # VLM (Visual Language Model — for scanned/image-only documents)
    vlm_enabled: bool = False  # Set True to enable Qwen2-VL for scanned pages
    vlm_model: str = "qwen2-vl:7b-instruct"  # ollama pull qwen2-vl:7b-instruct
    vlm_ollama_base_url: str = ""  # blank = same as ollama_base_url

    # Embeddings — multilingual-e5-large supports 100+ languages (1024 dims)
    # For English-only deployments: use all-MiniLM-L6-v2 (384 dims, faster)
    embedding_model: str = "intfloat/multilingual-e5-large-instruct"
    embedding_dimension: int = 1024

    # OCR
    ocr_language: str = "eng+ara+hin+chi_sim+jpn+kor+rus"  # Broad multilingual default
    ocr_dpi: int = 300  # 300 DPI recommended for Tesseract accuracy

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"
    langfuse_enabled: bool = False

    # Document Processing
    max_upload_size_mb: int = 50
    supported_formats: list[str] = Field(
        default=["pdf", "png", "jpg", "jpeg", "tiff", "docx", "xlsx", "xls", "csv"]
    )
    temp_upload_dir: str = "/tmp/mas_vgfr_uploads"

    # SAMR
    samr_enabled: bool = True
    samr_divergence_threshold: float = 0.85
    samr_perturbation_strength: float = 0.1

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Prometheus
    prometheus_enabled: bool = True
    metrics_port: int = 9090

    # ─── Rate Limiting ───────────────────────────────────────────────────────
    # Strategy the admin selects — controls HOW requests are bucketed
    rate_limit_strategy: RateLimitStrategy = "per_ip"
    # Sliding-window duration in seconds
    rate_limit_window_seconds: int = 60

    # Per-tier request limits (within the window above)
    # Auth endpoints (login, register) — tightest to prevent credential stuffing
    rate_limit_auth_requests: int = 10
    # General API endpoints
    rate_limit_api_requests: int = 120
    # Document upload — expensive; kept low
    rate_limit_upload_requests: int = 20

    # Burst allowance: how many extra requests are tolerated in the first second
    rate_limit_burst_multiplier: float = 1.5

    # Comma-separated CIDR ranges exempt from all rate limiting
    # e.g. "10.0.0.0/8,172.16.0.0/12" for internal services
    rate_limit_whitelist_cidrs: str = ""

    # Redis key prefix (allows multiple Ventro tenants sharing one Redis)
    rate_limit_redis_prefix: str = "ventro:rl"

    # Disable entirely (e.g. in test environments)
    rate_limit_enabled: bool = True

    # ─── LLM Fallback Chain ───────────────────────────────────────────────────
    # Ordered list of LLM providers to try on failure.
    # Valid values: "groq", "ollama", "rule_based"
    # "rule_based" = minimal regex extractor — always available, last resort
    llm_fallback_chain: list[str] = Field(
        default=["groq", "ollama", "rule_based"]
    )
    # Timeout (seconds) before trying the next provider in the chain
    llm_provider_timeout_seconds: float = 45.0
    # Max consecutive failures before a provider is temporarily marked unhealthy
    llm_max_failures_before_circuit_break: int = 3
    # How long (seconds) a circuit-broken provider is skipped before retry
    llm_circuit_break_recovery_seconds: int = 60

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
