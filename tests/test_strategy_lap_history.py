from __future__ import annotations

from types import SimpleNamespace as N

from src.race_engineer_acquisition.strategy_lap_history import StrategyLapHistory


def _telemetry():
    physics = N(
        fuel_kg=46.2,
        tyre_pressure_psi=(27.1, 27.2, 27.0, 27.1),
        tyre_core_temp_c=(82.0, 83.0, 81.0, 82.0),
        brake_temp_c=(450.0, 455.0, 430.0, 435.0),
        car_damage=(0.0, 0.0, 0.0, 0.0, 0.0),
    )
    graphics = N(
        fuel_per_lap_l=2.35,
        used_fuel_l=4.7,
        tyre_compound="Dry",
    )
    return N(
        physics=N(is_fresh=True, data=physics, capture_timestamp_ns=1_000,
                  capture_sequence=20),
        graphics=N(is_fresh=True, data=graphics, capture_timestamp_ns=1_000,
                   capture_sequence=30),
    )


def _batch(*events, gap=False):
    return N(events=events, gap_detected=gap)


def _event(sequence, lap, *, valid=True, out_lap=False, session="s1"):
    return N(
        sequence=sequence,
        event_type="lap.completed",
        session_id=session,
        source_timestamp_ns=1_000,
        source_capture_sequence=30 + lap,
        payload={
            "lap_number": lap,
            "lap_time_ms": 100_000 + lap,
            "lap_valid": valid,
            "validity_known": True,
            "out_lap": out_lap,
            "lap_classification": "classified",
        },
    )


def test_shared_history_records_compact_cross_strategy_fields_and_filters_eligibility():
    history = StrategyLapHistory()
    history.observe_live_cursor("s1", 0, track="Spa", car="car")
    history.consume(_batch(_event(1, 1, valid=True, out_lap=False)), _telemetry())
    history.observe_live_cursor("s1", 1, track="Spa", car="car")

    result = history.snapshot()
    assert result["history_complete"] is True
    assert result["observed_lap_count"] == 1
    assert result["valid_timed_lap_count"] == 1
    record = result["recent_records"][0]
    assert record["fuel_remaining_l"] == 46.2
    assert record["fuel_per_lap_l"] == 2.35
    assert record["tyre_pressure_psi"] == (27.1, 27.2, 27.0, 27.1)
    assert record["brake_temp_c"] == (450.0, 455.0, 430.0, 435.0)
    assert record["physics_capture_sequence"] == 20
    assert result["high_resolution_telemetry_stored"] is False
    history.close()


def test_invalid_and_out_laps_are_retained_but_not_eligible_for_timed_pace():
    history = StrategyLapHistory()
    history.observe_live_cursor("s1", 0)
    history.consume(_batch(
        _event(1, 1, valid=False, out_lap=False),
        _event(2, 2, valid=True, out_lap=True),
        _event(3, 3, valid=True, out_lap=False),
    ), _telemetry())
    history.observe_live_cursor("s1", 3)

    result = history.snapshot()
    assert result["observed_lap_count"] == 3
    assert result["valid_timed_lap_count"] == 1
    assert [item["lap_number"] for item in result["recent_records"]] == [1, 2, 3]
    history.close()


def test_event_gap_marks_history_incomplete_without_fabricating_laps():
    history = StrategyLapHistory()
    history.observe_live_cursor("s1", 0)
    history.consume(_batch(_event(1, 1), gap=True), _telemetry())
    history.observe_live_cursor("s1", 1)

    result = history.snapshot()
    assert result["observed_lap_count"] == 1
    assert result["history_complete"] is False
    assert result["event_gap_count"] >= 1
    history.close()


def test_sqlite_history_recovers_only_after_session_and_cursor_match(tmp_path):
    path = tmp_path / "strategy-history.sqlite3"
    history = StrategyLapHistory(path)
    history.observe_live_cursor("s1", 0, track="Spa", car="car")
    history.consume(_batch(_event(1, 1)), _telemetry())
    history.observe_live_cursor("s1", 1, track="Spa", car="car")
    history.close()

    recovered = StrategyLapHistory(path)
    assert recovered.recovery_pending is True
    recovered.observe_live_cursor("s1", 1, track="Spa", car="car")
    result = recovered.snapshot()
    assert result["history_complete"] is True
    assert result["observed_lap_count"] == 1
    recovered.close()


