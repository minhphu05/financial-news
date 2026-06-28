"""
Centralized configuration for the scraper package.

All tunable knobs are sourced from the project ``.env`` (loaded via
``python-dotenv``). Business-logic modules never read ``os.environ`` directly;
everything flows through :class:`ScraperSettings`.

Note: source-specific values (base URL, search-URL template) live inside the
individual parser classes under :mod:`src.scraper.sources`, not here, so the
core stays site-agnostic.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file: src/scraper/config.py
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"

# Idempotent; shell-exported variables win over the .env file.
load_dotenv(dotenv_path=ENV_FILE, override=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get(key: str, default: str | None = None, *, required: bool = False) -> str:
    """Read a string env var, optionally failing loudly when required."""
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise RuntimeError(
            f"Missing required environment variable '{key}'. "
            f"Set it in {ENV_FILE} or your shell."
        )
    return value  # type: ignore[return-value]


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw not in (None, "") else default


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw not in (None, "") else default


def _resolve_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScraperSettings:
    """Immutable container for every knob the scraper consumes."""

    # ---- Crawl behaviour ------------------------------------------------
    start_page: int
    max_pages: int
    consecutive_known_threshold: int
    crawler_version: str

    # ---- HTTP client ----------------------------------------------------
    user_agent: str
    request_timeout: int
    max_retries: int
    retry_delay: float
    request_delay_min: float
    request_delay_max: float

    # ---- Filesystem -----------------------------------------------------
    logs_dir: Path

    # ---- PostgreSQL (metadata) -----------------------------------------
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_database: str

    # ---- ADLS (content lake) -------------------------------------------
    adls_connection_string: str
    adls_account_name: str
    adls_account_key: str
    adls_filesystem: str
    adls_root_prefix: str

    @property
    def postgres_dsn(self) -> str:
        """SQLAlchemy-compatible PostgreSQL DSN."""
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


@lru_cache(maxsize=1)
def get_settings() -> ScraperSettings:
    """Build and cache the settings for the current process."""
    settings = ScraperSettings(
        # Crawl
        start_page=_get_int("SCRAPER_START_PAGE", 1),
        max_pages=_get_int("SCRAPER_MAX_PAGES", 200),
        consecutive_known_threshold=_get_int("SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD", 100),
        crawler_version=_get("SCRAPER_VERSION", "2.0.0"),
        # HTTP client
        user_agent=_get(
            "SCRAPER_USER_AGENT",
            "Mozilla/5.0 (compatible; FinancialNewsBot/2.0)",
        ),
        request_timeout=_get_int("SCRAPER_TIMEOUT", 30),
        max_retries=_get_int("SCRAPER_MAX_RETRIES", 3),
        retry_delay=_get_float("SCRAPER_DELAY", 2.0),
        request_delay_min=_get_float("SCRAPER_REQUEST_DELAY_MIN", 0.5),
        request_delay_max=_get_float("SCRAPER_REQUEST_DELAY_MAX", 1.5),
        # Filesystem
        logs_dir=_resolve_path(_get("LOGS_DIR", "./logs/scraper")),
        # PostgreSQL
        pg_host=_get(
            "METADATA_POSTGRES_HOST_EXTERNAL",
            os.getenv("METADATA_POSTGRES_HOST", "localhost"),
        ),
        pg_port=_get_int("METADATA_POSTGRES_EXTERNAL_PORT", 5434),
        pg_user=_get("METADATA_POSTGRES_USER", required=True),
        pg_password=_get("METADATA_POSTGRES_PASSWORD", required=True),
        pg_database=_get("METADATA_POSTGRES_DB", required=True),
        # ADLS
        adls_connection_string=_get("ADLS_CONNECTION_STRING", ""),
        adls_account_name=_get("ADLS_ACCOUNT_NAME", ""),
        adls_account_key=_get("ADLS_ACCOUNT_KEY", ""),
        adls_filesystem=_get("ADLS_FILESYSTEM", "financialnews-datalake"),
        adls_root_prefix=_get("ADLS_ROOT_PREFIX", "raw"),
    )

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
