import json
import zlib

from tools import export_acc_semantics_diagnostic as diagnostic


def test_semantics_export_preserves_graphics_and_physics_provenance(monkeypatch, tmp_path):
    payload = {
        "graphics": [
            {"capture_sequence": 30, "capture_timestamp_ns": 3000,
             "distance_traveled_m": 120.0, "normalized_car_position": 0.2,
             "current_time_ms": 10000, "session_time_left_ms": 600000,
             "completed_laps": 1, "is_in_pit": False, "is_in_pit_lane": False,
             "is_valid_lap": True, "sector": 1},
            {"capture_sequence": 34, "capture_timestamp_ns": 4000,
             "distance_traveled_m": 240.0, "normalized_car_position": 0.4,
             "current_time_ms": 20000, "session_time_left_ms": 590000,
             "completed_laps": 1, "is_in_pit": True, "is_in_pit_lane": True,
             "is_valid_lap": True, "sector": 2},
        ],
        "physics": [
            {"capture_sequence": 90, "capture_timestamp_ns": 2990,
             "data": {"speed_kph": 100.0, "throttle": 0.5}},
            {"capture_sequence": 95, "capture_timestamp_ns": 4010,
             "data": {"speed_kph": 80.0, "throttle": 0.0}},
        ],
    }
    monkeypatch.setattr(
        diagnostic, "read_trace_blob",
        lambda *_: zlib.compress(json.dumps(payload).encode("utf-8")),
    )
    rows, summary = diagnostic.build_semantics_evidence([{
        "session_id": "session-a", "lap_number": 2, "trace_status": "retained",
        "lap_valid": 1, "out_lap": 0, "track": "track-a",
        "track_configuration": "layout-a",
    }], tmp_path / "archive.sqlite3")

    graphics_distance = [r for r in rows if r["stream"] == "graphics"
                         and r["field"] == "distance_traveled_m"]
    physics_speed = [r for r in rows if r["stream"] == "physics"
                     and r["field"] == "speed_kph"]
    assert [r["capture_sequence"] for r in graphics_distance] == [30, 34]
    assert [r["capture_timestamp_ns"] for r in graphics_distance] == [3000, 4000]
    assert [r["capture_sequence"] for r in physics_speed] == [90, 95]
    assert all(r["stream"] == "physics" for r in physics_speed)

    pit = next(r for r in summary if r["stream"] == "graphics" and r["field"] == "is_in_pit")
    left = next(r for r in summary if r["stream"] == "graphics"
                and r["field"] == "session_time_left_ms")
    assert pit["transition_count"] == 1
    assert left["decrease_count"] == 1
    assert left["minimum"] == 590000


def test_semantics_export_skips_compact_records_without_full_trace(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "read_trace_blob", lambda *_: None)
    rows, summary = diagnostic.build_semantics_evidence([{
        "session_id": "session-a", "lap_number": 3,
        "trace_status": "compact_metadata", "lap_valid": 0, "out_lap": 1,
    }], tmp_path / "archive.sqlite3")
    assert rows == []
    assert summary == []


def test_export_writes_session_scoped_sample_and_summary_csv(monkeypatch, tmp_path):
    payload = {
        "graphics": [{"capture_sequence": 1, "capture_timestamp_ns": 100,
                      "distance_traveled_m": 12.0}],
        "physics": [{"capture_sequence": 2, "capture_timestamp_ns": 101,
                     "data": {"speed_kph": 42.0}}],
    }
    monkeypatch.setattr(
        diagnostic, "read_trace_blob",
        lambda *_: zlib.compress(json.dumps(payload).encode("utf-8")),
    )
    outputs = diagnostic.export_semantics_diagnostics([{
        "session_id": "session/one", "lap_number": 1,
        "trace_status": "retained", "lap_valid": 1, "out_lap": 0,
    }], tmp_path / "archive.sqlite3", tmp_path / "reports")
    assert len(outputs) == 2
    assert all(path.is_file() for path in outputs)
    assert {path.name for path in outputs} == {
        "acc_semantics_samples_session_one.csv",
        "acc_semantics_summary_session_one.csv",
    }
