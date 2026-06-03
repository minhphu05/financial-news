"""
Centralized configuration loader for the scraper package.

All tunable knobs are sourced from the project ``.env`` file (loaded via
``python-dotenv``). No values are hardcoded inside business-logic modules;
they must all flow through :class:`ScraperSettings`.

Resolution rules
----------------
1. Environment variables already exported in the shell win over ``.env``.
2. ``.env`` at the project root is loaded automatically.
3. Sensible defaults are provided only for non-secret operational knobs
   (e.g. timeouts, log directories). Secrets (DB passwords) have *no*
   default and will raise on access if missing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# .env discovery
# ---------------------------------------------------------------------------
# Project root = three levels up from this file: src/scraper/config.py
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"

# Loading is idempotent; safe to call at import time.
load_dotenv(dotenv_path=ENV_FILE, override=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get(key: str, default: str | None = None, *, required: bool = False) -> str:
    """
    Read a string value from the environment.

    Args:
        key: Environment variable name.
        default: Fallback value if the variable is missing.
        required: When ``True`` and no value is present, raise ``RuntimeError``.

    Returns:
        The resolved string value.
    """
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise RuntimeError(
            f"Missing required environment variable '{key}'. "
            f"Please set it in {ENV_FILE} or your shell."
        )
    return value  # type: ignore[return-value]


def _get_int(key: str, default: int) -> int:
    """Read an integer environment variable with a default."""
    raw = os.getenv(key)
    return int(raw) if raw not in (None, "") else default


def _get_float(key: str, default: float) -> float:
    """Read a float environment variable with a default."""
    raw = os.getenv(key)
    return float(raw) if raw not in (None, "") else default


def _resolve_path(raw: str) -> Path:
    """Resolve a (possibly relative) path against the project root."""
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScraperSettings:
    """
    Immutable container for every knob the scraper consumes.

    Instances are produced by :func:`get_settings`, which is cached so the
    ``.env`` is parsed exactly once per process.
    """

    # ---- Source ----------------------------------------------------------
    source_name: str
    base_url: str
    search_url_template: str
    start_page: int
    max_pages: int

    # ---- HTTP client ----------------------------------------------------
    user_agent: str
    request_timeout: int
    max_retries: int
    retry_delay: float
    request_delay_min: float
    request_delay_max: float

    # ---- Filesystem -----------------------------------------------------
    raw_input_dir: Path
    logs_dir: Path

    # ---- PostgreSQL (metadata) -----------------------------------------
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_database: str
    metadata_table_name: str

    # ---- MongoDB (content) ---------------------------------------------
    mongo_uri: str
    mongo_db: str
    mongo_collection: str

    # ---- Incremental scraping -------------------------------------------
    consecutive_known_threshold: int
    """Stop crawling a keyword when this many consecutive already-seen
    articles are encountered. Prevents re-scraping entire history."""

    # ---- DSN helper -----------------------------------------------------
    @property
    def postgres_dsn(self) -> str:
        """SQLAlchemy-compatible PostgreSQL DSN built from discrete fields."""
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def _build_mongo_uri() -> str:
    """
    Build a MongoDB URI from individual env vars.

    Prefers a fully formed ``MONGO_URI`` if provided; otherwise composes one
    from ``MONGO_USER`` / ``MONGO_PASSWORD`` / ``MONGO_HOST`` / ``MONGO_PORT``.
    """
    direct = os.getenv("MONGO_URI")
    if direct:
        return direct

    user = _get("MONGO_USER", "")
    password = _get("MONGO_PASSWORD", "")
    host = _get("MONGO_HOST", "localhost")
    port = _get_int("MONGO_PORT", 27017)

    if user and password:
        return f"mongodb://{user}:{password}@{host}:{port}/?authSource=admin"
    return f"mongodb://{host}:{port}"


@lru_cache(maxsize=1)
def get_settings() -> ScraperSettings:
    """
    Build and cache the :class:`ScraperSettings` for the current process.

    Returns:
        A frozen settings object reflecting the current ``.env``.
    """
    settings = ScraperSettings(
        # Source
        source_name=_get("SOURCE_NAME", "cafef"),
        base_url=_get("CAFEF_BASE_URL", "https://cafef.vn"),
        search_url_template=_get(
            "CAFEF_SEARCH_URL_TEMPLATE",
            "https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}",
        ),
        start_page=_get_int("CAFEF_START_PAGE", 1),
        max_pages=_get_int("CAFEF_MAX_PAGES", 200),
        # HTTP client
        user_agent=_get(
            "CAFEF_USER_AGENT",
            "Mozilla/5.0 (compatible; FinancialNewsBot/1.0)",
        ),
        request_timeout=_get_int("SCRAPER_TIMEOUT", 30),
        max_retries=_get_int("SCRAPER_MAX_RETRIES", 3),
        retry_delay=_get_float("SCRAPER_DELAY", 2.0),
        request_delay_min=_get_float("CAFEF_REQUEST_DELAY_MIN", 0.5),
        request_delay_max=_get_float("CAFEF_REQUEST_DELAY_MAX", 1.5),
        # Filesystem
        raw_input_dir=_resolve_path(_get("RAW_INPUT_DIR", "./data/raw")),
        logs_dir=_resolve_path(_get("LOGS_DIR", "./logs/scraper")),
        # PostgreSQL
        pg_host=_get("METADATA_POSTGRES_HOST_EXTERNAL", os.getenv("METADATA_POSTGRES_HOST", "localhost")),
        pg_port=_get_int("METADATA_POSTGRES_EXTERNAL_PORT", 5434),
        pg_user=_get("METADATA_POSTGRES_USER", required=True),
        pg_password=_get("METADATA_POSTGRES_PASSWORD", required=True),
        pg_database=_get("METADATA_POSTGRES_DB", required=True),
        metadata_table_name=_get("METADATA_TABLE_NAME", "news_articles"),
        # MongoDB
        mongo_uri=_build_mongo_uri(),
        mongo_db=_get("MONGO_CONTENT_DB", "financial_news"),
        mongo_collection=_get("MONGO_CONTENT_COLLECTION", "articles_content"),
        # Incremental scraping
        consecutive_known_threshold=_get_int("SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD", 100),
    )

    # Make sure output directories exist so logging never fails late.
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
