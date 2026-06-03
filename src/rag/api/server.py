"""FastAPI server exposing the Financial News RAG chatbot.

Run locally::

    uvicorn src.rag.api.server:app --host 0.0.0.0 --port 8000

Endpoints
---------
* ``GET /health``           - liveness + database stats.
* ``GET /models``           - list available LLM models.
* ``GET /stocks``           - VN50 catalogue + article counts.
* ``GET /news``             - paginated cleaned articles (filter by ticker/search).
* ``GET /news/by-link``     - single article fetched by URL.
* ``POST /chat``            - ask the RAG chatbot (supports model selection).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.rag.agent import FinanceRAGChatbot, OpenRouterLLM
from src.rag.api.metrics import record_chat_metrics, record_user_feedback, setup_metrics
from src.rag.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    HealthResponse,
    ModelsResponse,
    NewsArticleOut,
    NewsListResponse,
    StockListResponse,
    StockOut,
)
from src.rag.caching import AsyncRAGService, SemanticCache
from src.rag.config import get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion import VoyageAIEmbedder
from src.rag.lib import VN50_STOCKS
from src.rag.retrieval import Retriever
from src.rag.utils import get_logger

logger = get_logger(__name__)


class AppState:
    """Container for long-lived singletons.

    These objects own database connections and API clients, so they live for
    the entire lifetime of the FastAPI process and are reused across requests.
    """

    mongo: Optional[MongoRepository] = None
    qdrant: Optional[QdrantRepository] = None
    chatbot: Optional[FinanceRAGChatbot] = None
    async_service: Optional[AsyncRAGService] = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise databases and the chatbot on startup; close on shutdown."""
    settings = get_settings()
    logger.info("Starting Financial News API (env=%s).", settings.env)

    state.mongo = MongoRepository(settings=settings)
    state.qdrant = QdrantRepository(settings=settings)
    state.qdrant.ensure_collection()

    embedder = VoyageAIEmbedder(settings=settings)
    retriever = Retriever(embedder=embedder, qdrant=state.qdrant, settings=settings)
    llm = OpenRouterLLM(settings=settings)
    state.chatbot = FinanceRAGChatbot(retriever=retriever, llm=llm, settings=settings)

    state.async_service = AsyncRAGService(
        chatbot=state.chatbot,
        embedder=embedder,
        cache=SemanticCache(settings=settings),
        settings=settings,
    )

    try:
        yield
    finally:
        logger.info("Stopping Financial News API.")
        if state.mongo is not None:
            state.mongo.close()
        if state.qdrant is not None:
            state.qdrant.close()


def get_chatbot() -> FinanceRAGChatbot:
    """FastAPI dependency returning the singleton chatbot."""
    if state.chatbot is None:
        raise HTTPException(status_code=503, detail="Chatbot is not initialised yet.")
    return state.chatbot


def get_async_service() -> AsyncRAGService:
    """FastAPI dependency returning the async + cache-aware chatbot service."""
    if state.async_service is None:
        raise HTTPException(status_code=503, detail="Chat service is not initialised yet.")
    return state.async_service


