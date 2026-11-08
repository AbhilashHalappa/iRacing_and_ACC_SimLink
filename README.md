# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building and validating the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current project status

**As of 8 November 2026:** the source-independent Physics acquisition core and Windows ACC Physics shared-memory adapter are implemented. The pre-Stage-2 acquisition test suite passed locally (13/13), and a short live ACC smoke test successfully copied 100 Physics pages of the expected 784-byte size while observing 100 unique, advancing packet IDs. Stage 2 has added cadence metrics, rejection accounting and a live benchmark harness. The first live 120/240/480 Hz sweep completed with approximately 64.5 Hz observed cadence and zero application reconciliation delta in all trials. A 1 ms Windows timer-resolution request is now included for the controlled retest; the expanded tests must be run against the updated branch tip.

This is not yet a complete acquisition pipeline. Sustained acquisition through the acquirer and buffer, cadence/CPU measurement, Graphics and Static page acquisition, raw recording, recovery and end-of-session reconciliation remain outstanding.

The project-level stage tracker, evidence, limitations and next-stage acceptance gates are maintained in [docs/PROJECT_COMPLETION_STATUS.md](docs/PROJECT_COMPLETION_STATUS.md). Update that document whenever a stage reaches a new evidence-backed state.

## Current scope

The initial source-independent core is in `src/race_engineer_acquisition/`:

- Immutable raw Physics observation models.
- A bounded, preallocated SPSC ring buffer that never overwrites unread samples.
- Non-blocking producer insertion with explicit loss accounting.
- An injectable Physics acquisition loop with monotonic read timestamps.
- Packet-ID gap, duplicate, regression and consistency-retry accounting.
- A Windows read-only adapter for the audited `Local\\acpmf_physics` mapping/layout.

**Important:** ACC Shared Memory exposes latest-state pages, not a guaranteed delivery queue. The project distinguishes source packet progression from application-level buffer loss and does not claim zero source-level packet loss. The current implementation reads Physics only; Graphics and Static are not implemented. The package is not yet a complete raw recorder.

## Run the current tests

From the repository root on Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -v
```

## Stage 2 — Live acquisition benchmark

The repository now includes a controlled-cadence runner and a live benchmark harness. With ACC running, execute from the repository root:

```powershell
$env:PYTHONPATH = "src"
python scripts/benchmark_acc_physics.py --duration-seconds 120 --poll-hz 120
```

The benchmark requests a 1 ms Windows timer resolution during each trial by default to improve wait granularity; pass `--timer-resolution-ms 0` to disable that request for comparison. This request does not guarantee a specific wake-up time or polling rate. Repeat as separate trials at `--poll-hz 240` and `--poll-hz 480`. These are measurement points, not declared production targets. Keep the same duration and buffer capacity for comparable runs. The harness exercises the actual Windows Physics adapter, `PhysicsAcquirer`, bounded SPSC buffer and a separate draining consumer. It writes a timestamped JSON report under `user_data/benchmarks/` after the run; the acquisition thread itself performs no file I/O.

Review requested versus observed polling rate, source packet gaps, consistency retries, full-buffer and lock-contention rejects, buffer high-water mark, process CPU, and final reconciliation. A zero reconciliation delta means acquired snapshots were consumed or explicitly rejected by the application buffer; it does not mean every ACC publication was observed.

## Next gate

Run the expanded acquisition tests and repeat the live cadence sweep with the 1 ms Windows timer-resolution request active. Compare observed cadence against the initial approximately 64.5 Hz baseline. Do not begin the raw recorder until the acquisition measurement baseline and loss accounting are trustworthy.

See:
- [Project Completion Status](docs/PROJECT_COMPLETION_STATUS.md)
- [Acquisition and Data Integrity Decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md)
