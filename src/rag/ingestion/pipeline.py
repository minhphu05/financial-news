"""End-to-end ingestion pipeline (cleaning → chunking → embedding → load).

This module orchestrates :class:`TextCleaner`, :class:`TextChunker`,
:class:`VoyageAIEmbedder`, :class:`MongoRepository`, and
:class:`QdrantRepository` so that a single call moves data from the raw
Mongo collection all the way into Qdrant.

It is invoked by the Prefect ``ingest_flow`` defined in :mod:`src.flows`.
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


@dataclass
class IngestionReport:
    """Summary of an ingestion run, returned to the Prefect flow."""

    cleaned_articles: int = 0
    embedded_articles: int = 0
    chunks_written: int = 0
    failed_links: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp the report with the finish timestamp."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "cleaned_articles": self.cleaned_articles,
            "embedded_articles": self.embedded_articles,
            "chunks_written": self.chunks_written,
            "failed_links": self.failed_links,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class IngestionPipeline:
    """Run the cleaning + embedding pipeline end-to-end.

    Parameters
    ----------
    mongo : MongoRepository
        Mongo repository (raw + clean collections).
    qdrant : QdrantRepository
        Qdrant vector store repository.
    embedder : VoyageAIEmbedder
        Voyage AI embedding generator.
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    """

    def __init__(
        self,
        mongo: MongoRepository,
        qdrant: QdrantRepository,
        embedder: VoyageAIEmbedder,
        settings: Optional[Settings] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self._mongo = mongo
        self._qdrant = qdrant
        self._embedder = embedder
        self._settings = settings or get_settings()
        self._cleaner = TextCleaner()
        self._chunker = TextChunker(self._settings)
        self._run_id = run_id or str(uuid.uuid4())
        self._run_log = PipelineRunLogger(run_id=self._run_id)

    # -- public API ---------------------------------------------------------
    def run(self, max_articles: Optional[int] = None) -> IngestionReport:
        """Run the full pipeline.

        The pipeline executes two stages:

        1. **Cleaning** – read every raw article that has no entry in the
           clean collection, normalise it, and upsert the clean document.
        2. **Embedding** – read every clean article that has no
           ``embedded_at`` field, chunk it, generate embeddings, push them
           to PGVector, and mark the article as embedded.

        Parameters
        ----------
        max_articles : Optional[int]
            Hard cap on the number of articles processed in each stage.
            Helpful for safety-rails in the orchestrator.

        Returns
        -------
        IngestionReport
            Run summary.
        """
        report = IngestionReport()
        self._qdrant.ensure_collection()

        # 1. Clean stage
        for i, raw in enumerate(self._mongo.iter_raw_not_cleaned()):
            if max_articles is not None and i >= max_articles:
                break
            t0 = time.monotonic()
            link = raw.get("link", "")
            try:
                clean_doc = self._cleaner.clean_article(raw)
                dt = time.monotonic() - t0
                if not clean_doc["clean_text"]:
                    logger.warning("Skipping empty article: %s", link)
                    self._run_log.clean(link=link, success=False, skipped_empty=True, duration_s=dt)
                    continue
                self._mongo.upsert_clean(clean_doc)
                self._run_log.clean(link=link, success=True, duration_s=dt)
                report.cleaned_articles += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Cleaning failed for %s: %s", link, exc)
                self._run_log.clean(link=link, success=False, duration_s=time.monotonic() - t0)
                report.failed_links.append(link)

        # 2. Embed stage
        for i, clean in enumerate(self._mongo.iter_clean_not_embedded()):
            if max_articles is not None and i >= max_articles:
                break
            try:
                num_chunks = self._embed_and_store(clean)
                self._mongo.mark_embedded(clean["link"], num_chunks)
                report.embedded_articles += 1
                report.chunks_written += num_chunks
            except Exception as exc:  # noqa: BLE001
                logger.exception("Embedding failed for %s: %s", clean.get("link"), exc)
                report.failed_links.append(clean.get("link", ""))

        report.mark_done()
        logger.info("Ingestion finished: %s", report.as_dict())

        duration = (
            (report.finished_at - report.started_at).total_seconds()
            if report.finished_at
            else 0.0
        )

        # Emit structured pipeline summary for Fluent Bit → Loki.
        pending_clean = self._mongo.count_raw_not_cleaned()
        pending_embed = self._mongo.count_clean_not_embedded()
        self._run_log.pipeline_summary(
            cleaned=report.cleaned_articles,
            embedded=report.embedded_articles,
            chunks=report.chunks_written,
            failed=len(report.failed_links),
            duration_s=duration,
            pending_clean=pending_clean,
            pending_embed=pending_embed,
        )

        # Push metrics to Prometheus Pushgateway for Grafana monitoring.
        push_ingestion_metrics(
            cleaned_articles=report.cleaned_articles,
            embedded_articles=report.embedded_articles,
            chunks_written=report.chunks_written,
            failed_count=len(report.failed_links),
            duration_seconds=duration,
            settings=self._settings,
        )

        return report

    # -- internals ----------------------------------------------------------
    def _embed_and_store(self, clean_doc: Dict[str, Any]) -> int:
        """Chunk + embed + upsert a single cleaned article.

        Emits structured log events for the chunk, embed, and upsert stages
        so Fluent Bit can forward them to Loki for Grafana dashboards.

        Returns the number of chunks stored.
        """
        link: str = clean_doc["link"]
        text: str = clean_doc["clean_text"]
        cfg = self._settings.chunking

        # --- Chunking ---
        t0 = time.monotonic()
        chunks = self._chunker.split(text)
        chunk_duration = time.monotonic() - t0
        if not chunks:
            return 0
        self._run_log.chunk(
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
            embeddings = self._embedder.embed_documents(chunks)
            embed_duration = time.monotonic() - t0
            num_batches = max(1, len(self._embedder._make_token_safe_batches(chunks)))
            self._run_log.embed(
                link=link,
                model=self._embedder._model,
                num_chunks=len(chunks),
                num_batches=num_batches,
                est_tokens=est_tokens,
                duration_s=embed_duration,
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._run_log.embed(
                link=link,
                model=self._embedder._model,
                num_chunks=len(chunks),
                num_batches=0,
                est_tokens=est_tokens,
                duration_s=time.monotonic() - t0,
                success=False,
                error=str(exc),
            )
            raise

        metadata_base = {
            "title": clean_doc.get("title"),
            "post_date": clean_doc.get("post_date"),
            "ticker_symbol": clean_doc.get("ticker_symbol"),
            "ticker_name": clean_doc.get("ticker_name"),
            "keyword": clean_doc.get("keyword"),
            "source": clean_doc.get("source"),
        }
        metadata_base = {k: v for k, v in metadata_base.items() if v is not None}

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
            self._qdrant.upsert_chunks(records)
            self._run_log.upsert(
                link=link,
                num_points=len(records),
                collection=self._settings.qdrant.collection,
                duration_s=time.monotonic() - t0,
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._run_log.upsert(
                link=link,
                num_points=0,
                collection=self._settings.qdrant.collection,
                duration_s=time.monotonic() - t0,
                success=False,
            )
            raise

        return len(records)
