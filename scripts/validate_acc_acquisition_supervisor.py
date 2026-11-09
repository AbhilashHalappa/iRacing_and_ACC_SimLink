"""Performance-gated live ACC validation for the supervised acquisition runtime.

Run on Windows with ACC running. Independent drain threads keep the SPSC
buffers empty so this test measures acquisition cadence rather than buffer fill.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.supervisor import create_acc_acquisition_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--stop-timeout", type=float, default=10.0)
    parser.add_argument("--minimum-rate-ratio", type=float, default=0.99)
    parser.add_argument("--timer-resolution-ms", type=int, default=1)
    args = parser.parse_args()
    if args.seconds <= 0 or args.stop_timeout <= 0:
        parser.error("seconds and stop timeout must be positive")
    if not 0 < args.minimum_rate_ratio <= 1:
        parser.error("minimum-rate-ratio must be in (0, 1]")
    if args.timer_resolution_ms < 0:
        parser.error("timer-resolution-ms cannot be negative")

    runtime = create_acc_acquisition_runtime(
        timer_resolution_ms=args.timer_resolution_ms
    )
    drain_stop = threading.Event()
    consumed = {name: 0 for name in ("physics", "graphics", "static")}

    def drain(name: str) -> None:
        buffer = runtime.buffers[name]
        while not drain_stop.is_set() or buffer.size:
            item = buffer.try_get()
            if item is None:
                drain_stop.wait(0.0002)
            else:
                consumed[name] += 1

    drain_threads = [
        threading.Thread(target=drain, args=(name,), name=f"ACC-{name}-Validation-Drain", daemon=True)
        for name in consumed
    ]
    for thread in drain_threads:
        thread.start()

    started = time.perf_counter()
    cpu_started = time.process_time_ns()
    try:
        runtime.supervisor.start()
        time.sleep(args.seconds)
    finally:
        still_running = runtime.supervisor.stop(timeout=args.stop_timeout)
        drain_stop.set()
        for thread in drain_threads:
            thread.join(timeout=5.0)

    elapsed = time.perf_counter() - started
    cpu_elapsed = time.process_time_ns() - cpu_started
    cpu_one_core_percent = cpu_elapsed / (elapsed * 1_000_000_000) * 100 if elapsed else 0.0
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"process_cpu_one_core_percent={cpu_one_core_percent:.2f}")
    print(f"workers_still_running={list(still_running)}")
    failed = bool(still_running) or any(thread.is_alive() for thread in drain_threads)
    expected_rates = {"physics": 480.0, "graphics": 100.0}
    for name in ("physics", "graphics", "static"):
        status = runtime.supervisor.status[name]
        metrics = runtime.acquirers[name].metrics
        buffer = runtime.buffers[name]
        captures = metrics.capture_count
        health = status["health"]
        read_hz = health.successful_reads / elapsed if elapsed else 0.0
        capture_hz = captures / elapsed if elapsed else 0.0
        rejected = buffer.total_rejection_count
        reconciliation = captures - consumed[name] - rejected - buffer.size
        target = expected_rates.get(name)
        minimum = target * args.minimum_rate_ratio if target is not None else None
        print(
            f"{name}: state={status['state']} reads={health.successful_reads} "
            f"read_hz={read_hz:.2f} capture_hz={capture_hz:.2f} "
            f"target_hz={target if target is not None else 'n/a'} "
            f"minimum_hz={minimum if minimum is not None else 'n/a'} "
            f"consumed={consumed[name]} read_failures={health.source_read_failures} "
            f"consecutive_failures={health.consecutive_failures} "
            f"packet_gaps={getattr(metrics, 'source_packet_gap_count', 'n/a')} "
            f"duplicate_observations={getattr(metrics, 'duplicate_packet_observation_count', 'n/a')} "
            f"inconsistent_reads={getattr(metrics, 'inconsistent_snapshot_count', 'n/a')} "
            f"last_read_ns={health.last_read_duration_ns} "
            f"max_read_ns={health.max_read_duration_ns} "
            f"buffer_rejections={rejected} pending={buffer.size} "
            f"reconciliation_delta={reconciliation} "
            f"health_state={health.lifecycle_state} "
            f"timer_active={status['timer_resolution_active']} "
            f"timer_error={status['timer_resolution_error']} "
            f"error={status['error']} close_error={status['close_error']}"
        )
        if (
            status["state"] != "stopped"
            or health.lifecycle_state != "stopped"
            or health.successful_reads < 1
            or health.source_read_failures != 0
            or health.consecutive_failures != 0
            or rejected != 0
            or buffer.size != 0
            or reconciliation != 0
            or status["timer_resolution_active"]
            or status["timer_resolution_error"] is not None
            or (target is not None and read_hz < minimum)
        ):
            failed = True

    if failed:
        print("RESULT: FAILED — performance/loss/lifecycle acceptance gate not met")
        return 2
    print("RESULT: PASSED — polling-rate, loss, drain and lifecycle gates met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