def test_sqlite_history_refuses_recovery_when_acc_cursor_has_advanced(tmp_path):
    path = tmp_path / "strategy-history.sqlite3"
    history = StrategyLapHistory(path)
    history.observe_live_cursor("s1", 0)
    history.consume(_batch(_event(1, 1)), _telemetry())
    history.observe_live_cursor("s1", 1)
    history.close()

    recovered = StrategyLapHistory(path)
    recovered.observe_live_cursor("s1", 2)
    result = recovered.snapshot()
    assert result["history_complete"] is False
    assert any("does not match" in item for item in result["blockers"])
    recovered.close()

def test_history_uses_compact_boundary_sample_carried_by_stage2_event():
    history = StrategyLapHistory()
    history.observe_live_cursor("s1", 0)
    event = _event(1, 1)
    event.payload["strategy_sample"] = {
        "physics": {
            "capture_sequence": 55,
            "capture_timestamp_ns": 1_000,
            "fuel_remaining_l": 44.8,
            "tyre_pressure_psi": [27.0, 27.1, 27.2, 27.3],
            "tyre_core_temp_c": [80.0, 81.0, 82.0, 83.0],
            "brake_temp_c": [400.0, 410.0, 420.0, 430.0],
            "car_damage": [0.0, 0.0, 0.0, 0.0, 0.0],
            "air_temp_c": 22.0,
            "road_temp_c": 30.0,
        },
        "graphics": {
            "capture_sequence": 66,
            "capture_timestamp_ns": 1_000,
            "fuel_per_lap_l": 2.4,
            "fuel_used_l": 4.8,
            "tyre_compound": "Dry",
            "position": 4,
            "gap_ahead_ms": 1250,
            "gap_behind_ms": 980,
            "penalty_time_s": 5.0,
            "mandatory_pit_done": False,
            "driver_stint_left_ms": 600000,
            "rain_intensity": 0,
            "track_grip_status": 2,
        },
    }
    history.consume(_batch(event), telemetry=None)
    history.observe_live_cursor("s1", 1)
    record = history.snapshot()["recent_records"][0]
    assert record["fuel_remaining_l"] == 44.8
    assert record["fuel_per_lap_l"] == 2.4
    assert record["physics_capture_sequence"] == 55
    assert record["graphics_capture_sequence"] == 31
    assert record["position"] == 4
    assert record["gap_ahead_ms"] == 1250
    assert record["mandatory_pit_done"] is False
    assert record["air_temp_c"] == 22.0
    assert record["road_temp_c"] == 30.0
    history.close()


def test_sqlite_keeps_prior_session_records_when_new_session_reuses_acc_labels(tmp_path):
    import sqlite3

    path = tmp_path / "strategy-history.sqlite3"
    history = StrategyLapHistory(path)
    history.observe_live_cursor("acc-run:first:0:0", 0, track="Monza", car="car")
    history.consume(_batch(_event(1, 1, session="acc-run:first:0:0")), _telemetry())
    history.observe_live_cursor("acc-run:first:0:0", 1, track="Monza", car="car")

    # A second ACC run can report the exact same session_index/session_type
    # and lap number. Its unique broker identity must create a new history.
    history.observe_live_cursor("acc-run:second:0:0", 0, track="Monza", car="car")
    history.consume(_batch(_event(2, 1, session="acc-run:second:0:0")), _telemetry())
    history.observe_live_cursor("acc-run:second:0:0", 1, track="Monza", car="car")
    history.close()

    db = sqlite3.connect(path)
    sessions = db.execute(
        "SELECT session_id FROM session_meta_v2 ORDER BY session_id"
    ).fetchall()
    current_session = db.execute(
        "SELECT session_id FROM session_meta WHERE id=1"
    ).fetchone()
    records = db.execute(
        "SELECT session_id, lap_number FROM lap_records ORDER BY session_id"
    ).fetchall()
    db.close()

    assert sessions == [("acc-run:first:0:0",), ("acc-run:second:0:0",)]
    assert current_session == ("acc-run:second:0:0",)
    assert records == [
        ("acc-run:first:0:0", 1),
        ("acc-run:second:0:0", 1),
    ]


