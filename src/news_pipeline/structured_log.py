"""Small JSON logger shared by standalone hardened-pipeline commands."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
from typing import Any


def event(name: str, *, level: str = "INFO", **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": name,
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True), file=sys.stdout, flush=True)
