"""MongoDB repository for raw and cleaned CafeF articles.

The repository hides the ``pymongo`` API behind a small, typed surface so
that ingestion, scraping, and orchestration code never has to think about
collections, indices, or query primitives.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional

from pymongo import ASCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


class MongoRepository:
    """Thin repository wrapper over the MongoDB article collections.

    The repository manages two collections:

    * ``raw_collection``   - articles produced verbatim by the scraper.
    * ``clean_collection`` - articles after the cleaning step. Documents in
      this collection carry an ``embedded_at`` field once chunks have been
      pushed to the vector store, so the ingestion flow can skip them.

    Parameters
    ----------
    settings : Optional[Settings]
        Override the global settings. Useful for tests.
    """

    # -- lifecycle ----------------------------------------------------------
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._client: MongoClient = MongoClient(self._settings.mongo.uri)
        self._db = self._client[self._settings.mongo.database]
        self._raw: Collection = self._db[self._settings.mongo.raw_collection]
        self._clean: Collection = self._db[self._settings.mongo.clean_collection]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create the indexes needed by the ingestion + retrieval pipeline."""
        def _has_unique_link_index(collection: Collection) -> bool:
            for index_spec in collection.list_indexes():
                key = index_spec.get("key")
                if key is None:
                    continue
                if list(key.items()) == [("link", 1)] and bool(index_spec.get("unique")):
                    return True
            return False

        # Some legacy documents may have ``link=null``; partial unique indexes
        # keep idempotent upserts safe without breaking startup.
        if not _has_unique_link_index(self._raw):
            self._raw.create_index(
                [("link", ASCENDING)],
                unique=True,
                name="uniq_link_partial_raw",
                partialFilterExpression={"link": {"$type": "string", "$exists": True}},
            )
        self._raw.create_index([("scraped_at", ASCENDING)], name="scraped_at_idx")
        if not _has_unique_link_index(self._clean):
            self._clean.create_index(
                [("link", ASCENDING)],
                unique=True,
                name="uniq_link_partial_clean",
                partialFilterExpression={"link": {"$type": "string", "$exists": True}},
            )
        self._clean.create_index([("embedded_at", ASCENDING)], name="embedded_at_idx")

    @property
    def rejected_collection(self) -> Collection:
        """Audit collection for documents that failed the quality gate."""
        name = self._settings.mongo.rejected_collection
        return self._db[name]

    def save_rejections(self, rejections: Iterable[Dict[str, Any]]) -> int:
        """Persist quality-gate rejections for later inspection.

        Parameters
        ----------
        rejections : Iterable[dict]
            Each entry must contain ``link``, ``errors`` and ``payload``.

        Returns
        -------
        int
            Number of inserted documents.
        """
        now = datetime.now(timezone.utc)
        docs = [{**r, "rejected_at": now} for r in rejections]
        if not docs:
            return 0
        self.rejected_collection.insert_many(docs)
        return len(docs)

    def iter_recent_raw(self, limit: int) -> Iterator[Dict[str, Any]]:
        """Iterate over the most recently scraped raw articles.

        Parameters
        ----------
        limit : int
            Maximum number of documents to yield.
        """
        cursor = self._raw.find().sort("scraped_at", -1).limit(max(limit, 1))
        for doc in cursor:
            yield doc

    def get_raw_by_ids(self, news_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch raw articles by their ``news_id`` (which equals ``_id``).

        Parameters
        ----------
        news_ids : list[str]
            Article identifiers returned by the scrape step.

        Returns
        -------
        list[dict]
            Raw article documents, ordered by ``scraped_at`` ascending.
        """
        if not news_ids:
            return []
        cursor = self._raw.find({"_id": {"$in": news_ids}}).sort("scraped_at", ASCENDING)
        return list(cursor)

    # -- raw articles -------------------------------------------------------
    def upsert_raw(self, article: Dict[str, Any]) -> bool:
        """Upsert a raw article.

        Parameters
        ----------
        article : dict
            The scraped article. The dict MUST contain a ``link`` field which
            acts as the natural key. A ``scraped_at`` timestamp is added if
            missing.

        Returns
        -------
        bool
            ``True`` if the document was newly inserted, ``False`` if it was
            updated (already present).
        """
        if "link" not in article or not article["link"]:
            raise ValueError("Article is missing the required 'link' field.")

        article.setdefault("scraped_at", datetime.now(timezone.utc))

        result = self._raw.update_one(
            {"link": article["link"]},
            {"$setOnInsert": article},
            upsert=True,
        )
        return result.upserted_id is not None

    def bulk_upsert_raw(self, articles: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        """Bulk-upsert a batch of raw articles.

        Parameters
        ----------
        articles : Iterable[dict]
            Articles to upsert. Each must contain ``link``.

        Returns
        -------
        dict
            ``{"inserted": int, "matched": int}``. ``inserted`` counts the
            number of new documents created during the bulk write.
        """
        ops: List[UpdateOne] = []
        now = datetime.now(timezone.utc)
        for art in articles:
            if not art.get("link"):
                logger.warning("Skipping article without 'link': %s", art.get("title"))
                continue
            art.setdefault("scraped_at", now)
            ops.append(
                UpdateOne(
                    {"link": art["link"]},
                    {"$setOnInsert": art},
                    upsert=True,
                )
            )
        if not ops:
            return {"inserted": 0, "matched": 0}

        try:
            res = self._raw.bulk_write(ops, ordered=False)
            return {"inserted": res.upserted_count, "matched": res.matched_count}
        except BulkWriteError as exc:
            logger.warning("Bulk upsert raw errors: %s", exc.details.get("writeErrors", [])[:3])
            return {
                "inserted": exc.details.get("nUpserted", 0),
                "matched": exc.details.get("nMatched", 0),
            }

    def link_exists(self, link: str) -> bool:
        """Return ``True`` if the URL already exists in the raw collection."""
        return self._raw.count_documents({"link": link}, limit=1) > 0

    # -- cleaning -----------------------------------------------------------
    def iter_raw_not_cleaned(self, batch_size: int = 100) -> Iterator[Dict[str, Any]]:
        """Iterate over raw articles that have not been cleaned yet.

        Parameters
        ----------
        batch_size : int
            Mongo cursor batch size.

        Yields
        ------
        dict
            Raw article documents.
        """
        cleaned_links = {
            doc["link"] for doc in self._clean.find({}, {"link": 1, "_id": 0})
        }
        cursor = self._raw.find(
            {"link": {"$nin": list(cleaned_links)}},
            batch_size=batch_size,
        )
        for doc in cursor:
            yield doc

    def upsert_clean(self, article: Dict[str, Any]) -> None:
        """Upsert a cleaned article.

        Parameters
        ----------
        article : dict
            Must contain ``link`` and ``clean_text``. ``cleaned_at`` is filled
            in automatically.
        """
        if "link" not in article or "clean_text" not in article:
            raise ValueError("Cleaned article must contain 'link' and 'clean_text'.")
        article["cleaned_at"] = datetime.now(timezone.utc)

        self._clean.update_one(
            {"link": article["link"]},
            {"$set": article},
            upsert=True,
        )

    # -- ingestion / embedding gate ----------------------------------------
    def iter_clean_not_embedded(self, batch_size: int = 100) -> Iterator[Dict[str, Any]]:
        """Iterate over cleaned articles that still need embedding.

        A clean article is considered "pending" when its ``embedded_at`` is
        missing.
        """
        cursor = self._clean.find({"embedded_at": {"$exists": False}}, batch_size=batch_size)
        for doc in cursor:
            yield doc

    def count_raw_not_cleaned(self) -> int:
        """Return the number of raw articles not yet in the clean collection."""
        cleaned_links = {
            doc["link"] for doc in self._clean.find({}, {"link": 1, "_id": 0})
        }
        return self._raw.count_documents({"link": {"$nin": list(cleaned_links)}})

    def count_clean_not_embedded(self) -> int:
        """Return the number of clean articles waiting to be embedded."""
        return self._clean.count_documents({"embedded_at": {"$exists": False}})

    def mark_embedded(self, link: str, num_chunks: int) -> None:
        """Mark a cleaned article as fully embedded.

        Parameters
        ----------
        link : str
            URL of the article.
        num_chunks : int
            Number of chunks that have been pushed to the vector store.
        """
        self._clean.update_one(
            {"link": link},
            {
                "$set": {
                    "embedded_at": datetime.now(timezone.utc),
                    "num_chunks": num_chunks,
                }
            },
        )

    def reset_all_embedded(self) -> int:
        """Remove the ``embedded_at`` field from all clean articles.

        This forces the next ingestion run to re-embed every article.
        Use after deleting all Qdrant vectors for a full re-index.

        Returns
        -------
        int
            Number of documents reset.
        """
        result = self._clean.update_many(
            {"embedded_at": {"$exists": True}},
            {"$unset": {"embedded_at": "", "num_chunks": ""}},
        )
        logger.info("Reset embedded_at on %d clean articles.", result.modified_count)
        return result.modified_count

    # -- news listing (API) -------------------------------------------------
    def list_articles(
        self,
        ticker: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return a page of cleaned articles for the frontend.

        Parameters
        ----------
        ticker : Optional[str]
            Filter by ticker symbol (case-insensitive).
        skip : int
            Number of documents to skip (pagination offset).
        limit : int
            Maximum number of documents to return.
        search : Optional[str]
            Free-text search; matched case-insensitively against the
            article title.

        Returns
        -------
        list[dict]
            Cleaned articles sorted by ``cleaned_at`` descending.
        """
        query: Dict[str, Any] = {}
        if ticker:
            query["ticker_symbol"] = ticker.upper()
        if search:
            query["title"] = {"$regex": search, "$options": "i"}

        cursor = (
            self._clean.find(query)
            .sort("cleaned_at", -1)
            .skip(max(skip, 0))
            .limit(max(limit, 1))
        )
        return list(cursor)

    def count_articles(
        self,
        ticker: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count cleaned articles matching the same filters as ``list_articles``."""
        query: Dict[str, Any] = {}
        if ticker:
            query["ticker_symbol"] = ticker.upper()
        if search:
            query["title"] = {"$regex": search, "$options": "i"}
        return self._clean.count_documents(query)

    def get_article(self, link: str) -> Optional[Dict[str, Any]]:
        """Return a single cleaned article by URL, or ``None`` if absent."""
        return self._clean.find_one({"link": link})

    def list_tickers(self) -> List[str]:
        """Return the distinct ticker symbols currently present in the store."""
        return [t for t in self._clean.distinct("ticker_symbol") if t]

    # -- housekeeping -------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        """Return basic statistics for monitoring/Prefect logs."""
        return {
            "raw_count": self._raw.estimated_document_count(),
            "clean_count": self._clean.estimated_document_count(),
            "embedded_count": self._clean.count_documents({"embedded_at": {"$exists": True}}),
        }

    def close(self) -> None:
        """Close the underlying MongoDB client."""
        self._client.close()

    def __enter__(self) -> "MongoRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
