"""Source payload adapters; independent of HTTP, frontier and orchestration."""

from datetime import datetime
from zoneinfo import ZoneInfo


class SourceAdapter:
    """Explicit source-payload mapping to the already approved Bronze boundary."""

    version = "bronze-adapter-v1"

    def __init__(self, source):
        self.source = source

    def adapt(self, envelope):
        if (
            envelope["source"] != self.source.key
            or envelope["raw_schema_version"] != self.source.raw_schema_version
        ):
            raise ValueError("source_adapter_schema_mismatch")
        payload = envelope["payload"]
        title, summary, body, timestamp, _ = self.source.payload_fields
        native_time = payload[timestamp]
        converted = native_time
        if native_time:
            try:
                parsed = datetime.fromisoformat(native_time.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    # Only CafeF was observed using offset-free local publication.
                    if self.source.key != "cafef":
                        raise ValueError("timezone_missing")
                    parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
                converted = parsed.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime(
                    "%d-%m-%Y - %I:%M %p"
                )
            except ValueError:
                pass  # Preserve raw; canonical published_at will be null.
        return {
            "link": self.source.url(envelope["url"], article=True),
            "title": payload[title],
            "summary": payload[summary],
            "context": payload[body],
            "post date": converted,
        }
