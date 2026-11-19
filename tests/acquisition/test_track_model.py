import math

import pytest

from race_engineer_acquisition.track_model import build_track_model


def point(distance, xyz):
    return {"distance_m": distance, "position_xyz_m": xyz}


def test_track_model_builds_source_xyz_path_and_turn_regions():
    trajectory = [
        point(0.0, (0.0, 0.0, 0.0)),
        point(10.0, (10.0, 0.0, 0.0)),
        point(20.0, (20.0, 0.0, 0.0)),
        point(30.0, (20.0, 10.0, 0.0)),
        point(40.0, (20.0, 20.0, 0.0)),
        point(50.0, (20.0, 30.0, 0.0)),
    ]
    model = build_track_model(
        trajectory,
        minimum_turn_angle_rad=math.radians(30),
        minimum_corner_length_m=5.0,
        merge_gap_m=15.0,
    )
    assert model["available"] is True
    assert model["coordinate_system"] == "source_xyz_unrotated"
    assert model["point_count"] == 6
    assert model["corners"]
    assert model["corners"][0]["geometry_confidence"] == "candidate"
    assert model["corners"][0]["identity_scope"] == "lap_order_only"


def test_track_model_does_not_claim_cross_session_corner_identity():
    model = build_track_model(
        [point(0, (0, 0, 0)), point(10, (10, 0, 0)), point(20, (20, 0, 0))],
        minimum_turn_angle_rad=0.5,
        minimum_corner_length_m=2,
    )
    assert model["available"] is True
    assert model["corners"] == []
    assert "not cross-session stable" in model["corner_identity_warning"]


def test_track_model_rejects_nonmonotonic_distance():
    model = build_track_model(
        [point(0, (0, 0, 0)), point(20, (10, 0, 0)), point(10, (20, 0, 0))],
        minimum_turn_angle_rad=0.5,
        minimum_corner_length_m=2,
    )
    assert model["available"] is False
    assert model["reason"] == "non_monotonic_distance"


def test_track_model_requires_explicit_positive_geometry_policy():
    with pytest.raises(ValueError):
        build_track_model([], minimum_turn_angle_rad=0, minimum_corner_length_m=2)
    with pytest.raises(ValueError):
        build_track_model([], minimum_turn_angle_rad=0.5, minimum_corner_length_m=0)