def test_legacy_singleton_metadata_is_migrated_without_deleting_laps(tmp_path):
    import json
    import sqlite3

    path = tmp_path / "legacy-history.sqlite3"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE session_meta (id INTEGER PRIMARY KEY CHECK(id=1), "
        "session_id TEXT NOT NULL, track TEXT, car TEXT, baseline_lap INTEGER NOT NULL, "
        "last_cursor INTEGER, complete INTEGER NOT NULL, gap_count INTEGER NOT NULL, "
        "blockers TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE lap_records (session_id TEXT NOT NULL, lap_number INTEGER NOT NULL, "
        "payload TEXT NOT NULL, PRIMARY KEY(session_id, lap_number))"
    )
    db.execute(
        "INSERT INTO session_meta VALUES(1, 'legacy-session', 'Spa', 'car', 0, 1, 1, 0, '[]')"
    )
    payload = {
        "session_id": "legacy-session", "lap_number": 1, "lap_time_ms": 100001,
        "lap_valid": True, "out_lap": False, "classification": "classified",
        "fuel_remaining_l": None, "fuel_per_lap_l": None, "fuel_used_l": None,
        "tyre_compound": None, "position": None, "gap_ahead_ms": None,
        "gap_behind_ms": None, "penalty_time_s": None, "mandatory_pit_done": None,
        "driver_stint_left_ms": None, "rain_intensity": None, "track_grip_status": None,
        "tyre_pressure_psi": [], "tyre_core_temp_c": [], "brake_temp_c": [],
        "car_damage": [], "air_temp_c": None, "road_temp_c": None,
        "graphics_capture_sequence": None, "graphics_capture_timestamp_ns": None,
        "physics_capture_sequence": None, "physics_capture_timestamp_ns": None,
        "event_sequence": 1,
    }
    db.execute(
        "INSERT INTO lap_records VALUES('legacy-session', 1, ?)",
        (json.dumps(payload),),
    )
    db.commit()
    db.close()

    history = StrategyLapHistory(path)
    assert history.recovery_pending is True
    assert history.read_records()[0].session_id == "legacy-session"
    history.close()

    db = sqlite3.connect(path)
    assert db.execute(
        "SELECT COUNT(*) FROM lap_records WHERE session_id='legacy-session'"
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM session_meta_v2 WHERE session_id='legacy-session'"
    ).fetchone()[0] == 1
    db.close()


def test_restart_does_not_attach_previous_run_history_to_reused_acc_labels(tmp_path):
    import sqlite3

    path = tmp_path / "strategy-history.sqlite3"
    first = StrategyLapHistory(path)
    first.observe_live_cursor("acc-run:before-restart:0:0", 0)
    first.consume(
        _batch(_event(1, 1, session="acc-run:before-restart:0:0")),
        _telemetry(),
    )
    first.observe_live_cursor("acc-run:before-restart:0:0", 1)
    first.close()

    restarted = StrategyLapHistory(path)
    assert restarted.recovery_pending is True
    # The broker deliberately creates a new identity after process restart.
    # Even with the same ACC session labels and cursor, old laps are not
    # silently treated as belonging to this new observation window.
    restarted.observe_live_cursor("acc-run:after-restart:0:0", 1)
    current = restarted.snapshot()
    assert current["observed_lap_count"] == 0
    assert current["history_complete"] is False
    assert any("attached after the session" in item for item in current["blockers"])
    restarted.close()

    db = sqlite3.connect(path)
    old_laps = db.execute(
        "SELECT lap_number FROM lap_records WHERE session_id='acc-run:before-restart:0:0'"
    ).fetchall()
    db.close()
    assert old_laps == [(1,)]

def test_duplicate_latest_lap_event_is_idempotent_and_does_not_mark_history_gap():
    history = StrategyLapHistory()
    history.observe_live_cursor("s1", 0)
    history.consume(_batch(_event(1, 1)), _telemetry())
    history.consume(_batch(_event(2, 1)), _telemetry())

    result = history.snapshot()
    assert result["observed_lap_count"] == 1
    assert result["event_gap_count"] == 0
    assert result["history_complete"] is True
    history.close()

