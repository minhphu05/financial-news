"""Fail-fast source schema compatibility check for one incoming JSON snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EXPECTED_FIELDS: dict[str, type] = {
    "_id": str,
    "context": str,
    "index": int,
    "keyword": str,
    "link": str,
    "metadata": dict,
    "page": int,
    "post date": str,
    "summary": str,
    "ticket name": str,
    "ticket symbol": str,
    "title": str,
}
EXPECTED_METADATA_FIELDS: dict[str, type] = {"Date": str, "Time": str}
REQUIRED_TRANSFORMATION_FIELDS = {"context", "link", "title"}


class SourceSchemaDriftError(ValueError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__("Unsafe source schema mismatch: " + "; ".join(report["errors"][:8]))


def validate_source_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(rows, list):
        errors.append("root must be a JSON array")
        rows = []
    for index, row in enumerate(rows):
        location = f"row[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{location} must be an object")
            if len(errors) >= 100:
                break
            continue
        unknown = sorted(set(row) - set(EXPECTED_FIELDS))
        if unknown:
            errors.append(f"{location} has unexpected fields: {unknown}")
        missing_required = sorted(REQUIRED_TRANSFORMATION_FIELDS - set(row))
        if missing_required:
            errors.append(f"{location} is missing required fields: {missing_required}")
        for field, value in row.items():
            expected = EXPECTED_FIELDS.get(field)
            if expected and type(value) is not expected:
                errors.append(
                    f"{location}.{field} has type {type(value).__name__}; expected {expected.__name__}"
                )
        metadata = row.get("metadata")
        if isinstance(metadata, dict):
            unknown_metadata = sorted(set(metadata) - set(EXPECTED_METADATA_FIELDS))
            if unknown_metadata:
                errors.append(
                    f"{location}.metadata has unexpected fields: {unknown_metadata}"
                )
            for field, value in metadata.items():
                expected = EXPECTED_METADATA_FIELDS.get(field)
                if expected and type(value) is not expected:
                    errors.append(
                        f"{location}.metadata.{field} has type {type(value).__name__}; "
                        f"expected {expected.__name__}"
                    )
        if len(errors) >= 100:
            warnings.append("error list capped at 100 entries")
            break
    report = {
        "compatible": not errors,
        "source_file": str(source),
        "record_count": len(rows),
        "expected_fields": sorted(EXPECTED_FIELDS),
        "errors": errors,
        "warnings": warnings,
    }
    if errors:
        raise SourceSchemaDriftError(report)
    return report
