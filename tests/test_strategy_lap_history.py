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
