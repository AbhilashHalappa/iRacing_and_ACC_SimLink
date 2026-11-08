# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building and validating the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current project status

**As of 8 November 2026:** the source-independent Physics acquisition core and Windows ACC Physics shared-memory adapter are implemented. The expanded acquisition/recorder suite passed in GitHub Actions on both Ubuntu and Windows (31/31 on each platform; run 42492834805). A short live ACC smoke test copied 100 Physics pages of the expected 784-byte size and observed 100 unique, advancing packet IDs. The initial 120/240/480 Hz sweep was limited to approximately 64.5 Hz by ordinary Windows wait timing. The benchmark now requests a balanced 1 ms WinMM timer resolution by default. A second 120/240/480 Hz live sweep achieved 119.999/239.999/479.206 polling cycles per second, with zero application buffer rejections and zero reconciliation delta in every trial. At 480 Hz, 46,851 unique snapshots were accepted in 120 seconds (about 390.4/s), with 10,655 duplicate observations rejected and 1,703 source packet gaps. The observed unique-snapshot rate suggests the ACC Physics page was publishing at roughly 400 Hz under these conditions; this is an estimate, not a guaranteed ACC specification.

Stage 2 acquisition measurement is complete. A 10-minute 480 Hz live run achieved 479.672 polling cycles/s and accepted 233,102 unique snapshots (388.50/s), with 4.69% CPU, zero buffer rejections and zero reconciliation delta. A 120-second live raw-recording run at 480 Hz then acquired and persisted 46,924 snapshots, with zero queue rejects, write failures or pending records, zero reconciliation delta and 12.04% CPU of one core. The expanded 31-test fault-injection suite passed on Windows and Ubuntu, including delayed writes, simulated partial disk-write failure and interrupted-block recovery. A real abrupt-stop and physical storage-failure test remain pending. Graphics and Static page acquisition remain unimplemented.

The project-level stage tracker, evidence, limitations and next-stage acceptance gates are maintained in [docs/PROJECT_COMPLETION_STATUS.md](docs/PROJECT_COMPLETION_STATUS.md). Update that document whenever a stage reaches a new evidence-backed state.

## Current scope

The initial source-independent core is in `src/race_engineer_acquisition/`:

- Immutable raw Physics observation models.
- A bounded, preallocated SPSC ring buffer that never overwrites unread samples.
- Non-blocking producer insertion with explicit loss accounting.
- An injectable Physics acquisition loop with monotonic read timestamps.
- Packet-ID gap, duplicate, regression and consistency-retry accounting.
- A Windows read-only adapter for the audited `Local\\acpmf_physics` mapping/layout.

**Important:** ACC Shared Memory exposes latest-state pages, not a guaranteed delivery queue. The project distinguishes source packet progression from application-level buffer loss and does not claim zero source-level packet loss. The current implementation reads Physics only; Graphics and Static are not implemented. The recorder has passed a normal live recording smoke test; the expanded 31-test fault-injection suite has passed on Windows and Ubuntu; real interrupted-session and physical storage-failure validation are still required before Stage 3 can be signed off.

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

The expanded acquisition tests, cadence sweep and 10-minute 480 Hz acquisition validation are complete. The independent raw recorder also passed a 120-second live run: 46,924 acquired/persisted, zero queue rejects, zero write failures, zero pending records and reconciliation delta 0. The next gate is a real abrupt-stop recording test on Windows, followed by recovery and reconciliation of the resulting file.

See:
- [Project Completion Status](docs/PROJECT_COMPLETION_STATUS.md)
- [Acquisition and Data Integrity Decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md)

## Stage 3 — Raw Physics recording (target-PC fault validation pending)

The raw recorder is implemented in `src/race_engineer_acquisition/recorder.py`. It consumes a dedicated bounded queue on a separate thread; the acquisition loop remains free of file I/O. Recordings use a versioned binary header and append-only blocks containing capture sequence, ACC packet ID, monotonic timestamps and raw Physics bytes. Each block has a CRC32 checksum. The writer flushes and fsyncs completed blocks. Recovery scans sequential complete blocks and can truncate a corrupt or incomplete trailing block.

A live three-thread runner is provided:

```powershell
$env:PYTHONPATH = "src"
python scripts/record_acc_physics.py --duration-seconds 120 --poll-hz 480
```

It creates a UTC-named `.accraw` recording and JSON report under `user_data/raw_recordings/`. The report reconciles acquired snapshots against persisted snapshots, acquisition-queue rejects, recorder-queue rejects, failed writes and pending records. A zero delta is required for a clean run, but does not imply that every ACC publication was observed. The expanded 31-test suite passed on Ubuntu and Windows (GitHub Actions run 42492834805), including delayed writes, simulated partial disk-write failure and interrupted-second-block recovery. A real abrupt-stop and physical storage-failure test on the target Windows PC remain outstanding. Do not treat Stage 3 as complete until recovery after an actual process interruption has been reviewed.
