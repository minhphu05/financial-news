"""Pydantic request/response schemas for the chatbot API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body of ``POST /chat``."""

    question: str = Field(..., min_length=1, description="User question.")
    model: Optional[str] = Field(
        default=None,
        description=(
            "OpenRouter model ID to use. When omitted the server default is used. "
            "Allowed values are configured in OPENROUTER_AVAILABLE_MODELS."
        ),
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Number of chunks to retrieve.",
    )
    score_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score.",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Equality filters on chunk metadata (e.g. ticker_symbol).",
    )


class Citation(BaseModel):
    """Citation entry returned alongside an answer."""

    index: int
    score: float
    article_link: str
    title: Optional[str] = None
    post_date: Optional[str] = None
    ticker_symbol: Optional[str] = None


class ChatResponse(BaseModel):
    """Response payload returned by ``POST /chat``."""

    answer: str
    citations: List[Citation] = Field(default_factory=list)
    model: str = ""
    cache_hit: bool = False
    cache_score: Optional[float] = None
    latency_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """Response payload returned by ``GET /health``."""

    status: str = "ok"
    mongo_raw: int
    mongo_clean: int
    mongo_embedded: int
    qdrant_chunks: int


# ---------------------------------------------------------------------------
# Stocks & news
# ---------------------------------------------------------------------------
class StockOut(BaseModel):
    """Single VN50 stock returned by ``GET /stocks``."""

    ticker: str
    name_vi: str
    name_en: str
    sector: str
    article_count: int = 0


class StockListResponse(BaseModel):
    """List wrapper returned by ``GET /stocks``."""

    stocks: List[StockOut]
    total: int


class NewsArticleOut(BaseModel):
    """A single cleaned article returned to the frontend."""

    link: str
    title: Optional[str] = None
    post_date: Optional[str] = None
    summary: Optional[str] = None
    clean_text: Optional[str] = None
    ticker_symbol: Optional[str] = None
    ticker_name: Optional[str] = None
    keyword: Optional[str] = None
    source: Optional[str] = None
    char_count: Optional[int] = None
    cleaned_at: Optional[datetime] = None
    embedded_at: Optional[datetime] = None


class ModelsResponse(BaseModel):
    """Available LLM models returned by ``GET /models``."""

    models: List[str]
    default: str


class NewsListResponse(BaseModel):
    """Paginated news list returned by ``GET /news``."""

    items: List[NewsArticleOut]
    total: int
    skip: int
    limit: int
