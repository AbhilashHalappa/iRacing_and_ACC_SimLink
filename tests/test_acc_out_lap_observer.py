from types import SimpleNamespace as N

from src.race_engineer_acquisition.out_lap import ACCOutLapObserver


def frame(
    *,
    status=2,
    completed=0,
    position=0.40,
    in_pit=False,
    in_lane=False,
    setup=False,
):
    return N(
        status=status,
        completed_laps=completed,
        normalized_car_position=position,
        is_in_pit=in_pit,
        is_in_pit_lane=in_lane,
        setup_menu_visible=setup,
    )


def test_live_attach_after_garage_departure_starts_initial_out_lap():
    observer = ACCOutLapObserver()

    # The app's first telemetry sample arrives after the car has left the pits.
    assert observer.observe(frame(position=0.42), 65.0, ("practice", 0)) is True
    assert observer.active is True


def test_pre_live_garage_evidence_starts_out_lap_on_first_live_departure():
    observer = ACCOutLapObserver()

    assert observer.observe(
        frame(status=0, in_pit=True), 0.0, ("practice", 0)
    ) is False
    assert observer.observe(
        frame(position=0.08), 42.0, ("practice", 0)
    ) is True


def test_start_finish_wrap_ends_initial_out_lap():
    observer = ACCOutLapObserver()

    assert observer.observe(frame(position=0.92), 100.0, ("practice", 0)) is True
    assert observer.observe(frame(position=0.03), 120.0, ("practice", 0)) is False
    assert observer.out_lap_completed is True


def test_first_attached_frame_just_after_start_finish_is_not_marked_out_lap():
    observer = ACCOutLapObserver()

    assert observer.observe(frame(position=0.05), 70.0, ("practice", 0)) is False
    assert observer.out_lap_completed is True


def test_normal_mid_session_pit_exit_does_not_start_another_out_lap():
    observer = ACCOutLapObserver()

    assert observer.observe(
        frame(completed=3, in_pit=True), 0.0, ("race", 1)
    ) is False
    assert observer.observe(
        frame(completed=3, position=0.32), 45.0, ("race", 1)
    ) is False
    assert observer.active is False


def test_session_change_rearms_initial_out_lap_detection():
    observer = ACCOutLapObserver()

    assert observer.observe(frame(position=0.92), 80.0, ("practice", 0)) is True
    assert observer.observe(frame(position=0.02), 100.0, ("practice", 0)) is False
    assert observer.out_lap_completed is True

    assert observer.observe(frame(position=0.55), 60.0, ("qualify", 1)) is True
    assert observer.active is True
