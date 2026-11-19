from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time

from race_engineer_acquisition.candidate_lap_assembler import (
    CompactLapMetadata,
    CompletedLapTrace,
    LapAssemblyOutput,
    LapAssemblyDiagnostic,
)
from race_engineer_acquisition.decoded_sample_fanout import DecodedSample
from race_engineer_acquisition.performance_lap_archive import (
    LapArchiveContext,
    PerformanceArchiveConfig,
    PerformanceLapArchive,
    PerformanceLapPersistenceWorker,
    GRAPHICS_ARCHIVE_FIELDS,
    GRAPHICS_EXCLUDED_FIELDS,
    PHYSICS_ARCHIVE_FIELDS,
    assess_metadata_freshness,
)
from race_engineer_acquisition.graphics_decoder import DecodedGraphics
from race_engineer_acquisition.physics_decoder import DecodedPhysics


def _trace(session: str, lap: int, lap_time_ms: int = 90_000) -> CompletedLapTrace:
    physics = (
        DecodedSample("physics", 100 + lap * 10, 1_000 + lap * 100,
                      {"speed_kph": 123.4, "throttle": 0.75, "brake": 0.0,
                       "steering_angle": -0.12, "gear_raw": 4, "rpm": 7200}),
        DecodedSample("physics", 101 + lap * 10, 1_010 + lap * 100,
                      {"speed_kph": 124.0, "throttle": 0.80, "brake": 0.0,
                       "steering_angle": -0.10, "gear_raw": 4, "rpm": 7300}),
    )
    graphics = (
        DecodedSample("graphics", 200 + lap * 10, 1_000 + lap * 100,
                      {"normalized_car_position": 0.1, "distance_traveled_m": 100.0,
                       "player_world_position": (1.0, 2.0, 3.0), "packet_id": 501,
                       "sector": 1, "current_time_ms": 30_000,
                       "last_sector_time_ms": 29_500, "is_valid_lap": True}),
        DecodedSample("graphics", 201 + lap * 10, 1_010 + lap * 100,
                      {"normalized_car_position": 0.2, "distance_traveled_m": 110.0,
                       "player_world_position": (1.5, 2.1, 3.5), "packet_id": 502}),
    )
    return CompletedLapTrace(
        session_id=session,
        lap_number=lap,
        lap_time_ms=lap_time_ms,
        start_timestamp_ns=900 + lap * 100,
        end_timestamp_ns=1_100 + lap * 100,
        physics_samples=physics,
        graphics_samples=graphics,
    )


def _context() -> LapArchiveContext:
    return LapArchiveContext(
        car_model="porsche_992_gt3_r",
        track="spa",
        track_configuration="",
        session_index=1,
        session_type=2,
        weather={"rain_intensity": 0, "track_grip_status": 2, "air_temp_c": 21.5},
        metadata_source_timestamps_ns={"static": 900, "graphics": 1_100, "physics": 1_090},
    )


