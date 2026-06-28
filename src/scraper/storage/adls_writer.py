"""
ADLS Gen2 content writer.

Each scraped article's full body (text + images, in reading order) plus light
metadata is serialized to a JSON blob and uploaded to the
``financialnews-datalake`` filesystem. The returned path is stored in
``article_metadata.json_path`` so downstream jobs can fetch the raw content on
demand.

Path layout::

    {root_prefix}/{source}/{publish_year}/{ticker}/{timestamp}-{id}.json

``publish_year`` and ``timestamp`` come from the article's *publication* date
(not the scrape time); ``id`` is the source-native article id.

Authentication uses an account connection string (or account name + key) read
from configuration — see ``ADLS_*`` variables in ``.env``.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.scraper.config import ScraperSettings
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from azure.storage.filedatalake import DataLakeServiceClient

    _HAS_ADLS = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_ADLS = False


@dataclass(frozen=True)
class ContentDocument:
    """The JSON payload persisted to the data lake for one article."""

    id: Optional[str]
    url: str
    url_hash: str
    source: str
    ticker: str
    title: Optional[str]
    summary: Optional[str]
    cover_image: Optional[str]
    author: Optional[str]
    tag: Optional[str]
    type: Optional[str]
    language: Optional[str]
    published_at: Optional[str]
    scraped_at: str
    tickers: List[str]
    matched_keyword: Optional[str]
    content: Optional[str]
    blocks: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class ArticlePaths:
    """Resolved ADLS locations for one article.

    Layout::

        {folder}/{stem}.json          <- content document
        {folder}/images/{filename}    <- downloaded image binaries
    """

    folder: str
    stem: str

    @property
    def json_path(self) -> str:
        return f"{self.folder}/{self.stem}.json"

    def image_path(self, filename: str) -> str:
        return f"{self.folder}/images/{filename}"




class ADLSContentWriter:
    """Uploads article content JSON blobs to ADLS Gen2."""

    def __init__(self, settings: ScraperSettings) -> None:
        self._settings = settings
        self._service: Optional["DataLakeServiceClient"] = None
        self._filesystem = None

    # -- Lifecycle -------------------------------------------------------
    def connect(self) -> None:
        if not _HAS_ADLS:
            raise RuntimeError(
                "azure-storage-file-datalake is not installed. "
                "Add it to requirements and `pip install` before scraping."
            )
        self._service = self._build_service_client()
        self._filesystem = self._service.get_file_system_client(
            self._settings.adls_filesystem
        )
        # Create the filesystem (container) if it does not yet exist.
        try:
            if not self._filesystem.exists():
                self._filesystem.create_file_system()
                logger.info("Created ADLS filesystem '%s'.", self._settings.adls_filesystem)
        except Exception as exc:  # pragma: no cover - permission/network dependent
            logger.warning("Could not verify/create ADLS filesystem: %s", exc)
        logger.success(
            "Connected to ADLS filesystem '%s'.", self._settings.adls_filesystem
        )

    def close(self) -> None:
        if self._service is not None:
            self._service.close()
            self._service = None
            self._filesystem = None

    def __enter__(self) -> "ADLSContentWriter":
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # -- Public API ------------------------------------------------------
    def build_paths(
        self,
        source: str,
        ticker: str,
        external_id: Optional[str],
        url_hash: str,
        published_at: Optional[datetime],
    ) -> ArticlePaths:
        """Resolve the per-article folder + file stem.

        Layout: ``{prefix}/{source}/{publish_year}/{ticker}/{timestamp}-{id}/``
        where the year + timestamp come from the publication date. The folder
        holds ``{stem}.json`` and an ``images/`` subfolder.
        """
        stamp = published_at or datetime.now(timezone.utc)
        article_id = self._sanitize(external_id) or url_hash[:16]
        ticker_seg = self._sanitize(ticker) or "UNKNOWN"
        stem = f"{stamp:%Y%m%d%H%M%S}-{article_id}"
        folder = (
            f"{self._settings.adls_root_prefix}/{source}/"
            f"{stamp:%Y}/{ticker_seg}/{stem}"
        )
        return ArticlePaths(folder=folder, stem=stem)

    def upload_document(self, paths: ArticlePaths, document: ContentDocument) -> str:
        """Upload the content JSON for one article; return its ADLS path."""
        assert self._filesystem is not None, "ADLSContentWriter not connected"
        payload = document.to_json().encode("utf-8")
        file_client = self._filesystem.get_file_client(paths.json_path)
        file_client.upload_data(payload, overwrite=True)
        logger.debug("Uploaded content to ADLS: %s", paths.json_path)
        return paths.json_path

    def upload_image(self, paths: ArticlePaths, filename: str, data: bytes) -> str:
        """Upload one image binary into the article's ``images/`` folder."""
        assert self._filesystem is not None, "ADLSContentWriter not connected"
        path = paths.image_path(filename)
        file_client = self._filesystem.get_file_client(path)
        file_client.upload_data(data, overwrite=True)
        logger.debug("Uploaded image to ADLS: %s", path)
        return path

    def upload(
        self,
        document: ContentDocument,
        published_at: Optional[datetime],
    ) -> str:
        """Upload one content document; return its ADLS path."""
        paths = self.build_paths(
            document.source,
            document.ticker,
            document.id,
            document.url_hash,
            published_at,
        )
        return self.upload_document(paths, document)

    # -- Internals -------------------------------------------------------
    @staticmethod
    def _sanitize(value: Optional[str]) -> Optional[str]:
        """Make a string safe for use as a single ADLS path segment."""
        if not value:
            return None
        cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
        return cleaned.strip("_") or None

    def _build_service_client(self) -> "DataLakeServiceClient":
        s = self._settings
        if s.adls_connection_string:
            return DataLakeServiceClient.from_connection_string(s.adls_connection_string)
        if s.adls_account_name and s.adls_account_key:
            account_url = f"https://{s.adls_account_name}.dfs.core.windows.net"
            return DataLakeServiceClient(account_url=account_url, credential=s.adls_account_key)
        raise RuntimeError(
            "ADLS credentials missing. Set ADLS_CONNECTION_STRING, or both "
            "ADLS_ACCOUNT_NAME and ADLS_ACCOUNT_KEY in .env."
        )
