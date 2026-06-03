"""Core pipeline stages with explicit data flow.

Instead of relying on MongoDB set-difference queries to discover
"unprocessed" articles, this module receives a concrete list of ``news_id``
values from the scrape step, fetches the raw documents by those IDs, and
processes them through each stage: clean → chunk → embed → Qdrant.

Every stage function is a pure-ish operation that accepts its dependencies
explicitly, making them testable without Prefect or global state.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.rag.config import Settings, get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.databases.qdrant_client import ChunkRecord
from src.rag.ingestion.chunker import TextChunker
from src.rag.ingestion.cleaner import TextCleaner
from src.rag.ingestion.embedder import VoyageAIEmbedder
from src.rag.ingestion.metrics import push_ingestion_metrics
from src.rag.ingestion.pipeline_logger import PipelineRunLogger
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class IngestionReport:
    """Summary of an ingestion run, returned to the Prefect flow."""

    cleaned: int = 0
    embedded: int = 0
    chunks_written: int = 0
    failed_ids: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp the report with the finish timestamp."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "cleaned": self.cleaned,
            "embedded": self.embedded,
            "chunks_written": self.chunks_written,
            "failed_ids": self.failed_ids,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ============================================================================
# Stage 1 — Clean: raw doc → clean doc
# ============================================================================
def fetch_raw_by_ids(
    mongo: MongoRepository,
    news_ids: List[str],
) -> List[Dict[str, Any]]:
    """Fetch raw article documents from MongoDB by their ``news_id``.

    The scraper stores raw articles with ``_id == news_id``.  This function
    returns every matching document so the caller can clean them.
    """
    return mongo.get_raw_by_ids(news_ids)


def clean_article(
    cleaner: TextCleaner,
    raw_doc: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Clean a single raw article and return a clean document.

    Returns ``None`` when the cleaned text is empty (article body was blank).
    """
    link = raw_doc.get("link") or raw_doc.get("url")
    if not link:
        logger.warning("Raw doc missing link; skipping.")
        return None

    try:
        clean_doc = cleaner.clean_article(raw_doc)
        if not clean_doc.get("clean_text"):
            logger.warning("Empty clean text for %s; skipping.", link)
            return None
        return clean_doc
    except Exception:  # noqa: BLE001
        logger.exception("Cleaning failed for %s.", link)
        return None


def run_clean_stage(
    mongo: MongoRepository,
    cleaner: TextCleaner,
    news_ids: List[str],
    run_log: PipelineRunLogger,
) -> tuple[List[str], Dict[str, str]]:
    """Clean every raw article identified by ``news_ids``.

    Each successful clean document is upserted into the clean collection.

    Parameters
    ----------
    news_ids : list[str]
        Article identifiers returned by the scrape step.

    Returns
    -------
    tuple[list[str], dict[str, str]]
        ``(cleaned_links, link_to_id)`` where ``cleaned_links`` are the
        ``link`` values of successfully cleaned articles, and ``link_to_id``
        maps each ``link`` to its ``news_id`` (for failure tracking).
        Links that were not found in the raw collection are excluded from
        both values.
    """
    raw_docs = fetch_raw_by_ids(mongo, news_ids)
    if not raw_docs:
        logger.info("No raw documents found for the given news_ids.")
        return [], {}

    link_to_id: Dict[str, str] = {}
    cleaned_links: List[str] = []

    for doc in raw_docs:
        link = doc.get("link", "")
        doc_id = doc.get("_id", "") or doc.get("news_id", "")
        if link:
            link_to_id[link] = doc_id

        t0 = time.monotonic()
        clean_doc = clean_article(cleaner, doc)
        dt = time.monotonic() - t0

        if clean_doc is None:
            run_log.clean(link=link, success=False, skipped_empty=True, duration_s=dt)
            continue

        mongo.upsert_clean(clean_doc)
        run_log.clean(link=link, success=True, duration_s=dt)
        cleaned_links.append(link)

    logger.info("Clean stage: %d / %d articles cleaned.", len(cleaned_links), len(raw_docs))
    return cleaned_links, link_to_id


