import pytest

from race_engineer_acquisition.track_model_archive import CanonicalTrackModelStore


def _model(*, x_offset=0.0):
    return {
        "available": True,
        "coordinate_system": "source_xyz_unrotated",
        "points": [
            {"distance_m": 0.0, "position_xyz_m": [x_offset, 0.0, 0.0]},
            {"distance_m": 10.0, "position_xyz_m": [x_offset + 10.0, 0.0, 0.0]},
            {"distance_m": 20.0, "position_xyz_m": [x_offset + 20.0, 1.0, 0.0]},
        ],
        "corners": [{
            "corner_id": "turn-01",
            "ordinal": 1,
            "start_distance_m": 5.0,
            "end_distance_m": 15.0,
            "apex_distance_m": 10.0,
            "apex_position_xyz_m": [x_offset + 10.0, 0.0, 0.0],
            "length_m": 10.0,
            "geometry_confidence": "candidate",
            "identity_scope": "lap_order_only",
        }],
    }


def test_canonical_model_persists_reference_and_stable_corner_ids(tmp_path):
    first_store = CanonicalTrackModelStore(tmp_path)
    saved = first_store.save_reference_model(
        "Monza", "GP", _model(),
        reference_session_id="session-a",
        reference_lap_number=7,
        reference_lap_time_ms=101234,
    )
    stable_id = saved["model"]["corners"][0]["stable_corner_id"]

    reloaded = CanonicalTrackModelStore(tmp_path).load("MONZA", "gp")

    assert reloaded is not None
    assert reloaded["reference"] == {
        "session_id": "session-a",
        "lap_number": 7,
        "lap_time_ms": 101234,
    }
    assert reloaded["model"]["corners"][0]["stable_corner_id"] == stable_id
    assert reloaded["model"]["corners"][0]["identity_scope"] == "persisted_track_configuration"
    assert len(CanonicalTrackModelStore(tmp_path).list_models()) == 1


def test_candidate_lap_receives_stable_identity_from_persisted_reference(tmp_path):
    store = CanonicalTrackModelStore(tmp_path)
    reference = store.save_reference_model(
        "Spa", "GP", _model(),
        reference_session_id="session-a",
        reference_lap_number=2,
    )
    stable_id = reference["model"]["corners"][0]["stable_corner_id"]

    matched = store.match_candidate(
        "Spa", "GP", _model(x_offset=0.2),
        max_apex_separation_m=1.0,
        max_apex_distance_delta_m=2.0,
    )

    assert matched["identity_matching_available"] is True
    assert matched["corners"][0]["stable_corner_id"] == stable_id
    assert matched["corners"][0]["identity_status"] == "matched"


def test_missing_canonical_model_does_not_mint_candidate_identity(tmp_path):
    store = CanonicalTrackModelStore(tmp_path)

    result = store.match_candidate(
        "Brands Hatch", "GP", _model(),
        max_apex_separation_m=1.0,
        max_apex_distance_delta_m=2.0,
    )

    assert result["identity_matching_available"] is False
    assert result["identity_matching_reason"] == "canonical_track_model_not_found"
    assert result["corners"][0].get("stable_corner_id") is None


def test_canonical_model_refuses_implicit_overwrite_and_invalid_identity(tmp_path):
    store = CanonicalTrackModelStore(tmp_path)
    store.save_reference_model(
        "Suzuka", "GP", _model(),
        reference_session_id="session-a",
        reference_lap_number=1,
    )

    with pytest.raises(FileExistsError):
        store.save_reference_model(
            "Suzuka", "GP", _model(),
            reference_session_id="session-b",
            reference_lap_number=1,
        )
    with pytest.raises(ValueError, match="track_configuration"):
        store.save_reference_model(
            "Suzuka", "", _model(),
            reference_session_id="session-b",
            reference_lap_number=1,
        )
    with pytest.raises(ValueError, match="available"):
        store.save_reference_model(
            "Suzuka", "GP", {"available": False},
            reference_session_id="session-b",
            reference_lap_number=1,
        )
