"""Unit tests for Phase 04 metadata models and Debezium event handling."""

import json
import os
import unittest
from unittest.mock import patch

from src.metadata_control.config import MetadataSettings
from src.metadata_control.connector import connector_config
from src.metadata_control.events import MetadataState, parse_event


class MetadataControlTest(unittest.TestCase):
    def settings(self) -> MetadataSettings:
        return MetadataSettings(
            postgres_host="postgresql", postgres_port=5432, database="financial_metadata",
            admin_user="metadata_user", admin_password="admin-secret",
            cdc_user="metadata_cdc", cdc_password="cdc-secret", schema="control_metadata",
            publication="metadata_cdc_publication", slot="metadata_cdc_slot",
            kafka_bootstrap_servers="kafka:9092", connect_url="http://debezium:8083",
            connector_name="metadata-control-plane", topic_prefix="platform",
            consumer_group="metadata-inspector",
        )

    def event(self, operation: str, before=None, after=None, *, offset=1, value_override="missing"):
        value = None if value_override is None else json.dumps({
            "before": before, "after": after, "op": operation,
            "source": {"schema": "control_metadata", "table": "news_sources"},
            "ts_ms": 123456,
        })
        return parse_event(
            topic="platform.control_metadata.news_sources", partition=0, offset=offset,
            key=json.dumps({"source_id": "cafef.vn"}), value=value,
        )

    def test_required_secret_and_identifier_validation(self):
        with patch.dict(os.environ, {"METADATA_POSTGRES_PASSWORD": "", "METADATA_CDC_PASSWORD": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "METADATA_POSTGRES_PASSWORD"):
                MetadataSettings.from_env()
        with patch.dict(os.environ, {
            "METADATA_POSTGRES_PASSWORD": "admin", "METADATA_CDC_PASSWORD": "cdc",
            "METADATA_CDC_SLOT": "invalid-slot",
        }, clear=False):
            with self.assertRaisesRegex(ValueError, "lowercase PostgreSQL identifier"):
                MetadataSettings.from_env()

    def test_connector_captures_only_approved_tables_and_keeps_secret_runtime_only(self):
        config = connector_config(self.settings())
        self.assertEqual(
            config["table.include.list"],
            "control_metadata.news_sources,control_metadata.pipeline_configs",
        )
        self.assertEqual(config["plugin.name"], "pgoutput")
        self.assertEqual(config["snapshot.mode"], "initial")
        self.assertEqual(config["tombstones.on.delete"], "true")
        self.assertNotIn("articles", config["table.include.list"])
        self.assertEqual(config["database.password"], "cdc-secret")

    def test_insert_event_and_stable_key(self):
        event = self.event("c", after={"source_id": "cafef.vn", "enabled": True})
        self.assertEqual(event.operation, "insert")
        self.assertEqual(event.key, {"source_id": "cafef.vn"})
        self.assertEqual(event.entity, "news_sources")

    def test_snapshot_and_update_before_after(self):
        snapshot = self.event("r", after={"source_id": "cafef.vn", "enabled": True})
        self.assertEqual(snapshot.operation, "snapshot")
        update = self.event(
            "u",
            before={"source_id": "cafef.vn", "enabled": True},
            after={"source_id": "cafef.vn", "enabled": False},
            offset=2,
        )
        self.assertEqual(update.operation, "update")
        self.assertEqual(update.before["enabled"], True)
        self.assertEqual(update.after["enabled"], False)
        self.assertEqual(update.changed_fields, ("enabled",))

    def test_delete_and_tombstone(self):
        deleted = self.event("d", before={"source_id": "cafef.vn", "enabled": False}, offset=3)
        tombstone = self.event("d", offset=4, value_override=None)
        self.assertEqual(deleted.operation, "delete")
        self.assertEqual(deleted.before["source_id"], "cafef.vn")
        self.assertEqual(tombstone.operation, "tombstone")
        self.assertIsNone(tombstone.after)

    def test_replayed_offset_is_idempotent_and_delete_removes_state(self):
        state = MetadataState()
        inserted = self.event("c", after={"source_id": "cafef.vn", "enabled": True}, offset=10)
        self.assertTrue(state.apply(inserted))
        self.assertFalse(state.apply(inserted))
        self.assertEqual(len(state.values), 1)
        deleted = self.event("d", before=inserted.after, offset=11)
        self.assertTrue(state.apply(deleted))
        self.assertEqual(state.values, {})

    def test_invalid_message_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonempty JSON object"):
            parse_event(
                topic="platform.control_metadata.news_sources", partition=0, offset=1,
                key='"cafef.vn"', value=json.dumps({"op": "c", "before": None, "after": {}}),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
