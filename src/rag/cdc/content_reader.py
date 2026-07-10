"""Read scraped article content documents from MinIO or ADLS."""
from __future__ import annotations

import json
from importlib import import_module
from typing import Any

from src.scraper.config import ScraperSettings, normalize_content_storage_backend


class ContentDocumentReader:
    """Load article JSON content documents by scraper `json_path`."""

    def __init__(self, settings: ScraperSettings) -> None:
        self._settings = settings
        self._backend = normalize_content_storage_backend(settings.content_storage_backend)
        self._client = None

    def connect(self) -> None:
        if self._backend == "minio":
            minio_module = import_module("minio")
            self._client = minio_module.Minio(
                self._settings.minio_endpoint,
                access_key=self._settings.minio_access_key,
                secret_key=self._settings.minio_secret_key,
                secure=self._settings.minio_secure,
            )
            return

        if self._backend == "adls":
            adls_module = import_module("azure.storage.filedatalake")
            service_cls = adls_module.DataLakeServiceClient
            if self._settings.adls_connection_string:
                self._client = service_cls.from_connection_string(self._settings.adls_connection_string)
            elif self._settings.adls_account_name and self._settings.adls_account_key:
                account_url = f"https://{self._settings.adls_account_name}.dfs.core.windows.net"
                self._client = service_cls(account_url=account_url, credential=self._settings.adls_account_key)
            else:
                raise RuntimeError("ADLS credentials are missing for content reader.")
            return

        raise ValueError("content_storage_backend must be either 'minio' or 'adls'.")

    def close(self) -> None:
        if self._backend == "adls" and self._client is not None:
            self._client.close()
        self._client = None

    def __enter__(self) -> "ContentDocumentReader":
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def read_json(self, json_path: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("ContentDocumentReader is not connected.")
        if self._backend == "minio":
            response = self._client.get_object(self._settings.minio_bucket, json_path)
            try:
                payload = response.read().decode("utf-8")
            finally:
                response.close()
                response.release_conn()
            return json.loads(payload)

        filesystem = self._client.get_file_system_client(self._settings.adls_filesystem)
        file_client = filesystem.get_file_client(json_path)
        payload = file_client.download_file().readall().decode("utf-8")
        return json.loads(payload)
