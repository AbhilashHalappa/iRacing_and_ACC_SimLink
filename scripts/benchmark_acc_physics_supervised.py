"""Like-for-like Physics-only benchmark for the supervised acquisition path.

Run on Windows with ACC running. Mirrors benchmark_acc_physics.py's workload:
one Physics source/acquirer, one bounded SPSC queue, one dedicated drain thread,
1 ms timer-resolution request, and process CPU measured over the acquisition run.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.acc_windows import WindowsACCPhysicsSource
from race_engineer_acquisition.acquirer import PhysicsAcquirer
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.supervisor import AcquisitionStream, AcquisitionSupervisor
from race_engineer_acquisition.timing_windows import WindowsTimerResolution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=600.0)
    parser.add_argument("--poll-hz", type=float, default=480.0)
    parser.add_argument("--timer-resolution-ms", type=int, default=1)
    parser.add_argument("--buffer-capacity", type=int, default=100_000)
    parser.add_argument("--output-dir", type=Path, default=Path("user_data/benchmarks"))
    args = parser.parse_args()
    if args.seconds <= 0 or args.poll_hz <= 0 or args.buffer_capacity <= 0:
        parser.error("seconds, poll-hz and buffer-capacity must be positive")
    if args.timer_resolution_ms < 0:
        parser.error("timer-resolution-ms cannot be negative")

    source = WindowsACCPhysicsSource()
    buffer = AcquisitionRingBuffer(args.buffer_capacity)
    acquirer = PhysicsAcquirer(source, buffer)
    interval_ns = max(1, round(1_000_000_000 / args.poll_hz))
    drain_stop = threading.Event()
    consumed = {"count": 0, "sequence_gaps": 0, "first_sequence": None, "last_sequence": None}
    errors: list[str] = []

    def acquire(stop: threading.Event) -> None:
        try:
            acquirer.run(stop, poll_interval_ns=interval_ns)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            raise

    def drain() -> None:
        previous = None
        while not drain_stop.is_set() or buffer.size:
            item = buffer.try_get()
            if item is None:
                drain_stop.wait(0.0005)
                continue
            seq = item.capture_sequence
            if previous is not None and seq > previous + 1:
                consumed["sequence_gaps"] += seq - previous - 1
            if consumed["first_sequence"] is None:
                consumed["first_sequence"] = seq
            consumed["last_sequence"] = seq
            consumed["count"] += 1
            previous = seq

    supervisor = AcquisitionSupervisor(
        (AcquisitionStream("physics", acquire, source.close, acquirer.health),),
        timer_resolution=WindowsTimerResolution(args.timer_resolution_ms),
    )
    drain_thread = threading.Thread(target=drain, name="ACC-Physics-Benchmark-Drain", daemon=True)

    wall_start_ns = time.perf_counter_ns()
    cpu_start_ns = time.process_time_ns()
    drain_thread.start()
    try:
        supervisor.start()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    except Exception as exc:
        errors.append(f"Supervisor {type(exc).__name__}: {exc}")
    finally:
        still_running = supervisor.stop(timeout=10.0)
        drain_stop.set()
        drain_thread.join(timeout=10.0)

    wall_elapsed_ns = time.perf_counter_ns() - wall_start_ns
    cpu_elapsed_ns = time.process_time_ns() - cpu_start_ns
    metrics = asdict(acquirer.metrics)
    metrics = {k: v for k, v in metrics.items() if not k.startswith("_")}
    acquired = acquirer.metrics.capture_count
    rejected = buffer.total_rejection_count
    pending = buffer.size
    reconciliation = acquired - consumed["count"] - rejected - pending
    poll_hz = (
        acquirer.metrics.poll_interval_count * 1_000_000_000
        / acquirer.metrics.total_poll_interval_ns
        if acquirer.metrics.poll_interval_count and acquirer.metrics.total_poll_interval_ns
        else None
    )
    status = supervisor.status["physics"]
    report = {
        "schema_version": 1,
        "started_at_utc": datetime.fromtimestamp(
            (time.time_ns() - wall_elapsed_ns) / 1_000_000_000, tz=timezone.utc
        ).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "duration_seconds_requested": args.seconds,
            "poll_hz_requested": args.poll_hz,
            "poll_interval_ns_requested": interval_ns,
            "timer_resolution_ms_requested": args.timer_resolution_ms,
            "buffer_capacity": args.buffer_capacity,
            "streams": ["physics"],
            "consumer_threads": 1,
        },
        "environment": {"platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count()},
        "timing": {
            "wall_elapsed_ns": wall_elapsed_ns,
            "process_cpu_ns": cpu_elapsed_ns,
            "process_cpu_one_core_percent": cpu_elapsed_ns / wall_elapsed_ns * 100 if wall_elapsed_ns else 0,
            "average_observed_poll_hz": poll_hz,
        },
        "acquisition_metrics": metrics,
        "buffer_metrics": {
            "capacity": buffer.capacity,
            "high_water_mark": buffer.high_water_mark,
            "final_occupancy": pending,
            "rejection_count": rejected,
        },
        "consumer_metrics": consumed,
        "supervisor": {
            "state": status["state"],
            "health_state": status["health"].lifecycle_state,
            "source_read_failures": status["health"].source_read_failures,
            "timer_resolution_active": status["timer_resolution_active"],
            "timer_resolution_error": status["timer_resolution_error"],
            "workers_still_running": list(still_running),
            "drain_thread_alive": drain_thread.is_alive(),
        },
        "reconciliation": {
            "acquired_unique_snapshots": acquired,
            "consumed_snapshots": consumed["count"],
            "buffer_rejections": rejected,
            "pending_after_drain": pending,
            "unaccounted_delta": reconciliation,
        },
        "errors": errors,
    }
    report["status"] = "passed" if (
        not errors and not still_running and not drain_thread.is_alive()
        and status["state"] == "stopped" and status["health"].lifecycle_state == "stopped"
        and status["health"].source_read_failures == 0 and rejected == 0
        and pending == 0 and reconciliation == 0
        and not status["timer_resolution_active"] and status["timer_resolution_error"] is None
        and poll_hz is not None and poll_hz >= args.poll_hz * 0.99
    ) else "failed"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    path = args.output_dir / f"acc_physics_supervised_parity_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {path}")
    print(f"Elapsed: {wall_elapsed_ns / 1e9:.3f}s")
    print(f"Poll rate: {poll_hz:.2f} Hz" if poll_hz is not None else "Poll rate: n/a")
    print(f"Unique captures: {acquired} ({acquired / (wall_elapsed_ns / 1e9):.2f}/s)")
    print(f"Consumed: {consumed['count']}  Rejected: {rejected}  Pending: {pending}  Delta: {reconciliation}")
    print(f"CPU: {report['timing']['process_cpu_one_core_percent']:.2f}% of one core")
    print(f"Supervisor: {status['state']}  Timer active: {status['timer_resolution_active']}  Errors: {errors}")
    print(f"RESULT: {report['status'].upper()}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
