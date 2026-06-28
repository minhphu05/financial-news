"""
Keyword input providers.

The crawler is fed ``(stock, keyword)`` pairs through a small abstraction so
the *source of truth* for keywords can change without touching crawl logic.

Currently the active provider reads the ``stock`` + ``keyword`` tables in
PostgreSQL (:class:`PostgresKeywordProvider`). The Excel sheet is loaded into
those tables once via ``scripts/seed_scraper_db.py``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.scraper.storage.models import Keyword, Stock
from src.scraper.engine.types import KeywordRecord


class KeywordProvider(ABC):
    """Yields the ``(stock, keyword)`` pairs to crawl."""

    @abstractmethod
    def iter_keywords(
        self, tickers: Optional[Sequence[str]] = None
    ) -> Iterable[KeywordRecord]:
        """Yield active keyword records, optionally filtered by ticker.

        Args:
            tickers: Whitelist of ticker symbols. ``None`` (or empty) means all.
        """


class PostgresKeywordProvider(KeywordProvider):
    """Reads active keywords joined with their stock from PostgreSQL."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def iter_keywords(
        self, tickers: Optional[Sequence[str]] = None
    ) -> List[KeywordRecord]:
        whitelist = {t.upper() for t in tickers} if tickers else None

        stmt = (
            select(
                Stock.stock_id,
                Stock.ticker,
                Stock.company_name,
                Keyword.id,
                Keyword.keyword,
                Keyword.priority,
            )
            .join(Keyword, Keyword.stock_id == Stock.stock_id)
            .where(Stock.is_active.is_(True), Keyword.is_active.is_(True))
            .order_by(Stock.ticker, Keyword.priority.desc())
        )

        session: Session
        with self._session_factory() as session:
            rows = session.execute(stmt).all()

        records: List[KeywordRecord] = []
        for stock_id, ticker, company_name, keyword_id, keyword, priority in rows:
            if whitelist is not None and ticker.upper() not in whitelist:
                continue
            records.append(
                KeywordRecord(
                    stock_id=str(stock_id),
                    ticker=ticker,
                    company_name=company_name,
                    keyword=keyword,
                    keyword_id=str(keyword_id),
                    priority=priority,
                )
            )
        return records
