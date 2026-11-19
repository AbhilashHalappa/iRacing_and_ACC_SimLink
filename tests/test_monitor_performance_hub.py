from tools.monitor_performance_hub import default_db_path, write_session_evidence
from race_engineer_acquisition.storage_paths import (
    default_monitor_reports_dir,
    default_performance_archive_path,
)

import csv
import json



def _rows():
    return [
        {
            "session_id": "acc-run:session-one:0:0",
            "lap_number": 1,
            "lap_time_ms": 120000,
            "quality": {"ok": True},
        },
        {
            "session_id": "acc-run:session-one:0:0",
            "lap_number": 2,
            "lap_time_ms": 119000,
            "quality": {"ok": True},
            "trace_validation": {"ok": True},
        },
        {
            "session_id": "acc-run:session-two:0:0",
            "lap_number": 1,
            "lap_time_ms": 121000,
            "quality": {"ok": False},
        },
    ]


def test_write_session_evidence_keeps_all_files_under_session_folders(tmp_path):
    rows = _rows()
    snapshots = [{"timestamp_utc": "2026-11-19T11:37:00+00:00", "lap_metadata_count": 3}]

    evidence = write_session_evidence(rows, tmp_path, "20261119_170700", {"archive_data_check": "PASS"}, snapshots)

    assert len(evidence) == 2
    by_session = {item["session_id"]: item for item in evidence}
    first = by_session["acc-run:session-one:0:0"]
    second = by_session["acc-run:session-two:0:0"]

    assert first["directory"] == tmp_path / "acc-run_session-one_0_0"
    assert second["directory"] == tmp_path / "acc-run_session-two_0_0"
    for item in evidence:
        safe_id = item["directory"].name
        assert item["report"].name == f"performance_hub_report_{safe_id}.json"
        assert item["laps"].name == f"laps_{safe_id}.csv"
        assert item["snapshots"].name == f"monitor_snapshots_{safe_id}.csv"
        assert item["updated"] is True
        assert all(path.parent == item["directory"] for path in
                   (item["report"], item["laps"], item["snapshots"]))

    with first["laps"].open(newline="", encoding="utf-8-sig") as handle:
        first_laps = list(csv.DictReader(handle))
    with second["laps"].open(newline="", encoding="utf-8-sig") as handle:
        second_laps = list(csv.DictReader(handle))
    assert [row["lap_number"] for row in first_laps] == ["1", "2"]
    assert [row["lap_number"] for row in second_laps] == ["1"]
    assert first_laps[0]["quality"] == '{"ok":true}'
    assert first_laps[1]["trace_validation"] == '{"ok":true}'
    assert "trace_validation" in first_laps[0]

    first_report = json.loads(first["report"].read_text(encoding="utf-8"))
    assert first_report["session_id"] == "acc-run:session-one:0:0"
    assert first_report["session_lap_count"] == 2
    assert len(first_report["laps"]) == 2


def test_unchanged_sessions_are_not_touched_and_new_laps_update_only_their_session(tmp_path):
    rows = _rows()
    snapshots = [{"timestamp_utc": "first", "lap_metadata_count": 3}]
    initial = write_session_evidence(rows, tmp_path, "first", {"archive_data_check": "PASS"}, snapshots)
    first_by_session = {item["session_id"]: item for item in initial}
    untouched_dir = first_by_session["acc-run:session-two:0:0"]["directory"]
    untouched_files = {
        path.name: (path.stat().st_mtime_ns, path.read_bytes())
        for path in untouched_dir.iterdir()
    }

    unchanged = write_session_evidence(
        rows, tmp_path, "second", {"archive_data_check": "PASS"},
        [{"timestamp_utc": "second", "lap_metadata_count": 3}],
    )
    assert all(item["updated"] is False for item in unchanged)
    assert {
        path.name: (path.stat().st_mtime_ns, path.read_bytes())
        for path in untouched_dir.iterdir()
    } == untouched_files

    rows.append({
        "session_id": "acc-run:session-one:0:0",
        "lap_number": 3,
        "lap_time_ms": 118000,
        "quality": {"ok": True},
    })
    updated = write_session_evidence(
        rows, tmp_path, "third", {"archive_data_check": "PASS"}, snapshots
    )
    updated_by_session = {item["session_id"]: item for item in updated}
    assert updated_by_session["acc-run:session-one:0:0"]["updated"] is True
    assert updated_by_session["acc-run:session-two:0:0"]["updated"] is False
    assert {
        path.name: (path.stat().st_mtime_ns, path.read_bytes())
        for path in untouched_dir.iterdir()
    } == untouched_files

    with updated_by_session["acc-run:session-one:0:0"]["laps"].open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        updated_laps = list(csv.DictReader(handle))
    assert [row["lap_number"] for row in updated_laps] == ["1", "2", "3"]



def test_locked_legacy_export_does_not_abort_evidence_update(tmp_path, monkeypatch):
    rows = _rows()
    initial = write_session_evidence(
        rows, tmp_path, "first", {"archive_data_check": "PASS"}, []
    )
    session = next(item for item in initial if item["session_id"] == "acc-run:session-one:0:0")
    legacy = session["directory"] / "laps_acc-run_session-one_0_0_20261119_194308.csv"
    legacy.write_text("legacy", encoding="utf-8")

    rows.append({
        "session_id": "acc-run:session-one:0:0",
        "lap_number": 3,
        "lap_time_ms": 118000,
        "quality": {"ok": True},
    })

    original_unlink = type(legacy).unlink

    def unlink_with_lock(path, *args, **kwargs):
        if path == legacy:
            raise PermissionError("file is open")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(legacy), "unlink", unlink_with_lock)
    updated = write_session_evidence(
        rows, tmp_path, "second", {"archive_data_check": "PASS"}, []
    )
    changed_session = next(
        item for item in updated if item["session_id"] == "acc-run:session-one:0:0"
    )

    assert changed_session["updated"] is True
    assert legacy.exists()
    assert changed_session["cleanup_warnings"] == [
        f"legacy_file_in_use:{legacy.name}"
    ]
    assert changed_session["laps"].is_file()


def test_monitor_defaults_match_runtime_repository_relative_storage():
    assert default_db_path() == default_performance_archive_path()
    assert default_monitor_reports_dir().parts[-3:] == ("user_data", "PerformanceHub", "monitor_reports")
