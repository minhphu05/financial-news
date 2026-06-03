"""Pydantic-based quality validators for scraped articles.

The scraper produces dictionaries that may contain partial / malformed
data (truncated bodies, missing dates, broken URLs, …). The validators
exposed here gate the **Bronze** layer: only documents that pass
:class:`ScrapedArticleV1` are persisted to MongoDB.

The Prefect ``scrape_quality_flow`` calls :func:`validate_articles`
between the network step and the persistence step, so invalid data
never leaks into the medallion lake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
_VN_DATE_RE = re.compile(
    r"^(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{4})"
    r"(?:[ T](?P<H>\d{1,2}):(?P<M>\d{2}))?"
)


class ScrapedArticleV1(BaseModel):
    """Bronze-layer contract for a single scraped article.

    The schema is intentionally **strict**: every field must conform or
    Pydantic raises :class:`ValidationError`. The Prefect quality task
    converts those rejections into a structured report rather than
    failing the whole batch.

    Attributes
    ----------
    link : HttpUrl
        Canonical article URL. Acts as the natural key in MongoDB.
    title : str
        Article title; must contain at least 5 non-whitespace characters.
    context : str
        Article body; must contain at least 120 characters once stripped.
    summary : Optional[str]
        Search-result snippet, when available.
    post_date : Optional[str]
        Publication date as displayed by CafeF (free-form Vietnamese).
        Validated for parseability if provided.
    is_magazine : Optional[bool]
        Whether the article uses the long-form "magazine" layout.
    source : str
        Source domain. Defaults to ``"cafef.vn"``.
    scraped_keyword : Optional[str]
        Keyword that produced this scrape (used as a lightweight tag).
    keyword : Optional[str]
        Alias for ``scraped_keyword`` (Mongo legacy field).
    page : Optional[int]
        Page index of the search result that surfaced this article.
    ticker_symbol : Optional[str]
        Optional ticker tag (filled in by downstream enrichers).
    ticker_name : Optional[str]
        Optional Vietnamese company name.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    link: HttpUrl
    title: str = Field(..., min_length=5)
    context: str = Field(..., min_length=120)
    summary: Optional[str] = None
    post_date: Optional[str] = None
    is_magazine: Optional[bool] = None
    source: str = Field(default="cafef.vn")
    scraped_keyword: Optional[str] = None
    keyword: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)
    ticker_symbol: Optional[str] = None
    ticker_name: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_has_letters(cls, value: str) -> str:
        """A title that's just punctuation/digits is rejected."""
        if not re.search(r"[\w\u00C0-\u1EF9]", value):
            raise ValueError("title must contain at least one letter")
        return value

    @field_validator("context")
    @classmethod
    def _context_is_not_boilerplate(cls, value: str) -> str:
        """Refuse bodies that look like CafeF placeholder pages."""
        lower = value.lower()
        if "không có kết quả" in lower or "404 not found" in lower:
            raise ValueError("context is a placeholder/error page")
        return value

    @field_validator("post_date")
    @classmethod
    def _post_date_is_parseable(cls, value: Optional[str]) -> Optional[str]:
        """Best-effort sanity check for CafeF's free-form date string."""
        if value is None or not value.strip():
            return None
        if _VN_DATE_RE.search(value):
            return value
        # Accept ISO strings too.
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError as exc:
            raise ValueError(f"unparseable post_date: {value!r}") from exc

    @field_validator("ticker_symbol")
    @classmethod
    def _ticker_uppercase(cls, value: Optional[str]) -> Optional[str]:
        """Tickers are always uppercase, A-Z + digits, ≤ 5 chars."""
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            return None
        if not re.fullmatch(r"[A-Z0-9]{2,5}", cleaned):
            raise ValueError(f"invalid ticker_symbol: {value!r}")
        return cleaned


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class QualityRejection:
    """A single failed validation, kept for observability + replays."""

    link: Optional[str]
    errors: List[str]
    payload: Dict[str, Any]


@dataclass
class QualityReport:
    """Aggregate stats returned by :func:`validate_articles`.

    Attributes
    ----------
    valid : list[dict]
        Articles that passed validation, serialised back to dicts so they
        can be inserted directly into MongoDB.
    rejections : list[QualityRejection]
        Articles that failed, paired with their validation errors.
    started_at, finished_at : datetime
        Timestamps for MLflow / Prefect reporting.
    """

    valid: List[Dict[str, Any]] = field(default_factory=list)
    rejections: List[QualityRejection] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @property
    def total(self) -> int:
        """Total number of articles seen (valid + rejected)."""
        return len(self.valid) + len(self.rejections)

    @property
    def pass_rate(self) -> float:
        """Fraction of inputs that passed validation, in ``[0, 1]``."""
        return len(self.valid) / self.total if self.total else 1.0

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary suitable for logs/UI."""
        return {
            "total": self.total,
            "valid": len(self.valid),
            "rejected": len(self.rejections),
            "pass_rate": round(self.pass_rate, 4),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "rejection_samples": [
                {"link": r.link, "errors": r.errors[:3]} for r in self.rejections[:5]
            ],
        }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def validate_articles(
    articles: Iterable[Dict[str, Any]],
) -> QualityReport:
    """Validate a batch of scraped articles.

    Parameters
    ----------
    articles : Iterable[dict]
        Raw scraper output.

    Returns
    -------
    QualityReport
        Bucketed valid / rejected outputs ready to be forwarded to Mongo
        or persisted as a quality artefact in MLflow.
    """
    report = QualityReport()
    for art in articles:
        link = str(art.get("link") or "")
        try:
            parsed = ScrapedArticleV1.model_validate(art)
        except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError is broad
            errors = _flatten_errors(exc)
            report.rejections.append(
                QualityRejection(link=link or None, errors=errors, payload=art)
            )
            continue

        payload = parsed.model_dump(mode="json")
        # Pydantic serialises HttpUrl as ``str``; keep the original link form.
        payload["link"] = str(parsed.link)
        report.valid.append(payload)

    report.finished_at = datetime.now(timezone.utc)
    return report


def _flatten_errors(exc: Exception) -> List[str]:
    """Turn a Pydantic ``ValidationError`` into a flat list of messages."""
    errors_attr = getattr(exc, "errors", None)
    if callable(errors_attr):
        try:
            entries: List[Tuple[str, str]] = [
                (".".join(str(p) for p in err.get("loc", ())), err.get("msg", ""))
                for err in errors_attr()
            ]
            return [f"{loc or '<root>'}: {msg}" for loc, msg in entries]
        except Exception:  # noqa: BLE001
            pass
    return [str(exc)]
