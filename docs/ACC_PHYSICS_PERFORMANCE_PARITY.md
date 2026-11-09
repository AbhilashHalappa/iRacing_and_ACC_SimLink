# ACC Physics Acquisition Performance Parity

**Status:** ACCEPTED — supervised Physics acquisition achieved live 600-second performance parity with the direct benchmark; all polling, integrity and lifecycle gates passed.
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

## Initial supervised result — failed

The first 600-second supervised Physics-only run was completed on 2026-11-09
with the same 480 Hz request, 1 ms timer request, one Physics stream and one
drain thread. It did not meet the performance gate:

- Average poll cadence: **472.63 Hz** (below the 475.2 Hz minimum).
- Unique accepted snapshots: **372.45/s** (below the approximately 388.50/s reference).
- Process CPU: **6.22% of one core** (above the 4.69% reference).
- Source read failures, buffer rejections, pending records and reconciliation
  delta: **all zero**.
- Worker and drain shutdown: clean; timer resolution released; no errors.

The report showed 284,869 read attempts, 223,473 accepted unique snapshots,
1,291 inconsistent snapshots/retries, 60,105 duplicate packet observations,
4,423 poll schedule overruns and a maximum poll lateness of 60.22 ms. These
figures describe the run; they do not by themselves prove that health reporting
caused the regression.

A targeted optimization was then committed to common acquisition health:
worker-owned counters are now updated in place rather than replacing an
immutable dataclass on every successful read. Snapshot readers use a sequence
counter to retain coherent immutable snapshots without adding a lock to the
acquisition path. No source-read, consistency, packet-ID, timestamp, snapshot,
buffer, retry, polling-target or acceptance behavior was intentionally changed.

**The optimization is not yet performance-accepted.** Run the same 600-second
benchmark again and compare all three performance metrics. If it still misses
the reference, investigate the scheduling/read path; do not weaken thresholds
or alter data-quality guarantees.

## Final supervised parity result — passed

The final 600-second supervised Physics-only benchmark was completed on
2026-11-09 after aligning the supervised benchmark's empty-queue drain wait
with the original direct benchmark (time.sleep(0.0005)). The production
Physics reader and acquisition behavior were not changed for this harness
correction.

Report:
user_data/benchmarks/acc_physics_supervised_parity_20261109_164020_UTC.json

Measured result:
- Elapsed time: **600.003 seconds**.
- Requested polling cadence: **480 Hz**.
- Average observed poll cadence: **479.12 Hz**.
- Unique accepted Physics snapshots: **232,697 total; 387.83 snapshots/s**.
- Consumed snapshots: **232,697**.
- Buffer rejections: **0**.
- Pending snapshots after drain: **0**.
- Reconciliation delta: **0**.
- Process CPU: **5.82% of one core**.
- Supervisor state: **stopped**.
- Timer resolution active after shutdown: **false**.
- Supervisor errors: **none**.
- Harness result: **PASSED**.

### Direct-benchmark comparison

The same-day direct Physics benchmark reference was **479.24 Hz** and
**232,633 unique snapshots / 600 seconds = 387.72 snapshots/s**.

| Metric | Direct benchmark | Final supervised benchmark | Difference |
|---|---:|---:|---:|
| Poll cadence | 479.24 Hz | 479.12 Hz | -0.12 Hz (-0.025%) |
| Unique accepted snapshots/s | 387.72 | 387.83 | +0.11 (+0.028%) |
| Unique accepted snapshots | 232,633 | 232,697 | +64 |

The supervised run therefore achieved practical parity with the same-day
direct run for both polling cadence and unique accepted snapshot throughput.
It is also close to the historical reference of 479.672 Hz and approximately
388.50 unique snapshots/s, with expected run-to-run variation.

The final supervised CPU result was **5.82% of one core**, compared with the
historical reference of approximately **4.69%**. CPU is recorded as an
observation and is not claimed to be at parity. The measured polling cadence,
unique accepted snapshot throughput, data-integrity gates and lifecycle gates
all passed. The CPU observation does not justify changing acquisition
correctness behavior or relaxing any acceptance threshold.

### Performance acceptance decision

**Performance acceptance is granted for the supervised Physics acquisition
path.** The 480 Hz target and 99% polling floor remain unchanged. No source-read,
consistency, packet-ID, timestamp, snapshot, retry, buffer or data-quality
requirements were weakened.

Issue #2 was already closed for the common health implementation. The final
live parity evidence is recorded here and in the issue discussion. No further
600-second benchmark is required for this acceptance decision.

## Acceptance and interpretation

Compare the supervised run against the historical baseline using the same definitions:
1. Poll cadence: compare average observed poll Hz with 479.672 Hz.
2. Unique capture throughput: compare `capture_count / wall_elapsed_seconds` with approximately 388.50 snapshots/s.
3. CPU: compare process CPU percent of one core with approximately 4.69%, because the workload is now Physics-only with one drain thread on both sides.

Use the same machine, ACC session conditions, power mode and background workload where possible. A 600-second run is required for the primary comparison. If environment or session conditions differ materially, record them and repeat rather than claiming parity from a short run.

**Performance acceptance is recorded above.** Retain the 480 Hz target and all acquisition data-quality guarantees. Future changes to the Physics acquisition path should be evaluated against this accepted benchmark.
