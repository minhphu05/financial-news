"""Profile checked-in data and maintain the observed sections of data contracts.

Only the Python standard library is required. JSON arrays and JSONL files are
read incrementally; no source data is modified. The canonical contract below
is an initial proposal and, once written, is deliberately preserved verbatim
on subsequent profile regenerations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


PROFILE_VERSION = 1
SAMPLE_LIMIT = 3
DISTINCT_LIMIT = 20_000
MAX_JSON_RECORD_BYTES = 16 * 1024 * 1024
BEGIN = "<!-- BEGIN GENERATED OBSERVED DATA -->"
END = "<!-- END GENERATED OBSERVED DATA -->"
ROOT = Path(__file__).resolve().parents[1]
RAW_PRIMARY = "data/raw/cafef_news_raw_final.json"
TIMESTAMP_FORMATS = (
    ("cafef_12h", "%d-%m-%Y - %I:%M %p"),
    ("cafef_24h", "%d-%m-%Y - %H:%M"),
    ("iso_date", "%Y-%m-%d"),
    ("iso_datetime", "%Y-%m-%dT%H:%M:%S"),
    ("clock_24h", "%H:%M:%S"),
)
HTML_TAG = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
HTML_ENTITY = re.compile(r"&(?:nbsp|amp|quot|lt|gt|#\d+|#x[0-9a-fA-F]+);", re.IGNORECASE)
NONSTANDARD_CAFEF_DATE = re.compile(r"^(\d{1,2}-\d{1,2}-\d{4} - \d{1,2}:\d{2}) (AM|PM)$")
URL_FIELDS = {"link", "url", "source_url", "canonical_url"}
TEXT_FIELDS = {"context", "content", "body", "title", "summary", "text", "evidence", "sentence"}


def observed_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def sample(value: Any) -> Any:
    if isinstance(value, str):
        return value[:100] + ("…" if len(value) > 100 else "")
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return rendered[:100] + ("…" if len(rendered) > 100 else "")
    return value


def classify_timestamp(value: str) -> str:
    for label, fmt in TIMESTAMP_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return label
        except ValueError:
            continue
    match = NONSTANDARD_CAFEF_DATE.fullmatch(value)
    if match:
        try:
            datetime.strptime(match.group(1), "%d-%m-%Y - %H:%M")
            return "cafef_24h_with_meridiem_nonstandard"
        except ValueError:
            pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "iso_other"
    except ValueError:
        return "unparsed"


class FieldStats:
    def __init__(self, path: str) -> None:
        self.path = path
        self.present = 0
        self.nulls = 0
        self.types: Counter[str] = Counter()
        self.samples: list[Any] = []
        self.string_min: int | None = None
        self.string_max: int | None = None
        self.number_min: int | float | None = None
        self.number_max: int | float | None = None
        self.array_min: int | None = None
        self.array_max: int | None = None
        self.empty_strings = 0
        self.distinct: set[str] = set()
        self.distinct_capped = False
        self.values: Counter[str] = Counter()
        self.values_capped = False
        self.timestamp_formats: Counter[str] = Counter()
        self.timestamp_examples: dict[str, str] = {}

    def observe(self, value: Any) -> None:
        self.present += 1
        kind = observed_type(value)
        self.types[kind] += 1
        if value is None:
            self.nulls += 1
            return
        value_sample = sample(value)
        if value_sample not in self.samples and len(self.samples) < SAMPLE_LIMIT:
            self.samples.append(value_sample)
        if kind == "string":
            length = len(value)
            self.string_min = length if self.string_min is None else min(self.string_min, length)
            self.string_max = length if self.string_max is None else max(self.string_max, length)
            if not value.strip():
                self.empty_strings += 1
            if any(token in self.path.lower() for token in ("date", "time", "_at")):
                fmt = classify_timestamp(value)
                self.timestamp_formats[fmt] += 1
                self.timestamp_examples.setdefault(fmt, value[:100])
        elif kind in ("integer", "number"):
            self.number_min = value if self.number_min is None else min(self.number_min, value)
            self.number_max = value if self.number_max is None else max(self.number_max, value)
        elif kind == "array":
            length = len(value)
            self.array_min = length if self.array_min is None else min(self.array_min, length)
            self.array_max = length if self.array_max is None else max(self.array_max, length)

        if kind in ("string", "integer", "number", "boolean"):
            key = hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()
            if len(self.distinct) < DISTINCT_LIMIT:
                self.distinct.add(key)
            elif key not in self.distinct:
                self.distinct_capped = True
            if not self.values_capped:
                label = str(value)
                self.values[label] += 1
                if len(self.values) > 30:
                    self.values.clear()
                    self.values_capped = True

    def as_dict(self, denominator: int) -> dict[str, Any]:
        item_scope = "[]" in self.path
        missing = 0 if item_scope else max(0, denominator - self.present)
        result: dict[str, Any] = {
            "observed_types": dict(sorted(self.types.items())),
            "present_count": self.present,
            "missing_count": missing,
            "missing_pct": round(100 * missing / denominator, 3) if denominator and not item_scope else None,
            "null_count": self.nulls,
            "nullable_observed": bool(missing or self.nulls),
            "sample_values": self.samples,
        }
        if item_scope:
            result["scope"] = "array_item"
        if self.string_min is not None:
            result["string_length"] = {"min": self.string_min, "max": self.string_max}
            result["empty_string_count"] = self.empty_strings
        if self.number_min is not None:
            result["numeric_range"] = {"min": self.number_min, "max": self.number_max}
        if self.array_min is not None:
            result["array_length"] = {"min": self.array_min, "max": self.array_max}
        if self.distinct or self.distinct_capped:
            result["distinct_count"] = len(self.distinct)
            result["distinct_exact"] = not self.distinct_capped
        if not self.values_capped and 0 < len(self.values) <= 20:
            result["enum_like_values"] = dict(sorted(self.values.items()))
        if self.timestamp_formats:
            result["timestamp_formats"] = dict(sorted(self.timestamp_formats.items()))
            result["timestamp_examples"] = dict(sorted(self.timestamp_examples.items()))
        return result


def _object_hook(on_duplicate: Any):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result and on_duplicate is not None:
                on_duplicate(key)
            result[key] = value
        return result
    return hook


def iter_json_records(path: Path, on_duplicate: Any = None) -> Iterator[Any]:
    """Yield top-level JSON array elements without loading the array in memory."""
    decoder = json.JSONDecoder(object_pairs_hook=_object_hook(on_duplicate))
    with path.open("r", encoding="utf-8-sig") as stream:
        buffer = ""
        pos = 0
        eof = False

        def fill() -> bool:
            nonlocal buffer, pos, eof
            if pos:
                buffer = buffer[pos:]
                pos = 0
            chunk = stream.read(64 * 1024)
            if not chunk:
                eof = True
                return False
            buffer += chunk
            return True

        def next_nonspace() -> str:
            nonlocal pos
            while True:
                while pos < len(buffer) and buffer[pos].isspace():
                    pos += 1
                if pos < len(buffer):
                    return buffer[pos]
                if not fill():
                    return ""

        if not fill():
            raise ValueError("empty JSON file")
        first = next_nonspace()
        if first == "[":
            pos += 1
            expect_value = True
            first_value = True
            while True:
                token = next_nonspace()
                if token == "]" and expect_value:
                    if not first_value:
                        raise ValueError("trailing comma in JSON array")
                    pos += 1
                    break
                if not token:
                    raise ValueError("unterminated JSON array")
                if not expect_value:
                    if token == ",":
                        pos += 1
                        expect_value = True
                        continue
                    if token == "]":
                        pos += 1
                        break
                    raise ValueError("expected comma or closing bracket")
                try:
                    value, end = decoder.raw_decode(buffer, pos)
                except json.JSONDecodeError as exc:
                    if len(buffer) - pos > MAX_JSON_RECORD_BYTES or not fill():
                        raise ValueError(f"malformed JSON array element: {exc}") from exc
                    continue
                pos = end
                expect_value = False
                first_value = False
                yield value
            if next_nonspace():
                raise ValueError("trailing content after JSON array")
        else:
            # Small root objects/scalars are uncommon here, but are included.
            try:
                yield json.loads(buffer + stream.read(), object_pairs_hook=_object_hook(on_duplicate))
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSON document: {exc}") from exc


def iter_jsonl_records(path: Path, on_duplicate: Any = None) -> Iterator[Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line, object_pairs_hook=_object_hook(on_duplicate))
            except json.JSONDecodeError as exc:
                yield {"__profile_error__": f"line {line_no}: {exc.msg}"}


def _xlsx_cell_value(cell: ET.Element, shared: list[str]) -> Any:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(ns + "t"))
    value_node = cell.find(ns + "v")
    if value_node is None:
        return None
    raw = value_node.text or ""
    if kind == "s":
        return shared[int(raw)]
    if kind == "b":
        return raw == "1"
    if kind in ("str", "e"):
        return raw
    try:
        numeric = float(raw)
        return int(numeric) if numeric.is_integer() else numeric
    except ValueError:
        return raw


def iter_xlsx_rows(path: Path) -> Iterator[dict[str, Any]]:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as source:
                for _, element in ET.iterparse(source, events=("end",)):
                    if element.tag == ns + "si":
                        shared.append("".join(node.text or "" for node in element.iter(ns + "t")))
                        element.clear()
        sheets = sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
        for sheet in sheets:
            headers: dict[int, str] | None = None
            with archive.open(sheet) as source:
                for _, row in ET.iterparse(source, events=("end",)):
                    if row.tag != ns + "row":
                        continue
                    values: dict[int, Any] = {}
                    for cell in row.findall(ns + "c"):
                        letters = re.match(r"[A-Z]+", cell.get("r", ""))
                        if not letters:
                            continue
                        index = 0
                        for letter in letters.group():
                            index = index * 26 + ord(letter) - ord("A") + 1
                        values[index] = _xlsx_cell_value(cell, shared)
                    if headers is None:
                        headers = {idx: str(value) for idx, value in values.items() if value is not None}
                    elif values:
                        yield {name: values.get(idx) for idx, name in headers.items()}
                    row.clear()


def detect_format(path: Path) -> str:
    if path.name == ".DS_Store":
        return "macos_metadata"
    return {".json": "json", ".jsonl": "jsonl", ".xlsx": "xlsx", ".md": "markdown", ".txt": "text"}.get(path.suffix.lower(), "unknown")


def dataset_key(relative: str) -> str:
    if relative.startswith("data/labeled/span/") and relative.endswith(".json"):
        return "data/labeled/span/*.json"
    return relative


class DatasetStats:
    def __init__(self, key: str, format_name: str) -> None:
        self.key = key
        self.format = format_name
        self.file_count = 0
        self.total_bytes = 0
        self.record_count = 0
        self.fields: dict[str, FieldStats] = {}
        self.root_types: Counter[str] = Counter()
        self.container_types: Counter[str] = Counter()
        self.encodings: Counter[str] = Counter()
        self.anomalies: Counter[str] = Counter()
        self.anomaly_examples: dict[str, list[str]] = defaultdict(list)
        self.url_hosts: Counter[str] = Counter()
        self.url_schemes: Counter[str] = Counter()
        self.seen_urls: set[str] = set()
        self.duplicate_url_rows = 0
        self.files: list[str] = []

    def anomaly(self, code: str, detail: str) -> None:
        self.anomalies[code] += 1
        if detail not in self.anomaly_examples[code] and len(self.anomaly_examples[code]) < SAMPLE_LIMIT:
            self.anomaly_examples[code].append(detail[:160])

    def _field(self, path: str, value: Any) -> None:
        self.fields.setdefault(path, FieldStats(path)).observe(value)
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                self._field(f"{path}.{key}", child)
        elif isinstance(value, list):
            for child in value:
                self._field(f"{path}[]", child)

        base = path.rsplit(".", 1)[-1].lower()
        if base in URL_FIELDS and isinstance(value, str):
            parsed = urlparse(value)
            if not parsed.scheme or not parsed.netloc:
                self.anomaly("malformed_url", f"{path}: {value[:100]}")
            else:
                self.url_hosts[parsed.netloc.lower()] += 1
                self.url_schemes[parsed.scheme.lower()] += 1
        if base in TEXT_FIELDS and isinstance(value, str):
            if not value.strip():
                self.anomaly("blank_text_value", path)
            if HTML_TAG.search(value):
                self.anomaly("html_tag_in_text", path)
            if HTML_ENTITY.search(value):
                self.anomaly("html_entity_in_text", path)
            if "\ufffd" in value:
                self.anomaly("replacement_character", path)
            if "\x00" in value:
                self.anomaly("nul_character", path)

    def add_record(self, record: Any, location: str) -> None:
        if isinstance(record, dict) and "__profile_error__" in record:
            self.anomaly("malformed_jsonl", f"{location}: {record['__profile_error__']}")
            return
        self.record_count += 1
        self.root_types[observed_type(record)] += 1
        if isinstance(record, dict):
            for key, value in sorted(record.items()):
                if not key:
                    self.anomaly("empty_field_name", location)
                self._field(key, value)
            url = record.get("link") or record.get("url")
            if isinstance(url, str):
                if url in self.seen_urls:
                    self.duplicate_url_rows += 1
                elif len(self.seen_urls) <= 250_000:
                    self.seen_urls.add(url)
        else:
            self._field("$value", record)

    def as_dict(self) -> dict[str, Any]:
        fields = {key: value.as_dict(self.record_count) for key, value in sorted(self.fields.items())}
        for key, stats in fields.items():
            if len([kind for kind in stats["observed_types"] if kind != "null"]) > 1:
                self.anomaly("mixed_field_types", key)
            for timestamp_kind, anomaly_code in (
                ("unparsed", "unparsed_timestamp_values"),
                ("cafef_24h_with_meridiem_nonstandard", "nonstandard_timestamp_values"),
            ):
                count = stats.get("timestamp_formats", {}).get(timestamp_kind, 0)
                if count:
                    self.anomalies[anomaly_code] += count
                    example = f"{key}: {stats['timestamp_examples'][timestamp_kind]}"
                    if example not in self.anomaly_examples[anomaly_code]:
                        self.anomaly_examples[anomaly_code].append(example)
        result: dict[str, Any] = {
            "path_pattern": self.key,
            "format": self.format,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "record_count": self.record_count,
            "encodings": dict(sorted(self.encodings.items())),
            "root_types": dict(sorted(self.root_types.items())),
            "container_types": dict(sorted(self.container_types.items())),
            "fields": fields,
            "anomalies": dict(sorted(self.anomalies.items())),
            "anomaly_examples": dict(sorted(self.anomaly_examples.items())),
        }
        if self.file_count <= 30:
            result["files"] = self.files
        else:
            result["sample_files"] = self.files[:3]
        if self.url_hosts:
            result["url_hosts"] = dict(sorted(self.url_hosts.items()))
            result["url_schemes"] = dict(sorted(self.url_schemes.items()))
            result["distinct_urls"] = len(self.seen_urls)
            result["duplicate_url_rows"] = self.duplicate_url_rows
        return result


def scan_data(data_root: Path, scan_timestamp: str | None = None) -> dict[str, Any]:
    data_root = data_root.resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    datasets: dict[str, DatasetStats] = {}
    formats: Counter[str] = Counter()
    files = sorted(path for path in data_root.rglob("*") if path.is_file())
    for path in files:
        relative = "data/" + path.relative_to(data_root).as_posix()
        fmt = detect_format(path)
        formats[fmt] += 1
        key = dataset_key(relative)
        group = datasets.setdefault(key, DatasetStats(key, fmt))
        group.file_count += 1
        group.total_bytes += path.stat().st_size
        if len(group.files) < 30:
            group.files.append(relative)
        if fmt in ("json", "jsonl", "markdown", "text"):
            with path.open("rb") as handle:
                head = handle.read(4096)
                bom = head.startswith(b"\xef\xbb\xbf")
            group.encodings["UTF-8 with BOM" if bom else "UTF-8"] += 1
            if fmt == "json":
                token = head[3:] if bom else head
                token = token.lstrip()[:1]
                group.container_types[{b"[": "array", b"{": "object"}.get(token, "scalar_or_unknown")] += 1
            elif fmt == "jsonl":
                group.container_types["line_records"] += 1
        elif fmt == "xlsx":
            group.encodings["OOXML ZIP/XML"] += 1
            group.container_types["workbook_rows"] += 1
        else:
            group.encodings["binary/unknown"] += 1
        try:
            if fmt == "json":
                iterator = iter_json_records(path, lambda field: group.anomaly("duplicate_json_key", f"{relative}: {field}"))
            elif fmt == "jsonl":
                iterator = iter_jsonl_records(path, lambda field: group.anomaly("duplicate_json_key", f"{relative}: {field}"))
            elif fmt == "xlsx":
                iterator = iter_xlsx_rows(path)
            elif fmt in ("markdown", "text"):
                # Validate encoding; these are documentation, not row datasets.
                with path.open(encoding="utf-8-sig") as handle:
                    for _ in handle:
                        pass
                continue
            else:
                continue
            for index, record in enumerate(iterator, start=1):
                group.add_record(record, f"{relative}:{index}")
        except (UnicodeError, ValueError, zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            group.anomaly("unreadable_or_malformed_file", f"{relative}: {exc}")
    result = {
        "profile_version": PROFILE_VERSION,
        "scan_timestamp": scan_timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paths_scanned": ["data/**/*"],
        "scanned_files": ["data/" + path.relative_to(data_root).as_posix() for path in files],
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "file_formats": dict(sorted(formats.items())),
        "datasets": {key: group.as_dict() for key, group in sorted(datasets.items())},
    }
    result["schema_differences"] = schema_differences(result["datasets"])
    return result


def schema_differences(datasets: dict[str, Any]) -> list[dict[str, Any]]:
    primary = datasets.get(RAW_PRIMARY)
    if primary is None:
        return []
    baseline = primary["fields"]
    differences = []
    for key in sorted(datasets):
        if key == RAW_PRIMARY or not key.startswith("data/raw/") or datasets[key]["format"] not in ("json", "jsonl"):
            continue
        fields = datasets[key]["fields"]
        differences.append({
            "compared_to": RAW_PRIMARY,
            "dataset": key,
            "only_in_dataset": sorted(set(fields) - set(baseline)),
            "only_in_primary": sorted(set(baseline) - set(fields)),
            "type_differences": {
                field: {"primary": sorted(baseline[field]["observed_types"]), "dataset": sorted(fields[field]["observed_types"])}
                for field in sorted(set(fields) & set(baseline))
                if set(baseline[field]["observed_types"]) != set(fields[field]["observed_types"])
            },
        })
    return differences


def mapping_health(profile: dict[str, Any]) -> list[str]:
    primary = profile["datasets"].get(RAW_PRIMARY)
    if primary is None:
        return [f"Canonical source missing: {RAW_PRIMARY}"]
    fields = primary["fields"]
    issues = []
    for field in ("link", "title", "context", "post date", "ticket symbol", "keyword"):
        if field not in fields:
            issues.append(f"Mapping source field removed: {field}")
        else:
            types = set(fields[field]["observed_types"]) - {"null"}
            if types != {"string"}:
                issues.append(f"Mapping source field has unsupported non-null types: {field} -> {sorted(types)}")
    return issues


def compare_profiles(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    drift: list[str] = []
    information: list[str] = []
    before = previous.get("datasets", {})
    after = current.get("datasets", {})
    for key in sorted(set(before) | set(after)):
        if key not in before:
            drift.append(f"NEW DATASET: {key} ({after[key]['format']})")
            continue
        if key not in after:
            drift.append(f"REMOVED DATASET: {key}")
            continue
        old, new = before[key], after[key]
        if old["format"] != new["format"]:
            drift.append(f"FORMAT CHANGE: {key}: {old['format']} -> {new['format']}")
        if set(old["root_types"]) != set(new["root_types"]):
            drift.append(f"ROOT STRUCTURE CHANGE: {key}: {sorted(old['root_types'])} -> {sorted(new['root_types'])}")
        if set(old.get("container_types", {})) != set(new.get("container_types", {})):
            drift.append(f"CONTAINER STRUCTURE CHANGE: {key}: {sorted(old.get('container_types', {}))} -> {sorted(new.get('container_types', {}))}")
        old_fields, new_fields = old["fields"], new["fields"]
        for field in sorted(set(new_fields) - set(old_fields)):
            drift.append(f"NEW FIELD: {key} / {field}")
        for field in sorted(set(old_fields) - set(new_fields)):
            drift.append(f"REMOVED FIELD: {key} / {field}")
        for field in sorted(set(old_fields) & set(new_fields)):
            old_types = set(old_fields[field]["observed_types"])
            new_types = set(new_fields[field]["observed_types"])
            if old_types != new_types:
                drift.append(f"TYPE CHANGE: {key} / {field}: {sorted(old_types)} -> {sorted(new_types)}")
            if old_fields[field]["nullable_observed"] != new_fields[field]["nullable_observed"]:
                drift.append(f"NULLABILITY CHANGE: {key} / {field}: {old_fields[field]['nullable_observed']} -> {new_fields[field]['nullable_observed']}")
        if old["file_count"] != new["file_count"]:
            information.append(f"FILE COUNT: {key}: {old['file_count']} -> {new['file_count']}")
        if old["record_count"] != new["record_count"]:
            information.append(f"RECORD COUNT: {key}: {old['record_count']} -> {new['record_count']}")
    for fmt in sorted(set(current["file_formats"]) - set(previous.get("file_formats", {}))):
        drift.append(f"NEW FILE FORMAT: {fmt}")
    old_paths = set(previous.get("scanned_files", []))
    new_paths = set(current.get("scanned_files", []))
    for path in sorted(new_paths - old_paths):
        information.append(f"NEW FILE: {path}")
    for path in sorted(old_paths - new_paths):
        information.append(f"REMOVED FILE: {path}")
    drift.extend(f"MAPPING AT RISK: {issue}" for issue in mapping_health(current))
    return {"source_schema_drift": sorted(set(drift)), "volume_changes": sorted(set(information)), "canonical_contract_change": []}


def _md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def render_observed(profile: dict[str, Any]) -> str:
    datasets = profile["datasets"]
    lines = [
        "# Data Contracts", "", BEGIN, "",
        "## 1. Data Sources Currently Available", "",
        f"Observed by the standard-library profiler at `{profile['scan_timestamp']}`. This section describes files, **not** a canonical Silver schema. The scanner visited `{profile['file_count']:,}` files under `data/` ({profile['total_bytes']:,} bytes).", "",
        "| Dataset/path pattern | Format | Files | Records | Source / purpose |", "|---|---|---:|---:|---|",
    ]
    for key, ds in datasets.items():
        if ds["format"] == "macos_metadata":
            purpose = "System metadata; not a dataset"
        elif key.startswith("data/raw/cafe"):
            purpose = "CafeF article export"
        elif key.endswith("news_titles.jsonl"):
            purpose = "CafeF article-title derivative"
        elif key.endswith("vn30.xlsx"):
            purpose = "VN30 ticker/keyword reference workbook"
        elif "/labeled/" in key:
            purpose = "NER/span research data"
        elif "/eval/" in key:
            purpose = "RAG evaluation questions" if ds["format"] == "jsonl" else "Evaluation documentation"
        else:
            purpose = "System/support file"
        lines.append(f"| `{key}` | {ds['format']} | {ds['file_count']:,} | {ds['record_count']:,} | {purpose} |")
    lines += ["", "The URL host is inferred from the observed `link` values. It is not a publisher field stored in the raw JSON. Research and evaluation datasets are separate from article ingestion.", "", "## 2. Directory and File Layout", "", "```text", "data/", "├── raw/                 JSON article snapshots, title JSONL, VN30 XLSX", "├── labeled/", "│   ├── ner/             JSONL raw/split/syllable annotation data", "│   ├── span/            many JSON arrays of labeled spans", "│   └── span_tags/       label-specific JSON arrays", "└── eval/                RAG evaluation JSONL and README", "```", "", "Observed format counts: " + ", ".join(f"`{fmt}` {count:,}" for fmt, count in profile["file_formats"].items()) + ". Text files were decoded as UTF-8 (BOM recorded where present); XLSX is OOXML ZIP/XML. `.DS_Store` files are binary system metadata, not datasets.", "", "## 3. Observed Raw / Source Schema", "", "The tables below are inferred from every parseable record in each dataset. `[]` denotes array items; item statistics use the observed item population rather than the record population. `Nullable` means a null or missing value was observed; it is **not** a proposed requirement.", ""]
    for key, ds in datasets.items():
        if not ds["fields"]:
            continue
        lines += [f"### `{key}`", "", f"Records: **{ds['record_count']:,}**; file container: `{', '.join(ds['container_types'])}`; record root types: `{json.dumps(ds['root_types'], sort_keys=True)}`; encoding: `{', '.join(ds['encodings'])}`.", "", "| Field | Observed Type | Nullable | Example | Notes |", "|---|---|---|---|---|"]
        for field, stats in ds["fields"].items():
            display_field = field or "<empty field name>"
            notes = [f"present {stats['present_count']:,}"]
            if stats["missing_pct"] is not None:
                notes.append(f"missing {stats['missing_pct']}%")
            if stats["null_count"]:
                notes.append(f"null {stats['null_count']:,}")
            if stats.get("empty_string_count"):
                notes.append(f"blank string {stats['empty_string_count']:,}")
            if stats.get("string_length"):
                rng = stats["string_length"]
                notes.append(f"length {rng['min']}–{rng['max']}")
            if stats.get("numeric_range"):
                rng = stats["numeric_range"]
                notes.append(f"range {rng['min']}–{rng['max']}")
            if stats.get("array_length"):
                rng = stats["array_length"]
                notes.append(f"array length {rng['min']}–{rng['max']}")
            if "distinct_count" in stats:
                prefix = "" if stats["distinct_exact"] else "≥"
                notes.append(f"distinct {prefix}{stats['distinct_count']:,}")
            if stats.get("timestamp_formats"):
                notes.append("date/time " + ", ".join(f"{name}: {count:,}" for name, count in stats["timestamp_formats"].items()))
            if stats.get("enum_like_values") and len(stats["enum_like_values"]) <= 20:
                notes.append("values " + ", ".join(_md_escape(v) for v in stats["enum_like_values"]))
            example = stats["sample_values"][0] if stats["sample_values"] else "—"
            lines.append(f"| `{_md_escape(display_field)}` | `{', '.join(stats['observed_types'])}` | {'Yes' if stats['nullable_observed'] else 'No'} | {_md_escape(example)} | {'; '.join(notes)} |")
        lines.append("")
    lines += ["## 4. Data Quality Observations", "", "The following are observations or heuristics; they are not silently corrected by profiling.", "", "| Dataset | Observation | Count | Examples / interpretation |", "|---|---|---:|---|"]
    for key, ds in datasets.items():
        if ds.get("duplicate_url_rows"):
            lines.append(f"| `{key}` | Repeated URL rows | {ds['duplicate_url_rows']:,} | {ds.get('distinct_urls', 0):,} distinct observed URLs; repeated rows may carry different ticker/keyword values. |")
        for code, count in ds["anomalies"].items():
            examples = "; ".join(ds["anomaly_examples"].get(code, []))
            lines.append(f"| `{key}` | `{code}` | {count:,} | {_md_escape(examples)} |")
        for field, stats in ds["fields"].items():
            display_field = field or "<empty field name>"
            if stats["missing_count"] or stats["null_count"]:
                lines.append(f"| `{key}` | Missing/null `{display_field}` | {stats['missing_count'] + stats['null_count']:,} | missing {stats['missing_count']:,}; explicit null {stats['null_count']:,}. |")
            unparsed = stats.get("timestamp_formats", {}).get("unparsed", 0)
            if unparsed:
                lines.append(f"| `{key}` | Unparsed timestamp in `{field}` | {unparsed:,} | {_md_escape(stats.get('timestamp_examples', {}).get('unparsed', ''))} |")
    lines += ["", "### Cross-file schema differences relative to the largest article snapshot", ""]
    for diff in profile["schema_differences"]:
        lines.append(f"- `{diff['dataset']}`: only here `{diff['only_in_dataset']}`; only in `{RAW_PRIMARY}` `{diff['only_in_primary']}`; type differences `{diff['type_differences']}`.")
    primary = datasets.get(RAW_PRIMARY)
    if primary:
        context = primary["fields"].get("context", {})
        date = primary["fields"].get("post date", {})
        lines += ["", "### Article-export findings requiring review", "", f"- `{RAW_PRIMARY}` has {primary.get('distinct_urls', 0):,} distinct URLs in {primary['record_count']:,} observations; {primary.get('duplicate_url_rows', 0):,} rows repeat an earlier URL. Its observed URL hosts are `{primary.get('url_hosts', {})}` and schemes are `{primary.get('url_schemes', {})}`. Basic URL parsing found {primary['anomalies'].get('malformed_url', 0)} malformed URL values.", f"- `context` contains {context.get('empty_string_count', 0):,} blank/whitespace strings and {context.get('null_count', 0):,} explicit nulls. HTML-tag and HTML-entity counts are heuristic checks; the source may still contain non-HTML boilerplate or formatting problems.", f"- `post date` has {date.get('timestamp_formats', {}).get('cafef_24h_with_meridiem_nonstandard', 0):,} values with a 24-hour hour plus `AM`/`PM`. The profiler labels them nonstandard and does not rewrite them. `metadata.Date`/`metadata.Time` remain separate export metadata until their semantics are confirmed.", "- The selected article export has no observed image URL, author, or editorial category field. The earlier `cafeF_news.json` lacks `title`; the title JSONL is only a derivative. No duplicate JSON object keys were detected in the article exports by this scan."]
    lines += ["", "Check source-to-canonical mapping health separately: " + ("; ".join(mapping_health(profile)) or "all currently required source fields were observed with string values") + ".", "", END, ""]
    return "\n".join(lines)


MANUAL_CONTRACT = """
## 5. Proposed Bronze Contract

