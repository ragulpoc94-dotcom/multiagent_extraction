"""Application configuration loaded from environment variables / `.env`.

Secrets are wrapped in ``SecretStr`` so they never appear in logs or reprs.
Model IDs are never hardcoded: they come exclusively from MODEL_1..MODEL_3.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

MODEL_SLOTS = ("M1", "M2", "M3")


def _load_env_files() -> None:
    if load_dotenv is None:
        return
    for candidate in (REPO_DIR / ".env", BACKEND_DIR / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


class Settings(BaseModel):
    groq_api_key: SecretStr | None = None
    model_1: str | None = None
    model_2: str | None = None
    model_3: str | None = None

    # Orchestration / rate limiting
    max_concurrency: int = Field(default=3, ge=1, le=9)
    max_retries: int = Field(default=5, ge=0, le=10)
    backoff_base_seconds: float = 1.5
    backoff_max_seconds: float = 30.0
    request_timeout_seconds: float = 90.0
    requests_per_minute: int = Field(default=30, ge=1)

    # LLM generation
    max_output_tokens: int = 4096
    prompt_max_output_tokens: int = 3000
    temperature: float = 0.0

    # Document handling
    max_document_tokens: int = 6000  # per extraction call; larger documents are chunked
    ocr_language: str = "eng"
    ocr_dpi: int = 200
    min_chars_for_digital_page: int = 25
    max_upload_mb: int = 25

    # Paths & server
    data_dir: Path = BACKEND_DIR / "data"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models(self) -> dict[str, str | None]:
        return {"M1": self.model_1, "M2": self.model_2, "M3": self.model_3}

    @property
    def api_key_configured(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.get_secret_value().strip())

    def missing_configuration(self) -> list[str]:
        missing = []
        if not self.api_key_configured:
            missing.append("GROQ_API_KEY")
        for idx, slot in enumerate(MODEL_SLOTS, start=1):
            if not (self.models[slot] or "").strip():
                missing.append(f"MODEL_{idx}")
        return missing

    @classmethod
    def from_env(cls) -> "Settings":
        _load_env_files()
        key = os.getenv("GROQ_API_KEY")
        origins = os.getenv("CORS_ORIGINS")
        data = {
            "groq_api_key": SecretStr(key) if key else None,
            "model_1": (os.getenv("MODEL_1") or "").strip() or None,
            "model_2": (os.getenv("MODEL_2") or "").strip() or None,
            "model_3": (os.getenv("MODEL_3") or "").strip() or None,
            "max_concurrency": _int("MAX_CONCURRENCY", 3),
            "max_retries": _int("MAX_RETRIES", 5),
            "backoff_base_seconds": _float("BACKOFF_BASE_SECONDS", 1.5),
            "backoff_max_seconds": _float("BACKOFF_MAX_SECONDS", 30.0),
            "request_timeout_seconds": _float("REQUEST_TIMEOUT_SECONDS", 90.0),
            "requests_per_minute": _int("REQUESTS_PER_MINUTE", 30),
            "max_output_tokens": _int("MAX_OUTPUT_TOKENS", 4096),
            "prompt_max_output_tokens": _int("PROMPT_MAX_OUTPUT_TOKENS", 3000),
            "temperature": _float("TEMPERATURE", 0.0),
            "max_document_tokens": _int("MAX_DOCUMENT_TOKENS", 6000),
            "ocr_language": os.getenv("OCR_LANGUAGE", "eng"),
            "ocr_dpi": _int("OCR_DPI", 200),
            "max_upload_mb": _int("MAX_UPLOAD_MB", 25),
        }
        if os.getenv("DATA_DIR"):
            data["data_dir"] = Path(os.environ["DATA_DIR"])
        if origins:
            data["cors_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
        return cls(**data)


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
