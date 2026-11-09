"""Live ACC Physics acquisition-to-disk recording validation tool.

Run on Windows with ACC running. Acquisition, queue dispatch, disk writing and
periodic checkpointing run on four separate threads. The acquisition thread
never writes to disk.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE, WindowsACCPhysicsSource
from race_engineer_acquisition.acquirer import PhysicsAcquirer
from race_engineer_acquisition.checkpoint import PeriodicCheckpointWorker
from race_engineer_acquisition.recorder import PhysicsRecorderWorker, recover_recording
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.fanout import FanOutDispatcher
from race_engineer_acquisition.timing_windows import WindowsTimerResolution


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("--poll-hz", type=float, default=480.0)
    parser.add_argument("--acquisition-buffer-capacity", type=int, default=100_000)
    parser.add_argument("--recorder-buffer-capacity", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--timer-resolution-ms", type=int, default=1)
    parser.add_argument("--checkpoint-interval-seconds", type=float, default=1.0)
    parser.add_argument(
        "--simulated-write-delay-ms", type=float, default=0.0,
        help="Optional delay before each recorder batch write; recorder thread only.",
    )
    parser.add_argument(
        "--simulate-disk-full-after-batches", type=int, default=None,
        help="Test only: inject ENOSPC during the next block after N successful blocks.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("user_data/raw_recordings"))
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.poll_hz <= 0:
        parser.error("duration and poll rate must be positive")
    if min(args.acquisition_buffer_capacity, args.recorder_buffer_capacity, args.batch_size) <= 0:
        parser.error("buffer capacities and batch size must be positive")
    if args.timer_resolution_ms < 0:
        parser.error("timer resolution cannot be negative")
    if args.checkpoint_interval_seconds <= 0:
        parser.error("checkpoint interval must be positive")
    if args.simulated_write_delay_ms < 0:
        parser.error("simulated write delay cannot be negative")
    if args.simulate_disk_full_after_batches is not None and args.simulate_disk_full_after_batches <= 0:
        parser.error("simulated disk-full batch count must be positive")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(timezone.utc)
    stem = started_utc.strftime("acc_physics_%Y%m%dT%H%M%S_%fZ")
    recording_path = args.output_dir / f"{stem}.accraw"
    report_path = args.output_dir / f"{stem}.json"
    checkpoint_path = args.output_dir / f"{stem}.checkpoint.json"

    source = WindowsACCPhysicsSource()
    acquisition_buffer = AcquisitionRingBuffer(args.acquisition_buffer_capacity)
    fanout = FanOutDispatcher(acquisition_buffer)
    recorder_buffer = fanout.register(
        "recorder", args.recorder_buffer_capacity, required=True
    )
    acquirer = PhysicsAcquirer(source, acquisition_buffer)
    recorder = PhysicsRecorderWorker(
        recorder_buffer, recording_path, payload_size=PHYSICS_SIZE,
        batch_size=args.batch_size,
        simulated_write_delay_seconds=args.simulated_write_delay_ms / 1000.0,
        simulated_disk_full_after_batches=args.simulate_disk_full_after_batches,
    )
    acquisition_stop = threading.Event()
    recorder_stop = threading.Event()
    dispatcher_stop = threading.Event()
    checkpoint_stop = threading.Event()
    checkpoint_sequence = {"value": 0}
    producer_errors: list[str] = []

    def producer() -> None:
        try:
            interval_ns = max(1, round(1_000_000_000 / args.poll_hz))
            acquirer.run(acquisition_stop, poll_interval_ns=interval_ns)
        except Exception as exc:
            producer_errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                source.close()
            except Exception as exc:
                producer_errors.append(f"Source close {type(exc).__name__}: {exc}")
            # Source ownership ends here; dispatcher shutdown is signalled by main.
            pass

    recorder_thread = threading.Thread(
        target=recorder.run, args=(recorder_stop,), name="ACC-Raw-Recorder", daemon=True
    )
    dispatcher_thread = threading.Thread(
        target=fanout.run, args=(dispatcher_stop,),
        name="ACC-Recorder-Dispatcher", daemon=True
    )
    producer_thread = threading.Thread(
        target=producer, name="ACC-Physics-Acquisition", daemon=True
    )

    def checkpoint_snapshot() -> dict:
        checkpoint_sequence["value"] += 1
        acquired_now = acquirer.metrics.capture_count
        acquisition_rejected_now = acquisition_buffer.total_rejection_count
        consumer_now = recorder_buffer.metrics
        persisted_now = consumer_now.processed_count
        recorder_rejected_now = consumer_now.rejected_count
        failed_now = consumer_now.failed_count
        acquisition_pending_now = acquisition_buffer.size
        recorder_pending_now = consumer_now.pending_count
        dispatcher_in_flight = int(fanout.metrics.in_flight_sequence is not None)
        accounted_now = (
            persisted_now + acquisition_rejected_now + recorder_rejected_now
            + failed_now + acquisition_pending_now + recorder_pending_now
            + dispatcher_in_flight
        )
        return {
            "schema_version": 1,
            "recording_file": recording_path.name,
            "checkpoint_sequence": checkpoint_sequence["value"],
            "checkpointed_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_ns": time.perf_counter_ns() - wall_start_ns,
            "acquisition": {
                "capture_count": acquired_now,
                "last_capture_sequence": acquirer.metrics.last_capture_sequence,
                "last_packet_id": acquirer.metrics.last_packet_id,
                "source_packet_gap_count": acquirer.metrics.source_packet_gap_count,
                "inconsistent_snapshot_count": acquirer.metrics.inconsistent_snapshot_count,
                "duplicate_packet_observation_count": acquirer.metrics.duplicate_packet_observation_count,
            },
            "acquisition_buffer": {
                "capacity": acquisition_buffer.capacity,
                "pending": acquisition_pending_now,
                "high_water_mark": acquisition_buffer.high_water_mark,
                "rejections": acquisition_rejected_now,
                "first_lost_sequence": acquisition_buffer.first_lost_sequence,
                "last_lost_sequence": acquisition_buffer.last_lost_sequence,
            },
            "dispatcher": asdict(fanout.metrics),
            "recorder_consumer": asdict(consumer_now),
            "recorder_buffer": {
                "capacity": recorder_buffer.capacity,
                "pending": recorder_pending_now,
                "high_water_mark": consumer_now.high_water_mark,
                "rejections": recorder_rejected_now,
                "first_lost_sequence": consumer_now.first_lost_sequence,
                "last_lost_sequence": consumer_now.last_lost_sequence,
            },
            "recorder": {
                "persisted_snapshot_count": persisted_now,
                "persisted_block_count": recorder.metrics.persisted_block_count,
                "last_persisted_capture_sequence": recorder.metrics.last_persisted_capture_sequence,
                "write_failure_count": recorder.metrics.write_failure_count,
                "failed_snapshot_count": failed_now,
                "first_failed_sequence": recorder.metrics.first_failed_sequence,
                "last_failed_sequence": recorder.metrics.last_failed_sequence,
                "in_flight_snapshot_count": consumer_now.in_flight_count,
                "in_flight_first_sequence": recorder.metrics.in_flight_first_sequence,
                "in_flight_last_sequence": recorder.metrics.in_flight_last_sequence,
            },
            "accounting": {
                "acquired": acquired_now,
                "persisted": persisted_now,
                "acquisition_rejections": acquisition_rejected_now,
                "recorder_queue_rejections": recorder_rejected_now,
                "write_failed": failed_now,
                "acquisition_queue_pending": acquisition_pending_now,
                "recorder_queue_pending": recorder_pending_now,
                "dispatcher_in_flight": dispatcher_in_flight,
                "recorder_in_flight": consumer_now.in_flight_count,
                "observed_unclassified_delta": acquired_now - accounted_now,
            },
            "note": "Counters are sampled independently without locking the acquisition path; a brief non-zero accounting delta can occur while a sample moves between stages.",
        }

    checkpoint_worker = PeriodicCheckpointWorker(
        checkpoint_path, checkpoint_snapshot,
        interval_seconds=args.checkpoint_interval_seconds,
    )
    checkpoint_thread = threading.Thread(
        target=checkpoint_worker.run, args=(checkpoint_stop,),
        name="ACC-Recording-Checkpoint", daemon=True,
    )

    timer = WindowsTimerResolution(args.timer_resolution_ms)
    wall_start_ns = time.perf_counter_ns()
    cpu_start_ns = time.process_time_ns()
    producer_error = None
    timer.__enter__()
    try:
        recorder_thread.start()
        dispatcher_thread.start()
        producer_thread.start()
        checkpoint_thread.start()
        producer_thread.join(timeout=args.duration_seconds)
        acquisition_stop.set()
        if producer_thread.is_alive():
            producer_thread.join(timeout=10)
        if producer_thread.is_alive():
            producer_error = "Acquisition thread did not stop within 10 seconds."
        else:
            dispatcher_stop.set()
        dispatcher_thread.join(timeout=30)
        if dispatcher_thread.is_alive():
            producer_error = producer_error or "Dispatcher did not finish draining acquisition buffer."
        recorder_stop.set()
        recorder_thread.join(timeout=30)
        if recorder_thread.is_alive():
            producer_error = producer_error or "Recorder did not finish draining recorder buffer."
        checkpoint_stop.set()
        checkpoint_thread.join(timeout=5)
    except Exception as exc:
        producer_error = f"{type(exc).__name__}: {exc}"
        acquisition_stop.set()
        recorder_stop.set()
        checkpoint_stop.set()
        if checkpoint_thread.is_alive():
            checkpoint_thread.join(timeout=5)
    finally:
        timer.__exit__(None, None, None)

    wall_elapsed_ns = time.perf_counter_ns() - wall_start_ns
    process_cpu_ns = time.process_time_ns() - cpu_start_ns
    if producer_errors:
        producer_error = "; ".join(producer_errors)
    acquired = acquirer.metrics.capture_count
    consumer_final = recorder_buffer.metrics
    persisted = consumer_final.processed_count
    acquisition_rejected = acquisition_buffer.total_rejection_count
    recorder_rejected = consumer_final.rejected_count
    failed = consumer_final.failed_count
    pending_acquisition = acquisition_buffer.size
    pending_recorder = consumer_final.pending_count
    dispatcher_in_flight = int(fanout.metrics.in_flight_sequence is not None)
    accounted = (
        persisted + acquisition_rejected + recorder_rejected + failed
        + pending_acquisition + pending_recorder + dispatcher_in_flight
    )
    reconciliation_delta = acquired - accounted

    recovery = None
    if recording_path.exists():
        try:
            recovery = asdict(recover_recording(recording_path))
        except Exception as exc:
            recovery = {"error": f"{type(exc).__name__}: {exc}"}

    recovery_ok = (
        recovery is not None
        and "error" not in recovery
        and recovery.get("recovered_snapshot_count") == persisted
        and recovery.get("truncated_bytes") == 0
    )
    checkpoint_ok = (
        checkpoint_worker.error is None
        and checkpoint_worker.write_count > 0
        and not checkpoint_thread.is_alive()
    )
    report = {
        "schema_version": 1,
        "status": "completed" if (
            not producer_error and not recorder.error and recovery_ok and checkpoint_ok
            and reconciliation_delta == 0 and pending_acquisition == 0 and pending_recorder == 0
            and acquisition_rejected == 0 and recorder_rejected == 0 and failed == 0
        ) else "failed",
        "recovery_validation_passed": recovery_ok,
        "checkpoint_validation_passed": checkpoint_ok,
        "checkpoint_file": checkpoint_path.name,
        "checkpoint_write_count": checkpoint_worker.write_count,
        "checkpoint_write_failure_count": checkpoint_worker.write_failure_count,
        "checkpoint_error": checkpoint_worker.error,
        "started_at_utc": started_utc.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "recording_file": recording_path.name,
        "configuration": {
            "duration_seconds_requested": args.duration_seconds,
            "poll_hz_requested": args.poll_hz,
            "acquisition_buffer_capacity": args.acquisition_buffer_capacity,
            "recorder_buffer_capacity": args.recorder_buffer_capacity,
            "batch_size": args.batch_size,
            "timer_resolution_ms_requested": args.timer_resolution_ms,
            "checkpoint_interval_seconds": args.checkpoint_interval_seconds,
            "simulated_write_delay_ms": args.simulated_write_delay_ms,
            "simulate_disk_full_after_batches": args.simulate_disk_full_after_batches,
            "physics_payload_size": PHYSICS_SIZE,
        },
        "environment": {"platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count()},
        "timing": {
            "wall_elapsed_ns": wall_elapsed_ns,
            "process_cpu_ns": process_cpu_ns,
            "process_cpu_one_core_percent": process_cpu_ns / wall_elapsed_ns * 100 if wall_elapsed_ns else 0,
        },
        "acquisition_metrics": {key: value for key, value in asdict(acquirer.metrics).items() if not key.startswith("_")},
        "acquisition_buffer": {
            "capacity": acquisition_buffer.capacity,
            "high_water_mark": acquisition_buffer.high_water_mark,
            "rejections": acquisition_rejected,
            "pending": pending_acquisition,
        },
        "dispatcher": asdict(fanout.metrics),
        "recorder_consumer": asdict(consumer_final),
        "recorder_buffer": {
            "capacity": recorder_buffer.capacity,
            "high_water_mark": consumer_final.high_water_mark,
            "rejections": recorder_rejected,
            "pending": pending_recorder,
        },
        "recorder_metrics": asdict(recorder.metrics),
        "recorder_error": recorder.error,
        "producer_error": producer_error,
        "reconciliation": {
            "acquired": acquired,
            "persisted": persisted,
            "acquisition_buffer_rejections": acquisition_rejected,
            "recorder_buffer_rejections": recorder_rejected,
            "recorder_write_failures": failed,
            "pending_acquisition": pending_acquisition,
            "pending_recorder": pending_recorder,
            "accounted_total": accounted,
            "delta": reconciliation_delta,
        },
        "recovery_validation": recovery,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Status                  : {report['status']}")
    print(f"Recording               : {recording_path}")
    print(f"Report                  : {report_path}")
    print(f"Checkpoint              : {checkpoint_path}")
    print(f"Checkpoint writes       : {checkpoint_worker.write_count}")
    print(f"Checkpoint write failures: {checkpoint_worker.write_failure_count}")
    print(f"Checkpoint error        : {checkpoint_worker.error}")
    print(f"Acquired                : {acquired}")
    print(f"Persisted               : {persisted}")
    print(f"Recorder write failures : {failed}")
    print(f"Acquisition rejects     : {acquisition_rejected}")
    print(f"Recorder queue rejects  : {recorder_rejected}")
    print(f"Recorder queue high-water: {consumer_final.high_water_mark}")
    print(f"Recorder processed       : {consumer_final.processed_count}")
    print(f"Recorder failed          : {consumer_final.failed_count}")
    print(f"Required delivery losses : {fanout.metrics.required_delivery_rejection_count}")
    print(f"Pending                 : {pending_acquisition + pending_recorder}")
    print(f"Simulated write delay   : {recorder.metrics.simulated_write_delay_ns / 1_000_000:.1f} ms")
    print(f"Simulated disk full     : {recorder.metrics.simulated_disk_full_triggered}")
    print(f"Max persist duration    : {recorder.metrics.max_persist_duration_ns / 1_000_000:.1f} ms")
    print(f"Max block write duration: {recorder.metrics.max_block_write_duration_ns / 1_000_000:.1f} ms")
    print(f"Reconciliation delta    : {reconciliation_delta}")
    print(f"CPU (one core)          : {report['timing']['process_cpu_one_core_percent']:.2f}%")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
