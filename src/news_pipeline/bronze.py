"""Upload the selected snapshot byte-for-byte into content-addressed Bronze."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .storage import ObjectStore, create_object_store


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
        return _publish_partition_reference(settings, store, manifest)

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
    return _publish_partition_reference(settings, store, manifest)


def _publish_partition_reference(settings: Settings, store: ObjectStore, manifest: dict) -> dict:
    """Associate immutable Bronze bytes with an explicit logical partition."""
    processing_date = settings.processing_date or manifest["ingestion_date"]
    try:
        datetime.strptime(processing_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("NEWS_PROCESSING_DATE must use YYYY-MM-DD") from exc
    reference_key = (
        f"bronze/partitions/source={settings.source}/processing_date={processing_date}/"
        f"{manifest['ingestion_id']}.json"
    )
    reference = {
        "source": settings.source,
        "processing_date": processing_date,
        "ingestion_id": manifest["ingestion_id"],
        "manifest_key": f"bronze/{settings.source}/{manifest['ingestion_id']}/manifest.json",
        "raw_key": manifest["raw_key"],
        "source_file_sha256": manifest["source_file_sha256"],
        "record_count": manifest["record_count"],
    }
    encoded = json.dumps(reference, ensure_ascii=False, indent=2, sort_keys=True).encode()
    if store.exists(reference_key):
        if store.get_bytes(reference_key) != encoded:
            raise RuntimeError(f"Bronze partition reference conflict: {reference_key}")
    else:
        store.put_bytes(reference_key, encoded, "application/json")
    return {**manifest, "processing_date": processing_date, "partition_reference_key": reference_key}


def main() -> None:
    settings = Settings.from_env()
    print(json.dumps(ingest(settings, create_object_store(settings)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