def _wait_for(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_valid_lap_round_trip_preserves_source_sequences_timestamps_and_context(tmp_path):
    archive = PerformanceLapArchive(tmp_path / "archive.sqlite3")
    try:
        result = archive.write_output(
            LapAssemblyOutput(completed=(_trace("run-1", 1),)), _context()
        )
        assert result.completed_stored == 1
        assert result.trace_rejected == 0
        rows = archive.read_laps(car_model="porsche_992_gt3_r", track="spa")
        assert len(rows) == 1
        row = rows[0]
        assert row["track_configuration"] == ""
        assert row["lap_time_ms"] == 90_000
        assert row["start_timestamp_ns"] == 1_000
        assert row["end_timestamp_ns"] == 1_200
        assert row["lap_valid"] == 1
        assert row["out_lap"] == 0
        assert row["pinned_pb"] is True
        assert row["session_first_seen_utc"]
        assert row["weather"]["rain_intensity"] == 0
        assert row["quality"]["racing_line_available"] is True

        trace = archive.read_trace("run-1", 1)
        assert trace is not None
        assert [item["capture_sequence"] for item in trace["physics"]] == [110, 111]
        assert [item["capture_timestamp_ns"] for item in trace["physics"]] == [1_100, 1_110]
        assert trace["physics"][0]["data"]["speed_kph"] == 123.4
        assert trace["graphics"][0]["player_world_position"] == [1.0, 2.0, 3.0]
        assert trace["graphics"][0]["normalized_car_position"] == 0.1
        assert trace["graphics"][0]["sector"] == 1
        assert trace["graphics"][0]["current_time_ms"] == 30_000
        assert trace["graphics"][0]["last_sector_time_ms"] == 29_500
        assert trace["graphics"][0]["is_valid_lap"] is True
        assert archive.metrics["retained_trace_count"] == 1
    finally:
        archive.close()



def test_incomplete_identity_keeps_trace_without_assigning_a_pb_partition(tmp_path):
    archive = PerformanceLapArchive(tmp_path / "archive.sqlite3")
    try:
        archive.write_output(
            LapAssemblyOutput(completed=(_trace("run-unknown", 1),)),
            LapArchiveContext(),
        )
        rows = archive.read_laps(limit=10)
        assert len(rows) == 1
        assert rows[0]["trace_status"] == "identity_incomplete"
        assert rows[0]["pinned_pb"] is False
        assert archive.read_trace("run-unknown", 1) is not None
    finally:
        archive.close()


def test_invalid_and_out_laps_are_compact_metadata_only(tmp_path):
    archive = PerformanceLapArchive(tmp_path / "archive.sqlite3")
    invalid = CompactLapMetadata(
        session_id="run-2", lap_number=2, lap_time_ms=91_000,
        lap_valid=False, out_lap=False, start_timestamp_ns=100,
        end_timestamp_ns=200, physics_sample_count=10,
        graphics_sample_count=2, reason="invalid_lap",
        graphics_timing_observations=({
            "capture_sequence": 221, "capture_timestamp_ns": 1200,
            "changed_fields": ["sector", "is_valid_lap"],
            "data": {"sector": 2, "is_valid_lap": False},
        },),
    )
    out_lap = CompactLapMetadata(
        session_id="run-2", lap_number=3, lap_time_ms=None,
        lap_valid=True, out_lap=True, start_timestamp_ns=200,
        end_timestamp_ns=300, physics_sample_count=4,
        graphics_sample_count=1, reason="out_lap",
    )
    try:
        result = archive.write_output(
            LapAssemblyOutput(compact=(invalid, out_lap)), _context()
        )
        assert result.compact_stored == 2
        assert archive.read_trace("run-2", 2) is None
        assert archive.read_trace("run-2", 3) is None
        rows = archive.read_laps(track="spa")
        assert {row["trace_status"] for row in rows} == {"compact_metadata"}
        assert {row["reason"] for row in rows} == {"invalid_lap", "out_lap"}
        invalid_row = next(row for row in rows if row["lap_number"] == 2)
        assert invalid_row["quality"]["graphics_timing_observation_count"] == 1
        assert invalid_row["quality"]["graphics_timing_observations"][0]["data"]["sector"] == 2
        out_lap_row = next(row for row in rows if row["lap_number"] == 3)
        assert out_lap_row["quality"]["graphics_timing_observation_count"] == 0
        assert archive.metrics["retained_trace_count"] == 0
    finally:
        archive.close()


def test_retention_keeps_latest_thirty_and_pinned_personal_best(tmp_path):
    clock_value = [datetime(2026, 11, 18, tzinfo=timezone.utc)]
    archive = PerformanceLapArchive(
        tmp_path / "archive.sqlite3",
        config=PerformanceArchiveConfig(recent_laps_per_identity=30),
        clock=lambda: clock_value[0],
    )
    try:
        for index in range(1, 33):
            # Lap 1 remains the PB; later laps are slower.
            archive.write_output(
                LapAssemblyOutput(completed=(
                    _trace(f"run-{index}", 1, 80_000 if index == 1 else 90_000 + index),
                )),
                _context(),
            )
            clock_value[0] += timedelta(seconds=1)

        rows = archive.read_laps(track="spa", limit=100)
        retained = [row for row in rows if row["trace_status"] == "retained"]
        evicted = [row for row in rows if row["trace_status"] == "evicted_count"]
        assert len(retained) == 31
        assert len(evicted) == 1
        pb = next(row for row in rows if row["session_id"] == "run-1")
        assert pb["pinned_pb"] is True
        assert pb["trace_status"] == "retained"
        assert archive.read_trace("run-2", 1) is None
        assert archive.read_trace("run-1", 1) is not None
    finally:
        archive.close()


def test_global_limit_rejects_new_trace_without_evicting_pinned_pb(tmp_path):
    first = _trace("run-1", 1, 80_000)
    second = _trace("run-2", 1, 90_000)
    probe = PerformanceLapArchive(tmp_path / "probe.sqlite3")
    first_size = len(probe._encode_trace(first)[0])
    second_size = len(probe._encode_trace(second)[0])
    probe.close()
    cap = max(first_size, second_size) + 1
    assert first_size + second_size > cap

    archive = PerformanceLapArchive(
        tmp_path / "archive.sqlite3",
        config=PerformanceArchiveConfig(max_storage_bytes=cap),
    )
    try:
        accepted = archive.write_output(LapAssemblyOutput(completed=(first,)), _context())
        assert accepted.trace_rejected == 0
        rejected = archive.write_output(LapAssemblyOutput(completed=(second,)), _context())
        assert rejected.trace_rejected == 1
        assert archive.read_trace("run-1", 1) is not None
        assert archive.read_trace("run-2", 1) is None
        rows = archive.read_laps(track="spa", limit=10)
        second_row = next(row for row in rows if row["session_id"] == "run-2")
        assert second_row["trace_status"] == "rejected_storage_limit"
        assert archive.storage_bytes <= cap
    finally:
        archive.close()


def test_age_retention_evicts_non_pinned_traces_but_preserves_pb(tmp_path):
    clock_value = [datetime(2026, 11, 18, tzinfo=timezone.utc)]
    archive = PerformanceLapArchive(
        tmp_path / "archive.sqlite3",
        config=PerformanceArchiveConfig(max_age_days=1),
        clock=lambda: clock_value[0],
    )
    try:
        archive.write_output(
            LapAssemblyOutput(completed=(_trace("run-pb", 1, 80_000),)), _context()
        )
        clock_value[0] += timedelta(minutes=1)
        archive.write_output(
            LapAssemblyOutput(completed=(_trace("run-old", 1, 90_000),)), _context()
        )
        clock_value[0] += timedelta(days=2)
        archive.write_output(
            LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("test", "run-pb", 1, "retention trigger"),
            )),
            _context(),
        )
        assert archive.read_trace("run-pb", 1) is not None
        assert archive.read_trace("run-old", 1) is None
        rows = archive.read_laps(track="spa", limit=10)
        assert len(rows) == 1
        assert rows[0]["session_id"] == "run-pb"
    finally:
        archive.close()


