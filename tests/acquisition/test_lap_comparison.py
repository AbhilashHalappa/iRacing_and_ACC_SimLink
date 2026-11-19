import pytest

from race_engineer_acquisition.lap_comparison import (
    build_lap_profile,
    compare_lap_profiles,
)


def aligned(timestamp, distance, speed):
    return {
        "aligned": True,
        "physics": {
            "capture_timestamp_ns": timestamp,
            "values": {"speed_mps": speed},
        },
        "graphics": {"values": {"distance_m": distance}},
    }


def test_build_profile_uses_timestamp_aligned_physics_and_graphics():
    rows = [
        aligned(1_000_000_000, 0.0, 10.0),
        aligned(2_000_000_000, 10.0, 20.0),
        aligned(3_000_000_000, 20.0, 30.0),
    ]
    profile = build_lap_profile(rows)

    assert profile == (
        {"distance_m": 0.0, "elapsed_s": 0.0, "speed_mps": 10.0},
        {"distance_m": 10.0, "elapsed_s": 1.0, "speed_mps": 20.0},
        {"distance_m": 20.0, "elapsed_s": 2.0, "speed_mps": 30.0},
    )


def test_profile_skips_unaligned_and_incomplete_observations():
    rows = [
        aligned(1_000_000_000, 0.0, 10.0),
        {"aligned": False, "physics": None, "graphics": None},
        aligned(2_000_000_000, 10.0, 20.0),
        {"aligned": True, "physics": {"values": {}}, "graphics": {"values": {}}},
    ]
    assert len(build_lap_profile(rows)) == 2


def test_compare_profiles_interpolates_on_common_distance_grid():
    reference = [
        {"distance_m": 0.0, "elapsed_s": 0.0, "speed_mps": 10.0},
        {"distance_m": 10.0, "elapsed_s": 1.0, "speed_mps": 10.0},
        {"distance_m": 20.0, "elapsed_s": 2.0, "speed_mps": 10.0},
    ]
    comparison = [
        {"distance_m": 0.0, "elapsed_s": 0.0, "speed_mps": 10.0},
        {"distance_m": 10.0, "elapsed_s": 1.2, "speed_mps": 10.0},
        {"distance_m": 20.0, "elapsed_s": 2.2, "speed_mps": 10.0},
    ]
    result = compare_lap_profiles(
        reference, comparison, distance_step_m=10.0, max_bracket_gap_m=10.0
    )

    assert result["available"] is True
    assert [item["delta_s"] for item in result["samples"]] == pytest.approx([0.0, 0.2, 0.2])


def test_compare_profiles_does_not_extrapolate_or_bridge_large_gaps():
    reference = [
        {"distance_m": 0.0, "elapsed_s": 0.0},
        {"distance_m": 100.0, "elapsed_s": 10.0},
    ]
    comparison = [
        {"distance_m": 10.0, "elapsed_s": 0.0},
        {"distance_m": 90.0, "elapsed_s": 9.0},
    ]
    result = compare_lap_profiles(
        reference, comparison, distance_step_m=10.0, max_bracket_gap_m=20.0
    )
    assert result["available"] is False
    assert result["reason"] == "no_samples_within_bracket_gap_policy"


def test_compare_profiles_rejects_nonpositive_grid_policy():
    with pytest.raises(ValueError):
        compare_lap_profiles([], [], distance_step_m=0, max_bracket_gap_m=10)



def test_build_profile_rejects_non_monotonic_distance_instead_of_sorting_it_away():
    rows = [
        aligned(1_000_000_000, 0.0, 10.0),
        aligned(2_000_000_000, 20.0, 20.0),
        aligned(3_000_000_000, 15.0, 30.0),
    ]
    assert build_lap_profile(rows) == ()