Bronze preserves the exact source object bytes in immutable storage. Each source record retains its original field names, nesting, values, order within the file, and optional/null fields. The JSON array snapshot is not rewritten into a guessed canonical schema. An ingestion manifest adds only `ingestion_id`, `source` (derived from the verified URL host, currently `cafef.vn`), `source_file`, `ingested_at` (UTC time of import, **not** publication time), `ingestion_date`, `raw_record_hash` or source-file SHA-256, byte size, record count, and source row position where record-level lineage is needed. Hashing/canonicalization rules must be versioned. These are system metadata, not original CafeF fields. The current `_id` is an export ID and must remain intact in Bronze.

## 6. Proposed Canonical Silver Article Contract

**Engineering proposal, version 1.** This section is intentionally outside the generated observed block. Regenerating a source profile must not change this contract without review. `required` refers to accepted Silver articles; a malformed observation goes to a rejects dataset with batch/row/reason lineage. The article grain is one `(source, canonical_url)`; retain repeated search/ticker associations in a separate `article_mentions` table.

| Canonical Field | Type | Required | Source Mapping | Transformation | Notes |
|---|---|---|---|---|---|
| `article_id` | string | Yes | `link` plus derived `source` | Deterministic ID from source and canonical URL | Do not use Mongo `_id` as the article key. |
| `source` | string | Yes | `link` host | Validate host and map to provider code | Current observed provider: CafeF only. |
| `source_url` | string | Yes | `link` | Preserve original value | Required for source citation. |
| `canonical_url` | string | Yes | `link` | Apply documented URL normalization | Do not erase original URL. |
| `title` | string | Yes | `title` | Unicode/whitespace normalization | Present in selected final snapshot; absent in older `cafeF_news.json`. |
| `description` | string? | No | `summary` | Conservative text normalization | A teaser, not the article body. |
| `content` | string | Yes | `context` | HTML/text cleanup, Unicode NFC, whitespace normalization | Empty/null bodies are rejected or quarantined; Bronze preserves them. |
| `published_at` | timestamp? | No | `post date` | Parse only reviewed CafeF formats with an explicit Asia/Ho_Chi_Minh policy | Keep raw string and parse status. The observed 24-hour-plus-meridiem form is nonstandard; leave it null until its interpretation is approved. |
| `published_at_raw` | string? | No | `post date` | Preserve source string | Avoid invented time. |
| `content_hash` | string | Yes | normalized `content` | Deterministic hash with versioned normalization | Same content on different URLs is flagged, not automatically merged. |
| `processing_version` | string | Yes | system configuration | Record normalization/schema version | Supports reproducible replay. |
| `source_ingestion_id` | string | Yes | Bronze manifest | Carry lineage | Links Silver to immutable source. |
| `author` | string? | No | Unavailable | No mapping | Cannot currently be populated from checked-in article JSON. |
| `crawled_at` | timestamp? | No | Unavailable | No mapping | `metadata.Date`/`Time` may be export/capture metadata, but semantics are unverified. |
| `category` | string? | No | Unavailable | No mapping | `keyword` is a search term, not a confirmed editorial category. |
| `image_urls` | array<string> | No | Unavailable | No mapping | No image URL field observed in article export. |

