from race_engineer_acquisition.performance_analysis_service import analyze_archived_laps
from race_engineer_acquisition.track_model_archive import CanonicalTrackModelStore
from race_engineer_acquisition.service import RaceEngineerService


class FakeArchive:
    def __init__(self, traces):
        self.traces = traces

    def read_lap_metadata(self, session_id, lap_number):
        if (session_id, lap_number) not in self.traces:
            return None
        return {
            "session_id": session_id,
            "lap_number": lap_number,
            "lap_valid": 1,
            "out_lap": 0,
            "trace_status": "retained",
            "lap_time_ms": 90_000,
            "track": "Test Track",
            "track_configuration": "GP",
        }

    def read_trace(self, session_id, lap_number):
        return self.traces.get((session_id, lap_number))


def make_trace(base_ns, slow_corner=False, y_offset=0.0):
    distances = [0.0, 10.0, 20.0, 30.0, 40.0]
    positions = [
        (0.0, y_offset, 0.0),
        (10.0, y_offset, 0.0),
        (20.0, y_offset, 0.0),
        (20.0, 10.0 + y_offset, 0.0),
        (20.0, 20.0 + y_offset, 0.0),
    ]
    elapsed = [0.0, 1.0, 2.0, 3.0, 4.0]
    if slow_corner:
        elapsed = [0.0, 1.0, 2.0, 3.2, 4.4]
    physics = []
    graphics = []
    brake_values = [0.0, 0.0, 0.8, 0.1, 0.0] if slow_corner else [0.0, 0.6, 0.8, 0.1, 0.0]
    for index, (distance, position, seconds) in enumerate(zip(distances, positions, elapsed)):
        timestamp = base_ns + int(seconds * 1_000_000_000)
        physics.append({
            "capture_sequence": index + 1,
            "capture_timestamp_ns": timestamp + 1,
            "data": {
                "speed_kph": [180, 150, 100, 90, 120][index],
                "throttle": [0.2, 0.1, 0.0, 0.3, 0.8][index],
                "brake": brake_values[index],
                "steering_angle": [0.0, 0.1, 0.3, 0.2, 0.1][index],
                "gear_raw": 4,
                "rpm": 7000 + index * 100,
            },
        })
        graphics.append({
            "capture_sequence": index + 11,
            "capture_timestamp_ns": timestamp,
            "distance_traveled_m": distance + 2400.0,
            "normalized_car_position": index / 4,
            "player_world_position": position,
            "sector": index // 2,
            "last_sector_time_ms": 0,
        })
    return {"physics": physics, "graphics": graphics}


def policy():
    return {
        "max_alignment_delta_ns": 5,
        "distance_step_m": 10.0,
        "max_bracket_gap_m": 10.0,
        "minimum_point_spacing_m": 0.25,
        "minimum_channel_coverage": 0.8,
        "minimum_alignment_coverage": 0.8,
        "max_progress_step": 0.5,
        "minimum_turn_angle_rad": 0.4,
        "minimum_corner_length_m": 5.0,
        "max_corner_apex_separation_m": 2.0,
        "max_corner_apex_distance_delta_m": 5.0,
        "merge_gap_m": 15.0,
        "brake_onset_threshold": 0.1,
        "throttle_pickup_threshold": 0.5,
        "full_throttle_threshold": 0.98,
        "steering_threshold_rad": 0.2,
        "required_physics_channels": ("speed_mps", "throttle_ratio", "brake_ratio"),
        "required_graphics_channels": ("distance_m", "track_progress_ratio"),
    }


def test_archive_analysis_orchestrates_lap_delta_corner_line_and_coach():
    archive = FakeArchive({
        ("session", 1): make_trace(1_000_000_000),
        ("session", 2): make_trace(10_000_000_000, slow_corner=True, y_offset=1.0),
    })
    result = analyze_archived_laps(
        archive,
        reference_session_id="session",
        reference_lap_number=1,
        comparison_session_id="session",
        comparison_lap_number=2,
        policy=policy(),
    )
    assert result["status"] == "complete"
    assert result["lap_delta"]["available"] is True
    assert result["track_model"]["available"] is True
    assert result["comparison_track_model"]["identity_matching_available"] is True
    assert result["comparison_track_model"]["corners"][0]["identity_status"] == "matched"
    assert result["comparison_corner_metrics"]
    assert result["racing_line"]["available"] is True
    assert result["analysis_coach_opportunities"]


