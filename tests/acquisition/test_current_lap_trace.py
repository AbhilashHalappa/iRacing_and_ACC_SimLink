from types import SimpleNamespace

from race_engineer_acquisition.candidate_lap_assembler import CandidateLapAssembler
from race_engineer_acquisition.decoded_sample_fanout import DecodedSample
from race_engineer_acquisition.performance_lap_capture import PerformanceLapCaptureWorker


def _event(event_type, timestamp, payload, session="session-a", sequence=1):
    return SimpleNamespace(event_type=event_type, source_timestamp_ns=timestamp,
                           payload=payload, session_id=session, sequence=sequence)


def test_active_lap_snapshot_preserves_independent_stream_provenance():
    assembler = CandidateLapAssembler(max_samples_per_stream=8)
    assembler.ingest_event(_event("lap.started", 100, {"lap_number": 4}))
    assembler.ingest_sample(DecodedSample("physics", 11, 110, {"speed_kph": 120}))
    assembler.ingest_sample(DecodedSample("graphics", 91, 115, {"sector": 1}))
    assembler.ingest_sample(DecodedSample("physics", 12, 120, {"speed_kph": 130}))
    snapshot = assembler.current_lap_snapshot(snapshot_timestamp_ns=125)

    assert snapshot.status == "active"
    assert snapshot.session_id == "session-a"
    assert snapshot.lap_number == 4
    assert snapshot.start_timestamp_ns == 100
    assert snapshot.snapshot_timestamp_ns == 125
    assert [x.capture_sequence for x in snapshot.physics_samples] == [11, 12]
    assert [x.capture_sequence for x in snapshot.graphics_samples] == [91]
    assert snapshot.physics_provenance.first_capture_timestamp_ns == 110
    assert snapshot.graphics_provenance.first_capture_timestamp_ns == 115
    assert snapshot.physics_provenance.last_capture_timestamp_ns == 120
    assert snapshot.is_complete is False
    assert snapshot.is_usable_for_coaching is True


def test_active_lap_snapshot_is_degraded_after_sample_gap():
    assembler = CandidateLapAssembler(max_samples_per_stream=8)
    assembler.ingest_event(_event("lap.started", 100, {"lap_number": 1}))
    assembler.ingest_sample(DecodedSample("physics", 1, 110, {"speed_kph": 100}))
    assembler.ingest_sample(DecodedSample("graphics", 1, 115, {"sector": 1}))
    assembler.mark_stream_gap("physics", first_missing_sequence=2, last_missing_sequence=2)
    snapshot = assembler.current_lap_snapshot(snapshot_timestamp_ns=120)

    assert snapshot.status == "degraded"
    assert "physics_subscription_gap" in snapshot.quality_reasons
    assert snapshot.is_usable_for_coaching is False


def test_snapshot_waits_for_trusted_lap_boundary_and_reports_bounded_capacity():
    assembler = CandidateLapAssembler(max_samples_per_stream=2)
    assembler.ingest_sample(DecodedSample("physics", 1, 10, {"speed_kph": 10}))
    snapshot = assembler.current_lap_snapshot(snapshot_timestamp_ns=11)

    assert snapshot.status == "waiting_for_boundary"
    assert snapshot.per_stream_capacity == 2
    assert snapshot.physics_samples == ()
    assert snapshot.is_usable_for_coaching is False


def test_capture_worker_exposes_initial_snapshot_without_new_subscription():
    worker = PerformanceLapCaptureWorker(None, None, sample_capacity=16)
    snapshot = worker.current_lap_snapshot
    assert snapshot.status == "waiting_for_boundary"
    assert snapshot.per_stream_capacity == 16
    assert snapshot.physics_samples == ()
    assert snapshot.graphics_samples == ()
