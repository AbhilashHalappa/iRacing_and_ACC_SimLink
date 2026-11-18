from __future__ import annotations

from types import SimpleNamespace as N

from race_engineer_acquisition.candidate_lap_assembler import CandidateLapAssembler


def sample(stream, sequence, timestamp):
    return N(stream=stream, capture_sequence=sequence,
             capture_timestamp_ns=timestamp, data={"seq": sequence})


def event(sequence, lap, timestamp, *, session="run-A", valid=True,
          out_lap=False, lap_time_ms=100_000, event_type="lap.completed",
          current_laps=None):
    payload = {"lap_number": lap, "lap_time_ms": lap_time_ms,
               "lap_valid": valid, "out_lap": out_lap}
    if current_laps is not None:
        payload["current_completed_laps"] = current_laps
    return N(sequence=sequence, event_type=event_type, session_id=session,
             source_timestamp_ns=timestamp, payload=payload)


def seed(assembler, *, session="run-A", lap=1, timestamp=100):
    return assembler.ingest_event(event(1, lap, timestamp, session=session))


def test_first_event_seeds_boundary_without_fabricating_a_lap():
    assembler = CandidateLapAssembler()
    result = seed(assembler)
    assert result.completed == ()
    assert result.compact == ()
    assert assembler.waiting_for_boundary is False


def test_valid_lap_waits_for_both_stream_watermarks_and_preserves_timestamps():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 10, 110))
    assembler.ingest_sample(sample("physics", 11, 130))
    assembler.ingest_sample(sample("graphics", 20, 115))
    assembler.ingest_sample(sample("graphics", 21, 140))

    pending = assembler.ingest_event(event(2, 2, 150))
    assert pending.completed == ()
    assert pending.compact == ()

    # Graphics has crossed the boundary, but Physics has not.
    assembler.ingest_sample(sample("graphics", 22, 160))
    still_pending = assembler.ingest_sample(sample("physics", 12, 150))
    assert len(still_pending.completed) == 1
    trace = still_pending.completed[0]
    assert trace.lap_number == 2
    assert trace.lap_time_ms == 100_000
    assert [x.capture_sequence for x in trace.physics_samples] == [10, 11, 12]
    assert [x.capture_sequence for x in trace.graphics_samples] == [20, 21]
    assert trace.start_timestamp_ns == 100
    assert trace.end_timestamp_ns == 150


def test_samples_after_boundary_are_retained_for_next_lap_not_joined_by_index():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("physics", 2, 160))
    assembler.ingest_sample(sample("graphics", 1, 120))
    assembler.ingest_sample(sample("graphics", 2, 170))

    first = assembler.ingest_event(event(2, 2, 150))
    assert len(first.completed) == 1
    assert [x.capture_sequence for x in first.completed[0].physics_samples] == [1]
    assert [x.capture_sequence for x in first.completed[0].graphics_samples] == [1]

    second = assembler.ingest_event(event(3, 3, 200))
    assert second.completed == ()
    assembler.ingest_sample(sample("physics", 3, 210))
    result = assembler.ingest_sample(sample("graphics", 3, 220))
    assert len(result.completed) == 1
    assert [x.capture_sequence for x in result.completed[0].physics_samples] == [2]
    assert [x.capture_sequence for x in result.completed[0].graphics_samples] == [2]


def test_invalid_lap_emits_compact_metadata_without_trace():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    assembler.ingest_sample(sample("physics", 2, 120))
    assembler.ingest_sample(sample("graphics", 2, 120))
    result = assembler.ingest_event(event(2, 2, 120, valid=False))
    assert result.completed == ()
    assert len(result.compact) == 1
    assert result.compact[0].reason == "invalid_lap"
    assert result.compact[0].physics_sample_count == 1
    assert result.compact[0].graphics_sample_count == 1
    assert not hasattr(result.compact[0], "physics_samples")


