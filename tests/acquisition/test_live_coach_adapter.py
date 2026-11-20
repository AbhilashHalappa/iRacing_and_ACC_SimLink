from types import SimpleNamespace

from race_engineer_acquisition.live_coach_adapter import build_acc_live_coach_source


def _view(data, *, fresh=True, sequence=1, timestamp=100):
    return SimpleNamespace(
        data=data,
        is_fresh=fresh,
        capture_sequence=sequence,
        capture_timestamp_ns=timestamp,
    )


def test_live_coach_source_preserves_acc_fields_and_stream_provenance():
    telemetry = SimpleNamespace(
        physics=_view(SimpleNamespace(
            speed_kph=182.5, throttle=0.8, brake=0.0,
            steering_angle=-0.12, gear_raw=5, rpm=7200,
        ), sequence=41, timestamp=4100),
        graphics=_view(SimpleNamespace(
            status=2, session_index=7, completed_laps=3,
            current_time_ms=91234, last_time_ms=90123,
            is_valid_lap=True, is_in_pit=False, is_in_pit_lane=False,
            distance_traveled_m=12000.0, normalized_car_position=0.42,
            sector=2,
        ), sequence=52, timestamp=5200),
        static_decoded=_view(SimpleNamespace(
            car_model="GT3", track="Test Circuit",
            track_configuration="GP",
        ), sequence=9, timestamp=900),
    )

    result = build_acc_live_coach_source(
        telemetry, session_id="session-1",
        out_lap_status={"fresh": True, "active": False},
    )

    assert result.decoded_source_ready is True
    assert result.session_id == "session-1"
    assert result.physics_capture_sequence == 41
    assert result.physics_capture_timestamp_ns == 4100
    assert result.graphics_capture_sequence == 52
    assert result.graphics_capture_timestamp_ns == 5200
    assert result.static_capture_sequence == 9
    assert result.speed_kph == 182.5
    assert result.steering_angle_raw == -0.12
    assert result.current_time_ms_raw == 91234
    assert result.distance_traveled_m_raw == 12000.0
    assert result.track == "Test Circuit"
    assert result.out_lap_fresh is True
    assert result.out_lap_active is False
    assert "lap_local_distance_semantics" in result.unresolved_contracts


def test_live_coach_source_does_not_expose_stale_stream_values():
    telemetry = SimpleNamespace(
        physics=_view(SimpleNamespace(speed_kph=100.0), fresh=False, sequence=4),
        graphics=_view(SimpleNamespace(completed_laps=2), fresh=True, sequence=5),
        static_decoded=_view(SimpleNamespace(track="Test Circuit"), fresh=True, sequence=6),
    )

    result = build_acc_live_coach_source(
        telemetry, session_id="session-2",
        out_lap_status={"fresh": False, "active": True},
    )

    assert result.decoded_source_ready is False
    assert result.speed_kph is None
    assert result.completed_laps_raw == 2
    assert result.physics_capture_sequence == 4
    assert result.physics_capture_timestamp_ns == 100
    assert result.out_lap_fresh is False
    assert result.out_lap_active is None


def test_live_coach_source_keeps_physics_and_graphics_provenance_independent():
    telemetry = SimpleNamespace(
        physics=_view(SimpleNamespace(speed_kph=90.0), sequence=10, timestamp=1000),
        graphics=_view(SimpleNamespace(distance_traveled_m=500.0), sequence=90, timestamp=9000),
        static_decoded=_view(SimpleNamespace(track="Test Circuit"), sequence=2, timestamp=200),
    )

    result = build_acc_live_coach_source(
        telemetry, session_id="session-3",
        out_lap_status={"fresh": True, "active": False},
    )

    assert result.physics_capture_sequence == 10
    assert result.graphics_capture_sequence == 90
    assert result.physics_capture_timestamp_ns == 1000
    assert result.graphics_capture_timestamp_ns == 9000
