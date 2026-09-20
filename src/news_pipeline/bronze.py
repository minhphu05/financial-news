"""Upload the selected snapshot byte-for-byte into content-addressed Bronze."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .storage import ObjectStore, S3ObjectStore


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ingest(settings: Settings, store: ObjectStore) -> dict:
    path = Path(settings.source_file)
    if not path.is_file():
        raise FileNotFoundError(path)
    checksum = file_sha256(path)
    ingestion_id = checksum
    raw_key = f"bronze/{settings.source}/{ingestion_id}/raw.json"
    manifest_key = f"bronze/{settings.source}/{ingestion_id}/manifest.json"
    store.ensure_bucket()
    if store.exists(manifest_key):
        manifest = json.loads(store.get_bytes(manifest_key))
        if manifest["source_file_sha256"] != checksum or not store.exists(raw_key):
            raise RuntimeError("Bronze manifest does not match its raw object")
        return manifest

    # The source JSON is an array. The exported row order is retained in raw.json.
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Expected the contracted JSON array snapshot")

    now = datetime.now(timezone.utc)
    manifest = {
        "ingestion_id": ingestion_id,
        "source": settings.source,
        "source_file": path.name,
        "ingested_at": now.isoformat(),
        "ingestion_date": now.date().isoformat(),
        "source_file_sha256": checksum,
        "byte_size": path.stat().st_size,
        "record_count": len(records),
        "raw_key": raw_key,
    }
    if store.exists(raw_key):
        if hashlib.sha256(store.get_bytes(raw_key)).hexdigest() != checksum:
            raise RuntimeError("Existing Bronze raw object differs from source checksum")
    else:
        store.upload_file(str(path), raw_key)
    store.put_bytes(manifest_key, json.dumps(manifest, ensure_ascii=False, indent=2).encode(), "application/json")
    return manifest


def main() -> None:
    settings = Settings.from_env()
    print(json.dumps(ingest(settings, S3ObjectStore(settings)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
