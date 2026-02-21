"""
MAS-VGFR Application Configuration
Centralized settings using pydantic-settings.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ollama_primary_model: str = "mistral:7b-instruct"
    ollama_extraction_model: str = "mistral:7b-instruct"
    ollama_drafting_model: str = "mistral:7b-instruct"

    # Groq (cloud free-tier LLM — used when GROQ_API_KEY is set)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"  # best quality on Groq free tier

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"
    langfuse_enabled: bool = False

    # Document Processing
    max_upload_size_mb: int = 50
    supported_formats: list[str] = Field(default=["pdf", "png", "jpg", "jpeg", "tiff", "docx"])
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
