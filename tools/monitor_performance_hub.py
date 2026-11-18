"""Monitor the live Performance Hub SQLite archive while ACC is running.

This is a read-only observer. It never writes to the application database and
does not attach to ACC shared memory or alter acquisition/decoder behaviour.
Stop with Ctrl+C; a JSON summary and CSV evidence files are written.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import zlib
from typing import Any

GIB = 1024 ** 3
LAP_COLUMNS = (
    "session_id", "lap_number", "car_model", "track", "track_configuration",
    "completed_at_utc", "lap_time_ms", "lap_valid", "out_lap",
    "start_timestamp_ns", "end_timestamp_ns", "physics_sample_count",
    "graphics_sample_count", "weather_json", "quality_json", "trace_blob",
    "trace_bytes", "trace_status", "reason", "pinned_pb",
)


def default_db_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
        return root / "RaceEngineerACC" / "PerformanceHub" / "lap_archive.sqlite3"
    root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share"))
    return root / "race-engineer-acc" / "performance_hub" / "lap_archive.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_readonly(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=3.0)
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA busy_timeout=3000")
    return db


def check_trace(blob: bytes | None, expected_physics: int, expected_graphics: int) -> dict[str, Any]:
    if blob is None:
        return {"ok": False, "reason": "trace_blob_missing"}
    try:
        payload = json.loads(zlib.decompress(blob).decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": f"trace_decode_error:{type(exc).__name__}:{exc}"}

    physics = payload.get("physics")
    graphics = payload.get("graphics")
    if not isinstance(physics, list) or not isinstance(graphics, list):
        return {"ok": False, "reason": "physics_or_graphics_not_a_list"}
    if not physics or not graphics:
        return {"ok": False, "reason": "one_or_both_streams_empty"}

    problems: list[str] = []
    if len(physics) != expected_physics:
        problems.append(f"physics_count:{len(physics)}!={expected_physics}")
    if len(graphics) != expected_graphics:
        problems.append(f"graphics_count:{len(graphics)}!={expected_graphics}")

    for stream_name, samples in (("physics", physics), ("graphics", graphics)):
        sequences = [s.get("capture_sequence") for s in samples]
        timestamps = [s.get("capture_timestamp_ns") for s in samples]
        if any(not isinstance(v, int) or isinstance(v, bool) for v in sequences):
            problems.append(f"{stream_name}_invalid_sequence")
        elif any(b <= a for a, b in zip(sequences, sequences[1:])):
            problems.append(f"{stream_name}_sequence_not_increasing")
        if any(not isinstance(v, int) or isinstance(v, bool) for v in timestamps):
            problems.append(f"{stream_name}_invalid_timestamp")
        elif any(b < a for a, b in zip(timestamps, timestamps[1:])):
            problems.append(f"{stream_name}_timestamp_regression")

    return {
        "ok": not problems,
        "reason": ";".join(problems) if problems else None,
        "physics_count": len(physics),
        "graphics_count": len(graphics),
        "physics_first_sequence": physics[0].get("capture_sequence"),
        "physics_last_sequence": physics[-1].get("capture_sequence"),
        "graphics_first_sequence": graphics[0].get("capture_sequence"),
        "graphics_last_sequence": graphics[-1].get("capture_sequence"),
    }


def read_archive(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with open_readonly(path) as db:
        integrity = db.execute("PRAGMA quick_check").fetchone()
        schema = int(db.execute("PRAGMA user_version").fetchone()[0])
        rows = db.execute(
            """SELECT session_id,lap_number,car_model,track,track_configuration,
               completed_at_utc,lap_time_ms,lap_valid,out_lap,start_timestamp_ns,
               end_timestamp_ns,physics_sample_count,graphics_sample_count,
               weather_json,quality_json,trace_blob,trace_bytes,trace_status,
               reason,pinned_pb
               FROM laps ORDER BY completed_at_utc,id"""
        ).fetchall()
        result = []
        for raw in rows:
            item = dict(zip(LAP_COLUMNS, raw))
            item["weather"] = json.loads(item.pop("weather_json") or "{}")
            item["quality"] = json.loads(item.pop("quality_json") or "{}")
            item["pinned_pb"] = bool(item["pinned_pb"])
            result.append(item)
        return result, {"integrity": integrity[0] if integrity else "no_result", "schema_version": schema}


def evaluate(rows: list[dict[str, Any]], db_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    full = [r for r in rows if r["trace_blob"] is not None]
    compact = [r for r in rows if r["trace_blob"] is None]
    trace_checks = {}
    for row in rows:
        key = f'{row["session_id"]}:{row["lap_number"]}'
        if row["trace_blob"] is not None:
            trace_checks[key] = check_trace(
                row["trace_blob"], int(row["physics_sample_count"] or 0),
                int(row["graphics_sample_count"] or 0),
            )
            if not trace_checks[key]["ok"]:
                issues.append(f"trace_invalid:{key}:{trace_checks[key]['reason']}")
        elif row["trace_status"] in ("retained", "identity_incomplete"):
            issues.append(f"trace_missing_for_status:{key}:{row['trace_status']}")

        if row["trace_blob"] is not None and (
            row["lap_valid"] != 1 or row["out_lap"] != 0
        ):
            issues.append(f"ineligible_lap_has_full_trace:{key}")

        if row["trace_blob"] is None and row["trace_status"] == "compact_metadata":
            if row["lap_valid"] == 1 and row["out_lap"] == 0:
                issues.append(f"eligible_lap_compacted:{key}")

    partitions: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for row in full:
        identity = (row["car_model"], row["track"], row["track_configuration"])
        if all(v is not None for v in identity):
            partitions.setdefault(identity, []).append(row)

    for identity, group in partitions.items():
        pinned = [r for r in group if r["pinned_pb"]]
        if len(pinned) > 1:
            issues.append(f"multiple_pinned_pbs:{identity}")
        if len(group) > 31:
            issues.append(f"retained_over_31_including_pb:{identity}:{len(group)}")
        timed = [r for r in group if isinstance(r["lap_time_ms"], int) and r["lap_time_ms"] > 0]
        if pinned and timed and pinned[0]["lap_time_ms"] is not None:
            if pinned[0]["lap_time_ms"] > min(r["lap_time_ms"] for r in timed):
                issues.append(f"pinned_pb_not_fastest_retained:{identity}")

    db_bytes = db_path.stat().st_size if db_path.exists() else 0
    wal_path = Path(str(db_path) + "-wal")
    shm_path = Path(str(db_path) + "-shm")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    shm_bytes = shm_path.stat().st_size if shm_path.exists() else 0
    physical_bytes = db_bytes + wal_bytes + shm_bytes
    trace_bytes = sum(int(r["trace_bytes"] or 0) for r in rows)

    return {
        "lap_metadata_count": len(rows),
        "full_trace_count": len(full),
        "compact_or_evicted_count": len(compact),
        "session_count": len({r["session_id"] for r in rows}),
        "pinned_pb_count": sum(1 for r in full if r["pinned_pb"]),
        "trace_bytes_accounted_by_archive": trace_bytes,
        "database_bytes": db_bytes,
        "wal_bytes": wal_bytes,
        "shm_bytes": shm_bytes,
        "physical_archive_bytes": physical_bytes,
        "physical_archive_over_2_gib": physical_bytes > 2 * GIB,
        "trace_checks": trace_checks,
        "issues": issues,
        "archive_data_check": "PASS" if not issues else "FAIL",
    }


def serializable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "trace_blob"} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only live monitor for the Race Engineer ACC Performance Hub archive."
    )
    parser.add_argument("--db", type=Path, default=default_db_path(),
                        help="Archive SQLite path (defaults to the app's standard path).")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Polling interval in seconds (default: 2).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory (default: LOCALAPPDATA/.../monitor_reports/<timestamp>).")
    args = parser.parse_args()
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output is None:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
        else:
            root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share"))
        output_dir = root / "RaceEngineerACC" / "PerformanceHub" / "monitor_reports" / stamp
    else:
        output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Performance Hub monitor — read-only mode")
    print(f"Archive: {args.db}")
    print(f"Evidence folder: {output_dir}")
    print("Start/continue driving in ACC. Stop this monitor with Ctrl+C.")
    print("The report only verifies data persisted in the archive; it cannot read internal live queue counters.")

    seen: set[tuple[str, int]] = set()
    first_seen: dict[tuple[str, int], str] = {}
    snapshots: list[dict[str, Any]] = []
    last_rows: list[dict[str, Any]] = []
    db_info: dict[str, Any] = {}
    started = time.monotonic()
    archive_seen = False

    try:
        while True:
            if not args.db.exists():
                print(f"[{utc_now()}] WAITING — archive database has not been created yet")
                time.sleep(args.interval)
                continue
            try:
                rows, db_info = read_archive(args.db)
                archive_seen = True
                last_rows = rows
                new_rows = []
                for row in rows:
                    key = (str(row["session_id"]), int(row["lap_number"]))
                    if key not in seen:
                        seen.add(key)
                        first_seen[key] = utc_now()
                        new_rows.append(row)

                report = evaluate(rows, args.db)
                snapshot = {
                    "timestamp_utc": utc_now(),
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                    **db_info,
                    **{k: v for k, v in report.items() if k != "trace_checks"},
                }
                snapshots.append(snapshot)
                status = report["archive_data_check"]
                print(
                    f'[{snapshot["timestamp_utc"]}] {status} | '
                    f'laps={report["lap_metadata_count"]} '
                    f'full_traces={report["full_trace_count"]} '
                    f'compact/evicted={report["compact_or_evicted_count"]} '
                    f'archive={report["physical_archive_bytes"] / (1024*1024):.2f} MiB '
                    f'new={len(new_rows)}'
                )
                if report["issues"]:
                    for issue in report["issues"]:
                        print(f"  ISSUE: {issue}")
                time.sleep(args.interval)
            except (sqlite3.Error, OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"[{utc_now()}] RETRY — archive temporarily unavailable: {type(exc).__name__}: {exc}")
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping monitor and writing evidence...")

    final_report: dict[str, Any] = {
        "monitor_started_utc": datetime.fromtimestamp(
            time.time() - (time.monotonic() - started), timezone.utc
        ).isoformat(timespec="seconds"),
        "monitor_stopped_utc": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 1),
        "archive_path": str(args.db),
        "archive_was_seen": archive_seen,
        "database_info": db_info,
    }
    if archive_seen:
        final_report["results"] = evaluate(last_rows, args.db)
        final_report["laps"] = serializable_rows(last_rows)
        final_report["new_lap_first_seen_utc"] = {
            f"{session}:{lap}": seen_at for (session, lap), seen_at in first_seen.items()
        }
    else:
        final_report["results"] = {
            "archive_data_check": "NOT VERIFIED",
            "reason": "archive_database_not_seen_during_monitoring",
        }
    final_report["snapshots"] = snapshots

    report_path = output_dir / "performance_hub_report.json"
    report_path.write_text(json.dumps(final_report, indent=2, default=str), encoding="utf-8")
    laps_path = output_dir / "laps.csv"
    csv_rows = serializable_rows(last_rows)
    if csv_rows:
        with laps_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            for row in csv_rows:
                writer.writerow({
                    key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                })
    snapshots_path = output_dir / "monitor_snapshots.csv"
    if snapshots:
        with snapshots_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(snapshots[0].keys()))
            writer.writeheader()
            writer.writerows(snapshots)

    print(f"Report: {report_path}")
    if csv_rows:
        print(f"Lap records: {laps_path}")
    if snapshots:
        print(f"Monitoring history: {snapshots_path}")
    result_status = final_report["results"].get("archive_data_check", "NOT VERIFIED")
    print(f"Final archive-data result: {result_status}")
    return 0 if result_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