def test_archive_analysis_rejects_invalid_or_out_lap_before_comparison():
    class InvalidArchive(FakeArchive):
        def read_lap_metadata(self, session_id, lap_number):
            result = super().read_lap_metadata(session_id, lap_number)
            result["lap_valid"] = 0
            return result

    archive = InvalidArchive({("session", 1): make_trace(1_000_000_000)})
    try:
        analyze_archived_laps(
            archive,
            reference_session_id="session",
            reference_lap_number=1,
            comparison_session_id="session",
            comparison_lap_number=1,
            policy=policy(),
        )
    except ValueError as exc:
        assert "eligible valid non-out lap" in str(exc)
    else:
        raise AssertionError("invalid lap should not enter comparison")


def test_archive_analysis_requires_explicit_cadence_and_feature_policy():
    archive = FakeArchive({})
    try:
        analyze_archived_laps(
            archive,
            reference_session_id="s", reference_lap_number=1,
            comparison_session_id="s", comparison_lap_number=2,
            policy={},
        )
    except ValueError as exc:
        assert "missing analysis policy values" in str(exc)
    else:
        raise AssertionError("analysis without policy should be rejected")


def test_archive_analysis_rejects_nonfinite_or_invalid_policy_values():
    invalid = policy()
    invalid["distance_step_m"] = float("nan")
    archive = FakeArchive({})
    try:
        analyze_archived_laps(
            archive,
            reference_session_id="s", reference_lap_number=1,
            comparison_session_id="s", comparison_lap_number=2,
            policy=invalid,
        )
    except ValueError as exc:
        assert "finite numbers" in str(exc)
    else:
        raise AssertionError("non-finite analysis policy should be rejected")



def test_archive_analysis_uses_persisted_canonical_corner_ids_across_sessions(tmp_path):
    archive = FakeArchive({
        ("reference-session", 3): make_trace(1_000_000_000),
        ("comparison-session", 9): make_trace(
            10_000_000_000, slow_corner=True, y_offset=0.5
        ),
    })
    store = CanonicalTrackModelStore(tmp_path)
    baseline = analyze_archived_laps(
        archive,
        reference_session_id="reference-session",
        reference_lap_number=3,
        comparison_session_id="reference-session",
        comparison_lap_number=3,
        policy=policy(),
    )
    saved = store.save_reference_model(
        "Test Track", "GP", baseline["track_model"],
        reference_session_id="reference-session",
        reference_lap_number=3,
        reference_lap_time_ms=90_000,
    )
    stable_id = saved["model"]["corners"][0]["stable_corner_id"]

    result = analyze_archived_laps(
        archive,
        reference_session_id="reference-session",
        reference_lap_number=3,
        comparison_session_id="comparison-session",
        comparison_lap_number=9,
        policy=policy(),
        canonical_track_model_store=store,
    )

    assert result["corner_identity_scope"] == "persisted_track_configuration"
    assert result["track_model"]["corners"][0]["stable_corner_id"] == stable_id
    assert result["comparison_track_model"]["corners"][0]["stable_corner_id"] == stable_id



def test_service_explicitly_saves_selected_valid_lap_as_canonical_reference(tmp_path):
    archive = FakeArchive({("reference-session", 3): make_trace(1_000_000_000)})
    service = RaceEngineerService.__new__(RaceEngineerService)
    service._performance_archive = archive
    service._canonical_track_models = CanonicalTrackModelStore(tmp_path)

    saved = service.save_canonical_track_model(
        session_id="reference-session",
        lap_number=3,
        geometry_policy={
            "minimum_point_spacing_m": 0.25,
            "minimum_turn_angle_rad": 0.4,
            "minimum_corner_length_m": 5.0,
            "merge_gap_m": 15.0,
        },
    )

    assert saved["reference"]["session_id"] == "reference-session"
    assert saved["reference"]["lap_number"] == 3
    assert saved["model"]["corners"][0]["stable_corner_id"].startswith("corner-")
    assert service.list_canonical_track_models()[0]["track"] == "Test Track"


def test_service_rejects_nonfinite_canonical_geometry_policy(tmp_path):
    archive = FakeArchive({("reference-session", 3): make_trace(1_000_000_000)})
    service = RaceEngineerService.__new__(RaceEngineerService)
    service._performance_archive = archive
    service._canonical_track_models = CanonicalTrackModelStore(tmp_path)

    try:
        service.save_canonical_track_model(
            session_id="reference-session",
            lap_number=3,
            geometry_policy={
                "minimum_point_spacing_m": 0.25,
                "minimum_turn_angle_rad": float("nan"),
                "minimum_corner_length_m": 5.0,
                "merge_gap_m": 15.0,
            },
        )
    except ValueError as exc:
        assert "finite number" in str(exc)
    else:
        raise AssertionError("non-finite geometry policy should be rejected")
