"""Settings read from the environment (and from a local .env file)."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

ANTHROPIC = "anthropic"
OPENAI_COMPATIBLE = "openai_compatible"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class ConfigError(ValueError):
    """Raised when the environment doesn't allow the agent to start."""


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    effort: str
    data_dir: Path
    db_path: Path
    fixed_now: datetime | None
    rate_limit_per_minute: int = 10
    rate_limit_per_day: int = 300


def _default_db_path() -> Path:
    # Serverless functions can only write to the temporary directory (ADR-006).
    return Path(tempfile.gettempdir()) / "emporio.db" if os.getenv("VERCEL") else ROOT / "emporio.db"


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    provider = os.getenv("LLM_PROVIDER", OPENAI_COMPATIBLE).strip()
    if provider not in (ANTHROPIC, OPENAI_COMPATIBLE):
        raise ConfigError(f"LLM_PROVIDER must be '{ANTHROPIC}' or '{OPENAI_COMPATIBLE}', got '{provider}'.")

    model = os.getenv("LLM_MODEL", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    api_key = os.getenv("LLM_API_KEY", "").strip() or None
    if provider == ANTHROPIC:
        model = model or DEFAULT_ANTHROPIC_MODEL
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip() or None
    else:
        model = model or DEFAULT_GEMINI_MODEL
        base_url = base_url or GEMINI_BASE_URL
        api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip() or None

    fixed_now = os.getenv("AGENT_NOW", "").strip()
    return Settings(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        effort=os.getenv("LLM_EFFORT", "medium").strip(),
        data_dir=Path(os.getenv("DATA_DIR", ROOT / "data")),
        db_path=Path(os.getenv("DB_PATH", _default_db_path())),
        fixed_now=datetime.fromisoformat(fixed_now) if fixed_now else None,
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
        rate_limit_per_day=int(os.getenv("RATE_LIMIT_PER_DAY", "300")),
    )
