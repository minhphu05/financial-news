"""Immutable crawler evidence and adapter batches behind the existing ObjectStore."""

import hashlib
import json
from pathlib import Path


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def immutable_put(store, key, body, content_type="application/json"):
    if store.exists(key):
        if store.get_bytes(key) != body:
            raise ValueError("immutable_landing_conflict")
    else:
        store.put_bytes(key, body, content_type)


class Landing:
    def __init__(self, store):
        self.store = store
        store.ensure_bucket()

    def observation(self, envelope, html):
        raw_hash = hashlib.sha256(html).hexdigest()
        scope = "fixture" if envelope.get("data_kind") == "FIXTURE" else "live"
        html_key = f"landing/{scope}/{envelope['source']}/html/{raw_hash}.html"
        immutable_put(self.store, html_key, html, "text/html; charset=utf-8")
        envelope = {**envelope, "raw_html_key": html_key, "raw_html_sha256": raw_hash}
        key = f"landing/{scope}/{envelope['source']}/observations/{envelope['crawl_run_id']}/{hashlib.sha256(envelope['url'].encode()).hexdigest()}.json"
        immutable_put(self.store, key, encoded(envelope))
        return key, envelope

    def batch(
        self,
        source,
        rows,
        envelopes,
        run,
        day,
        processing_version,
        adapter_version,
        *,
        data_kind="LIVE",
    ):
        body = encoded(sorted(rows, key=lambda r: r["link"]))
        digest = hashlib.sha256(
            body + processing_version.encode() + adapter_version.encode() + run.encode()
        ).hexdigest()
        batch_id = f"crawl-{source}-{digest[:32]}"
        scope = "fixture" if data_kind == "FIXTURE" else "live"
        prefix = f"landing/{scope}/{source}/batches/{batch_id}"
        json_key = prefix + "/bronze-input.json"
        manifest_key = prefix + "/manifest.json"
        immutable_put(self.store, json_key, body)
        manifest = {
            "batch_id": batch_id,
            "data_kind": data_kind,
            "source": source,
            "crawl_run_id": run,
            "processing_date": day,
            "processing_version": processing_version,
            "adapter_version": adapter_version,
            "bronze_input_key": json_key,
            "bronze_input_sha256": hashlib.sha256(body).hexdigest(),
            "record_count": len(rows),
            "envelope_keys": envelopes,
        }
        if self.store.exists(manifest_key):
            manifest = json.loads(self.store.get_bytes(manifest_key))
        else:
            immutable_put(self.store, manifest_key, encoded(manifest))
        return manifest_key, manifest

    def restore(self, manifest_key, directory):
        manifest = json.loads(self.store.get_bytes(manifest_key))
        body = self.store.get_bytes(manifest["bronze_input_key"])
        if hashlib.sha256(body).hexdigest() != manifest["bronze_input_sha256"]:
            raise ValueError("landing_batch_checksum_mismatch")
        path = Path(directory) / (manifest["batch_id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return manifest, str(path)
