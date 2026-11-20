"""Export field-level telemetry coverage from the Performance Hub archive.

The exporter is read-only. It reports archive contract presence separately from
non-null value coverage and preserves per-stream capture sequence/timestamp
ranges. Compact invalid/out-lap records are represented as compact evidence,
not as missing full-resolution traces.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import zlib
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for import_path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from tools.monitor_performance_hub import (
    check_trace,
    default_db_path,
    read_archive,
    read_trace_blob,
    safe_session_name,
)
from race_engineer_acquisition.performance_lap_archive import (
    GRAPHICS_ARCHIVE_FIELDS,
    PHYSICS_ARCHIVE_FIELDS,
)

COLUMNS = (
    "session_id", "lap_number", "trace_status", "stream", "field",
    "sample_count", "field_in_all_samples", "non_null_sample_count",
    "null_value_sample_count", "missing_key_sample_count", "coverage_percent",
    "source_sequence_first", "source_sequence_last",
    "source_timestamp_first_ns", "source_timestamp_last_ns",
    "stream_validation_status",
)


def _coverage_rows_for_trace(
    row: dict[str, Any], payload: dict[str, Any], validation: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for stream, contract_fields, samples, data_samples in (
        (
            "physics",
            PHYSICS_ARCHIVE_FIELDS,
            payload["physics"],
            [sample.get("data") if isinstance(sample.get("data"), dict) else {}
             for sample in payload["physics"]],
        ),
        (
            "graphics",
            GRAPHICS_ARCHIVE_FIELDS,
            payload["graphics"],
            payload["graphics"],
        ),
    ):
        count = len(samples)
        sequences = [sample.get("capture_sequence") for sample in samples]
        timestamps = [sample.get("capture_timestamp_ns") for sample in samples]
        missing_contract = set(validation.get(f"{stream}_missing_archive_fields", []))
        for field in contract_fields:
            missing_keys = sum(1 for sample in data_samples if field not in sample)
            null_values = sum(
                1 for sample in data_samples
                if field in sample and sample.get(field) is None
            )
            non_null = count - missing_keys - null_values
            result.append({
                "session_id": row["session_id"],
                "lap_number": row["lap_number"],
                "trace_status": row["trace_status"],
                "stream": stream,
                "field": field,
                "sample_count": count,
                "field_in_all_samples": field not in missing_contract,
                "non_null_sample_count": non_null,
                "null_value_sample_count": null_values,
                "missing_key_sample_count": missing_keys,
                "coverage_percent": round((non_null / count) * 100, 2) if count else 0.0,
                "source_sequence_first": sequences[0] if sequences else None,
                "source_sequence_last": sequences[-1] if sequences else None,
                "source_timestamp_first_ns": timestamps[0] if timestamps else None,
                "source_timestamp_last_ns": timestamps[-1] if timestamps else None,
                "stream_validation_status": "PASS" if validation.get("ok") else "FAIL",
            })
    return result


def build_coverage_rows(
    rows: list[dict[str, Any]], archive_path: Path
) -> list[dict[str, Any]]:
    """Build field-level coverage rows without changing archive contents."""
    coverage: list[dict[str, Any]] = []
    for row in rows:
        trace_status = row.get("trace_status")
        if trace_status in ("retained", "identity_incomplete"):
            blob = read_trace_blob(
                archive_path, str(row["session_id"]), int(row["lap_number"])
            )
            validation = check_trace(
                blob,
                int(row.get("physics_sample_count") or 0),
                int(row.get("graphics_sample_count") or 0),
            )
            if blob is None:
                continue
            try:
                payload = json.loads(zlib.decompress(blob).decode("utf-8"))
            except (ValueError, zlib.error, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if not isinstance(payload.get("physics"), list) or not isinstance(payload.get("graphics"), list):
                continue
            coverage.extend(_coverage_rows_for_trace(row, payload, validation))
        else:
            quality = row.get("quality") if isinstance(row.get("quality"), dict) else {}
            sector = quality.get("sector_evidence") if isinstance(quality.get("sector_evidence"), dict) else {}
            timing_count = quality.get("graphics_timing_observation_count", 0)
            for field, count, status in (
                ("graphics_timing_change_points", timing_count, "COMPACT_EVIDENCE_ONLY"),
                ("raw_sector_observations", sector.get("observation_count", 0),
                 "NOT_ASSIGNED_TO_SECTOR_TIMES"),
            ):
                coverage.append({
                    "session_id": row["session_id"],
                    "lap_number": row["lap_number"],
                    "trace_status": trace_status,
                    "stream": "compact_metadata",
                    "field": field,
                    "sample_count": count,
                    "field_in_all_samples": None,
                    "non_null_sample_count": count,
                    "null_value_sample_count": None,
                    "missing_key_sample_count": None,
                    "coverage_percent": None,
                    "source_sequence_first": None,
                    "source_sequence_last": None,
                    "source_timestamp_first_ns": None,
                    "source_timestamp_last_ns": None,
                    "stream_validation_status": status,
                })
    return coverage


def write_session_coverage(
    rows: list[dict[str, Any]], archive_path: Path, output_dir: Path
) -> list[Path]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("session_id") or "unknown-session"), []).append(row)

    written: list[Path] = []
    for session_id, session_rows in sorted(grouped.items()):
        coverage_rows = build_coverage_rows(session_rows, archive_path)
        if not coverage_rows:
            continue
        safe_id = safe_session_name(session_id)
        session_dir = output_dir / safe_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"telemetry_coverage_{safe_id}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(coverage_rows)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export read-only per-field telemetry coverage CSVs."
    )
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"archive not found: {args.db}")
    output_dir = args.output or (
        PROJECT_ROOT / "user_data" / "PerformanceHub" / "monitor_reports"
    )
    rows, _ = read_archive(args.db)
    paths = write_session_coverage(rows, args.db, output_dir)
    print(f"Sessions exported: {len(paths)}")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
