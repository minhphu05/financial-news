"""Focused tests for the standard-library data profiler and drift workflow."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_data_contracts import (
    BEGIN,
    END,
    compare_profiles,
    classify_timestamp,
    iter_json_records,
    mapping_health,
    scan_data,
    write_contract_document,
)


class DataContractsTests(unittest.TestCase):
    def _write_json(self, data_root: Path, name: str, records: list[dict]) -> Path:
        path = data_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        return path

    def test_json_array_streaming_with_nested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.json"
            records = [{"id": index, "nested": {"value": "x" * 1000}} for index in range(200)]
            path.write_text(json.dumps(records), encoding="utf-8")
            self.assertEqual(list(iter_json_records(path)), records)

    def test_duplicate_json_keys_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            path = root / "raw" / "articles.json"
            path.parent.mkdir(parents=True)
            path.write_text('[{"title":"first","title":"second"}]', encoding="utf-8")
            profile = scan_data(root, "fixed")
            self.assertEqual(profile["datasets"]["data/raw/articles.json"]["anomalies"]["duplicate_json_key"], 1)

    def test_nonstandard_cafef_date_is_identified_without_correction(self) -> None:
        self.assertEqual(classify_timestamp("28-01-2026 - 16:44 PM"), "cafef_24h_with_meridiem_nonstandard")
        self.assertEqual(classify_timestamp("02-02-2026 - 07:32 AM"), "cafef_12h")

    def test_infers_nested_null_missing_and_mixed_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            self._write_json(root, "raw/articles.json", [
                {"link": "https://cafef.vn/a.chn", "metadata": {"Date": "2026-01-01"}, "tags": ["ACB", "VCB"], "value": 1},
                {"link": "https://cafef.vn/b.chn", "metadata": {"Date": None}, "tags": [], "value": "2"},
                {"link": "https://cafef.vn/b.chn", "metadata": {}, "value": None},
            ])
            profile = scan_data(root, "2026-09-20T00:00:00+00:00")
            dataset = profile["datasets"]["data/raw/articles.json"]
            self.assertEqual(dataset["record_count"], 3)
            self.assertEqual(dataset["duplicate_url_rows"], 1)
            self.assertEqual(dataset["fields"]["metadata.Date"]["missing_count"], 1)
            self.assertEqual(dataset["fields"]["metadata.Date"]["null_count"], 1)
            self.assertEqual(dataset["fields"]["value"]["observed_types"], {"integer": 1, "null": 1, "string": 1})
            self.assertEqual(dataset["fields"]["tags[]"]["present_count"], 2)
            self.assertIn("mixed_field_types", dataset["anomalies"])

    def test_deterministic_profile_except_explicit_scan_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            self._write_json(root, "raw/articles.json", [{"z": 2, "a": 1}])
            first = scan_data(root, "fixed")
            second = scan_data(root, "fixed")
            self.assertEqual(first, second)

    def test_detects_field_type_nullability_and_new_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            self._write_json(root, "raw/articles.json", [{"link": "https://cafef.vn/a.chn", "value": 1}])
            before = scan_data(root, "fixed")
            self._write_json(root, "raw/articles.json", [{"link": "https://cafef.vn/a.chn", "value": None, "new": "x"}])
            (root / "new.txt").write_text("hello", encoding="utf-8")
            after = scan_data(root, "fixed")
            drift = compare_profiles(before, after)["source_schema_drift"]
            self.assertTrue(any("NEW FIELD" in item for item in drift))
            self.assertTrue(any("TYPE CHANGE" in item for item in drift))
            self.assertTrue(any("NULLABILITY CHANGE" in item for item in drift))
            self.assertTrue(any("NEW FILE FORMAT" in item for item in drift))
            self.assertEqual(compare_profiles(before, after)["canonical_contract_change"], [])

    def test_detects_json_container_structure_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            path = self._write_json(root, "raw/articles.json", [{"title": "A"}])
            before = scan_data(root, "fixed")
            path.write_text('{"title":"A"}', encoding="utf-8")
            after = scan_data(root, "fixed")
            self.assertTrue(any("CONTAINER STRUCTURE CHANGE" in item for item in compare_profiles(before, after)["source_schema_drift"]))

    def test_mapping_health_flags_removed_primary_source_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            self._write_json(root, "raw/cafef_news_raw_final.json", [{"link": "https://cafef.vn/a.chn"}])
            issues = mapping_health(scan_data(root, "fixed"))
            self.assertTrue(any("title" in issue for issue in issues))

    def test_regeneration_preserves_managed_contract_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            self._write_json(root, "raw/articles.json", [{"title": "A"}])
            profile = scan_data(root, "fixed")
            document = Path(temp) / "data-contracts.md"
            write_contract_document(document, profile)
            initial = document.read_text(encoding="utf-8")
            self.assertIn(BEGIN, initial)
            self.assertIn(END, initial)
            marker = "\nManual engineering decision: keep this.\n"
            document.write_text(initial + marker, encoding="utf-8")
            write_contract_document(document, profile)
            self.assertTrue(document.read_text(encoding="utf-8").endswith(marker))


if __name__ == "__main__":
    unittest.main()
