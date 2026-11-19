import pytest

from race_engineer_acquisition.corner_identity import match_corner_identities


def model(corners):
    return {"available": True, "corners": corners}


def corner(name, distance, xyz, stable=None):
    return {
        "corner_id": name,
        "apex_distance_m": distance,
        "apex_position_xyz_m": xyz,
        "stable_corner_id": stable,
    }


def test_corner_identity_matches_by_xyz_and_lap_distance_within_policy():
    reference = model([corner("turn-01", 500.0, (10.0, 0.0, 20.0), "spa-corner-01")])
    candidate = model([corner("turn-03", 501.0, (10.5, 0.0, 20.0))])

    result = match_corner_identities(
        reference, candidate,
        max_apex_separation_m=2.0,
        max_apex_distance_delta_m=5.0,
    )
    matched = result["corners"][0]
    assert matched["stable_corner_id"] == "spa-corner-01"
    assert matched["matched_reference_corner_id"] == "turn-01"
    assert matched["identity_status"] == "matched"
    assert matched["apex_separation_m"] == pytest.approx(0.5)


def test_corner_identity_does_not_force_match_outside_tolerances():
    reference = model([corner("turn-01", 500.0, (10.0, 0.0, 20.0))])
    candidate = model([corner("turn-02", 550.0, (100.0, 0.0, 20.0))])
    result = match_corner_identities(
        reference, candidate,
        max_apex_separation_m=2.0,
        max_apex_distance_delta_m=5.0,
    )
    assert result["corners"][0]["stable_corner_id"] is None
    assert result["corners"][0]["identity_status"] == "unmatched"


def test_corner_identity_matching_is_one_to_one():
    reference = model([
        corner("turn-01", 100.0, (0.0, 0.0, 0.0)),
        corner("turn-02", 200.0, (10.0, 0.0, 0.0)),
    ])
    candidate = model([
        corner("turn-a", 100.0, (0.1, 0.0, 0.0)),
        corner("turn-b", 100.5, (0.2, 0.0, 0.0)),
    ])
    result = match_corner_identities(
        reference, candidate,
        max_apex_separation_m=2.0,
        max_apex_distance_delta_m=5.0,
    )
    assert sum(row["identity_status"] == "matched" for row in result["corners"]) == 1


def test_corner_identity_requires_explicit_positive_tolerances():
    with pytest.raises(ValueError):
        match_corner_identities(
            model([]), model([]),
            max_apex_separation_m=0,
            max_apex_distance_delta_m=1,
        )
