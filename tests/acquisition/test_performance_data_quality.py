import pytest

from race_engineer_acquisition.performance_data_quality import (
    analysis_readiness,
    channel_availability,
    check_progress_continuity,
)


def row(timestamp, values):
    return {"capture_timestamp_ns": timestamp, "values": values}


def test_channel_availability_distinguishes_zero_partial_and_missing():
    rows = [
        row(10, {"speed_mps": 0.0, "brake_ratio": 0.2}),
        row(20, {"speed_mps": 12.0, "brake_ratio": None}),
        row(30, {"speed_mps": None}),
    ]
    result = channel_availability(rows, stream="physics")

    assert result["channels"]["speed_mps"] == {
        "present_samples": 2, "missing_samples": 1,
        "coverage_ratio": pytest.approx(2 / 3), "status": "partial",
    }
    assert result["channels"]["brake_ratio"]["coverage_ratio"] == pytest.approx(1 / 3)


def test_progress_continuity_reports_regression_and_large_jump():
    rows = [
        row(10, {"track_progress_ratio": 0.1}),
        row(20, {"track_progress_ratio": 0.2}),
        row(30, {"track_progress_ratio": 0.15}),
        row(40, {"track_progress_ratio": 0.8}),
    ]
    result = check_progress_continuity(rows, max_progress_step=0.25)

    assert result["ok"] is False
    assert [item["kind"] for item in result["issues"]] == [
        "progress_regression", "progress_jump"
    ]


def test_analysis_readiness_is_separate_from_acc_lap_validity():
    physics = [row(10, {"speed_mps": 10.0, "brake_ratio": 0.0})]
    graphics = [row(11, {"distance_m": 100.0, "track_progress_ratio": 0.2})]
    progress = check_progress_continuity(graphics, max_progress_step=0.1)

    result = analysis_readiness(
        physics, graphics,
        required_physics_channels=("speed_mps", "brake_ratio"),
        required_graphics_channels=("distance_m",),
        minimum_channel_coverage=1.0,
        progress_check=progress,
    )

    assert result["eligible"] is True
    assert result["acc_lap_validity"] == "not_evaluated"


def test_analysis_readiness_rejects_missing_required_channel():
    result = analysis_readiness(
        [row(10, {"speed_mps": 10.0})],
        [row(11, {"distance_m": None})],
        required_physics_channels=("speed_mps",),
        required_graphics_channels=("distance_m",),
        minimum_channel_coverage=0.9,
    )

    assert result["eligible"] is False
    assert result["required_channel_failures"] == [
        {"stream": "graphics", "channel": "distance_m", "coverage_ratio": 0.0}
    ]


def test_quality_policy_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        check_progress_continuity([], max_progress_step=0)
    with pytest.raises(ValueError):
        analysis_readiness([], [], required_physics_channels=(),
                           required_graphics_channels=(),
                           minimum_channel_coverage=1.1)


def test_progress_quality_does_not_sort_away_capture_timestamp_regression():
    rows = [
        row(100, {"track_progress_ratio": 0.1}),
        row(300, {"track_progress_ratio": 0.2}),
        row(200, {"track_progress_ratio": 0.3}),
    ]
    result = check_progress_continuity(rows, max_progress_step=0.5)
    assert result["ok"] is False
    assert any(
        issue["kind"] == "capture_timestamp_not_increasing"
        for issue in result["issues"]
    )
