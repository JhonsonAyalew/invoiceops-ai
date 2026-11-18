"""Runtime configuration. Everything comes from environment variables / .env (no secrets in code)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> Path | None:
    """Minimal .env loader (no extra dependency). Real environment variables always win.
    Windows paths work as-is: C:\\poppler\\Library\\bin (quotes optional, no escaping)."""
    here = Path(__file__).resolve()
    candidates = [Path(path)] if path else [Path.cwd() / ".env", here.parents[1] / ".env", here.parents[2] / ".env"]
    for p in candidates:
        if p.is_file():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                os.environ.setdefault(k.strip(), v)
            return p
    return None


def _split(v: str) -> list[str]:
    return [p.strip() for p in v.split("+") if p.strip()]


@dataclass(frozen=True)
class OcrSettings:
    model_dir: str | None = None  # folder containing PP-OCRv6_medium_det and PP-OCRv6_medium_rec
    device: str = "cpu"  # cpu | gpu
    poppler_path: str | None = None  # e.g. C:\poppler\Library\bin
    languages: tuple[str, ...] = ("eng",)  # informational: PP-OCRv6 Medium is one multilingual model
    timeout_seconds: int = 180
    dpi: int = 300
    min_native_chars_per_page: int = 40  # below this a page is treated as scanned

    @classmethod
    def from_env(cls) -> "OcrSettings":
        e = os.environ.get
        return cls(
            model_dir=e("PADDLE_MODEL_DIR") or None,
            device=(e("PADDLE_DEVICE", "cpu") or "cpu").lower(),
            poppler_path=e("POPPLER_PATH") or None,
            languages=tuple(_split(e("OCR_LANGUAGES", "eng"))) or ("eng",),
            timeout_seconds=int(e("OCR_TIMEOUT_SECONDS", "180")),
            dpi=int(e("OCR_DPI", "300")),
        )


@dataclass(frozen=True)
class AiSettings:
    """AI is optional. provider: none | ollama (local) | groq (cloud, needs per-job consent)."""

    provider: str = "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:1.5b-fast"
    groq_api_key: str = field(default="", repr=False)  # secret: environment only, never stored in the DB
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"  # fast; openai/gpt-oss-120b is stronger but slower
    timeout_seconds: float = 90.0
    max_chars: int = 24000  # text sent to a model is truncated to this

    @classmethod
    def from_env(cls) -> "AiSettings":
        e = os.environ.get
        return cls(
            provider=(e("AI_PROVIDER", "none") or "none").lower(),
            ollama_url=e("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=e("OLLAMA_MODEL", "qwen2.5-coder:1.5b-fast"),
            groq_api_key=e("GROQ_API_KEY", "") or "",
            groq_base_url=e("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            groq_model=e("GROQ_MODEL", "openai/gpt-oss-20b"),
            timeout_seconds=float(e("AI_TIMEOUT_SECONDS", "90")),
        )


@dataclass(frozen=True)
class AppSettings:
    database_url: str = "sqlite:///./data/invoiceops.db"  # production: postgresql+psycopg://user:pass@localhost/invoiceops
    data_dir: str = "./data"
    admin_token: str | None = None  # if set, required on every API call (X-Admin-Token header or ?token=)
    max_upload_mb: int = 50  # per PDF
    max_zip_files: int = 1000
    max_zip_uncompressed_mb: int = 2000
    retention_days: int = 0  # 0 = keep until deleted manually
    workers: int = 2
    sync_processing: bool = False  # tests: process inline
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def from_env(cls) -> "AppSettings":
        e = os.environ.get
        return cls(
            database_url=e("DATABASE_URL", cls.database_url),
            data_dir=e("DATA_DIR", cls.data_dir),
            admin_token=e("ADMIN_TOKEN") or None,
            max_upload_mb=int(e("MAX_UPLOAD_MB", "50")),
            max_zip_files=int(e("MAX_ZIP_FILES", "1000")),
            max_zip_uncompressed_mb=int(e("MAX_ZIP_UNCOMPRESSED_MB", "2000")),
            retention_days=int(e("RETENTION_DAYS", "0")),
            workers=max(1, int(e("PROCESSING_WORKERS", "2"))),
        )
