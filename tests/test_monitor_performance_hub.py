import csv
import json

from tools.monitor_performance_hub import write_session_evidence


def test_write_session_evidence_keeps_all_files_under_session_folders(tmp_path):
    rows = [
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
        },
        {
            "session_id": "acc-run:session-two:0:0",
            "lap_number": 1,
            "lap_time_ms": 121000,
            "quality": {"ok": False},
        },
    ]
    stamp = "20261119_170700"
    snapshots = [{"timestamp_utc": "2026-11-19T11:37:00+00:00", "lap_metadata_count": 3}]

    evidence = write_session_evidence(rows, tmp_path, stamp, {"archive": "summary"}, snapshots)

    assert len(evidence) == 2
    by_session = {item["session_id"]: item for item in evidence}
    first = by_session["acc-run:session-one:0:0"]
    second = by_session["acc-run:session-two:0:0"]

    assert first["directory"] == tmp_path / "acc-run_session-one_0_0"
    assert second["directory"] == tmp_path / "acc-run_session-two_0_0"
    for item in evidence:
        safe_id = item["directory"].name
        assert item["report"].name == f"performance_hub_report_{safe_id}_{stamp}.json"
        assert item["laps"].name == f"laps_{safe_id}_{stamp}.csv"
        assert item["snapshots"].name == f"monitor_snapshots_{safe_id}_{stamp}.csv"
        assert all(path.parent == item["directory"] for path in
                   (item["report"], item["laps"], item["snapshots"]))

    with first["laps"].open(newline="", encoding="utf-8-sig") as handle:
        first_laps = list(csv.DictReader(handle))
    with second["laps"].open(newline="", encoding="utf-8-sig") as handle:
        second_laps = list(csv.DictReader(handle))
    assert [row["lap_number"] for row in first_laps] == ["1", "2"]
    assert [row["lap_number"] for row in second_laps] == ["1"]
    assert first_laps[0]["quality"] == '{"ok":true}'

    first_report = json.loads(first["report"].read_text(encoding="utf-8"))
    assert first_report["session_id"] == "acc-run:session-one:0:0"
    assert first_report["session_lap_count"] == 2
    assert len(first_report["laps"]) == 2
