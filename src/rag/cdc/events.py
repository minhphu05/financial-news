"""Debezium event parsing for article metadata changes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ArticleFileEvent:
    """A normalized event for one scraped article content file."""

    article_id: str
    source_id: Optional[str]
    crawl_job_id: Optional[str]
    url: str
    url_hash: str
    json_path: str
    status: Optional[str]
    operation: str
    event_key: str

    @property
    def is_processable(self) -> bool:
        return bool(self.article_id and self.url and self.json_path)


def parse_debezium_article_event(message: Mapping[str, Any]) -> Optional[ArticleFileEvent]:
    """Extract an article file event from a Debezium JSON message.

    Debezium emits an envelope with `payload.before`, `payload.after`, and
    `payload.op`. Tombstones and delete records are ignored by default.
    """
    payload = message.get("payload") if "payload" in message else message
    if not isinstance(payload, Mapping):
        return None

    op = str(payload.get("op") or "").lower()
    after = payload.get("after")
    if op in {"d", "t"} or after is None:
        return None
    if not isinstance(after, Mapping):
        return None

    article_id = _as_str(after.get("id"))
    url = _as_str(after.get("url"))
    url_hash = _as_str(after.get("url_hash"))
    json_path = _as_str(after.get("json_path"))
    if not article_id or not json_path:
        return None

    return ArticleFileEvent(
        article_id=article_id,
        source_id=_as_str(after.get("source_id")),
        crawl_job_id=_as_str(after.get("crawl_job_id")),
        url=url,
        url_hash=url_hash,
        json_path=json_path,
        status=_as_str(after.get("status")),
        operation=op or "unknown",
        event_key=f"{article_id}:{json_path}",
    )


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)
