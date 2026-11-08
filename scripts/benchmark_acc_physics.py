"""Live ACC Physics acquisition benchmark.

Run on Windows with ACC running. This tool exercises the real Windows source,
PhysicsAcquirer and SPSC buffer. The consumer drains the buffer on a separate
thread; no files are written by the acquisition thread.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from race_engineer_acquisition.acc_windows import WindowsACCPhysicsSource
from race_engineer_acquisition.acquirer import PhysicsAcquirer
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument(
        "--poll-hz",
        type=float,
        required=True,
        help="Requested maximum poll cadence; run separate trials at different rates.",
    )
    parser.add_argument("--buffer-capacity", type=int, default=100_000)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("user_data/benchmarks"),
    )
    args = parser.parse_args()
    if args.duration_seconds <= 0:
        parser.error("--duration-seconds must be positive")
    if args.poll_hz <= 0:
        parser.error("--poll-hz must be positive")
    if args.buffer_capacity <= 0:
        parser.error("--buffer-capacity must be positive")
    return args


def main() -> int:
    args = parse_args()
    poll_interval_ns = max(1, round(1_000_000_000 / args.poll_hz))
    source = WindowsACCPhysicsSource()
    buffer = AcquisitionRingBuffer(args.buffer_capacity)
    acquirer = PhysicsAcquirer(source, buffer)
    stop_event = threading.Event()
    producer_done = threading.Event()
    consumer_stop = threading.Event()
    producer_errors: list[str] = []
    consumer_stats = {
        "consumed_count": 0,
        "first_capture_sequence": None,
        "last_capture_sequence": None,
        "sequence_gap_count": 0,
    }

    def producer() -> None:
        try:
            acquirer.run(stop_event, poll_interval_ns=poll_interval_ns)
        except Exception as exc:  # surfaced in the benchmark report
            producer_errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                source.close()
            finally:
                producer_done.set()

    def consumer() -> None:
        previous_sequence = None
        while not consumer_stop.is_set() or buffer.size > 0:
            snapshot = buffer.try_get()
            if snapshot is None:
                time.sleep(0.0005)
                continue
            if previous_sequence is not None and snapshot.capture_sequence > previous_sequence + 1:
                consumer_stats["sequence_gap_count"] += (
                    snapshot.capture_sequence - previous_sequence - 1
                )
            if consumer_stats["first_capture_sequence"] is None:
                consumer_stats["first_capture_sequence"] = snapshot.capture_sequence
            consumer_stats["last_capture_sequence"] = snapshot.capture_sequence
            consumer_stats["consumed_count"] += 1
            previous_sequence = snapshot.capture_sequence

    producer_thread = threading.Thread(
        target=producer, name="ACC-Physics-Acquisition", daemon=True
    )
    consumer_thread = threading.Thread(
        target=consumer, name="ACC-Physics-Benchmark-Drain", daemon=True
    )

    wall_start_ns = time.perf_counter_ns()
    cpu_start_ns = time.process_time_ns()
    consumer_thread.start()
    producer_thread.start()

    deadline = time.monotonic() + args.duration_seconds
    while not producer_done.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        producer_done.wait(min(remaining, 0.2))

    stop_event.set()
    producer_thread.join(timeout=10.0)
    if producer_thread.is_alive():
        producer_errors.append("Acquisition thread did not stop within 10 seconds.")
    consumer_stop.set()
    consumer_thread.join(timeout=10.0)
    if consumer_thread.is_alive():
        producer_errors.append("Buffer-drain thread did not stop within 10 seconds.")

    wall_elapsed_ns = time.perf_counter_ns() - wall_start_ns
    process_cpu_ns = time.process_time_ns() - cpu_start_ns
    metrics = {
        key: value
        for key, value in asdict(acquirer.metrics).items()
        if not key.startswith("_")
    }
    rejected = buffer.total_rejection_count
    pending = buffer.size
    consumed = consumer_stats["consumed_count"]
    acquired = acquirer.metrics.capture_count
    reconciliation_delta = acquired - consumed - rejected - pending
    average_poll_interval_ns = (
        acquirer.metrics.total_poll_interval_ns
        / acquirer.metrics.poll_interval_count
        if acquirer.metrics.poll_interval_count
        else None
    )
    average_read_attempt_ns = (
        acquirer.metrics.total_read_attempt_duration_ns
        / acquirer.metrics.read_attempt_count
        if acquirer.metrics.read_attempt_count
        else None
    )

    report = {
        "schema_version": 1,
        "started_at_utc": datetime.fromtimestamp(
            (time.time_ns() - wall_elapsed_ns) / 1_000_000_000,
            tz=timezone.utc,
        ).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if producer_errors else "completed",
        "configuration": {
            "duration_seconds_requested": args.duration_seconds,
            "poll_hz_requested": args.poll_hz,
            "poll_interval_ns_requested": poll_interval_ns,
            "buffer_capacity": args.buffer_capacity,
        },
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "cpu_count": os.cpu_count(),
        },
        "timing": {
            "wall_elapsed_ns": wall_elapsed_ns,
            "process_cpu_ns": process_cpu_ns,
            "process_cpu_one_core_percent": (
                process_cpu_ns / wall_elapsed_ns * 100 if wall_elapsed_ns else 0
            ),
            "average_poll_interval_ns": average_poll_interval_ns,
            "average_observed_poll_hz": (
                1_000_000_000 / average_poll_interval_ns
                if average_poll_interval_ns
                else None
            ),
            "average_read_attempt_duration_ns": average_read_attempt_ns,
        },
        "acquisition_metrics": metrics,
        "buffer_metrics": {
            "capacity": buffer.capacity,
            "high_water_mark": buffer.high_water_mark,
            "final_occupancy": pending,
            "full_buffer_rejection_count": buffer.full_buffer_rejection_count,
            "lock_contention_count": buffer.lock_contention_count,
            "total_rejection_count": rejected,
            "first_lost_sequence": buffer.first_lost_sequence,
            "last_lost_sequence": buffer.last_lost_sequence,
        },
        "consumer_metrics": consumer_stats,
        "reconciliation": {
            "acquired_snapshots": acquired,
            "consumed_snapshots": consumed,
            "buffer_rejections": rejected,
            "pending_after_drain": pending,
            "unaccounted_delta": reconciliation_delta,
            "sequence_gap_count_observed_by_consumer": consumer_stats[
                "sequence_gap_count"
            ],
        },
        "producer_errors": producer_errors,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    output_path = args.output_dir / f"acc_physics_benchmark_{stamp}.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n========== ACC PHYSICS ACQUISITION BENCHMARK ==========")
    print(f"Report                  : {output_path}")
    print(f"Requested poll rate     : {args.poll_hz:.2f} Hz")
    print(f"Observed average rate   : {report['timing']['average_observed_poll_hz']}")
    print(f"Wall duration           : {wall_elapsed_ns / 1e9:.2f} s")
    print(f"Process CPU             : {report['timing']['process_cpu_one_core_percent']:.2f}% of one core")
    print(f"Acquired snapshots      : {acquired}")
    print(f"Consumed snapshots      : {consumed}")
    print(f"Source packet gaps      : {acquirer.metrics.source_packet_gap_count}")
    print(f"Inconsistent reads      : {acquirer.metrics.inconsistent_snapshot_count}")
    print(f"Consistency retries     : {acquirer.metrics.consistency_retry_count}")
    print(f"Duplicate observations : {acquirer.metrics.duplicate_packet_observation_count}")
    print(f"Buffer high-water       : {buffer.high_water_mark}/{buffer.capacity}")
    print(f"Full-buffer rejects     : {buffer.full_buffer_rejection_count}")
    print(f"Lock-contention rejects : {buffer.lock_contention_count}")
    print(f"Pending after drain     : {pending}")
    print(f"Reconciliation delta    : {reconciliation_delta}")
    print(f"Producer errors         : {producer_errors}")
    print("========================================================")
    return 1 if producer_errors or reconciliation_delta != 0 or pending != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
