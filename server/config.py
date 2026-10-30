from functools import lru_cache
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # In deployments, provide secrets through the environment or a secret manager.
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "server" / ".env")
        if ENVIRONMENT in {"development", "dev", "local"}
        else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Merchant Policy Assistant"
    environment: str = ENVIRONMENT
    log_level: str = "INFO"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    prompt_version: str = "v1"
    chroma_persist_directory: Path = PROJECT_ROOT / "server" / "data" / "chroma"
    document_directory: Path = PROJECT_ROOT / "server" / "data" / "documents"
    memory_database_path: Path = PROJECT_ROOT / "server" / "data" / "memory.sqlite3"
    chunk_size: int = 900
    chunk_overlap: int = 150
    retrieval_k: int = 8
    relevance_threshold: float = 0.35
    cors_origins: str = "http://localhost:8501"

    @field_validator(
        "chroma_persist_directory",
        "document_directory",
        "memory_database_path",
        mode="before",
    )
    @classmethod
    def resolve_data_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
