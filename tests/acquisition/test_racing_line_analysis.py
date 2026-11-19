import pytest

from race_engineer_acquisition.racing_line_analysis import (
    build_track_trajectory,
    compare_racing_lines,
)


def sample(timestamp, sequence, distance, xyz):
    return {
        "capture_timestamp_ns": timestamp,
        "capture_sequence": sequence,
        "player_world_position": xyz,
        "distance_traveled_m": distance,
    }


def test_build_trajectory_preserves_xyz_and_source_provenance():
    points = build_track_trajectory([
        sample(100, 10, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 11, 1.0, (1.0, 0.0, 0.0)),
        sample(300, 12, 2.0, (2.0, 0.0, 0.0)),
    ])
    assert len(points) == 3
    assert points[1]["position_xyz_m"] == (1.0, 0.0, 0.0)
    assert points[1]["capture_sequence"] == 11
    assert points[1]["capture_timestamp_ns"] == 200


def test_trajectory_skips_missing_and_nonfinite_positions():
    points = build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 1.0, (float("nan"), 0.0, 0.0)),
        sample(300, 3, 2.0, (2.0, 0.0, 0.0)),
    ])
    assert len(points) == 2


def test_trajectory_rejects_nonmonotonic_distance_or_time():
    assert build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 2.0, (1.0, 0.0, 0.0)),
        sample(300, 3, 1.0, (2.0, 0.0, 0.0)),
    ]) == ()


def test_compare_lines_reports_spatial_separation_on_common_distance():
    reference = build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 10.0, (10.0, 0.0, 0.0)),
        sample(300, 3, 20.0, (20.0, 0.0, 0.0)),
    ])
    comparison = build_track_trajectory([
        sample(100, 4, 0.0, (0.0, 1.0, 0.0)),
        sample(200, 5, 10.0, (10.0, 1.0, 0.0)),
        sample(300, 6, 20.0, (20.0, 1.0, 0.0)),
    ])
    result = compare_racing_lines(
        reference, comparison, distance_step_m=10.0, max_bracket_gap_m=10.0
    )
    assert result["available"] is True
    assert [row["separation_m"] for row in result["samples"]] == pytest.approx([1.0, 1.0, 1.0])


def test_compare_lines_does_not_bridge_large_missing_position_gaps():
    reference = build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 100.0, (100.0, 0.0, 0.0)),
    ])
    comparison = build_track_trajectory([
        sample(100, 3, 0.0, (0.0, 1.0, 0.0)),
        sample(200, 4, 100.0, (100.0, 1.0, 0.0)),
    ])
    result = compare_racing_lines(
        reference, comparison, distance_step_m=10.0, max_bracket_gap_m=5.0
    )
    assert result["available"] is False
    assert result["reason"] == "no_samples_within_bracket_gap_policy"


def test_trajectory_policy_must_be_nonnegative():
    with pytest.raises(ValueError):
        build_track_trajectory([], minimum_point_spacing_m=-1)


def test_trajectory_rejects_out_of_order_capture_timestamps():
    assert build_track_trajectory([
        sample(200, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(100, 2, 1.0, (1.0, 0.0, 0.0)),
    ]) == ()


def test_trajectory_normalizes_cumulative_source_distance_to_lap_local():
    points = build_track_trajectory([
        sample(100, 1, 2400.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 2410.0, (10.0, 0.0, 0.0)),
        sample(300, 3, 2420.0, (20.0, 0.0, 0.0)),
    ])
    assert [point["distance_m"] for point in points] == [0.0, 10.0, 20.0]
    assert [point["source_distance_m"] for point in points] == [2400.0, 2410.0, 2420.0]


def test_trajectory_keeps_lap_origin_when_first_position_sample_is_missing():
    points = build_track_trajectory([
        sample(100, 1, 2400.0, None),
        sample(200, 2, 2410.0, (0.0, 0.0, 0.0)),
        sample(300, 3, 2420.0, (10.0, 0.0, 0.0)),
    ])
    assert [point["distance_m"] for point in points] == [10.0, 20.0]


def test_racing_line_comparison_rejects_unbounded_distance_grid():
    reference = build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, 2.0, (2.0, 0.0, 0.0)),
    ])
    with pytest.raises(ValueError, match="100000-sample"):
        compare_racing_lines(
            reference, reference, distance_step_m=0.000001, max_bracket_gap_m=2.0
        )


def test_trajectory_detects_distance_regression_even_when_position_is_missing():
    assert build_track_trajectory([
        sample(100, 1, 0.0, (0.0, 0.0, 0.0)),
        sample(200, 2, -1.0, None),
        sample(300, 3, 2.0, (2.0, 0.0, 0.0)),
    ]) == ()
