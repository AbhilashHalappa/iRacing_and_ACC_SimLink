"""Monitor the live Performance Hub SQLite archive while ACC is running.

This is a read-only observer. It never writes to the application database and
does not attach to ACC shared memory or alter acquisition/decoder behaviour.
Stop with Ctrl+C; a JSON summary and CSV evidence files are written.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
import zlib
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from race_engineer_acquisition.storage_paths import (
    default_monitor_reports_dir,
    default_performance_archive_path,
    migrate_legacy_performance_hub_data,
)
from race_engineer_acquisition.performance_lap_archive import (
    GRAPHICS_ARCHIVE_FIELDS,
)

GIB = 1024 ** 3
LAP_COLUMNS = (
    "session_id", "lap_number", "car_model", "track", "track_configuration",
    "completed_at_utc", "lap_time_ms", "lap_valid", "out_lap",
    "start_timestamp_ns", "end_timestamp_ns", "physics_sample_count",
    "graphics_sample_count", "weather_json", "quality_json", "trace_bytes",
    "trace_status", "reason", "pinned_pb",
)


def default_db_path() -> Path:
    """Return the same repository-relative archive path used by the runtime."""
    return default_performance_archive_path()


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

    graphics_field_presence = {
        name: all(name in sample for sample in graphics)
        for name in GRAPHICS_ARCHIVE_FIELDS
    }
    missing_graphics_fields = sorted(
        name for name, present in graphics_field_presence.items() if not present
    )
    if missing_graphics_fields:
        problems.append(
            "graphics_missing_archive_fields:" + ",".join(missing_graphics_fields)
        )

    for stream_name, samples in (("physics", physics), ("graphics", graphics)):
        sequences = [s.get("capture_sequence") for s in samples]
        timestamps = [s.get("capture_timestamp_ns") for s in samples]
        if any(not isinstance(v, int) or isinstance(v, bool) for v in sequences):
            problems.append(f"{stream_name}_invalid_sequence")
        elif any(b <= a for a, b in zip(sequences, sequences[1:])):
            problems.append(f"{stream_name}_sequence_not_increasing")
        elif any(b != a + 1 for a, b in zip(sequences, sequences[1:])):
            problems.append(f"{stream_name}_sequence_gap")
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
        "graphics_field_contract_count": len(GRAPHICS_ARCHIVE_FIELDS),
        "graphics_field_coverage_count": len(GRAPHICS_ARCHIVE_FIELDS) - len(missing_graphics_fields),
        "graphics_missing_archive_fields": missing_graphics_fields,
    }


def read_archive(path: Path, *, check_integrity: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with closing(open_readonly(path)) as db:
        integrity = db.execute("PRAGMA quick_check").fetchone() if check_integrity else None
        schema = int(db.execute("PRAGMA user_version").fetchone()[0])
        rows = db.execute(
            """SELECT session_id,lap_number,car_model,track,track_configuration,
               completed_at_utc,lap_time_ms,lap_valid,out_lap,start_timestamp_ns,
               end_timestamp_ns,physics_sample_count,graphics_sample_count,
               weather_json,quality_json,trace_bytes,trace_status,
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
        return result, {"integrity": integrity[0] if integrity else "not_checked", "schema_version": schema}


def read_trace_blob(path: Path, session_id: str, lap_number: int) -> bytes | None:
    with closing(open_readonly(path)) as db:
        row = db.execute(
            "SELECT trace_blob FROM laps WHERE session_id=? AND lap_number=?",
            (session_id, lap_number),
        ).fetchone()
    return row[0] if row else None