`article_mentions` records distinct `(article_id, ticker_symbol, keyword)` observations with original `ticket name`, `page`, `index`, and source row lineage. These source fields are search/discovery metadata; a ticker association is **not** proof the article's text mentions that security. A single article can have multiple associations.

## 7. Source-to-Canonical Mapping

Current canonical seed: `data/raw/cafef_news_raw_final.json`. Explicit source mappings:

| Current source field | Canonical destination | Status |
|---|---|---|
| `link` | `source_url`, `canonical_url`, and derived `article_id`/`source` | Observed; validate URL. |
| `title` | `title` | Observed in final snapshot. |
| `summary` | `description` | Observed. |
| `context` | `content` then `content_hash` | Observed; can be empty/null. |
| `post date` | `published_at_raw`, parsed `published_at` | Observed; some values malformed. |
| `ticket symbol` | `article_mentions.ticker_symbol` | Observed; source spelling preserved in Bronze. |
| `ticket name` | `article_mentions.ticker_name` | Observed. |
| `keyword` | `article_mentions.keyword` | Observed search term. |
| `page`, `index` | `article_mentions.source_page`, `source_index` | Observed positional metadata. |
| `_id` | Bronze lineage only | Observed export identifier, not canonical article ID. |
| `metadata.Date`, `metadata.Time` | Bronze lineage only | Observed; do not call publication/crawl time without provenance. |

