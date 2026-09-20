"""Contract v1 normalization, independent of Spark and storage drivers."""

from datetime import datetime
import hashlib
import html
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


_SPACE = re.compile(r"\s+")
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_DATE = re.compile(r"^\d{2}-\d{2}-\d{4} - (?:0[1-9]|1[0-2]):[0-5]\d [AP]M$")
_FOOTER = re.compile(r"^(?:nguồn\s*:\s*cafe\s*f|theo\s+cafe\s*f|đọc thêm\s*:).*$", re.I)


class _TextFromHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("p", "br", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalize_text(value: str | None, *, body: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    value = html.unescape(value)
    if _TAG.search(value):
        parser = _TextFromHTML()
        parser.feed(value)
        value = "".join(parser.parts)
    value = unicodedata.normalize("NFC", value)
    lines = [line.strip() for line in value.splitlines()]
    if body:
        lines = [line for line in lines if not _FOOTER.fullmatch(line)]
    return _SPACE.sub(" ", " ".join(lines)).strip()


def canonical_url(value: str, expected_source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing_or_invalid_link")
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("missing_or_invalid_link")
    if parsed.username or parsed.password or parsed.hostname.lower() != expected_source:
        raise ValueError("unexpected_source_host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("missing_or_invalid_link") from exc
    if port and port not in (80, 443):
        raise ValueError("unexpected_source_port")
    host = parsed.hostname.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), host, path, parsed.query, ""))


def published_at(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%d-%m-%Y - %I:%M %p").replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    except ValueError:
        return None


def normalize_observation(row: object, row_index: int, ingestion_id: str, source: str, version: str) -> dict:
    """Return an article/mention observation or a lineage-carrying reject."""
    if not isinstance(row, dict):
        return {"reject": {"source_ingestion_id": ingestion_id, "source_row_position": row_index, "source_index": None, "reason": "not_an_object"}}
    export_index = row.get("index") if type(row.get("index")) is int else None
    for field in ("link", "title", "context"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            return {"reject": {"source_ingestion_id": ingestion_id, "source_row_position": row_index, "source_index": export_index, "reason": f"missing_or_invalid_{field}"}}
    try:
        url = canonical_url(row["link"], source)
    except ValueError as exc:
        return {"reject": {"source_ingestion_id": ingestion_id, "source_row_position": row_index, "source_index": export_index, "reason": str(exc)}}
    title = normalize_text(row["title"])
    content = normalize_text(row["context"], body=True)
    if not title or not content:
        return {"reject": {"source_ingestion_id": ingestion_id, "source_row_position": row_index, "source_index": export_index, "reason": "empty_after_cleaning"}}
    article_id = hashlib.sha256(f"{source}\n{url}".encode()).hexdigest()
    result = {
        "article_id": article_id,
        "source": source,
        "source_url": row["link"],
        "canonical_url": url,
        "title": title,
        "description": normalize_text(row.get("summary")) or None,
        "content": content,
        "published_at": published_at(row.get("post date")),
        "published_at_raw": row.get("post date") if isinstance(row.get("post date"), str) else None,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "processing_version": version,
        "source_ingestion_id": ingestion_id,
        "author": None,
        "crawled_at": None,
        "category": None,
        "image_urls": None,
        "source_index": export_index,
        "source_row_position": row_index,
        "ticker_symbol": row.get("ticket symbol") if isinstance(row.get("ticket symbol"), str) else None,
        "ticker_name": row.get("ticket name") if isinstance(row.get("ticket name"), str) else None,
        "keyword": row.get("keyword") if isinstance(row.get("keyword"), str) else None,
        "source_page": row.get("page") if type(row.get("page")) is int else None,
    }
    return {"valid": result}