def evaluate(rows: list[dict[str, Any]], db_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    full = [r for r in rows if r["trace_status"] in ("retained", "identity_incomplete")]
    compact = [r for r in rows if r not in full]
    trace_checks = {}
    for row in rows:
        key = f'{row["session_id"]}:{row["lap_number"]}'
        validation = row.get("trace_validation")
        if row["trace_status"] in ("retained", "identity_incomplete"):
            if not validation:
                issues.append(f"trace_not_checked:{key}")
            elif not validation.get("ok"):
                issues.append(f"trace_invalid:{key}:{validation.get('reason')}")

        if row["trace_status"] in ("retained", "identity_incomplete") and (
            row["lap_valid"] != 1 or row["out_lap"] != 0
        ):
            issues.append(f"ineligible_lap_has_full_trace:{key}")

        if row["trace_status"] == "compact_metadata":
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

    compact_timing_observation_count = 0
    compact_laps_with_timing_evidence = 0
    metadata_freshness_counts: dict[str, int] = {}
    metadata_age_known_threshold_unconfigured = 0
    for row in compact:
        quality = row.get("quality") if isinstance(row.get("quality"), dict) else {}
        observation_count = quality.get("graphics_timing_observation_count", 0)
        if isinstance(observation_count, int) and not isinstance(observation_count, bool):
            compact_timing_observation_count += max(0, observation_count)
            compact_laps_with_timing_evidence += int(observation_count > 0)
        freshness = quality.get("metadata_freshness")
        fields = freshness.get("fields", {}) if isinstance(freshness, dict) else {}
        for metadata_name, metadata in fields.items():
            status = metadata.get("status") if isinstance(metadata, dict) else "unavailable"
            metadata_freshness_counts[str(status)] = metadata_freshness_counts.get(str(status), 0) + 1
            if status == "age_known_threshold_unconfigured":
                metadata_age_known_threshold_unconfigured += 1

    db_bytes = db_path.stat().st_size if db_path.exists() else 0
    wal_path = Path(str(db_path) + "-wal")
    shm_path = Path(str(db_path) + "-shm")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    shm_bytes = shm_path.stat().st_size if shm_path.exists() else 0
    physical_bytes = db_bytes + wal_bytes + shm_bytes
    trace_bytes = sum(int(r["trace_bytes"] or 0) for r in rows)
    if trace_bytes > 2 * GIB:
        issues.append("accounted_trace_bytes_exceed_2_gib")
    if physical_bytes > 2 * GIB:
        issues.append("physical_archive_directory_files_exceed_2_gib")

    return {
        "lap_metadata_count": len(rows),
        "full_trace_count": len(full),
        "compact_or_evicted_count": len(compact),
        "session_count": len({r["session_id"] for r in rows}),
        "pinned_pb_count": sum(1 for r in full if r["pinned_pb"]),
        "compact_timing_observation_count": compact_timing_observation_count,
        "compact_laps_with_timing_evidence": compact_laps_with_timing_evidence,
        "metadata_freshness_counts": metadata_freshness_counts,
        "metadata_age_known_threshold_unconfigured": metadata_age_known_threshold_unconfigured,
        "trace_bytes_accounted_by_archive": trace_bytes,
        "database_bytes": db_bytes,
        "wal_bytes": wal_bytes,
        "shm_bytes": shm_bytes,
        "physical_archive_bytes": physical_bytes,
        "physical_archive_over_2_gib": physical_bytes > 2 * GIB,
        "trace_checks": trace_checks,
        "issues": issues,
        "archive_data_check": ("NOT VERIFIED" if not rows else ("PASS" if not issues else "FAIL")),
    }


def serializable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "trace_blob"} for row in rows]


def safe_session_name(session_id: str) -> str:
    """Make an ACC session ID safe for Windows folder and file names."""
    return "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "_"
        for char in session_id
    ).strip("._") or "unknown-session"