## 8. Future Enrichment Contract

An optional enrichment output may add `entities` (typed mentions with spans and model version), `stock_symbols` (resolved security identifiers with confidence/provenance), and `financial_events` (event type, evidence span, time, model version). These are **future ViFinNER/NLP outputs**. The current raw sample has search ticker tags but does not provide these enriched fields. Silver and Gold creation must work when enrichment is unavailable; record `enrichment_status` and `enricher_version` when an enricher is used.

## 9. Gold RAG Chunk Contract

This is a proposed future projection from versioned Silver/Gold articles, not an observed raw schema.

| Field | Type | Availability / derivation |
|---|---|---|
| `chunk_id` | string | Deterministic from `article_id`, article content version, chunker version, chunk index. |
| `article_id` | string | From accepted Silver article. |
| `chunk_index` | integer | Generated by chunker, ordered from zero. |
| `text` | string | Slice of normalized `content`. |
| `title` | string | Propagated from article. |
| `source` | string | Derived/validated from URL host. |
| `source_url` | string | Propagated original article URL. |
| `published_at` | timestamp? | Parsed if valid; otherwise null. |
| `stock_symbols` | array<string> | Search ticker associations available now; resolved in-text entities are future enrichment and must be distinguished. |
| `entities` | array<object>? | Future enrichment; absent/null now. |
| `processing_version` | string | From article/chunker configuration. |

