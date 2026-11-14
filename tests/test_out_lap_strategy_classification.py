from __future__ import annotations

from types import SimpleNamespace as N

from src.race_engineer_acquisition.out_lap import ACCOutLapObserver


def _frame(*, completed=0, position=0.5, status=2, in_pit=False):
    return N(
        completed_laps=completed,
        normalized_car_position=position,
        status=status,
        is_in_pit=in_pit,
        is_in_pit_lane=False,
        setup_menu_visible=False,
    )


def test_existing_out_lap_observer_exposes_classification_at_counter_transition():
    observer = ACCOutLapObserver()
    key = ("practice", 0)
    assert observer.observe(_frame(position=0.92), 100.0, key) is True
    assert observer.observe(_frame(position=0.03), 110.0, key) is False
    assert observer.last_completed_lap_out_lap is None

    observer.observe(_frame(completed=1, position=0.04), 80.0, key)
    assert observer.last_completed_lap_out_lap is True

    observer.observe(_frame(completed=2, position=0.10), 80.0, key)
    assert observer.last_completed_lap_out_lap is False


def test_out_lap_classification_remains_unknown_without_existing_observer_evidence():
    observer = ACCOutLapObserver()
    key = ("practice", 0)
    observer.observe(_frame(position=0.40), 0.0, key)
    observer.observe(_frame(completed=1, position=0.50), 0.0, key)
    assert observer.last_completed_lap_out_lap is None