def write_session_evidence(
    rows: list[dict[str, Any]], output_dir: Path, stamp: str,
    report: dict[str, Any], snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write evidence only when a session's lap data is new or has changed.

    The archive is audited by the caller on every run. Evidence is session-scoped
    and uses stable filenames, so unchanged sessions are never touched.
    """
    import hashlib

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in serializable_rows(rows):
        session_id = str(row.get("session_id") or "unknown-session")
        grouped.setdefault(session_id, []).append(row)

    written: list[dict[str, Any]] = []
    for session_id, session_rows in sorted(grouped.items()):
        safe_id = safe_session_name(session_id)
        session_dir = output_dir / safe_id
        manifest_path = session_dir / ".session_evidence.json"
        canonical_paths = {
            "report": session_dir / f"performance_hub_report_{safe_id}.json",
            "laps": session_dir / f"laps_{safe_id}.csv",
            "snapshots": session_dir / f"monitor_snapshots_{safe_id}.csv",
        }

        fingerprint_payload = json.dumps(
            session_rows, sort_keys=True, separators=(",", ":"), default=str
        )
        fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
        previous_fingerprint = None
        if manifest_path.is_file():
            try:
                previous_fingerprint = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                ).get("session_data_sha256")
            except (OSError, ValueError, json.JSONDecodeError):
                previous_fingerprint = None

        changed = (
            not session_dir.is_dir()
            or previous_fingerprint != fingerprint
            or not all(path.is_file() for path in canonical_paths.values())
        )
        if not changed:
            written.append({
                "session_id": session_id, "directory": session_dir,
                **canonical_paths, "updated": False,
            })
            continue

        session_dir.mkdir(parents=True, exist_ok=True)
        audit = report.get("results", report)
        database_info = report.get("database_info", {})
        session_report = {
            "session_id": session_id,
            "session_lap_count": len(session_rows),
            "laps": session_rows,
            "archive_audit": {
                "archive_data_check": audit.get("archive_data_check"),
                "issues": audit.get("issues", []),
                "schema_version": report.get("archive_schema_version", database_info.get("schema_version")),
                "integrity": report.get("archive_integrity", database_info.get("integrity")),
            },
        }
        canonical_paths["report"].write_text(
            json.dumps(session_report, indent=2, default=str), encoding="utf-8"
        )

        fieldnames = list(dict.fromkeys(
            key for row in session_rows for key in row.keys()
        ))
        with canonical_paths["laps"].open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in session_rows:
                writer.writerow({
                    key: json.dumps(value, separators=(",", ":"))
                    if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                })

        if snapshots:
            with canonical_paths["snapshots"].open(
                "w", newline="", encoding="utf-8-sig"
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=list(snapshots[0].keys()))
                writer.writeheader()
                writer.writerows(snapshots)
        else:
            canonical_paths["snapshots"].write_text("", encoding="utf-8")

        # Remove only legacy timestamped exports created by the previous writer.
        # Windows may refuse deletion when a CSV is open in Excel or another viewer.
        cleanup_warnings: list[str] = []
        legacy_patterns = (
            f"performance_hub_report_{safe_id}_*.json",
            f"laps_{safe_id}_*.csv",
            f"monitor_snapshots_{safe_id}_*.csv",
        )
        for pattern in legacy_patterns:
            for legacy_path in session_dir.glob(pattern):
                if legacy_path not in canonical_paths.values() and legacy_path.is_file():
                    try:
                        legacy_path.unlink()
                    except PermissionError:
                        cleanup_warnings.append(
                            f"legacy_file_in_use:{legacy_path.name}"
                        )

        manifest_path.write_text(
            json.dumps({"session_data_sha256": fingerprint}, indent=2),
            encoding="utf-8",
        )
        written.append({
            "session_id": session_id, "directory": session_dir,
            **canonical_paths, "updated": True,
            "cleanup_warnings": cleanup_warnings,
        })
    return written

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only live monitor for the Race Engineer ACC Performance Hub archive."
    )
    parser.add_argument("--db", type=Path, default=default_db_path(),
                        help="Archive SQLite path (defaults to the app's standard path).")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Polling interval in seconds (default: 2).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Persistent output root (default: repository user_data/PerformanceHub/monitor_reports).")
    parser.add_argument("--once", action="store_true",
                        help="Validate the archive once and exit (use after closing the game/app).")
    args = parser.parse_args()
    if args.db == default_db_path():
        migration = migrate_legacy_performance_hub_data()
        if migration["archive_copied"] or migration["reports_copied"]:
            print(
                "Migrated legacy Performance Hub data into the repository user_data folder: "
                f"archive={migration['archive_copied']} reports={migration['reports_copied']}"
            )
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output is None:
        output_dir = default_monitor_reports_dir()
    else:
        output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Performance Hub monitor — read-only mode")
    print(f"Archive: {args.db}")
    print(f"Evidence folder: {output_dir}")
    if args.once:
        print("One-shot validation mode — checking the archive as it exists now.")
    else:
        print("Live monitoring mode — leave this running while driving; stop with Ctrl+C.")
    print("The report verifies persisted archive data; it cannot read internal live queue counters.")

    seen: set[tuple[str, int]] = set()
    first_seen: dict[tuple[str, int], str] = {}
    snapshots: list[dict[str, Any]] = []
    last_rows: list[dict[str, Any]] = []
    db_info: dict[str, Any] = {}
    started = time.monotonic()
    archive_seen = False
    integrity_checked = False
    integrity_status = "not_run"
    schema_status: int | None = None
    trace_checks_cache: dict[tuple[str, int], dict[str, Any]] = {}

    try:
        while True:
            if not args.db.exists():
                print(f"[{utc_now()}] ARCHIVE NOT FOUND — {args.db}")
                if args.once:
                    break
                time.sleep(args.interval)
                continue
            try:
                rows, db_info = read_archive(args.db, check_integrity=not integrity_checked)
                if not integrity_checked:
                    integrity_status = str(db_info["integrity"])
                    schema_status = int(db_info["schema_version"])
                integrity_checked = True
                archive_seen = True
                last_rows = rows
                new_rows = []
                for row in rows:
                    key = (str(row["session_id"]), int(row["lap_number"]))
                    if key not in seen:
                        seen.add(key)
                        first_seen[key] = utc_now()
                        new_rows.append(row)
                        if row["trace_status"] in ("retained", "identity_incomplete"):
                            blob = read_trace_blob(args.db, key[0], key[1])
                            trace_checks_cache[key] = check_trace(
                                blob, int(row["physics_sample_count"] or 0),
                                int(row["graphics_sample_count"] or 0),
                            )
                    if key in trace_checks_cache:
                        row["trace_validation"] = trace_checks_cache[key]

                report = evaluate(rows, args.db)
                if integrity_status != "ok":
                    report["issues"].append(f"sqlite_integrity_check:{integrity_status}")
                if schema_status != 1:
                    report["issues"].append(f"unsupported_archive_schema:{schema_status}")
                if report["issues"]:
                    report["archive_data_check"] = "FAIL"
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
                if args.once:
                    break
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
        if integrity_status != "ok":
            final_report["results"]["issues"].append(f"sqlite_integrity_check:{integrity_status}")
        if schema_status != 1:
            final_report["results"]["issues"].append(f"unsupported_archive_schema:{schema_status}")
        if final_report["results"]["issues"]:
            final_report["results"]["archive_data_check"] = "FAIL"
        final_report["archive_integrity"] = integrity_status
        final_report["archive_schema_version"] = schema_status
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

    session_evidence = write_session_evidence(
        last_rows, output_dir, stamp, final_report, snapshots
    ) if last_rows else []
    if session_evidence:
        print(f"Session evidence folders: {len(session_evidence)}")
        for item in session_evidence:
            print(f"  Session: {item['session_id']}")
            print(f"    Folder: {item['directory']}")
            print(f"    Evidence: {'updated' if item['updated'] else 'unchanged'}")
            print(f"    Report: {item['report']}")
            print(f"    Laps: {item['laps']}")
            if snapshots and item["updated"]:
                print(f"    Monitoring history: {item['snapshots']}")
            for warning in item.get("cleanup_warnings", []):
                print(f"    CLEANUP SKIPPED (file is open): {warning}")
    else:
        print("No session records found; no session evidence files were written.")
    result_status = final_report["results"].get("archive_data_check", "NOT VERIFIED")
    print(f"Final archive-data result: {result_status}")
    return 0 if result_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