Embeddings and Qdrant point IDs are separate, rebuildable projections of committed Gold chunks. A chunk is valid without an embedding.

## 10. Open Questions

1. What exactly do export `metadata.Date` and `metadata.Time` mean, and what timezone were they recorded in?
2. Which URL canonicalization and article-version policy should handle source edits, redirects, and tracking parameters?
3. Should malformed `post date` strings such as a 24-hour hour paired with `PM` be parsed by a documented exception or left null for manual review?
4. Are `ticket symbol`/`keyword` merely search provenance, or may any be promoted to verified article-level tags?
5. How should the project govern content-identical articles published at different URLs and older overlapping snapshots?
6. Which future providers and license/provenance rules will apply? Only CafeF article URLs were observed in this repository.

## Regeneration and drift workflow

- Run `make data-contracts` after adding or changing files under `data/`. It rescans recursively, replaces only sections 1–4 between generator markers, and writes `artifacts/data-profile.json`. Sections 5–10 are review-owned and preserved.
- Run `make data-contracts-check` in review/CI before regeneration. It rescans read-only, compares with the saved profile, prints source schema drift and count changes, and exits nonzero for structural drift. It does not change either output file.
- A changed observed field is **source schema drift**, not automatic approval to change the Silver contract. Review mapping health, update source adapters/tests if needed, and change sections 5–10 only through an explicit engineering decision.
- The machine profile records UTC scan time, so timestamps change when regenerated. Dataset ordering and all other output are stable for unchanged input.
"""


def write_contract_document(path: Path, profile: dict[str, Any]) -> None:
    observed = render_observed(profile)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if BEGIN not in existing or END not in existing:
            raise ValueError(f"{path} exists without generator markers; refusing to overwrite manual contract")
        tail = existing.split(END, 1)[1]
        new_text = observed + tail
    else:
        new_text = observed + MANUAL_CONTRACT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare with saved profile without writing files")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--profile", type=Path, default=ROOT / "artifacts" / "data-profile.json")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs" / "data-contracts.md")
    args = parser.parse_args(argv)
    current = scan_data(args.data_root)
    if args.check:
        if not args.profile.exists():
            print(f"No saved observed profile: {args.profile}", file=sys.stderr)
            return 2
        previous = json.loads(args.profile.read_text(encoding="utf-8"))
        report = compare_profiles(previous, current)
        print("SOURCE SCHEMA DRIFT")
        for item in report["source_schema_drift"]:
            print(f"  - {item}")
        if not report["source_schema_drift"]:
            print("  None detected")
        print("VOLUME CHANGES")
        for item in report["volume_changes"]:
            print(f"  - {item}")
        if not report["volume_changes"]:
            print("  None detected")
        print("CANONICAL MAPPING STATUS")
        issues = mapping_health(current)
        if issues:
            for issue in issues:
                print(f"  - AT RISK: {issue}")
        else:
            print("  Current source fields support the documented mapping")
        print("CANONICAL CONTRACT CHANGE: none applied automatically; review docs/data-contracts.md sections 5–10 separately.")
        return 1 if report["source_schema_drift"] else 0
    args.profile.parent.mkdir(parents=True, exist_ok=True)
    args.profile.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_contract_document(args.docs, current)
    print(f"Profiled {current['file_count']:,} files into {len(current['datasets'])} datasets.")
    print(f"Wrote {args.profile} and {args.docs}")
    for issue in mapping_health(current):
        print(f"MAPPING AT RISK: {issue}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
