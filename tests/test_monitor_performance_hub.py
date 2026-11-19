import csv

from tools.monitor_performance_hub import write_session_csvs


def test_write_session_csvs_keeps_acc_sessions_separate(tmp_path):
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

    paths = write_session_csvs(rows, tmp_path)

    assert len(paths) == 2
    assert all(path.name == "laps.csv" for path in paths)
    assert all(path.parent.parent.name == "sessions" for path in paths)

    exported = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            exported[path.parent.name] = list(csv.DictReader(handle))

    first = exported["acc-run_session-one_0_0"]
    second = exported["acc-run_session-two_0_0"]
    assert [row["lap_number"] for row in first] == ["1", "2"]
    assert [row["lap_number"] for row in second] == ["1"]
    assert first[0]["quality"] == '{"ok":true}'
    assert second[0]["session_id"] == "acc-run:session-two:0:0"
