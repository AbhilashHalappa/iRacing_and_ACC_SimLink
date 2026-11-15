from types import SimpleNamespace

from src.race_engineer_acquisition.service import _race_rules_observation


def _telemetry(*, fresh=True, data=None):
    return SimpleNamespace(
        graphics=SimpleNamespace(
            is_fresh=fresh,
            capture_sequence=42,
            capture_timestamp_ns=123456789,
            data=data,
        )
    )


def test_fresh_graphics_exposes_mandatory_pit_and_driver_stint_candidates():
    graphics = SimpleNamespace(
        mandatory_pit_done=False,
        missing_mandatory_pits=2,
        driver_stint_total_ms=3600000,
        driver_stint_left_ms=3540000,
        is_in_pit=False,
        is_in_pit_lane=False,
    )

    result = _race_rules_observation(_telemetry(data=graphics))

    assert result == {
        "status": "fresh",
        "capture_sequence": 42,
        "capture_timestamp_ns": 123456789,
        "semantics": "unqualified_candidates",
        "mandatory_pit_done_candidate": False,
        "missing_mandatory_pits_candidate": 2,
        "driver_stint_total_ms_candidate": 3600000,
        "driver_stint_left_ms_candidate": 3540000,
        "is_in_pit_candidate": False,
        "is_in_pit_lane_candidate": False,
    }


def test_stale_graphics_fails_closed_without_candidate_values():
    result = _race_rules_observation(
        _telemetry(
            fresh=False,
            data=SimpleNamespace(missing_mandatory_pits=0),
        )
    )

    assert result["status"] == "unavailable"
    assert result["missing_mandatory_pits_candidate"] is None
    assert result["driver_stint_left_ms_candidate"] is None


def test_fresh_graphics_without_data_fails_closed():
    result = _race_rules_observation(_telemetry(data=None))

    assert result["status"] == "unavailable"
    assert result["capture_sequence"] == 42
    assert result["mandatory_pit_done_candidate"] is None
