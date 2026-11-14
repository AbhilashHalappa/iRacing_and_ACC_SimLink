from __future__ import annotations

from types import SimpleNamespace

from src.race_engineer_acquisition.lap_events import CompletedLapEventObserver


def _telemetry(*, laps=0, session_index=1, session=2, status=2, fresh=True,
               last_time_ms=100000, valid=True, sequence=10, timestamp=1000):
    graphics = SimpleNamespace(
        status=status,
        completed_laps=laps,
        session_index=session_index,
        session=session,
        last_time_ms=last_time_ms,
        last_time_str="1:40.000",
        is_valid_lap=valid,
    )
    return SimpleNamespace(
        graphics=SimpleNamespace(
            is_fresh=fresh,
            data=graphics,
            capture_sequence=sequence,
            capture_timestamp_ns=timestamp,
            max_age_ns=1_000_000_000,
            consumer_lifecycle="running",
            acquisition_lifecycle="running",
        )
    )


def test_first_live_snapshot_seeds_without_fabricating_historical_lap():
    observer = CompletedLapEventObserver()
    assert observer.observe(_telemetry(laps=4)) == ()


def test_single_completed_lap_transition_emits_identified_candidate():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=4))
    events = observer.observe(_telemetry(
        laps=5, last_time_ms=101234, valid=True, sequence=11, timestamp=2000
    ))
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "lap.completed"
    assert event.session_id == "acc-session:1:2"
    assert event.source_capture_sequence == 11
    assert event.source_timestamp_ns == 2000
    assert event.payload["lap_number"] == 5
    assert event.payload["lap_time_ms"] == 101234
    assert event.payload["lap_valid"] is True
    assert event.payload["out_lap"] is None
    assert event.payload["lap_classification"] == "pending_out_lap_classification"


def test_acc_invalid_lap_is_preserved_as_invalid():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=1))
    event = observer.observe(_telemetry(laps=2, valid=False))[0]
    assert event.payload["lap_valid"] is False
    assert event.payload["validity_source"] == "ACC_Graphics.is_valid_lap"


def test_counter_jump_emits_gap_not_fabricated_lap_records():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=1))
    events = observer.observe(_telemetry(laps=4))
    assert len(events) == 1
    assert events[0].event_type == "lap.completion_gap"
    assert events[0].payload["missing_lap_count"] == 2
    assert events[0].payload["reconciliation_required"] is True


def test_session_change_and_counter_reset_reseed_without_event():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=8))
    assert observer.observe(_telemetry(laps=0, session_index=2)) == ()
    # The first observation in the new session seeds at zero; the next
    # increment is a real completed lap and must be emitted.
    events = observer.observe(_telemetry(laps=1, session_index=2))
    assert len(events) == 1
    assert events[0].event_type == "lap.completed"
    # A decreasing counter within the same session is a reset, not a lap.
    assert observer.observe(_telemetry(laps=0, session_index=2)) == ()


def test_stale_or_non_live_graphics_never_produces_lap_event():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=1))
    assert observer.observe(_telemetry(laps=2, fresh=False)) == ()
    assert observer.observe(_telemetry(laps=2, status=1)) == ()


def test_reconciliation_resyncs_latest_cursor_without_claiming_history_replay():
    from src.race_engineer_acquisition.lap_events import reconcile_lap_progress

    result = reconcile_lap_progress(_telemetry(
        laps=7, last_time_ms=99876, valid=False, sequence=44, timestamp=9000
    ), now_ns=9001)
    assert result is not None
    assert result.session_id == "acc-session:1:2"
    assert result.completed_laps == 7
    assert result.latest_lap_time_ms == 99876
    assert result.latest_lap_valid is False
    assert result.source_capture_sequence == 44
    assert result.historical_laps_recovered is False


def test_reconciliation_refuses_stale_or_non_live_state():
    from src.race_engineer_acquisition.lap_events import reconcile_lap_progress

    assert reconcile_lap_progress(_telemetry(laps=7, fresh=False)) is None
    assert reconcile_lap_progress(_telemetry(laps=7, status=1)) is None


def test_reconciliation_rechecks_sample_age_even_if_old_view_says_fresh():
    from src.race_engineer_acquisition.lap_events import reconcile_lap_progress

    telemetry = _telemetry(laps=7, timestamp=1000)
    assert reconcile_lap_progress(telemetry, now_ns=1_000_002_000) is None


def test_unknown_acc_validity_is_not_upgraded_to_valid():
    observer = CompletedLapEventObserver()
    observer.observe(_telemetry(laps=1))
    telemetry = _telemetry(laps=2, valid=None)
    event = observer.observe(telemetry)[0]
    assert event.payload["lap_valid"] is None
    assert event.payload["validity_known"] is False
