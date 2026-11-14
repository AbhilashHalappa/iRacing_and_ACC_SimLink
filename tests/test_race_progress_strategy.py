from types import SimpleNamespace

from src.race_engineer_acquisition.race_progress_strategy import assess_race_progress


def _telemetry(*, fresh=True, status=2, session=2, completed=4, time_left=612.5, lap_limit=0):
    graphics = SimpleNamespace(
        status=status,
        session=session,
        completed_laps=completed,
        session_time_left_s=time_left,
        number_of_laps=lap_limit,
    )
    return SimpleNamespace(
        graphics=SimpleNamespace(data=graphics, is_fresh=fresh)
    )


def test_fresh_live_graphics_exposes_observed_progress_without_guessing_mode():
    result = assess_race_progress(_telemetry())

    assert result.status == "observing"
    assert result.session_mode == "unknown"
    assert result.session_type_code == 2
    assert result.completed_laps == 4
    assert result.session_time_remaining_s == 612.5
    assert result.lap_limit_candidate is None
    assert result.lap_limit_qualified is False
    assert result.laps_remaining is None
    assert result.projected_fuel_required_l is None
    assert any("session-type enum mapping" in item for item in result.blockers)
    assert any("number_of_laps" in item for item in result.blockers)


def test_lap_limit_is_exposed_only_as_unqualified_candidate():
    result = assess_race_progress(_telemetry(lap_limit=25))

    assert result.lap_limit_candidate == 25
    assert result.lap_limit_qualified is False
    assert result.laps_remaining is None


def test_invalid_time_is_not_reported_as_remaining_time():
    result = assess_race_progress(_telemetry(time_left=float("nan")))

    assert result.session_time_remaining_s is None
    assert any("time remaining is unavailable" in item for item in result.blockers)


def test_stale_or_non_live_graphics_fails_closed():
    stale = assess_race_progress(_telemetry(fresh=False))
    paused = assess_race_progress(_telemetry(status=3))

    for result in (stale, paused):
        assert result.status == "unavailable"
        assert result.session_mode == "unknown"
        assert result.completed_laps is None
        assert result.session_time_remaining_s is None
        assert result.projected_fuel_required_l is None
