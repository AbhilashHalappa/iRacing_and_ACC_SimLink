from types import SimpleNamespace

from src.race_engineer_acquisition.service import _is_next_assessable_lap_event


def _event(*, event_type="lap.completed", session="run-1", lap=5, valid=True, out_lap=False):
    return SimpleNamespace(
        event_type=event_type,
        session_id=session,
        payload={
            "lap_number": lap,
            "lap_valid": valid,
            "out_lap": out_lap,
        },
    )


def test_completed_classified_lap_is_assessable_once_in_sequence():
    assert _is_next_assessable_lap_event(
        _event(lap=5),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_invalid_lap_is_assessable_but_remains_classified_input():
    # The lap-boundary assessment still runs; the lap-history pace selector
    # independently excludes lap_valid=False from its five-lap average.
    assert _is_next_assessable_lap_event(
        _event(lap=5, valid=False),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_duplicate_lap_number_does_not_trigger_another_assessment():
    assert not _is_next_assessable_lap_event(
        _event(lap=4),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_skipped_lap_number_does_not_advance_assessment_state():
    assert not _is_next_assessable_lap_event(
        _event(lap=6),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_pending_classification_and_out_lap_do_not_trigger_assessment():
    assert not _is_next_assessable_lap_event(
        _event(lap=5, valid=None),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )
    assert not _is_next_assessable_lap_event(
        _event(lap=5, out_lap=True),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_gap_event_and_wrong_session_do_not_trigger_assessment():
    assert not _is_next_assessable_lap_event(
        _event(event_type="lap.completion_gap", lap=5),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )
    assert not _is_next_assessable_lap_event(
        _event(session="old-run", lap=5),
        session_id="run-1",
        last_session_id="run-1",
        last_lap_number=4,
    )


def test_new_session_reseeds_lap_sequence():
    assert _is_next_assessable_lap_event(
        _event(session="run-2", lap=1),
        session_id="run-2",
        last_session_id="run-1",
        last_lap_number=22,
    )
