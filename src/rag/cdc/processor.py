"""CDC medallion processor for scraped article files."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.rag.cdc.content_reader import ContentDocumentReader
from src.rag.cdc.events import ArticleFileEvent
from src.rag.cdc.store import CdcCheckpointStore
from src.rag.config import Settings as RagSettings, get_settings as get_rag_settings
from src.rag.databases import QdrantRepository
from src.rag.databases.qdrant_client import ChunkRecord
from src.rag.ingestion.chunker import TextChunker
from src.rag.ingestion.cleaner import TextCleaner
from src.rag.ingestion.embedder import VoyageAIEmbedder
from src.rag.utils import get_logger

logger = get_logger(__name__)


@dataclass
class CdcProcessingReport:
    """Result of processing one CDC article file event."""

    article_id: str
    json_path: str
    skipped: bool = False
    bronze_done: bool = False
    silver_done: bool = False
    gold_done: bool = False
    chunks_written: int = 0
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "json_path": self.json_path,
            "skipped": self.skipped,
            "bronze_done": self.bronze_done,
            "silver_done": self.silver_done,
            "gold_done": self.gold_done,
            "chunks_written": self.chunks_written,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class CdcMedallionProcessor:
    """Process Debezium article-file events into Qdrant with checkpoints."""

    def __init__(
        self,
        *,
        reader: ContentDocumentReader,
        checkpoint_store: CdcCheckpointStore,
        qdrant: QdrantRepository,
        embedder: VoyageAIEmbedder,
        rag_settings: Optional[RagSettings] = None,
    ) -> None:
        self._reader = reader
        self._store = checkpoint_store
        self._qdrant = qdrant
        self._embedder = embedder
        self._settings = rag_settings or get_rag_settings()
        self._cleaner = TextCleaner()
        self._chunker = TextChunker(self._settings)

    def process(self, event: ArticleFileEvent) -> CdcProcessingReport:
        """Process one article file event through bronze, silver, and gold."""
        report = CdcProcessingReport(article_id=event.article_id, json_path=event.json_path)
        if not event.is_processable:
            report.skipped = True
            report.error = "event is missing article_id, url, or json_path"
            report.mark_done()
            return report

        if self._store.is_completed(event.article_id):
            logger.info("CDC skip already completed article_id=%s json_path=%s", event.article_id, event.json_path)
            report.skipped = True
            report.gold_done = True
            report.mark_done()
            return report

        self._store.mark_received(event)
        self._store.mark_started(event.article_id)

        try:
            content_doc = self._reader.read_json(event.json_path)
            bronze_doc = _to_bronze(event, content_doc)
            self._store.mark_bronze_done(event.article_id, bronze_doc)
            report.bronze_done = True

            silver_doc = self._to_silver(bronze_doc)
            self._store.mark_silver_done(event.article_id, silver_doc)
            report.silver_done = True

            chunks_written = self._to_gold(silver_doc)
            self._store.mark_gold_done(event.article_id, chunks_written)
            report.gold_done = True
            report.chunks_written = chunks_written
            logger.info(
                "CDC medallion processed article_id=%s chunks=%s json_path=%s",
                event.article_id,
                chunks_written,
                event.json_path,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            self._store.mark_failed(event.article_id, error)
            report.error = error
            logger.exception("CDC medallion failed article_id=%s json_path=%s: %s", event.article_id, event.json_path, exc)

        report.mark_done()
        return report

    def _to_silver(self, bronze_doc: dict[str, Any]) -> dict[str, Any]:
        cleaned = self._cleaner.clean_article(bronze_doc)
        if not cleaned.get("clean_text"):
            raise ValueError("silver clean_text is empty")
        cleaned["article_id"] = bronze_doc.get("article_id")
        cleaned["url_hash"] = bronze_doc.get("url_hash")
        cleaned["json_path"] = bronze_doc.get("json_path")
        cleaned["content_hash"] = _content_hash(cleaned["clean_text"])
        cleaned["cleaned_at"] = datetime.now(timezone.utc).isoformat()
        return cleaned

    def _to_gold(self, silver_doc: dict[str, Any]) -> int:
        self._qdrant.ensure_collection()
        chunks = self._chunker.split(silver_doc["clean_text"])
        if not chunks:
            return 0
        embeddings = self._embedder.embed_documents(chunks)
        if len(embeddings) != len(chunks):
            raise RuntimeError(f"embedder returned {len(embeddings)} vectors for {len(chunks)} chunks")

        metadata = {
            "article_id": silver_doc.get("article_id"),
            "title": silver_doc.get("title"),
            "post_date": silver_doc.get("post_date"),
            "ticker_symbol": silver_doc.get("ticker_symbol"),
            "ticker_name": silver_doc.get("ticker_name"),
            "keyword": silver_doc.get("keyword"),
            "source": silver_doc.get("source"),
            "content_hash": silver_doc.get("content_hash"),
            "json_path": silver_doc.get("json_path"),
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}

        records = [
            ChunkRecord(
                article_link=silver_doc["link"],
                chunk_index=index,
                content=chunk,
                embedding=embedding,
                metadata={**metadata, "chunk_index": index},
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        return self._qdrant.upsert_chunks(records)


def _to_bronze(event: ArticleFileEvent, content_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "article_id": event.article_id,
        "source_id": event.source_id,
        "crawl_job_id": event.crawl_job_id,
        "url_hash": event.url_hash,
        "json_path": event.json_path,
        "link": content_doc.get("url") or event.url,
        "url": content_doc.get("url") or event.url,
        "title": content_doc.get("title"),
        "summary": content_doc.get("summary"),
        "context": content_doc.get("content"),
        "content": content_doc.get("content"),
        "blocks": content_doc.get("blocks") or [],
        "post_date": content_doc.get("published_at"),
        "published_at": content_doc.get("published_at"),
        "scraped_at": content_doc.get("scraped_at"),
        "ticker_symbol": content_doc.get("ticker") or _first_or_none(content_doc.get("tickers")),
        "ticker_name": content_doc.get("ticker_name"),
        "keyword": content_doc.get("matched_keyword"),
        "source": content_doc.get("source"),
        "language": content_doc.get("language"),
        "author": content_doc.get("author"),
        "tag": content_doc.get("tag"),
        "type": content_doc.get("type"),
    }


def _first_or_none(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return None


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()
