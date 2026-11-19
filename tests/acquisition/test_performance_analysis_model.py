from types import SimpleNamespace as N

import pytest

from race_engineer_acquisition.performance_analysis_model import (
    NORMALIZATION_VERSION,
    align_by_timestamp,
    normalize_sample,
)


def test_physics_normalization_keeps_raw_values_units_and_source_identity():
    sample = N(
        stream="physics", capture_sequence=17, capture_timestamp_ns=1_000,
        data=N(speed_kph=180.0, throttle=0.75, brake=0.1, steering_angle=-0.2,
               rpm=8200, velocity=(1.0, 2.0, 3.0)),
    )
    row = normalize_sample(sample)

    assert row["normalization_version"] == NORMALIZATION_VERSION
    assert row["capture_sequence"] == 17
    assert row["capture_timestamp_ns"] == 1_000
    assert row["source_values"]["speed_kph"] == 180.0
    assert row["values"]["speed_mps"] == pytest.approx(50.0)
    assert row["units"]["speed_mps"] == "m/s"
    assert row["values"]["throttle_ratio"] == 0.75
    assert row["values"]["world_velocity_mps"] == (1.0, 2.0, 3.0)


def test_graphics_normalization_preserves_unknown_sector_semantics():
    sample = N(
        stream="graphics", capture_sequence=8, capture_timestamp_ns=1_010,
        data=N(distance_traveled_m=250.0, normalized_car_position=0.25,
               sector=2, last_sector_time_ms=-1, is_valid_lap=True),
    )
    row = normalize_sample(sample)

    assert row["values"]["distance_m"] == 250.0
    assert row["values"]["track_progress_ratio"] == 0.25
    assert row["values"]["sector_index_raw"] == 2
    assert row["values"]["last_sector_time_ms"] == -1
    assert row["source_values"]["sector"] == 2
    assert row["units"]["sector_index_raw"] == "raw_enum"


def test_timestamp_alignment_uses_nearest_capture_time_not_array_index():
    physics = [
        {"capture_sequence": 10, "capture_timestamp_ns": 100, "values": {"speed_mps": 10}},
        {"capture_sequence": 11, "capture_timestamp_ns": 300, "values": {"speed_mps": 30}},
    ]
    graphics = [
        {"capture_sequence": 90, "capture_timestamp_ns": 280},
        {"capture_sequence": 91, "capture_timestamp_ns": 105},
    ]

    aligned = align_by_timestamp(physics, graphics, max_delta_ns=30)

    assert aligned[0]["physics"] is physics[1]
    assert aligned[0]["alignment_delta_ns"] == 20
    assert aligned[1]["physics"] is physics[0]
    assert aligned[1]["alignment_delta_ns"] == 5


def test_timestamp_alignment_marks_out_of_tolerance_and_missing_timestamp_unaligned():
    physics = [{"capture_timestamp_ns": 100}]
    graphics = [
        {"capture_timestamp_ns": 150},
        {"capture_timestamp_ns": None},
    ]

    aligned = align_by_timestamp(physics, graphics, max_delta_ns=10)

    assert aligned[0]["aligned"] is False
    assert aligned[0]["physics"] is None
    assert aligned[0]["alignment_delta_ns"] == 50
    assert aligned[1]["aligned"] is False
    assert aligned[1]["alignment_delta_ns"] is None


def test_alignment_requires_explicit_nonnegative_tolerance():
    with pytest.raises(ValueError):
        align_by_timestamp([], [], max_delta_ns=-1)


def test_normalizer_rejects_unknown_stream():
    with pytest.raises(ValueError):
        normalize_sample(N(stream="telemetry", data={}))