def test_archive_recovers_committed_trace_after_reopen(tmp_path):
    path = tmp_path / "archive.sqlite3"
    archive = PerformanceLapArchive(path)
    archive.write_output(LapAssemblyOutput(completed=(_trace("run-1", 1),)), _context())
    archive.close()

    reopened = PerformanceLapArchive(path)
    try:
        assert reopened.metrics["available"] is True
        assert reopened.read_trace("run-1", 1) is not None
    finally:
        reopened.close()


@dataclass
class _OneResultCapture:
    output: LapAssemblyOutput
    consumed: bool = False

    def read_result(self):
        if self.consumed:
            return None
        self.consumed = True
        return self.output


def test_persistence_worker_drains_capture_results_off_thread(tmp_path):
    archive = PerformanceLapArchive(tmp_path / "archive.sqlite3")
    capture = _OneResultCapture(LapAssemblyOutput(completed=(_trace("run-1", 1),)))
    worker = PerformanceLapPersistenceWorker(capture, archive, _context)
    try:
        worker.start()
        assert _wait_for(lambda: worker.metrics["processed_output_count"] == 1)
        assert worker.close(timeout=1.0) is True
        assert worker.metrics["failed_output_count"] == 0
        assert worker.metrics["stored_lap_count"] == 1
        assert archive.read_trace("run-1", 1) is not None
    finally:
        worker.close()
        archive.close()



def test_archive_round_trip_preserves_entire_graphics_field_contract_and_physics_payload(tmp_path):
    """Every declared Graphics field and the complete Physics mapping survive storage."""
    graphics_data = {
        name: f"preserved:{name}" for name in GRAPHICS_ARCHIVE_FIELDS
    }
    physics_data = {
        "speed_kph": 123.4,
        "future_decoder_field": {"nested": [1, 2, 3]},
    }
    trace = CompletedLapTrace(
        session_id="run-field-contract",
        lap_number=1,
        lap_time_ms=90_000,
        start_timestamp_ns=100,
        end_timestamp_ns=200,
        physics_samples=(
            DecodedSample("physics", 41, 110, physics_data),
        ),
        graphics_samples=(
            DecodedSample("graphics", 73, 120, graphics_data),
        ),
    )
    archive = PerformanceLapArchive(tmp_path / "field-contract.sqlite3")
    try:
        result = archive.write_output(
            LapAssemblyOutput(completed=(trace,)),
            _context(),
        )
        assert result.completed_stored == 1
        stored = archive.read_trace("run-field-contract", 1)
        assert stored is not None

        graphics = stored["graphics"][0]
        assert graphics["capture_sequence"] == 73
        assert graphics["capture_timestamp_ns"] == 120
        for name in GRAPHICS_ARCHIVE_FIELDS:
            assert graphics[name] == graphics_data[name], name

        physics = stored["physics"][0]
        assert physics["capture_sequence"] == 41
        assert physics["capture_timestamp_ns"] == 110
        assert physics["data"] == physics_data
    finally:
        archive.close()



