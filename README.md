# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building and validating the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current project status

**As of 8 November 2026:** the source-independent Physics acquisition core and Windows ACC Physics shared-memory adapter are implemented. The expanded acquisition/recorder suite, including checkpoint integrity and in-flight tests, passed in GitHub Actions on both Ubuntu and Windows (run 42497405943); the same workflow also compiles the operational scripts. A short live ACC smoke test copied 100 Physics pages of the expected 800-byte size and observed 100 unique, advancing packet IDs. The initial 120/240/480 Hz sweep was limited to approximately 64.5 Hz by ordinary Windows wait timing. The benchmark now requests a balanced 1 ms WinMM timer resolution by default. A second 120/240/480 Hz live sweep achieved 119.999/239.999/479.206 polling cycles per second, with zero application buffer rejections and zero reconciliation delta in every trial. At 480 Hz, 46,851 unique snapshots were accepted in 120 seconds (about 390.4/s), with 10,655 duplicate observations rejected and 1,703 source packet gaps. The observed unique-snapshot rate suggests the ACC Physics page was publishing at roughly 400 Hz under these conditions; this is an estimate, not a guaranteed ACC specification.

Stage 2 acquisition measurement is complete. A 10-minute 480 Hz live run achieved 479.672 polling cycles/s and accepted 233,102 unique snapshots (388.50/s), with 4.69% CPU, zero buffer rejections and zero reconciliation delta. A 120-second live raw-recording run at 480 Hz then acquired and persisted 46,924 snapshots, with zero queue rejects, write failures or pending records, zero reconciliation delta and 12.04% CPU of one core. The expanded acquisition/recorder suite passed on Windows and Ubuntu, including delayed writes, simulated partial disk-write failure, interrupted-block recovery, checkpoint integrity and the new slow-storage simulation tests. A real forced-process-termination recovery test passed before checkpointing was added. Checkpoint-assisted forced termination has now passed twice on the target Windows PC, each with zero checkpoint-known samples missing. The target-PC slow-storage simulation passed with 11,800/11,800 snapshots persisted, zero rejects and a 4,247-sample recorder-queue high-water mark. The target-PC simulated-ENOSPC test preserved three complete blocks and reported 11,780 unpersisted queued samples; physical disk-full testing was intentionally skipped. Graphics and Static page acquisition remain unimplemented.


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

## Physics field coverage audit

The complete 82-field, 800-byte structural inventory is documented in [docs/ACC_PHYSICS_FIELD_COVERAGE_AUDIT.md](docs/ACC_PHYSICS_FIELD_COVERAGE_AUDIT.md). It records offsets, types, sizes, whether raw recording preserves each field, whether the reference decoder exposes it, and unused/deprecated naming. The reference decoder exposes 53 output keys; two (`wheel_load` and `tyre_dirty`) are returned as `None`, while the remaining fields are not exposed. Automated regression tests now lock the 82-field layout; CI is pending. Individual live values have not yet been validated. The high-priority acquisition loop remains raw-only; decoder implementation is explicitly deferred. A future live decoder must use its own independent handoff buffer rather than competing with the recorder's SPSC queue.

## Next gate

The expanded acquisition tests, cadence sweep and 10-minute 480 Hz acquisition validation are complete. The independent raw recorder also passed a 120-second live run: 46,924 acquired/persisted, zero queue rejects, zero write failures, zero pending records and reconciliation delta 0. The abrupt-stop recovery test has passed on Windows: 11,938 snapshots across 11,517 valid blocks recovered, with zero invalid/trailing bytes and no truncation. The target-PC slow-storage simulation has passed with 11,800/11,800 snapshots persisted and zero rejects. The next gate is Physics field coverage: cross-check the 84-field inventory against the authoritative ACC specification, run the new layout regression tests on Windows and Ubuntu, then validate representative fields during controlled live ACC states. No decoder is being added yet. The two checkpointed forced-stop tests found zero checkpoint-known samples missing; total loss after the final checkpoint remains unquantified.

See:
- [Project Completion Status](docs/PROJECT_COMPLETION_STATUS.md)
- [Acquisition and Data Integrity Decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md)

## Stage 3 — Raw Physics recording (abrupt-stop recovery passed; physical storage-failure validation pending)

The raw recorder is implemented in `src/race_engineer_acquisition/recorder.py`. It consumes a dedicated bounded queue on a separate thread; the acquisition loop remains free of file I/O. Recordings use a versioned binary header and append-only blocks containing capture sequence, ACC packet ID, monotonic timestamps and raw Physics bytes. Each block has a CRC32 checksum. The writer flushes and fsyncs completed blocks. Recovery scans sequential complete blocks and can truncate a corrupt or incomplete trailing block. A separate checkpoint worker writes a checksummed JSON sidecar every second by default using fsync plus atomic replacement; it records acquisition progress, persisted sequence, both queue depths/loss counters, dispatcher state and recorder in-flight batch state.

