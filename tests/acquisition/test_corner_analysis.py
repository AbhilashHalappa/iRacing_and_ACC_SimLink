import pytest

from race_engineer_acquisition.corner_analysis import analyze_corner


def point(distance, elapsed, speed, brake, throttle, steering):
    return {
        "distance_m": distance,
        "elapsed_s": elapsed,
        "speed_mps": speed,
        "brake_ratio": brake,
        "throttle_ratio": throttle,
        "steering_angle_rad": steering,
    }


def test_corner_analysis_measures_braking_turn_in_min_speed_and_throttle_pickup():
    profile = [
        point(100, 10.0, 50, 0.0, 0.2, 0.0),
        point(110, 11.0, 45, 0.5, 0.1, 0.1),
        point(120, 12.0, 30, 0.8, 0.0, 0.3),
        point(130, 13.0, 25, 0.4, 0.1, 0.4),
        point(140, 14.0, 28, 0.0, 0.3, 0.2),
        point(150, 15.0, 35, 0.0, 1.0, 0.1),
    ]
    result = analyze_corner(
        profile,
        {"corner_id": "turn-01", "start_distance_m": 100, "end_distance_m": 150},
        brake_onset_threshold=0.1,
        throttle_pickup_threshold=0.5,
        full_throttle_threshold=0.98,
        steering_threshold_rad=0.2, max_bracket_gap_m=10.0,
    )
    assert result["available"] is True
    assert result["braking_point_m"] == 110
    assert result["peak_brake_ratio"] == pytest.approx(0.8)
    assert result["peak_brake_point_m"] == 120
    assert result["brake_release_point_m"] == 140
    assert result["trail_braking_distance_m"] == 20
    assert result["trail_braking_active_at_turn_in"] is True
    assert result["turn_in_point_m"] == 120
    assert result["minimum_speed_mps"] == 25
    assert result["minimum_speed_point_m"] == 130
    assert result["throttle_pickup_point_m"] == 150
    assert result["full_throttle_point_m"] == 150


def test_corner_analysis_calculates_time_delta_only_when_both_profiles_bracket_corner():
    reference = [
        point(100, 10.0, 50, 0.0, 0.2, 0.0),
        point(150, 15.0, 35, 0.0, 0.8, 0.1),
    ]
    comparison = [
        point(100, 10.0, 50, 0.0, 0.2, 0.0),
        point(150, 15.5, 35, 0.0, 0.8, 0.1),
    ]
    result = analyze_corner(
        comparison, {"corner_id": "turn-1", "start_distance_m": 100, "end_distance_m": 150},
        brake_onset_threshold=0.1, throttle_pickup_threshold=0.5, full_throttle_threshold=0.98,
        steering_threshold_rad=0.2, max_bracket_gap_m=10.0, reference_profile=reference,
    )
    assert result["corner_time_delta_s"] == pytest.approx(0.5)


def test_corner_analysis_keeps_missing_channels_unavailable():
    profile = [
        {"distance_m": 1, "elapsed_s": 0, "speed_mps": 20},
        {"distance_m": 2, "elapsed_s": 1, "speed_mps": 10},
    ]
    result = analyze_corner(
        profile, {"corner_id": "turn-1", "start_distance_m": 1, "end_distance_m": 2},
        brake_onset_threshold=0.1, throttle_pickup_threshold=0.5, full_throttle_threshold=0.98,
        steering_threshold_rad=0.2, max_bracket_gap_m=10.0,
    )
    assert result["braking_point_m"] is None
    assert result["turn_in_point_m"] is None
    assert result["throttle_pickup_point_m"] is None
    assert "braking_point" in result["missing_metrics"]


def test_corner_analysis_rejects_invalid_thresholds_and_region():
    with pytest.raises(ValueError):
        analyze_corner([], {"start_distance_m": 1, "end_distance_m": 2},
                       brake_onset_threshold=1.1, throttle_pickup_threshold=0.5, full_throttle_threshold=0.98,
                       steering_threshold_rad=0.2)
    with pytest.raises(ValueError):
        analyze_corner([], {"start_distance_m": 2, "end_distance_m": 1},
                       brake_onset_threshold=0.1, throttle_pickup_threshold=0.5, full_throttle_threshold=0.98,
                       steering_threshold_rad=0.2)
