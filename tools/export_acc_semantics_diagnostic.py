"""Export raw ACC lap/session semantic evidence from retained archive traces.

This is an offline, read-only diagnostic. It reports observed values and
transitions with original per-stream provenance; it does not infer ACC field
semantics or align Physics and Graphics by array index.
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
    default_db_path, read_archive, read_trace_blob, safe_session_name,
)

GRAPHICS_FIELDS = (
    "status", "session_index", "completed_laps", "current_time_ms",
    "last_time_ms", "session_time_left_ms", "clock_s",
    "distance_traveled_m", "normalized_car_position", "sector",
    "is_in_pit", "is_in_pit_lane", "is_valid_lap", "last_sector_time_ms",
)
PHYSICS_FIELDS = ("speed_kph", "throttle", "brake", "steering_angle", "gear_raw", "rpm")
COLUMNS = (
    "session_id", "archive_lap_number", "archive_lap_valid", "archive_out_lap",
    "stream", "capture_sequence", "capture_timestamp_ns", "field", "value",
)
SUMMARY_FIELDS = (
    "session_id", "track", "track_configuration", "lap_number", "stream",
    "field", "sample_count", "non_null_count", "minimum", "maximum",
    "decrease_count", "increase_count", "unchanged_count", "transition_count",
    "first_capture_sequence", "last_capture_sequence",
    "first_capture_timestamp_ns", "last_capture_timestamp_ns",
)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _summarize_field(values: list[Any]) -> dict[str, Any]:
    observed = [value for value in values if _finite(value)]
    decreases = increases = unchanged = transitions = 0
    previous = None
    previous_set = False
    for value in values:
        if value is None:
            continue
        if previous_set:
            transitions += int(value != previous)
            if _finite(value) and _finite(previous):
                decreases += int(value < previous)
                increases += int(value > previous)
                unchanged += int(value == previous)
        previous, previous_set = value, True
    return {
        "sample_count": len(values),
        "non_null_count": sum(value is not None for value in values),
        "minimum": min(observed) if observed else None,
        "maximum": max(observed) if observed else None,
        "decrease_count": decreases,
        "increase_count": increases,
        "unchanged_count": unchanged,
        "transition_count": transitions,
    }


def _decode_trace(blob: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(zlib.decompress(blob).decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("physics"), list) or not isinstance(payload.get("graphics"), list):
        return None
    return payload


def build_semantics_evidence(rows: list[dict[str, Any]], archive_path: Path):
    """Return long-form source samples and per-field observational summaries."""
    sample_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for lap in rows:
        if lap.get("trace_status") not in ("retained", "identity_incomplete"):
            continue
        blob = read_trace_blob(archive_path, str(lap["session_id"]), int(lap["lap_number"]))
        payload = _decode_trace(blob) if blob else None
        if payload is None:
            continue
        for stream, fields in (("graphics", GRAPHICS_FIELDS), ("physics", PHYSICS_FIELDS)):
            samples = payload[stream]
            for field in fields:
                values = [sample.get(field) if stream == "graphics" else
                          (sample.get("data") or {}).get(field)
                          for sample in samples]
                for sample, value in zip(samples, values):
                    sample_rows.append({
                        "session_id": lap["session_id"],
                        "archive_lap_number": lap["lap_number"],
                        "archive_lap_valid": lap.get("lap_valid"),
                        "archive_out_lap": lap.get("out_lap"),
                        "stream": stream,
                        "capture_sequence": sample.get("capture_sequence"),
                        "capture_timestamp_ns": sample.get("capture_timestamp_ns"),
                        "field": field,
                        "value": value,
                    })
                stats = _summarize_field(values)
                summaries.append({
                    "session_id": lap["session_id"], "track": lap.get("track"),
                    "track_configuration": lap.get("track_configuration"),
                    "lap_number": lap["lap_number"], "stream": stream, "field": field,
                    **stats,
                    "first_capture_sequence": samples[0].get("capture_sequence") if samples else None,
                    "last_capture_sequence": samples[-1].get("capture_sequence") if samples else None,
                    "first_capture_timestamp_ns": samples[0].get("capture_timestamp_ns") if samples else None,
                    "last_capture_timestamp_ns": samples[-1].get("capture_timestamp_ns") if samples else None,
                })
    return sample_rows, summaries


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def export_semantics_diagnostics(rows: list[dict[str, Any]], archive_path: Path, output_dir: Path):
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("session_id") or "unknown-session"), []).append(row)
    outputs: list[Path] = []
    for session_id, session_rows in sorted(grouped.items()):
        samples, summaries = build_semantics_evidence(session_rows, archive_path)
        if not samples:
            continue
        safe_id = safe_session_name(session_id)
        folder = output_dir / safe_id
        folder.mkdir(parents=True, exist_ok=True)
        samples_path = folder / f"acc_semantics_samples_{safe_id}.csv"
        summary_path = folder / f"acc_semantics_summary_{safe_id}.csv"
        _write_csv(samples_path, COLUMNS, samples)
        _write_csv(summary_path, SUMMARY_FIELDS, summaries)
        outputs.extend((samples_path, summary_path))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export raw ACC timing, distance, lap, sector and pit-state evidence."
    )
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"archive not found: {args.db}")
    output = args.output or (PROJECT_ROOT / "user_data" / "PerformanceHub" / "monitor_reports")
    rows, _ = read_archive(args.db)
    paths = export_semantics_diagnostics(rows, args.db, output)
    print(f"Diagnostic files written: {len(paths)}")
    for path in paths:
        print(path)
    if not paths:
        print("No retained full-resolution traces found. Complete at least one eligible timed lap in ACC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