# ============================================================================
# Stage 2 — Embed: clean doc → chunk → embed → Qdrant
# ============================================================================
def _embed_and_store(
    clean_doc: Dict[str, Any],
    chunker: TextChunker,
    embedder: VoyageAIEmbedder,
    qdrant: QdrantRepository,
    run_log: PipelineRunLogger,
    settings: Settings,
) -> int:
    """Chunk + embed + upsert a single cleaned article.

    Returns the number of chunks stored, or 0 on failure.
    """
    link: str = clean_doc["link"]
    text: str = clean_doc["clean_text"]
    cfg = settings.chunking

    # --- Chunking ---
    t0 = time.monotonic()
    chunks = chunker.split(text)
    chunk_duration = time.monotonic() - t0
    if not chunks:
        return 0

    run_log.chunk(
        link=link,
        num_chunks=len(chunks),
        total_chars=len(text),
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        duration_s=chunk_duration,
    )

    # --- Embedding ---
    est_tokens = sum(int(len(c) / 0.77) for c in chunks)
    t0 = time.monotonic()
    try:
        embeddings = embedder.embed_documents(chunks)
        embed_duration = time.monotonic() - t0
        num_batches = max(1, len(embedder._make_token_safe_batches(chunks)))
        run_log.embed(
            link=link,
            model=embedder._model,
            num_chunks=len(chunks),
            num_batches=num_batches,
            est_tokens=est_tokens,
            duration_s=embed_duration,
            success=True,
        )
    except Exception:  # noqa: BLE001
        run_log.embed(
            link=link,
            model=embedder._model,
            num_chunks=len(chunks),
            num_batches=0,
            est_tokens=est_tokens,
            duration_s=time.monotonic() - t0,
            success=False,
            error="embedding failed",
        )
        return 0

    # Build metadata payload for every chunk.
    metadata_base = {
        k: clean_doc.get(k)
        for k in ("title", "post_date", "ticker_symbol", "ticker_name", "keyword", "source")
        if clean_doc.get(k) is not None
    }

    records = [
        ChunkRecord(
            article_link=link,
            chunk_index=idx,
            content=chunk,
            embedding=emb,
            metadata={**metadata_base, "chunk_index": idx},
        )
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    # --- Qdrant Upsert ---
    t0 = time.monotonic()
    try:
        qdrant.upsert_chunks(records)
        run_log.upsert(
            link=link,
            num_points=len(records),
            collection=settings.qdrant.collection,
            duration_s=time.monotonic() - t0,
            success=True,
        )
    except Exception:  # noqa: BLE001
        run_log.upsert(
            link=link,
            num_points=0,
            collection=settings.qdrant.collection,
            duration_s=time.monotonic() - t0,
            success=False,
        )
        return 0

    return len(records)


def run_embed_stage(
    mongo: MongoRepository,
    qdrant: QdrantRepository,
    chunker: TextChunker,
    embedder: VoyageAIEmbedder,
    cleaned_links: List[str],
    run_log: PipelineRunLogger,
    settings: Settings,
) -> tuple[int, int]:
    """Chunk, embed, and store every cleaned article identified by ``cleaned_links``.

    Parameters
    ----------
    cleaned_links : list[str]
        ``link`` values of articles just cleaned in the previous stage.

    Returns
    -------
    tuple[int, int]
        ``(total_chunks, embedded_count)`` — total chunks written to Qdrant
        and number of articles that were successfully embedded.
    """
    if not cleaned_links:
        return 0, 0

    qdrant.ensure_collection()
    total_chunks = 0
    embedded_count = 0

    for link in cleaned_links:
        clean_doc = mongo.get_article(link)
        if clean_doc is None:
            logger.warning("Clean doc not found for link %s; skipping.", link)
            continue

        t0 = time.monotonic()
        num_chunks = _embed_and_store(clean_doc, chunker, embedder, qdrant, run_log, settings)

        if num_chunks > 0:
            mongo.mark_embedded(link, num_chunks)
            total_chunks += num_chunks
            embedded_count += 1
            logger.info(
                "Embedded %s: %d chunks in %.1fs.",
                link, num_chunks, time.monotonic() - t0,
            )
        else:
            logger.warning("Embedding produced no chunks for %s.", link)

    return total_chunks, embedded_count


# ============================================================================
# Orchestrator
# ============================================================================
def run_ingestion(
    mongo: MongoRepository,
    qdrant: QdrantRepository,
    embedder: VoyageAIEmbedder,
    news_ids: List[str],
    settings: Optional[Settings] = None,
    run_id: Optional[str] = None,
) -> IngestionReport:
    """Process a concrete list of newly scraped articles end-to-end.

    This is the primary entry point for the pipeline.  It:

    1. **Clean** — fetch raw docs by ``news_id``, clean them, upsert to clean collection.
    2. **Embed** — chunk each cleaned article, embed chunks, upsert vectors to Qdrant.

    Parameters
    ----------
    news_ids : list[str]
        ``news_id`` values of articles that were newly persisted during
        the scrape that preceded this call.  Only these articles are
        processed — not the entire backlog.

    Returns
    -------
    IngestionReport
        Run summary (cleaned / embedded counts, failures, timing).
    """
    effective_settings = settings or get_settings()
    effective_run_id = run_id or str(uuid.uuid4())
    run_log = PipelineRunLogger(run_id=effective_run_id)
    report = IngestionReport()

    logger.info(
        "Starting ingestion for %d news_id(s) (run_id=%s).",
        len(news_ids),
        effective_run_id,
    )

    if not news_ids:
        logger.info("No news_ids to process; skipping ingestion.")
        report.mark_done()
        return report

    cleaner = TextCleaner()
    chunker = TextChunker(effective_settings)

    # Stage 1: Clean
    cleaned_links, link_to_id = run_clean_stage(mongo, cleaner, news_ids, run_log)
    report.cleaned = len(cleaned_links)

    # Track failures: news_ids whose raw docs were found but cleaning failed.
    seen_links = set(cleaned_links)
    report.failed_ids = [
        nid for link, nid in link_to_id.items() if link not in seen_links
    ]

    # Track news_ids that had no raw document at all.
    found_ids = set(link_to_id.values()) | set(link_to_id.keys())
    not_found_ids = [
        nid for nid in news_ids
        if nid not in found_ids and nid not in link_to_id
    ]
    if not_found_ids:
        logger.warning(
            "Raw documents not found for %d news_id(s): %s",
            len(not_found_ids),
            not_found_ids[:10],
        )

    # Stage 2: Embed
    total_chunks, embedded_count = run_embed_stage(
        mongo, qdrant, chunker, embedder, cleaned_links, run_log, effective_settings,
    )
    report.embedded = embedded_count
    report.chunks_written = total_chunks

    report.mark_done()
    duration = (report.finished_at - report.started_at).total_seconds()

    logger.info(
        "Ingestion complete: %d cleaned, %d embedded, %d chunks in %.1fs.",
        report.cleaned,
        report.embedded,
        report.chunks_written,
        duration,
    )

    # Structured log event for Fluent Bit → Loki.
    run_log.pipeline_summary(
        cleaned=report.cleaned,
        embedded=report.embedded,
        chunks=report.chunks_written,
        failed=len(report.failed_ids),
        duration_s=duration,
    )

    # Prometheus metrics.
    push_ingestion_metrics(
        cleaned_articles=report.cleaned,
        embedded_articles=report.embedded,
        chunks_written=report.chunks_written,
        failed_count=len(report.failed_ids),
        duration_seconds=duration,
        settings=effective_settings,
    )

    return report
