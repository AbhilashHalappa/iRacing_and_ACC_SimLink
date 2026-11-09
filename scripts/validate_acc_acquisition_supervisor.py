"""Short live ACC smoke test for the unified Physics/Graphics/Static supervisor."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.supervisor import create_acc_acquisition_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--stop-timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.seconds <= 0 or args.stop_timeout <= 0:
        parser.error("seconds and stop timeout must be positive")

    runtime = create_acc_acquisition_runtime()
    started = time.monotonic()
    runtime.supervisor.start()
    try:
        time.sleep(args.seconds)
    finally:
        still_running = runtime.supervisor.stop(timeout=args.stop_timeout)

    elapsed = time.monotonic() - started
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"workers_still_running={list(still_running)}")
    failed = False
    for name in ("physics", "graphics", "static"):
        status = runtime.supervisor.status[name]
        metrics = runtime.acquirers[name].metrics
        buffer = runtime.buffers[name]
        captures = metrics.capture_count
        health = status["health"]
        print(
            f"{name}: state={status['state']} captures={captures} "
            f"reads={health.successful_reads} read_failures={health.source_read_failures} "
            f"consecutive_failures={health.consecutive_failures} "
            f"last_read_ns={health.last_read_duration_ns} "
            f"max_read_ns={health.max_read_duration_ns} "
            f"last_success_ns={health.last_successful_read_ns} "
            f"buffer_pending={buffer.size} buffer_rejections={buffer.total_rejection_count} "
            f"health_state={health.lifecycle_state} error={status['error']} "
            f"close_error={status['close_error']}"
        )
        if (
            status["state"] != "stopped"
            or health.lifecycle_state != "stopped"
            or captures < 1
            or health.successful_reads < 1
            or health.source_read_failures != 0
            or health.consecutive_failures != 0
        ):
            failed = True

    if still_running or failed:
        print("RESULT: FAILED")
        return 2
    print("RESULT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
