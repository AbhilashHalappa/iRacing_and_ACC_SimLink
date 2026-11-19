from race_engineer_acquisition.session_analysis import build_session_summary


def lap(number, time_ms, *, valid=1, out=0, end=None, status="retained"):
    return {
        "lap_number": number,
        "lap_time_ms": time_ms,
        "lap_valid": valid,
        "out_lap": out,
        "end_timestamp_ns": end if end is not None else number * 1_000_000,
        "trace_status": status,
        "physics_sample_count": 100,
        "graphics_sample_count": 20,
        "quality": {
            "graphics_position_sample_count": 18,
            "graphics_timing_observation_count": 2,
        },
        "reason": None,
    }


def test_session_summary_counts_classification_and_valid_lap_timing():
    result = build_session_summary([
        lap(1, 100_000),
        lap(2, 99_000),
        lap(3, None, valid=0, status="compact_metadata"),
        lap(4, None, valid=1, out=1, status="compact_metadata"),
        lap(5, None, valid=None, out=None, status="compact_metadata"),
    ])
    assert result["lap_count"] == 5
    assert result["eligible_valid_lap_count"] == 2
    assert result["valid_classified_lap_count"] == 2
    assert result["invalid_lap_count"] == 1
    assert result["out_lap_count"] == 1
    assert result["classification_unknown_count"] == 1
    assert result["best_lap_time_ms"] == 99_000
    assert result["last_eligible_lap_time_ms"] == 99_000
    assert result["average_lap_time_ms"] == 99_500
    assert result["lap_time_stddev_ms"] == 500


def test_session_summary_keeps_history_and_data_coverage():
    result = build_session_summary([lap(1, 100_000), lap(2, 101_000)])
    history = result["lap_history"]
    assert [row["lap_number"] for row in history] == [1, 2]
    assert history[0]["delta_to_best_ms"] == 0
    assert history[1]["delta_to_best_ms"] == 1000
    assert history[0]["graphics_position_sample_count"] == 18
    assert result["full_trace_count"] == 2


def test_session_summary_does_not_invent_theoretical_best_sector_time():
    result = build_session_summary([lap(1, 100_000)])
    assert result["theoretical_best"]["available"] is False
    assert result["theoretical_best"]["reason"] == "authoritative_sector_time_assignment_not_verified"


def test_empty_session_summary_is_explicitly_unavailable():
    result = build_session_summary([])
    assert result["lap_count"] == 0
    assert result["best_lap_time_ms"] is None
    assert result["average_lap_time_ms"] is None
    assert result["lap_history"] == []
