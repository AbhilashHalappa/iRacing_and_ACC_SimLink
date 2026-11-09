# ACC Physics Acquisition Performance Parity

**Status:** Methodology and benchmark harness prepared; supervised parity run pending.
**Branch:** `feature/acquisition-foundation`
**Purpose:** Verify that the supervised Physics acquisition path preserves the original Physics-only performance, without reducing the 480 Hz target or weakening acceptance thresholds.

## Reference benchmark

The reference is the original `scripts/benchmark_acc_physics.py`. It runs one Windows ACC Physics mapping, one `PhysicsAcquirer`, one bounded SPSC buffer, and one dedicated consumer/drain thread. It requests a 1 ms Windows timer resolution for the trial and measures process CPU as a percentage of one logical core:

`process_cpu_one_core_percent = process_time_ns / wall_elapsed_ns * 100`

The reference benchmark's capture counter is `PhysicsAcquirer.metrics.capture_count`. It increments only after a consistent read with a packet ID different from the preceding packet ID. Therefore it represents unique, accepted Physics snapshots—not raw polling attempts and not all successful source reads.

Recorded original baseline (600-second Physics-only trial):
- Average poll cadence: **479.672 Hz**
- Unique accepted snapshots: **approximately 388.50 snapshots/s**
- Process CPU: **approximately 4.69% of one core**

These are the comparison values. The original benchmark script currently defaults to 120 seconds, but its CLI accepts a duration; the historical baseline above was collected over 600 seconds.

## Why the previous supervisor run was not a parity comparison

The 120-second supervisor validation ran Physics, Graphics and Static concurrently and used three drain threads. Its reported **11.64% CPU** includes all three acquisition workers and all three consumers, so it cannot be compared directly with the Physics-only **4.69%** baseline.

Its Physics result of **385.92 captures/s** uses the same `capture_count` semantics as the reference (unique accepted snapshots), but the run duration and surrounding workload differ. The arithmetic difference from the historical baseline is about **-0.66%**; this is an observation, not a valid parity conclusion.

The supervisor validation remains useful for its own gates: the recorded run met the 480 Hz Physics and 100 Hz Graphics polling floors, had zero source read failures, zero buffer rejections, zero pending records after draining, zero reconciliation delta, clean worker shutdown and timer-resolution release. Those results do not replace the Physics-only performance comparison.

## Like-for-like supervised benchmark

Use `scripts/benchmark_acc_physics_supervised.py`. It deliberately exercises the supervised Physics worker while retaining the reference workload shape:
- Physics only; Graphics and Static are not created or polled.
- One Physics source, one Physics acquirer and one bounded SPSC queue.
- One dedicated consumer/drain thread.
- 480 Hz requested cadence.
- 1 ms Windows timer-resolution request.
- Same unique accepted snapshot counter and process CPU calculation.
- 600-second default duration.
- Reports JSON evidence, actual polling cadence, unique snapshots/s, CPU, rejects, pending records, reconciliation and shutdown/timer state.

Run in Windows PowerShell from the repository root with ACC running:

```powershell
$env:PYTHONPATH = "src"
python scripts/benchmark_acc_physics_supervised.py --seconds 600 --poll-hz 480 --timer-resolution-ms 1
```

The harness passes only if observed poll cadence is at least 99% of 480 Hz, there are zero source read failures, zero buffer rejections, zero pending records and zero reconciliation delta, the worker and consumer stop, and timer resolution is released without error. It does not lower the acquisition target.

## Acceptance and interpretation

Compare the supervised run against the historical baseline using the same definitions:
1. Poll cadence: compare average observed poll Hz with 479.672 Hz.
2. Unique capture throughput: compare `capture_count / wall_elapsed_seconds` with approximately 388.50 snapshots/s.
3. CPU: compare process CPU percent of one core with approximately 4.69%, because the workload is now Physics-only with one drain thread on both sides.

Use the same machine, ACC session conditions, power mode and background workload where possible. A 600-second run is required for the primary comparison. If environment or session conditions differ materially, record them and repeat rather than claiming parity from a short run.

**No performance acceptance is granted by this document alone.** The supervised parity result must be recorded here after the live run. Do not close the performance portion of Issue #2 or proceed on the assumption of parity until the measured 600-second result has been reviewed. Do not alter the 480 Hz target or the acquisition hot path to satisfy the benchmark.