A live runner uses four independent threads: Physics acquisition, queue dispatch, raw recording and periodic checkpointing:

```powershell
$env:PYTHONPATH = "src"
python scripts/record_acc_physics.py --duration-seconds 120 --poll-hz 480 --checkpoint-interval-seconds 1
```

It creates a UTC-named `.accraw` recording, final `.json` report and `.checkpoint.json` sidecar under `user_data/raw_recordings/`. The checkpoint interval can be changed with `--checkpoint-interval-seconds` (default `1`). For controlled slow-storage testing, `--simulated-write-delay-ms` inserts a delay before each recorder batch write on the recorder thread only (default `0`, so normal operation is unchanged). The final report reconciles acquired snapshots against persisted snapshots, acquisition-queue rejects, recorder-queue rejects, failed writes and pending records. The checkpoint runs independently and does not add disk I/O to the acquisition thread. A zero delta is required for a clean run, but does not imply that every ACC publication was observed. The optional delay is a deterministic throughput stressor, not a physical disk benchmark. Start with a 30-second run at 480 Hz and a 500 ms delay per batch:

```powershell
$env:PYTHONPATH = "src"
python scripts/record_acc_physics.py --duration-seconds 30 --poll-hz 480 --checkpoint-interval-seconds 1 --simulated-write-delay-ms 500
```

With the observed input rate near 390 unique snapshots/s and 128 records per batch, this delay intentionally limits the simulated recorder to roughly 256 snapshots/s before real disk-write time. The recorder queue should build during capture and then drain during graceful shutdown. Review recorder-queue high-water, maximum persist duration, total injected delay, final pending count, rejects, persisted count and reconciliation. This is not a physical disk-full test and does not modify the acquisition loop. A bounded ENOSPC fault can also be injected after a chosen number of complete blocks using `--simulate-disk-full-after-batches N`. It writes only a short incomplete block prefix to the test recording and raises the standard no-space-left errno on the recorder thread; it never fills a drive. For example, after pulling the latest changes, run:

```powershell
$env:PYTHONPATH = "src"
python scripts/record_acc_physics.py --duration-seconds 30 --poll-hz 480 --checkpoint-interval-seconds 1 --simulate-disk-full-after-batches 3
```

This test is expected to finish with **Status: failed** and a non-zero process exit because the injected disk-full condition is intentional. It should report the simulated failure, preserve the three complete blocks, account for the failed batch and remaining recorder queue, and recover/truncate only the incomplete trailing block. Then inspect the checkpoint sidecar with `python scripts/recover_acc_recording.py <recording-path>`. It validates application handling of ENOSPC but is not a substitute for a real storage device failure. The acquisition/recorder suite passed on Ubuntu and Windows (GitHub Actions run 42497405943), including delayed writes, simulated partial disk-write failure, interrupted-block recovery, checkpoint checksum/atomic replacement and in-flight accounting.

For a controlled abrupt-stop test on Windows, use a separate PowerShell window and intentionally terminate a 10-minute recording after about 30 seconds. This test discards queued/in-flight data by design; it checks that already completed blocks survive and that the incomplete tail can be recovered:

```powershell
$env:PYTHONPATH = "src"
$startedAt = Get-Date
$recordingProcess = Start-Process -FilePath python -ArgumentList @(
    "scripts/record_acc_physics.py",
    "--duration-seconds", "600",
    "--poll-hz", "480",
    "--checkpoint-interval-seconds", "1"
) -PassThru -NoNewWindow

Start-Sleep -Seconds 30
Stop-Process -Id $recordingProcess.Id -Force
Start-Sleep -Seconds 1

$recording = Get-ChildItem "user_data/raw_recordings/*.accraw" |
    Where-Object { $_.LastWriteTime -ge $startedAt } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $recording) { throw "No recording file was created for the interrupted test." }

python scripts/recover_acc_recording.py $recording.FullName
```

The recovery utility preserves complete sequential CRC-valid blocks and truncates only an incomplete/corrupt tail. Use `--no-truncate` first if you want a read-only inspection. It automatically looks for the matching `.checkpoint.json` sidecar and reports the last checkpoint's acquired/persisted sequences, queue depths, in-flight work, checkpoint accounting delta, and a minimum count of checkpoint-known snapshots not recovered. Share the recovery output; do not delete the test recording or checkpoint until they have been reviewed. The real forced-termination recovery test passed: 11,938 snapshots were recovered from 11,517 complete blocks; the scanner reported 0 invalid/trailing bytes and did not truncate the file. Because the process was killed before finalization, this test does not quantify queued/in-flight samples lost at termination. A physical disk-full/slow-storage test remains outstanding. The checkpoint is a periodic point-in-time snapshot, not an exact accounting of captures made after the last checkpoint; the reported unrecovered count is a minimum for checkpoint-known work, and total crash loss can be higher. Do not treat Stage 3 as complete until the target-PC slow-storage simulation and physical storage-failure behavior are validated.