def _get_mongo() -> MongoRepository:
    """FastAPI dependency returning the singleton Mongo repository."""
    if state.mongo is None:
        raise HTTPException(status_code=503, detail="MongoDB is not initialised yet.")
    return state.mongo


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Financial News RAG Chatbot",
        version="0.3.0",
        description=(
            "Financial news RAG chatbot backed by "
            "Voyage AI embeddings + Qdrant + OpenRouter LLMs. "
            "Exposes the VN50 catalogue, paginated news, and a /chat endpoint."
        ),
        lifespan=lifespan,
    )

    settings = get_settings()
    extra_origins = getattr(settings, "cors_origins", None) or []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:4173",
            "http://localhost:3000",
            *extra_origins,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Liveness probe + database stats."""
        if state.mongo is None or state.qdrant is None:
            raise HTTPException(status_code=503, detail="Resources not ready.")
        mongo_stats = state.mongo.stats()
        qdrant_stats = state.qdrant.stats()
        return HealthResponse(
            status="ok",
            mongo_raw=mongo_stats["raw_count"],
            mongo_clean=mongo_stats["clean_count"],
            mongo_embedded=mongo_stats["embedded_count"],
            qdrant_chunks=qdrant_stats["chunk_count"],
        )

    @app.get("/models", response_model=ModelsResponse)
    def list_models() -> ModelsResponse:
        """Return the list of available OpenRouter LLM models.

        Clients use this endpoint to populate a model-selector dropdown in
        the UI without hard-coding the model list on the frontend.
        """
        cfg = get_settings().openrouter
        return ModelsResponse(
            models=sorted(cfg.available_models),
            default=cfg.default_model,
        )

    @app.get("/stocks", response_model=StockListResponse)
    def list_stocks(
        with_counts: bool = Query(
            default=True,
            description="If true, attach article counts for each ticker.",
        ),
        mongo: MongoRepository = Depends(_get_mongo),
    ) -> StockListResponse:
        """Return the VN50 catalogue with per-ticker article counts."""
        if with_counts:
            counts = {
                s.ticker: mongo.count_articles(ticker=s.ticker) for s in VN50_STOCKS
            }
        else:
            counts = {s.ticker: 0 for s in VN50_STOCKS}

        items = [
            StockOut(
                ticker=s.ticker,
                name_vi=s.name_vi,
                name_en=s.name_en,
                sector=s.sector,
                article_count=counts[s.ticker],
            )
            for s in VN50_STOCKS
        ]
        return StockListResponse(stocks=items, total=len(items))

    @app.get("/news", response_model=NewsListResponse)
    def list_news(
        ticker: Optional[str] = Query(default=None, description="Filter by ticker."),
        search: Optional[str] = Query(default=None, description="Title substring search."),
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
        mongo: MongoRepository = Depends(_get_mongo),
    ) -> NewsListResponse:
        """Return a page of cleaned articles."""
        items = mongo.list_articles(ticker=ticker, search=search, skip=skip, limit=limit)
        total = mongo.count_articles(ticker=ticker, search=search)
        return NewsListResponse(
            items=[NewsArticleOut.model_validate(item) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    @app.get("/news/by-link", response_model=NewsArticleOut)
    def get_news(
        link: str = Query(..., description="Article URL to fetch."),
        mongo: MongoRepository = Depends(_get_mongo),
    ) -> NewsArticleOut:
        """Return a single cleaned article by its URL."""
        doc = mongo.get_article(link)
        if doc is None:
            raise HTTPException(status_code=404, detail="Article not found.")
        return NewsArticleOut.model_validate(doc)

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        request: ChatRequest,
        service: AsyncRAGService = Depends(get_async_service),
    ) -> ChatResponse:
        """Ask the chatbot a question.

        Supports optional model selection via ``request.model``. The handler
        is async-aware: the query is embedded, looked up in the Redis semantic
        cache, and — on a miss — forwarded to the synchronous RAG path inside
        ``asyncio.to_thread``.
        """
        try:
            result = await service.ask(
                question=request.question,
                model=request.model,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
                filters=request.filters,
            )
        except ValueError as exc:
            # Raised by OpenRouterLLM when an invalid model ID is supplied.
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Capture end-to-end runtime and cache hit/miss for dashboarding.
        record_chat_metrics(
            model=getattr(result, "model", request.model or get_settings().openrouter.default_model),
            total_latency_s=max(result.latency_ms, 0.0) / 1000,
            cache_hit=result.cache_hit,
        )

        return ChatResponse(
            answer=result.answer,
            citations=[Citation(**c) for c in result.citations],
            model=getattr(result, "model", request.model or ""),
            cache_hit=result.cache_hit,
            cache_score=result.cache_score,
            latency_ms=result.latency_ms,
        )

    @app.post("/feedback")
    def submit_feedback(positive: bool = Query(..., description="True for 👍, False for 👎")):
        """Record user feedback for RAG quality tracking."""
        record_user_feedback(positive)
        return {"status": "ok"}

    return app


app = create_app()
setup_metrics(app)

