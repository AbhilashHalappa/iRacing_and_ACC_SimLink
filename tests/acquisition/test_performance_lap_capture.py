from __future__ import annotations

import time

from race_engineer_acquisition.decoded_events import DecodedEventPublisher
from race_engineer_acquisition.decoded_sample_fanout import DecodedSampleSubscription
from race_engineer_acquisition.performance_lap_capture import PerformanceLapCaptureWorker


def _event(publisher, lap, timestamp):
    return publisher.publish(
        "lap.completed",
        session_id="run-A",
        source_stream="graphics",
        source_capture_sequence=lap,
        source_timestamp_ns=timestamp,
        payload={
            "lap_number": lap,
            "lap_time_ms": 100_000,
            "lap_valid": True,
            "out_lap": False,
        },
    )


def _wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_worker_assembles_trace_from_independent_feeds():
    samples = DecodedSampleSubscription("samples", capacity=32)
    event_publisher = DecodedEventPublisher()
    events = event_publisher.subscribe("events", capacity=8)
    worker = PerformanceLapCaptureWorker(samples, events, poll_interval_s=0.002)
    try:
        _event(event_publisher, 1, 100)  # first event is only a boundary anchor
        _event(event_publisher, 2, 120)
        for stream, seq_offset in (("physics", 0), ("graphics", 10)):
            samples._offer(type("Sample", (), {
                "stream": stream,
                "capture_sequence": seq_offset + 1,
                "capture_timestamp_ns": 110,
                "data": {"sample": 1},
            })())
            samples._offer(type("Sample", (), {
                "stream": stream,
                "capture_sequence": seq_offset + 2,
                "capture_timestamp_ns": 120,
                "data": {"sample": 2},
            })())
        worker.start()
        assert _wait_for(lambda: worker.metrics["processed_sample_count"] == 4)
        results = []
        def collect_result():
            result = worker.read_result()
            if result is not None:
                results.append(result)
            return bool(results)
        assert _wait_for(collect_result)
        assert len(results[0].completed) == 1
        trace = results[0].completed[0]
        assert trace.lap_number == 2
        assert len(trace.physics_samples) == 2
        assert len(trace.graphics_samples) == 2
    finally:
        worker.close()


def test_worker_reports_event_mailbox_gap_and_shuts_down():
    samples = DecodedSampleSubscription("samples", capacity=8)
    publisher = DecodedEventPublisher()
    events = publisher.subscribe("events", capacity=1)
    worker = PerformanceLapCaptureWorker(samples, events, poll_interval_s=0.002)
    _event(publisher, 1, 100)
    _event(publisher, 2, 120)  # drops the first event in this mailbox
    worker.start()
    try:
        assert _wait_for(lambda: worker.metrics["processed_event_count"] == 1)
        assert _wait_for(lambda: worker.metrics["diagnostic_count"] >= 1)
        assert worker.close(timeout=1.0) is True
    finally:
        worker.close()