def test_every_decoded_graphics_field_is_archived_or_explicitly_excluded():
    decoder_fields = set(DecodedGraphics.__dataclass_fields__)
    archived_fields = set(GRAPHICS_ARCHIVE_FIELDS)
    excluded_fields = set(GRAPHICS_EXCLUDED_FIELDS)

    assert archived_fields.isdisjoint(excluded_fields)
    assert decoder_fields == archived_fields | excluded_fields
    assert all(GRAPHICS_EXCLUDED_FIELDS.values())



def test_metadata_freshness_reports_age_without_inventing_threshold():
    result = assess_metadata_freshness(
        {"weather": 80, "car_identity": None},
        reference_timestamp_ns=100,
    )
    assert result["fields"]["weather"]["status"] == "age_known_threshold_unconfigured"
    assert result["fields"]["weather"]["age_ns"] == 20
    assert result["fields"]["car_identity"]["status"] == "unavailable"


def test_metadata_freshness_distinguishes_fresh_stale_and_future():
    result = assess_metadata_freshness(
        {"weather": 95, "track": 50, "future": 101},
        reference_timestamp_ns=100,
        stale_after_ns=20,
    )
    assert result["fields"]["weather"]["status"] == "fresh"
    assert result["fields"]["track"]["status"] == "stale"
    assert result["fields"]["future"]["status"] == "future_timestamp"



def test_every_decoded_physics_field_is_in_full_payload_archive_contract():
    decoder_fields = set(DecodedPhysics.__dataclass_fields__)
    assert decoder_fields == set(PHYSICS_ARCHIVE_FIELDS)



def test_archive_persists_raw_sector_evidence_for_valid_trace(tmp_path):
    trace = _trace("run-sector", 1)
    archive = PerformanceLapArchive(tmp_path / "sector.sqlite3")
    try:
        archive.write_output(LapAssemblyOutput(completed=(trace,)), _context())
        row = archive.read_laps(track="spa", limit=10)[0]
        quality = row["quality"]
        assert quality["sector_evidence"]["sector_time_assignment"] == "not_inferred"
        assert quality["sector_evidence"]["observation_count"] >= 0
    finally:
        archive.close()


def test_archive_persists_raw_sector_evidence_for_compact_lap(tmp_path):
    compact = CompactLapMetadata(
        session_id="run-compact-sector",
        lap_number=2,
        lap_time_ms=None,
        lap_valid=False,
        out_lap=False,
        start_timestamp_ns=100,
        end_timestamp_ns=300,
        physics_sample_count=0,
        graphics_sample_count=2,
        reason="invalid_lap",
        graphics_timing_observations=(
            {
                "observation_kind": "graphics_timing_change_point",
                "source_stream": "graphics",
                "capture_sequence": 10,
                "capture_timestamp_ns": 150,
                "changed_fields": ["sector", "last_sector_time_ms"],
                "data": {
                    "sector": 1,
                    "last_sector_time_ms": 28_000,
                },
            },
            {
                "observation_kind": "graphics_timing_change_point",
                "source_stream": "graphics",
                "capture_sequence": 20,
                "capture_timestamp_ns": 250,
                "changed_fields": ["sector", "last_sector_time_ms"],
                "data": {
                    "sector": 2,
                    "last_sector_time_ms": 31_000,
                },
            },
        ),
    )
    archive = PerformanceLapArchive(tmp_path / "compact-sector.sqlite3")
    try:
        archive.write_output(LapAssemblyOutput(compact=(compact,)), _context())
        row = archive.read_laps(track="spa", limit=10)[0]
        evidence = row["quality"]["sector_evidence"]
        assert evidence["raw_sector_values"] == [1, 2]
        assert evidence["sector_time_assignment"] == "not_inferred"
        assert len(row["quality"]["sector_observations"]) == 2
    finally:
        archive.close()
