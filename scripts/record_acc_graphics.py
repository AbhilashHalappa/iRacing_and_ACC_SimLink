"""Live ACC Graphics raw-page acquisition-to-disk validation.

Copies the complete mapping allocation discovered at runtime. No candidate
field decoder is used. Acquisition, dispatch, disk recording and checkpoints
run on separate threads.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from race_engineer_acquisition.checkpoint import PeriodicCheckpointWorker
from race_engineer_acquisition.graphics import (
    GraphicsAcquirer, GraphicsRecorderWorker, WindowsACCGraphicsSource,
    recover_graphics_recording,
)
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.timing_windows import WindowsTimerResolution


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("--poll-hz", type=float, default=100.0)
    parser.add_argument("--acquisition-buffer-capacity", type=int, default=10_000)
    parser.add_argument("--recorder-buffer-capacity", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--timer-resolution-ms", type=int, default=1)
    parser.add_argument("--checkpoint-interval-seconds", type=float, default=1.0)
    parser.add_argument("--simulated-write-delay-ms", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, default=Path("user_data/raw_recordings"))
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.poll_hz <= 0:
        parser.error("duration and poll rate must be positive")
    if min(args.acquisition_buffer_capacity, args.recorder_buffer_capacity, args.batch_size) <= 0:
        parser.error("buffer capacities and batch size must be positive")
    if args.timer_resolution_ms < 0 or args.checkpoint_interval_seconds <= 0:
        parser.error("timer resolution must be non-negative and checkpoint interval positive")
    if args.simulated_write_delay_ms < 0:
        parser.error("simulated write delay cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(timezone.utc)
    stem = started_utc.strftime("acc_graphics_%Y%m%dT%H%M%S_%fZ")
    recording_path = args.output_dir / f"{stem}.gfxraw"
    report_path = args.output_dir / f"{stem}.json"
    checkpoint_path = args.output_dir / f"{stem}.checkpoint.json"

    source = WindowsACCGraphicsSource()
    page_size = source.page_size
    acquisition_buffer = AcquisitionRingBuffer(args.acquisition_buffer_capacity)
    recorder_buffer = AcquisitionRingBuffer(args.recorder_buffer_capacity)
    acquirer = GraphicsAcquirer(source, acquisition_buffer)
    recorder = GraphicsRecorderWorker(
        recorder_buffer, recording_path, page_size=page_size,
        batch_size=args.batch_size,
        simulated_write_delay_seconds=args.simulated_write_delay_ms / 1000.0,
    )

    acquisition_stop = threading.Event()
    recorder_stop = threading.Event()
    producer_done = threading.Event()
    checkpoint_stop = threading.Event()
    dispatcher_stats = {"transferred_count": 0, "in_flight_sequence": None}
    checkpoint_sequence = {"value": 0}
    producer_errors: list[str] = []
    wall_start_ns = time.perf_counter_ns()

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
            producer_done.set()

    def dispatcher() -> None:
        while not producer_done.is_set() or acquisition_buffer.size > 0:
            item = acquisition_buffer.try_get()
            if item is None:
                time.sleep(0.0005)
                continue
            dispatcher_stats["in_flight_sequence"] = item.capture_sequence
            if recorder_buffer.try_put(item):
                dispatcher_stats["transferred_count"] += 1
            dispatcher_stats["in_flight_sequence"] = None

    recorder_thread = threading.Thread(
        target=recorder.run, args=(recorder_stop,),
        name="ACC-Graphics-Recorder", daemon=True,
    )
    dispatcher_thread = threading.Thread(
        target=dispatcher, name="ACC-Graphics-Dispatcher", daemon=True,
    )
    producer_thread = threading.Thread(
        target=producer, name="ACC-Graphics-Acquisition", daemon=True,
    )

    def checkpoint_snapshot() -> dict:
        checkpoint_sequence["value"] += 1
        acquired = acquirer.metrics.capture_count
        persisted = recorder.metrics.persisted_snapshot_count
        acquisition_rejected = acquisition_buffer.total_rejection_count
        recorder_rejected = recorder_buffer.total_rejection_count
        failed = recorder.metrics.failed_snapshot_count
        acquisition_pending = acquisition_buffer.size
        recorder_pending = recorder_buffer.size
        dispatcher_in_flight = int(dispatcher_stats["in_flight_sequence"] is not None)
        recorder_in_flight = recorder.metrics.in_flight_snapshot_count
        accounted = (
            persisted + acquisition_rejected + recorder_rejected + failed
            + acquisition_pending + recorder_pending
            + dispatcher_in_flight + recorder_in_flight
        )
        return {
            "schema_version": 1, "page": "graphics",
            "recording_file": recording_path.name,
            "mapping_name": "Local\\acpmf_graphics",
            "mapping_page_size_bytes": page_size,
            "checkpoint_sequence": checkpoint_sequence["value"],
            "checkpointed_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_ns": time.perf_counter_ns() - wall_start_ns,
            "acquisition": asdict(acquirer.metrics),
            "acquisition_buffer": {
                "capacity": acquisition_buffer.capacity, "pending": acquisition_pending,
                "high_water_mark": acquisition_buffer.high_water_mark,
                "rejections": acquisition_rejected,
                "first_lost_sequence": acquisition_buffer.first_lost_sequence,
                "last_lost_sequence": acquisition_buffer.last_lost_sequence,
            },
            "dispatcher": dispatcher_stats.copy(),
            "recorder_buffer": {
                "capacity": recorder_buffer.capacity, "pending": recorder_pending,
                "high_water_mark": recorder_buffer.high_water_mark,
                "rejections": recorder_rejected,
                "first_lost_sequence": recorder_buffer.first_lost_sequence,
                "last_lost_sequence": recorder_buffer.last_lost_sequence,
            },
            "recorder": asdict(recorder.metrics),
            "accounting": {
                "acquired": acquired, "persisted": persisted,
                "acquisition_rejections": acquisition_rejected,
                "recorder_queue_rejections": recorder_rejected,
                "write_failed": failed,
                "acquisition_queue_pending": acquisition_pending,
                "recorder_queue_pending": recorder_pending,
                "dispatcher_in_flight": dispatcher_in_flight,
                "recorder_in_flight": recorder_in_flight,
                "observed_unclassified_delta": acquired - accounted,
            },
            "note": "Periodic point-in-time counters; brief non-zero delta can occur while a sample moves between stages.",
        }

    checkpoint_worker = PeriodicCheckpointWorker(
        checkpoint_path, checkpoint_snapshot,
        interval_seconds=args.checkpoint_interval_seconds,
    )
    checkpoint_thread = threading.Thread(
        target=checkpoint_worker.run, args=(checkpoint_stop,),
        name="ACC-Graphics-Checkpoint", daemon=True,
    )

    timer = WindowsTimerResolution(args.timer_resolution_ms)
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
        producer_thread.join(timeout=10)
        if producer_thread.is_alive():
            producer_error = "Graphics acquisition thread did not stop within 10 seconds."
        dispatcher_thread.join(timeout=30)
        if dispatcher_thread.is_alive():
            producer_error = producer_error or "Graphics dispatcher did not finish draining."
        recorder_stop.set()
        recorder_thread.join(timeout=30)
        if recorder_thread.is_alive():
            producer_error = producer_error or "Graphics recorder did not finish draining."
        checkpoint_stop.set()
        checkpoint_thread.join(timeout=5)
    except Exception as exc:
        producer_error = f"{type(exc).__name__}: {exc}"
        acquisition_stop.set()
        recorder_stop.set()
        checkpoint_stop.set()
    finally:
        timer.__exit__(None, None, None)

    wall_elapsed_ns = time.perf_counter_ns() - wall_start_ns
    process_cpu_ns = time.process_time_ns() - cpu_start_ns
    if producer_errors:
        producer_error = "; ".join(producer_errors)

    acquired = acquirer.metrics.capture_count
    persisted = recorder.metrics.persisted_snapshot_count
    acquisition_rejected = acquisition_buffer.total_rejection_count
    recorder_rejected = recorder_buffer.total_rejection_count
    failed = recorder.metrics.failed_snapshot_count
    pending_acquisition = acquisition_buffer.size
    pending_recorder = recorder_buffer.size
    dispatcher_in_flight = int(dispatcher_stats["in_flight_sequence"] is not None)
    recorder_in_flight = recorder.metrics.in_flight_snapshot_count
    accounted = (
        persisted + acquisition_rejected + recorder_rejected + failed
        + pending_acquisition + pending_recorder
        + dispatcher_in_flight + recorder_in_flight
    )
    reconciliation_delta = acquired - accounted

    try:
        recovery = asdict(recover_graphics_recording(recording_path))
        recovery_ok = (
            recovery["recovered_snapshot_count"] == persisted
            and recovery["truncated_bytes"] == 0
            and recovery["page_size"] == page_size
        )
    except Exception as exc:
        recovery = {"error": f"{type(exc).__name__}: {exc}"}
        recovery_ok = False

    checkpoint_ok = (
        checkpoint_worker.error is None and checkpoint_worker.write_count > 0
        and not checkpoint_thread.is_alive()
    )
    status = (
        "completed"
        if not producer_error and not recorder.error and recovery_ok
        and checkpoint_ok and reconciliation_delta == 0
        and pending_acquisition == 0 and pending_recorder == 0
        else "failed"
    )
    report = {
        "schema_version": 1, "page": "graphics", "status": status,
        "mapping_name": "Local\\acpmf_graphics",
        "mapping_allocation_size_bytes": page_size,
        "candidate_struct_size_bytes": 1588,
        "candidate_struct_status": "reference-only; not used to limit raw capture",
        "recording_file": recording_path.name, "checkpoint_file": checkpoint_path.name,
        "checkpoint_write_count": checkpoint_worker.write_count,
        "checkpoint_write_failure_count": checkpoint_worker.write_failure_count,
        "checkpoint_error": checkpoint_worker.error,
        "started_at_utc": started_utc.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "duration_seconds_requested": args.duration_seconds,
            "poll_hz_requested": args.poll_hz,
            "acquisition_buffer_capacity": args.acquisition_buffer_capacity,
            "recorder_buffer_capacity": args.recorder_buffer_capacity,
            "batch_size": args.batch_size,
            "timer_resolution_ms_requested": args.timer_resolution_ms,
            "checkpoint_interval_seconds": args.checkpoint_interval_seconds,
            "simulated_write_delay_ms": args.simulated_write_delay_ms,
        },
        "environment": {
            "platform": platform.platform(), "python": sys.version,
            "cpu_count": os.cpu_count(),
        },
        "timing": {
            "wall_elapsed_ns": wall_elapsed_ns, "process_cpu_ns": process_cpu_ns,
            "process_cpu_one_core_percent": process_cpu_ns / wall_elapsed_ns * 100 if wall_elapsed_ns else 0,
        },
        "acquisition_metrics": asdict(acquirer.metrics),
        "acquisition_buffer": {
            "capacity": acquisition_buffer.capacity,
            "high_water_mark": acquisition_buffer.high_water_mark,
            "rejections": acquisition_rejected, "pending": pending_acquisition,
        },
        "dispatcher": dispatcher_stats,
        "recorder_buffer": {
            "capacity": recorder_buffer.capacity,
            "high_water_mark": recorder_buffer.high_water_mark,
            "rejections": recorder_rejected, "pending": pending_recorder,
        },
        "recorder_metrics": asdict(recorder.metrics),
        "recorder_error": recorder.error, "producer_error": producer_error,
        "reconciliation": {
            "acquired": acquired, "persisted": persisted,
            "acquisition_buffer_rejections": acquisition_rejected,
            "recorder_buffer_rejections": recorder_rejected,
            "recorder_write_failures": failed,
            "pending_acquisition": pending_acquisition,
            "pending_recorder": pending_recorder,
            "dispatcher_in_flight": dispatcher_in_flight,
            "recorder_in_flight": recorder_in_flight,
            "accounted_total": accounted, "delta": reconciliation_delta,
        },
        "recovery_validation": recovery,
        "recovery_validation_passed": recovery_ok,
        "checkpoint_validation_passed": checkpoint_ok,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Status                  : {status}")
    print(f"Recording               : {recording_path}")
    print(f"Report                  : {report_path}")
    print(f"Checkpoint              : {checkpoint_path}")
    print(f"Mapping page size       : {page_size} bytes")
    print(f"Acquired                : {acquired}")
    print(f"Persisted               : {persisted}")
    print(f"Acquisition rejects     : {acquisition_rejected}")
    print(f"Recorder queue rejects  : {recorder_rejected}")
    print(f"Recorder write failures : {failed}")
    print(f"Pending                 : {pending_acquisition + pending_recorder}")
    print(f"Reconciliation delta    : {reconciliation_delta}")
    print(f"Recovery validation    : {recovery_ok}")
    print(f"Checkpoint validation  : {checkpoint_ok}")
    print(f"CPU (one core)          : {report['timing']['process_cpu_one_core_percent']:.2f}%")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
