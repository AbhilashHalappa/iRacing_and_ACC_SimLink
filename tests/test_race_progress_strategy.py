from types import SimpleNamespace

from src.race_engineer_acquisition.race_progress_strategy import assess_race_progress


def _telemetry(*, fresh=True, status=2, session=2, completed=4, time_left=612500.0, lap_limit=0, static_fresh=False, is_timed_race=None, has_extra_lap=None, chequered=False):
    graphics = SimpleNamespace(
        status=status,
        session=session,
        completed_laps=completed,
        session_time_left_ms=time_left,
        number_of_laps=lap_limit,
        global_chequered=chequered,
    )
    static_data = SimpleNamespace(is_timed_race=is_timed_race, has_extra_lap=has_extra_lap)
    return SimpleNamespace(
        graphics=SimpleNamespace(data=graphics, is_fresh=fresh),
        static_decoded=SimpleNamespace(data=static_data, is_fresh=static_fresh),
    )


def test_fresh_live_graphics_exposes_observed_progress_without_guessing_mode():
    result = assess_race_progress(_telemetry())

    assert result.status == "observing"
    assert result.session_mode == "unknown"
    assert result.session_type_code == 2
    assert result.session_type_label == "race"
    assert result.completed_laps == 4
    assert result.session_time_remaining_s == 612.5
    assert result.lap_limit_candidate is None
    assert result.lap_limit_qualified is False
    assert result.laps_remaining is None
    assert result.projected_fuel_required_l is None
    assert not any("session-type enum mapping" in item for item in result.blockers)
    assert any("number_of_laps" in item for item in result.blockers)


def test_acc_millisecond_timer_is_converted_to_seconds():
    result = assess_race_progress(_telemetry(time_left=295327.0))

    assert result.session_time_remaining_s == 295.327


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


def test_fresh_static_metadata_classifies_timed_race_without_guessing_lap_limit():
    result = assess_race_progress(_telemetry(static_fresh=True, is_timed_race=True, has_extra_lap=True))
    assert result.session_mode == "timed"
    assert result.session_mode_source == "ACC_Static.is_timed_race"
    assert result.has_extra_lap is True
    assert result.lap_limit_qualified is False
    assert result.laps_remaining is None


def test_fresh_static_metadata_classifies_lap_based_race():
    result = assess_race_progress(_telemetry(static_fresh=True, is_timed_race=False, has_extra_lap=False))
    assert result.session_mode == "lap_based"
    assert result.has_extra_lap is False


def test_stale_static_metadata_does_not_classify_race_mode():
    result = assess_race_progress(_telemetry(static_fresh=False, is_timed_race=True, has_extra_lap=True))
    assert result.session_mode == "unknown"
    assert result.session_mode_source is None
    assert result.has_extra_lap is None
    assert any("Static race-mode metadata is unavailable" in item for item in result.blockers)


def test_chequered_flag_is_exposed_only_as_unqualified_candidate():
    result = assess_race_progress(_telemetry(chequered=True))
    assert result.chequered_flag_candidate is True
    assert result.chequered_flag_qualified is False
    assert any("global_chequered" in item for item in result.blockers)


def test_stale_graphics_does_not_expose_chequered_flag_candidate():
    result = assess_race_progress(_telemetry(fresh=False, chequered=True))
    assert result.chequered_flag_candidate is None
    assert result.chequered_flag_qualified is False


def test_only_live_observed_session_codes_are_labelled():
    practice = assess_race_progress(_telemetry(session=0))
    race = assess_race_progress(_telemetry(session=2))
    unknown = assess_race_progress(_telemetry(session=1))
    assert practice.session_type_label == "practice"
    assert race.session_type_label == "race"
    assert unknown.session_type_label is None
    assert any("not yet qualified" in item for item in unknown.blockers)



def _lap_records(*lap_times, invalid_indices=()):
    return [
        SimpleNamespace(
            lap_valid=(index not in invalid_indices),
            out_lap=False,
            classification="classified",
            lap_time_ms=lap_time,
        )
        for index, lap_time in enumerate(lap_times)
    ]


def test_timed_race_estimates_laps_from_average_of_latest_five_valid_laps():
    records = _lap_records(120000, 118000, 121000, 119000, 122000)
    result = assess_race_progress(
        _telemetry(time_left=295327.0, static_fresh=True, is_timed_race=True),
        lap_records=records,
    )

    assert result.lap_time_sample_count == 5
    assert result.average_lap_time_ms == 120000.0
    assert result.laps_remaining == 2


def test_timed_race_requires_five_valid_classified_non_out_laps():
    records = _lap_records(120000, 118000, 121000, 119000)
    result = assess_race_progress(
        _telemetry(time_left=600000.0, static_fresh=True, is_timed_race=True),
        lap_records=records,
    )

    assert result.lap_time_sample_count == 4
    assert result.average_lap_time_ms is None
    assert result.laps_remaining is None
    assert any("needs five valid completed lap times" in item for item in result.blockers)


def test_timed_race_lap_average_excludes_invalid_laps():
    records = _lap_records(120000, 90000, 121000, 119000, 122000, invalid_indices=(1,))
    result = assess_race_progress(
        _telemetry(time_left=295327.0, static_fresh=True, is_timed_race=True),
        lap_records=records,
    )

    assert result.lap_time_sample_count == 5
    assert result.average_lap_time_ms == 120500.0
    assert result.laps_remaining == 2


def test_lap_based_session_does_not_use_timed_lap_estimate():
    records = _lap_records(120000, 118000, 121000, 119000, 122000)
    result = assess_race_progress(
        _telemetry(time_left=600000.0, static_fresh=True, is_timed_race=False),
        lap_records=records,
    )

    assert result.average_lap_time_ms == 120000.0
    assert result.laps_remaining is None
