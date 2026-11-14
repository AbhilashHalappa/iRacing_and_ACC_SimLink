from __future__ import annotations

from types import SimpleNamespace as N

from src.race_engineer_acquisition.lap_events import CompletedLapEventObserver


def _telemetry(laps: int, *, valid: bool = True):
    graphics = N(
        status=2, completed_laps=laps, session_index=1, session=2,
        last_time_ms=101000, last_time_str="1:41.000", is_valid_lap=valid,
    )
    return N(graphics=N(
        is_fresh=True, data=graphics, capture_sequence=laps + 10,
        capture_timestamp_ns=laps + 100,
    ))


def test_completed_lap_event_uses_existing_out_lap_classification_independently_of_acc_validity():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(0))
    event = observer.observe(
        _telemetry(1, valid=False), completed_lap_out_lap=True
    )[0]
    assert event.payload["lap_valid"] is False
    assert event.payload["out_lap"] is True
    assert event.payload["lap_classification"] == "classified"
    assert event.payload["out_lap_source"] == "ACCOutLapObserver"
