"""
Seed the scraper metadata database from the VN30 Excel sheet.

Loads ``data/raw/vn30.xlsx`` (columns: ``ticket_symbol``, ``company_name_vi``,
``company_name_en``, ``Keywords``) into ``core.stocks`` and
``scraping.keywords``, and registers known rows in ``scraping.sources``.
Idempotent — safe to run repeatedly; existing rows are left untouched.

Run once after ``docker compose up -d`` (and after applying the schema SQL)::

    python -m scripts.seed_scraper_db
    # or target a different sheet:
    python -m scripts.seed_scraper_db --xlsx data/raw/vn30.xlsx
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from src.scraper.config import get_settings
from src.scraper.storage.models import Keyword, Source, Stock
from src.utils.logger import get_logger

logger = get_logger("scripts.seed_scraper_db")

_TICKER_COLUMN = "ticket_symbol"
_COMPANY_COLUMN = "company_name_vi"
_KEYWORDS_COLUMN = "Keywords"

# News sources to register (only cafef is implemented today; the rest are
# pre-registered so metadata foreign keys are ready when their parsers land).
_SOURCES = [
    {"name": "cafef", "base_url": "https://cafef.vn", "language": "vi"},
    {"name": "vnexpress", "base_url": "https://vnexpress.net", "language": "vi"},
    {"name": "baomoi", "base_url": "https://baomoi.com", "language": "vi"},
    {"name": "thanhnien", "base_url": "https://thanhnien.vn", "language": "vi"},
    {"name": "tuoitre", "base_url": "https://tuoitre.vn", "language": "vi"},
    {"name": "vietstock", "base_url": "https://banggia.vietstock.vn", "language": "vi"},
]


def _coerce_keywords(raw: object) -> List[str]:
    """Normalize a Keywords cell (list or stringified list) into list[str]."""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (ValueError, SyntaxError):
            pass
    return []


def _load_sheet(xlsx_path: Path) -> pd.DataFrame:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Excel file not found: {xlsx_path}")
    df = pd.read_excel(xlsx_path, header=0)
    missing = {_TICKER_COLUMN, _COMPANY_COLUMN, _KEYWORDS_COLUMN} - set(df.columns)
    if missing:
        raise ValueError(f"{xlsx_path.name} is missing columns: {sorted(missing)}")
    df[_KEYWORDS_COLUMN] = df[_KEYWORDS_COLUMN].apply(_coerce_keywords)
    return df


def _exchange_from_index(index_name: str | None) -> str | None:
    if not index_name:
        return None
    normalized = index_name.upper().strip()
    if normalized == "HNX30":
        return "HNX"
    if normalized == "VN30":
        return "HOSE"
    return None


def _load_generated_keywords(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Generated keywords file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("items", []):
        ticker = str(item.get("ticker", "")).strip().upper()
        keywords = [str(value).strip() for value in item.get("keywords", []) if str(value).strip()]
        if ticker and keywords:
            mapping[ticker] = {
                "company_name": str(item.get("company_name") or ticker).strip(),
                "index_name": str(item.get("index_name") or "").strip().upper(),
                "keywords": keywords,
            }
    return mapping


def seed(xlsx_path: Path, *, keywords_json_path: Path | None = None) -> None:
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    df = _load_sheet(xlsx_path)
    logger.info("Loaded %s ticker rows from %s", len(df), xlsx_path.name)
    generated_keywords = _load_generated_keywords(keywords_json_path) if keywords_json_path else None
    if generated_keywords is not None:
        logger.info("Loaded generated keywords for %s ticker(s) from %s", len(generated_keywords), keywords_json_path)

    sources_added = stocks_added = keywords_added = 0

    with session_factory() as session:
        # --- sources ---
        for src in _SOURCES:
            stmt = (
                pg_insert(Source)
                .values(**src)
                .on_conflict_do_nothing(index_elements=[Source.name])
            )
            sources_added += session.execute(stmt).rowcount or 0
        session.commit()

        # --- stocks + keywords ---
        for _, row in df.iterrows():
            ticker = str(row[_TICKER_COLUMN]).strip().upper()
            company = str(row[_COMPANY_COLUMN]).strip()
            generated_item = generated_keywords.get(ticker) if generated_keywords is not None else None
            keywords = generated_item["keywords"] if generated_item is not None else row[_KEYWORDS_COLUMN]
            if not ticker:
                continue

            stmt = (
                pg_insert(Stock)
                .values(
                    ticker=ticker,
                    company_name=company,
                    exchange=_exchange_from_index(generated_item.get("index_name") if generated_item else "VN30"),
                )
                .on_conflict_do_nothing(index_elements=[Stock.ticker])
            )
            stocks_added += session.execute(stmt).rowcount or 0
            session.commit()

            stock_id = session.execute(
                select(Stock.stock_id).where(Stock.ticker == ticker)
            ).scalar_one()

            for priority, keyword in enumerate(keywords, start=1):
                kw_stmt = (
                    pg_insert(Keyword)
                    .values(
                        stock_id=stock_id,
                        keyword=keyword,
                        # Earlier keywords (e.g. the ticker itself) rank higher.
                        priority=max(1, len(keywords) - priority + 1),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[Keyword.stock_id, Keyword.keyword]
                    )
                )
                keywords_added += session.execute(kw_stmt).rowcount or 0
            session.commit()

        if generated_keywords is not None:
            existing_tickers = {str(value).strip().upper() for value in df[_TICKER_COLUMN]}
            for ticker, item in generated_keywords.items():
                if ticker in existing_tickers:
                    continue
                company = str(item.get("company_name") or ticker).strip()
                keywords = item.get("keywords", [])
                stmt = (
                    pg_insert(Stock)
                    .values(
                        ticker=ticker,
                        company_name=company,
                        exchange=_exchange_from_index(item.get("index_name")),
                    )
                    .on_conflict_do_nothing(index_elements=[Stock.ticker])
                )
                stocks_added += session.execute(stmt).rowcount or 0
                session.commit()

                stock_id = session.execute(
                    select(Stock.stock_id).where(Stock.ticker == ticker)
                ).scalar_one()

                for priority, keyword in enumerate(keywords, start=1):
                    kw_stmt = (
                        pg_insert(Keyword)
                        .values(
                            stock_id=stock_id,
                            keyword=keyword,
                            priority=max(1, len(keywords) - priority + 1),
                        )
                        .on_conflict_do_nothing(
                            index_elements=[Keyword.stock_id, Keyword.keyword]
                        )
                    )
                    keywords_added += session.execute(kw_stmt).rowcount or 0
                session.commit()

    engine.dispose()
    logger.success(
        "Seed complete: +%s sources, +%s stocks, +%s keywords.",
        sources_added,
        stocks_added,
        keywords_added,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.seed_scraper_db")
    parser.add_argument(
        "--xlsx",
        default="data/raw/vn30.xlsx",
        help="Path to the VN30 Excel sheet (relative to project root or absolute).",
    )
    parser.add_argument(
        "--keywords-json",
        default=None,
        help="Optional JSON produced by src.scraper.keyword_generation.gemini_keyword_generator.",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    xlsx_path = Path(args.xlsx)
    if not xlsx_path.is_absolute():
        xlsx_path = (project_root / xlsx_path).resolve()

    keywords_json_path = Path(args.keywords_json) if args.keywords_json else None
    if keywords_json_path is not None and not keywords_json_path.is_absolute():
        keywords_json_path = (project_root / keywords_json_path).resolve()

    try:
        seed(xlsx_path, keywords_json_path=keywords_json_path)
    except Exception as exc:
        logger.exception("Seeding failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
