from types import SimpleNamespace

from race_engineer_acquisition.fuel_lap_history import FuelLapHistory


def _event(sequence, event_type="lap.completed", payload=None, session="s1"):
    return SimpleNamespace(
        sequence=sequence,
        event_type=event_type,
        session_id=session,
        payload=payload or {},
    )


def _batch(events=(), gap=False):
    return SimpleNamespace(events=tuple(events), gap_detected=gap)


def test_fuel_history_records_completed_laps_but_blocks_unclassified_rolling_average():
    history = FuelLapHistory()
    history.consume(_batch([
        _event(1, payload={
            "lap_number": 2,
            "lap_time_ms": 100000,
            "lap_valid": True,
            "validity_known": True,
            "out_lap": None,
            "lap_classification": "pending_out_lap_classification",
        })
    ]))

    result = history.snapshot()
    assert result["observed_lap_count"] == 1
    assert result["valid_lap_count"] == 0
    assert result["history_complete"] is False
    assert result["recent_valid_lap_times_ms"] == []
    assert result["rolling_five_lap_average_ms"] is None
    assert result["rolling_calculation_enabled"] is False
    assert any("Out-lap classification" in item for item in result["blockers"])


def test_fuel_history_marks_delivery_gap_and_never_fabricates_missing_laps():
    history = FuelLapHistory()
    history.consume(_batch([
        _event(1, payload={
            "lap_number": 2, "lap_time_ms": 100000, "lap_valid": True,
            "validity_known": True, "out_lap": False,
            "lap_classification": "classified",
        })
    ]))
    history.consume(_batch([
        _event(4, payload={
            "lap_number": 5, "lap_time_ms": 101000, "lap_valid": True,
            "validity_known": True, "out_lap": False,
            "lap_classification": "classified",
        })
    ], gap=True))

    result = history.snapshot()
    assert result["observed_lap_count"] == 2
    assert result["event_gap_count"] >= 1
    assert result["history_complete"] is False
    assert result["rolling_five_lap_average_ms"] is None
    assert result["rolling_calculation_enabled"] is False


def test_cursor_reconciliation_does_not_claim_historical_recovery():
    history = FuelLapHistory()
    history.reconcile_cursor(SimpleNamespace(
        session_id="s1", completed_laps=10, historical_laps_recovered=False
    ))
    result = history.snapshot()
    assert result["history_complete"] is False
    assert result["rolling_calculation_enabled"] is False
    assert any("historical lap records were not recovered" in item for item in result["blockers"])