def test_unknown_validity_and_out_lap_are_not_eligible_for_full_trace():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    assembler.ingest_sample(sample("physics", 2, 120))
    assembler.ingest_sample(sample("graphics", 2, 120))
    unknown = assembler.ingest_event(event(2, 2, 120, valid=None))
    assert unknown.compact[0].reason == "validity_unknown"

    assembler.ingest_sample(sample("physics", 3, 140))
    assembler.ingest_sample(sample("graphics", 3, 140))
    out_lap = assembler.ingest_event(event(3, 3, 140, out_lap=True))
    assert out_lap.compact[0].reason == "out_lap"


def test_session_change_discards_unfinalized_previous_session_samples():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    result = assembler.ingest_event(event(2, 1, 120, session="run-B"))
    assert any(x.kind == "session_changed" for x in result.diagnostics)
    assert result.completed == ()
    assert assembler.session_id == "run-B"


def test_completion_gap_discards_candidate_and_reanchors_without_fabrication():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    result = assembler.ingest_event(event(
        2, 4, 120, event_type="lap.completion_gap", current_laps=4
    ))
    assert result.completed == ()
    assert any(x.kind == "completion_gap" for x in result.diagnostics)
    assert assembler.waiting_for_boundary is False


def test_timestamp_regression_prevents_candidate_from_becoming_eligible():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 2, 120))
    assembler.ingest_sample(sample("physics", 3, 115))
    assembler.ingest_sample(sample("physics", 4, 130))
    assembler.ingest_sample(sample("graphics", 1, 120))
    assembler.ingest_sample(sample("graphics", 2, 130))
    result = assembler.ingest_event(event(2, 2, 130))
    assert len(result.compact) == 1
    assert "physics_timestamp_regressed" in result.compact[0].reason


def test_per_stream_buffer_is_bounded_and_overflow_downgrades_trace():
    assembler = CandidateLapAssembler(max_samples_per_stream=1)
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("physics", 2, 115))
    assembler.ingest_sample(sample("graphics", 1, 120))
    assembler.ingest_sample(sample("physics", 3, 130))
    assembler.ingest_sample(sample("graphics", 2, 130))
    result = assembler.ingest_event(event(2, 2, 130))
    assert result.completed == ()
    assert result.compact[0].reason == "physics_sample_buffer_overflow"

def test_sample_sequence_gap_downgrades_candidate_to_compact_only():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 10, 110))
    assembler.ingest_sample(sample("physics", 12, 120))
    assembler.ingest_sample(sample("graphics", 20, 120))
    assembler.ingest_sample(sample("physics", 13, 130))
    assembler.ingest_sample(sample("graphics", 21, 130))
    result = assembler.ingest_event(event(2, 2, 130))
    assert result.completed == ()
    assert "physics_sequence_gap" in result.compact[0].reason


def test_reported_sample_subscription_gap_downgrades_candidate():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    diagnostic = assembler.mark_stream_gap(
        "physics", first_missing_sequence=2, last_missing_sequence=3
    )
    assert diagnostic.diagnostics[0].kind == "sample_gap"
    assembler.ingest_sample(sample("physics", 2, 120))
    assembler.ingest_sample(sample("graphics", 2, 120))
    result = assembler.ingest_event(event(2, 2, 120))
    assert result.completed == ()
    assert "physics_subscription_gap" in result.compact[0].reason


def test_reported_event_mailbox_gap_discards_candidate_until_new_anchor():
    assembler = CandidateLapAssembler()
    seed(assembler)
    assembler.ingest_sample(sample("physics", 1, 110))
    assembler.ingest_sample(sample("graphics", 1, 110))
    diagnostic = assembler.mark_event_gap()
    assert diagnostic.diagnostics[0].kind == "event_gap"
    assert assembler.waiting_for_boundary is True
    reseed = assembler.ingest_event(event(3, 3, 130))
    assert reseed.completed == ()
    assert reseed.compact == ()
    assert assembler.waiting_for_boundary is False

