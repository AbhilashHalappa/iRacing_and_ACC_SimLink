# Race Engineer ACC New — Project Completion Status

**Last updated:** 9 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Project phase:** Greenfield acquisition foundation  
**Status:** Physics acquisition and raw-recording layer closed for the current scope. The 800-byte layout is strongly corroborated; live 120-second acquisition/recording, CRC inspection and independent raw-byte cross-check passed. Field-by-field semantic validation remains explicitly qualified. Stage 3 normal recording, forced-termination recovery, checkpoint-assisted recovery, live slow-storage simulation and bounded simulated-ENOSPC fault handling have been exercised. The target-PC slow-storage run persisted 11,800/11,800 samples with zero rejects; the target-PC simulated-ENOSPC run preserved three complete blocks and accounted for 11,780 unpersisted queued samples. Physical disk-full testing was intentionally skipped. The Physics adapter now uses the corroborated 800-byte layout: `current_max_rpm` is int32 at offset 588, `mz[4]` is at offset 592, and later fields use corrected offsets. The final 16 bytes are opaque. Only the 800-byte Physics recording layout is supported; historical 784-byte recordings are not supported by the inspector. No Physics decoder or Static adapter has been added. A separate raw-only Graphics reader/recorder has been implemented; target-PC validation is pending.

This is the project-level status record. Update it whenever a stage reaches a new evidence-backed state. Keep implementation, automated tests, live validation and release readiness as separate claims.

## 1. Executive status

The project is being built from a clean foundation, with reliable telemetry acquisition and data integrity taking priority over UI, coaching and lap analysis.

The Physics path connects to ACC's Windows Physics mapping and copies the validated 800-byte page. A separate Graphics path now reads the Windows Graphics mapping, discovers its allocation size at runtime and copies the complete allocation without decoding or truncating it. Graphics target-PC validation is pending.

**The project is not complete.** Physics acquisition is closed for its defined scope. Raw-only Graphics acquisition and recording are implemented separately, with automated CI passed and target-PC validation pending. Raw Physics recording and recovery of completed CRC-valid blocks are implemented and tested. Checkpoint-assisted abnormal-shutdown estimation has now been exercised twice on the target Windows PC, with zero checkpoint-known samples missing in both runs. The recorder now supports an opt-in simulated write delay and bounded ENOSPC fault injection, both isolated to the recorder thread. The live target-PC slow-storage simulation passed with 11,800/11,800 snapshots persisted and zero rejects; target-PC ENOSPC execution and physical storage-failure testing remain outstanding. Static page acquisition and downstream application features are not yet implemented.

### Current evidence

| Area | Status | Evidence / limitation |
|---|---|---|
| Source-independent acquisition models | Implemented | Immutable raw observation and snapshot models |
| Bounded SPSC buffer | Implemented | FIFO, wraparound and reject-without-overwrite unit tests |
| Physics acquisition loop | Implemented | Injectable source/clock, monotonic timestamps, sequence assignment and retry/accounting metrics |
| Windows ACC Physics adapter | Implemented; live connection verified | Read-only `Local\\acpmf_physics` mapping |
| Automated acquisition tests | Passed locally | User reported 22/22 tests passing on 8 November 2026, including Windows timer-resolution lifecycle tests |
| Live ACC page copy | Passed for a short smoke test | 100 reads; expected and actual page size 800 bytes; 100 unique packet IDs; one bracketed read was inconsistent |
| Sustained driving acquisition | Controlled sweep and 10-minute soak passed | Three 120-second post-timer trials plus one 600-second 480 Hz trial; all had zero buffer rejects and zero reconciliation delta |
| Polling cadence / CPU baseline | Validated; 480 Hz selected for acquisition polling | 600-second trial: 479.672 polls/s, 233,102 unique snapshots (388.50/s), 4.69% CPU, 54,702 duplicate observations, 6,899 source packet gaps, zero buffer rejects and zero reconciliation delta |
| Graphics raw-only acquisition and recording | Implemented — CI passed; target-PC validation pending | Separate read-only mapping adapter copies the complete reported Graphics allocation; separate CRC-block writer, recovery path and automated tests added. No Graphics field decoder is used. |
| Static acquisition | Not implemented | Separate future page; not merged with Physics or Graphics |
| Raw binary recorder | Implemented; normal live run and abrupt-stop recovery passed | Normal 120-second ACC run: 46,924 acquired/persisted, zero rejects/failures/pending, reconciliation delta 0. Forced termination after about 30 seconds: 11,938 snapshots in 11,517 CRC-valid blocks recovered; zero invalid/trailing bytes; no truncation needed. Abnormal-run queue reconciliation is unavailable because the process was killed before writing its report |
| End-of-session reconciliation | Normal shutdown passed; checkpoint-based abnormal-shutdown visibility implemented and exercised twice on target PC | A separate 1-second checkpoint records acquired/persisted counts, queue depths/rejections, dispatcher and recorder in-flight work. Recovery reports a minimum of checkpoint-known snapshots not recovered; it cannot include captures made after the final checkpoint |
| Desktop UI, coaching and analysis | Deferred | Deliberately outside the current acquisition-first milestone |

## 2. Stage-by-stage completion

Status meanings:
- **Complete:** implementation and required validation evidence for that stage are satisfied.
- **Implemented — validation pending:** code exists, but the stage's acceptance evidence is incomplete.
- **In progress:** work is underway and the stage is not yet at its acceptance gate.
- **Not started:** no implementation is claimed.

### Stage 0 — Project foundation and engineering contract


**Status: Complete**

- [x] Dedicated greenfield acquisition branch established from `feature/overview-hardware-migration`.
- [x] Acquisition-first scope documented.
- [x] ACC Shared Memory treated correctly as a latest-state interface, not a guaranteed delivery queue.
- [x] Source packet progression distinguished from application buffer loss.
- [x] No zero-source-loss guarantee is made.
- [x] Acquisition critical path kept separate from decoding, UI, coaching, database and disk I/O.
- [x] Python-first implementation policy established; native code requires profiling evidence.

**Acceptance:** Project scope and data-integrity constraints are documented and used to guide implementation.

### Stage 1 — Physics acquisition core and Windows source adapter

**Status: Implemented — controlled cadence sweep and 10-minute live validation passed**

- [x] Immutable raw acquisition data models.
- [x] Preallocated bounded SPSC ring buffer.
- [x] FIFO and wraparound behavior.
- [x] No overwrite of unread samples.
- [x] Non-blocking producer insertion and explicit rejection accounting.
- [x] Injectable acquisition source and clock.
- [x] Monotonic read timestamps and capture sequence assignment.
- [x] Packet-ID gap, duplicate and regression accounting.
- [x] Snapshot consistency retries.
- [x] Windows read-only ACC Physics shared-memory adapter.
- [x] Physics page layout transcribed from the audited decoder source.
- [x] Expanded automated acquisition tests: 22/22 passed in the user's local run on 8 November 2026.
- [x] Live ACC smoke test: 100 page copies; the earlier 784-byte adapter smoke test predates the corrected 800-byte ABI.
- [x] Live ACC smoke test observed 100 unique packet IDs, advancing from 4066 to 6320.
- [x] One of 100 bracketed reads observed a packet-ID change during copying; this confirms why consistency retry handling is required.
- [ ] Validate packet-ID field atomicity and consistency behavior more thoroughly on the target Windows environment.
- [x] Exercise the actual `PhysicsAcquirer` and ring buffer together during six 120-second live ACC benchmark trials.
- [x] Confirm zero application buffer rejections and zero reconciliation delta in all six trials; quantify source packet gaps under driving load.
- [x] Establish measured polling cadence, unique accepted snapshot rate, CPU use, duplicate observations and buffer high-water behavior before and after the timer-resolution change.

**Interpretation of the live test:** It proves that the Windows process can open the ACC Physics mapping, copy a page of the expected size and observe packet-ID progression. It does not prove that every ACC publication was observed, that the full acquisition pipeline is loss-free, or that sustained recording works.

**Stage exit gate:** A controlled sustained live test of the acquirer plus buffer, with documented cadence, retries, source packet gaps, buffer rejects, occupancy/high-water and CPU impact. Any losses must be explicitly accounted for.

### Stage 2 — Sustained acquisition measurement and cadence baseline

**Status: Complete — expanded tests, 120/240/480 Hz controlled sweep, 10-minute 480 Hz validation and operating cadence selection completed**

Implemented in this stage:
- [x] Add configurable monotonic polling intervals to `PhysicsAcquirer.run()`; zero retains explicit maximum-throughput mode, positive intervals use deadline-based waiting.
- [x] Skip missed deadlines instead of issuing catch-up bursts.
- [x] Measure poll start-to-start intervals separately from individual shared-memory read durations.
- [x] Record schedule lateness and missed polling deadlines.
- [x] Expose ring-buffer high-water mark and separate full-buffer rejections from lock-contention rejections.
- [x] Add a live Windows benchmark harness exercising the actual adapter, acquirer, SPSC buffer and a separate draining consumer.
- [x] Write benchmark JSON only after acquisition stops, outside the acquisition thread.
- [x] Include acquired/consumed/rejected/pending reconciliation in the report.
- [x] Run the expanded automated acquisition test suite: 22/22 passed in the user's local run.
- [x] Run target-PC live trials at 120, 240 and 480 requested Hz for 120 seconds each under comparable ACC driving conditions.
- [x] Review initial cadence, source packet gaps, retries, buffer rejects/high-water, CPU impact and final reconciliation.
- [x] Add a balanced 1 ms Windows timer-resolution request around benchmark trials.
- [x] Repeat the 120/240/480 Hz cadence sweep with the timer-resolution request active.
- [x] Confirm zero application buffer rejections and zero reconciliation delta in all three post-change trials.
- [x] Run a 600-second live validation at 480 Hz with the 1 ms timer-resolution request active.
- [x] Select 480 Hz as the benchmark operating polling cadence based on the measured unique snapshot rate, source packet gaps, duplicate observations and CPU cost. This is an evidence-backed project setting, not a guarantee of ACC publication frequency.

**Stage exit gate: Passed.** The 600-second 480 Hz live run documented polling cadence, unique accepted snapshots, source packet gaps, duplicate observations, consistency retries, CPU cost and application-level reconciliation. A zero application reconciliation delta does not mean every ACC publication was observed.

### Stage 3 — Independent raw persistence

**Status: Implemented and target-PC exercised — normal recording, abrupt-stop recovery, checkpoint recovery, slow-storage backlog/drain and simulated ENOSPC accounting passed; physical disk-full testing intentionally skipped**

Implemented:
- [x] Add a separate recorder worker; the acquisition loop does not perform disk I/O.
- [x] Add a second bounded SPSC recorder handoff queue, independent of the acquisition queue.
- [x] Add explicit full-buffer and lock-contention rejection accounting through the existing queue metrics.
- [x] Persist append-only binary blocks in configurable batches.
- [x] Preserve capture sequence, ACC packet ID, read-start/read-complete/capture monotonic timestamps, and block sequence.
- [x] Add per-block CRC32 integrity checks and a versioned file header with header checksum.
- [x] Flush and fsync the file header and each completed block.
- [x] Recover valid sequential blocks and truncate an incomplete or corrupt trailing block.
- [x] Generate UTC-timestamped recording filenames and retain UTC creation time in the file header.
- [x] Add a four-thread live runner: acquisition, queue dispatcher, recorder, and independent periodic checkpoint worker.
- [x] Add final-drain accounting for acquired, persisted, both queue rejection stages, recorder write failures and pending records.
- [x] Run the expanded automated tests in GitHub Actions on Ubuntu and Windows: 31/31 passed on both platforms (run 42492834805).
- [x] Run a live ACC recording at the selected 480 Hz polling cadence for 120 seconds: 46,924 acquired and persisted, zero rejects/failures/pending, reconciliation delta 0, 12.04% CPU of one core.
- [x] Add automated fault-injection coverage for delayed storage, a simulated disk-full partial block write, and recovery after an interrupted second block.
- [x] Add `scripts/recover_acc_recording.py` to inspect and recover `.accraw` files after interrupted runs.
- [x] Confirm the expanded fault-injection tests pass on Ubuntu and Windows in GitHub Actions (run 42492834805).
- [x] Force-terminate a live recording process on the target Windows PC after approximately 30 seconds; recover 11,938 snapshots across 11,517 CRC-valid blocks with zero invalid/trailing bytes and no truncation.
- [x] Add a separate periodic checkpoint worker (1-second default) with checksummed JSON, fsync and atomic replacement.
- [x] Include acquired/persisted sequence positions, queue depths and losses, dispatcher handoff state, recorder in-flight batch range and a sampled accounting delta in each checkpoint.
- [x] Extend recovery reporting to validate the sidecar and estimate the minimum number of checkpoint-known snapshots not recovered.
- [x] Add checkpoint checksum/atomic-replacement, checkpoint write-failure retention and recorder in-flight tests; checkpoint/recorder tests passed on Windows and Ubuntu; the latest full workflow (run 42497405943) also compiled the operational scripts and passed the complete suite, including the new slow-storage simulation tests.
- [ ] Validate checkpoint sidecar and loss estimate in a new forced-termination run on the target Windows PC.
- [ ] Exercise real slow storage and physical disk-full/write failures on the target Windows PC.
- [ ] Quantify queued/in-flight samples lost during abnormal termination; the forced-kill run cannot produce a final reconciliation report.

**Stage exit gate:** A normal live ACC recording has passed with zero unexplained reconciliation delta. The new automated fault-injection tests must pass on Ubuntu and Windows, and a real interrupted-session test must preserve complete blocks and account for the unpersisted tail before Stage 3 is complete.

### Stage 4 — Reliability diagnostics and fault testing

**Status: In progress — automated fault injection, two checkpoint-assisted abrupt-process recovery runs, live slow-storage simulation and live simulated-ENOSPC accounting validated**

Planned work:
- [x] Add automated delayed-storage, partial-write/disk-full and interrupted-block recovery tests.
- [ ] Consolidate source, acquisition, buffer and recorder metrics.
- [ ] Expose sequence ranges, queue depth/high-water and explicit failure reasons.
- [ ] Add long-duration soak tests.
- [ ] Inject slow consumers and storage failures.
- [x] Test forced process termination during active acquisition and recording; verify recovery of completed blocks.
- [x] Verify recovery scanner accepts complete blocks and reports invalid/trailing bytes after abrupt termination (this run had none).
- [x] Implement periodic durable checkpoints exposing queued/in-flight counts and sequence ranges for abnormal-shutdown analysis.
- [x] Validate checkpoint-assisted forced termination twice on the target Windows PC; both runs recovered every checkpoint-persisted sample and reported zero checkpoint-known samples missing.
- [x] Add an opt-in simulated write delay on the recorder thread, plus timing metrics and automated queue-drain tests; default behavior remains unchanged.
- [x] Validate checkpoint-based loss estimates against two forced-termination runs; both reported zero checkpoint-known samples missing. Captures after the last checkpoint remain outside the estimate.
- [x] Run the controlled `--simulated-write-delay-ms 500` live ACC test on the target PC: 11,800 acquired/persisted, recorder queue high-water 4,247, zero rejects/failures, pending 0 and reconciliation delta 0.
- [x] Implement bounded `--simulate-disk-full-after-batches N` ENOSPC fault injection and automated tests for complete-block preservation, failed-batch accounting, queued-sample visibility and tail recovery.
- [x] Run the target-PC simulated-ENOSPC test: three complete blocks recovered; 11,780 queued samples remained unpersisted and were identified by checkpoint accounting; reconciliation delta 0.
- [x] Confirm recovery reports checkpoint-persisted samples missing = 0 and minimum checkpoint-known samples not recovered = 11,780 for this injected failure.
- [x] Record that physical disk-full testing was intentionally skipped by user decision; it is not a remaining acceptance gate for this phase.

**Stage exit gate:** Failure modes are observable, reproducible and correctly accounted for; sustained sessions complete without unexplained data loss.

### Stage 5 — Performance optimization and acquisition sign-off

**Status: Not started**

Planned work:
- [ ] Profile the complete acquisition and recording path.
- [ ] Optimize only measured bottlenecks.
- [ ] Decide whether faster polling, process isolation or native C++/Rust code is justified.
- [ ] Repeat live and fault-injection tests after optimization.
- [ ] Publish acquisition performance and integrity limits.

**Stage exit gate:** Acquisition and persistence meet documented performance/reliability targets, with evidence. Native implementation is optional and must be justified by measurements.

## 3. ACC data coverage

A structural inventory of all 82 named Physics fields, including byte offsets, C types, sizes, raw-preservation status, reference-decoder exposure and unused/deprecated naming, is maintained in [ACC Physics Field Coverage Audit](ACC_PHYSICS_FIELD_COVERAGE_AUDIT.md). The inventory documents the corrected 800-byte structure. Automated regression tests now lock all 82 named field names, types, array lengths, offsets and sizes, plus the total structure size and contiguous layout; CI execution for the new tests is pending. Representative field values have been validated live; unresolved fields remain individually marked. The corrected offsets are regression-locked, with an official Kunos v1.9 header still unavailable. This audit does not add a decoder.


| ACC shared-memory page | Current state |
|---|---|
| Physics | Windows adapter implemented; short live page-copy smoke test passed |
| Graphics | Not implemented |
| Static | Not implemented |

Therefore, **the application is not yet reading all data exposed by ACC**. The current live validation applies only to the Physics page. Additional page adapters must be implemented and validated independently, with their own layout provenance and consistency rules.

## 4. Current implementation boundary

Current package: `src/race_engineer_acquisition/`

- `models.py` — immutable raw read/snapshot/loss models.
- `ring_buffer.py` — bounded SPSC buffer.
- `acquirer.py` — source-independent Physics acquisition orchestration and metrics.
- `acc_windows.py` — Windows ACC Physics shared-memory adapter.
- `recorder.py` — separate raw recorder worker, checksummed blocks and recovery.
- `scripts/record_acc_physics.py` — live acquisition/dispatch/recording runner.
- `scripts/recover_acc_recording.py` — inspect and recover complete blocks after an interrupted recording.
- `tests/acquisition/test_recorder.py` — recorder format, recovery and worker tests.
- `tests/acquisition/` — unit tests for buffer, acquirer and Windows source adapter.

The adapter copies the complete 800-byte Physics page as raw bytes; the 16-byte tail is opaque. It does not decode all Physics fields, read Graphics or Static, record to disk, or feed UI/coaching/lap-analysis consumers.

## 5. Known limitations and decisions

1. ACC shared memory exposes the latest state. Updates overwritten before observation cannot be reconstructed by this reader.
2. A packet-ID gap indicates counter progression between observations; it is not proof of an application ring-buffer drop.
3. Packet-ID bracketing is best-effort consistency validation, not an atomic snapshot guarantee.
4. The direct 100-read live test did not exercise `PhysicsAcquirer` or the ring buffer.
5. The run loop supports configurable monotonic polling. The initial sweep observed approximately 64.5 Hz for all three requested rates. With the benchmark's balanced 1 ms WinMM timer-resolution request, the second sweep achieved 119.999/239.999/479.206 polling cycles/s. A 600-second 480 Hz trial then achieved 479.672 polling cycles/s and accepted 233,102 unique snapshots (388.50/s), with 54,702 duplicate observations rejected and 6,899 source packet gaps. The 480 Hz polling cadence is selected for the next acquisition/recorder stage based on these measurements; ACC's exact publication rate is not guaranteed.
6. The initial queue is SPSC. Multiple consumers require explicit fan-out and independent loss accounting.
7. Normal raw recording and automated fault-injection tests have passed; guarantees for real power loss, process termination and physical storage failure are not claimed until target-PC validation passes.
8. No downstream lap/sector logic, coaching, UI or other application feature should be allowed to compromise the acquisition critical path.

## 6. Latest verified baseline and next action

**Latest Stage 3 implementation update:** normal live ACC recording passed for 120 seconds at 480 Hz: 46,924 acquired and persisted, zero acquisition/recorder queue rejects, zero write failures, zero pending records, zero reconciliation delta and 12.04% CPU of one core. A real forced-process-termination test recovered 11,938 snapshots across 11,517 valid blocks; invalid/trailing bytes were 0 and no truncation was required. New atomic periodic checkpoints now expose acquired/persisted sequence positions, both queue depths and rejection ranges, dispatcher state, recorder in-flight batch state and sampled accounting delta. The latest CI run 42497405943 passed operational-script compilation and the complete acquisition/recorder suite on both Windows and Ubuntu. The checkpoint implementation has not yet been exercised in a target-PC forced-stop run. The acquisition implementation remains on `feature/acquisition-foundation`.  
**Branch:** `feature/acquisition-foundation`

**Latest automated test:** GitHub Actions run 42497405943 passed the operational-script compilation step and complete acquisition/recorder unit-test suite on both Windows and Ubuntu on 8 November 2026. The suite includes delayed-storage, simulated disk-full partial-write, interrupted-block recovery, checkpoint checksum/atomic-replacement, checkpoint write-failure retention, recorder in-flight visibility and slow-storage simulation tests. The earlier 31-test baseline was run 42492834805.

**Latest user-reported live ACC smoke test (Stage 1):**
- Expected Physics page: 800 bytes
- Actual copied page: 800 bytes
- Reads: 100
- Consistent bracketed reads: 99
- Unique packet IDs: 100
- First/last packet IDs: 4066 / 6320
- Packet ID advanced: yes

**Latest live Stage 2 validation (user-reported, 8 November 2026; 600-second 480 Hz trial):**

| Requested cadence | Observed polling cadence | Unique acquired | Consumed | CPU (one core) | Inconsistent reads | Duplicates rejected | Source packet gaps | Buffer rejects | High-water | Pending | Reconciliation delta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 480 Hz | 479.672 Hz | 233,102 | 233,102 | 4.69% | 1,278 | 54,702 | 6,899 | 0 | 2 | 0 | 0 |

The 10-minute run had no producer errors, no buffer rejections, no pending records after drain and zero reconciliation delta. It supports 480 Hz as the project's selected polling cadence for the next stage. The 388.50 unique snapshots/s is the accepted snapshot rate; do not confuse it with the 479.67 polling rate.

**Supporting 120-second post-timer sweep (user-reported):**

| Requested cadence | Observed cadence | Acquired | Consumed | CPU (one core) | Inconsistent reads | Duplicates | Buffer rejects | High-water | Reconciliation delta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 120 Hz | 64.47 Hz | 7,738 | 7,738 | 2.33% | 65 | 0 | 0 | 1 | 0 |
| 240 Hz | 64.52 Hz | 7,742 | 7,742 | 2.02% | 56 | 2 | 0 | 1 | 0 |
| 480 Hz | 64.53 Hz | 7,738 | 7,738 | 2.71% | 70 | 7 | 0 | 2 | 0 |

All three application-level reconciliations passed. The nearly fixed 15.5 ms average interval, despite changing requested cadence, points to a Windows wait/timer-resolution limitation; it is a hypothesis to test, not yet a proven diagnosis. Source packet gaps were 40,509 / 40,822 / 40,655 respectively and remain distinct from application buffer losses.

**Next action:** Run the safe 30-second target-PC ENOSPC simulation documented in README with `--simulate-disk-full-after-batches 3`; verify complete blocks, failed batch, queued samples and recovery using the checkpoint sidecar. Only after that consider physical storage-failure testing on a dedicated non-system test volume. The previous forced-stop recovery test recovered 11,938 snapshots in 11,517 valid blocks, with zero invalid/trailing bytes and no truncation. The selected polling cadence remains 480 Hz; the acquisition critical path remains unchanged.

## 7. Stage 2 implementation details

- `PhysicsAcquirer.run(stop_event, poll_interval_ns=...)` now supports an explicit target cadence. It uses monotonic deadlines and skips missed slots rather than trying to catch up in a burst.
- Poll intervals are measured between acquisition cycles, not between consistency retries. Read-attempt duration remains a separate metric.
- The SPSC buffer reports high-water mark, full-buffer rejects, lock-contention rejects and total rejected snapshots independently.
- `timing_windows.py` balances a WinMM 1 ms timer-resolution request for the duration of the live benchmark; the request is released after the trial and is not a guarantee of exact wake-up timing.
- The user's post-change 120-second live sweep measured 119.999/239.999/479.206 polling cycles/s at requested 120/240/480 Hz. The follow-up 600-second 480 Hz validation measured 479.672 polling cycles/s, 233,102 unique snapshots (388.50/s), 54,702 duplicates, 6,899 source packet gaps, 1,278 inconsistent reads/retries, 4.69% CPU and zero application buffer rejects or reconciliation delta.
- `scripts/benchmark_acc_physics.py` runs the real Windows source/acquirer/buffer path with a separate consumer thread and writes a timestamped JSON report after stopping.
- Benchmark rates 120/240/480 Hz are exploratory comparison points only. The live measurements, not these requested values, determine the later operating target.

## 8. Update policy

Update this document at every stage boundary and whenever a material validation result changes the project status.

For each update:
1. Change the last-updated date and stage status.
2. Mark implementation tasks only when code exists.
3. Mark tests only when their result is observed.
4. Record live test conditions and measured results separately from unit tests.
5. Preserve known limitations and unresolved failures.
6. Record the relevant commit SHA.
7. Update the README's current status/next gate if the project phase materially changes.

Never mark a stage complete solely because its code has been written.


## Physics acquisition layer closure — 9 November 2026

**Status: CLOSED for the defined Physics acquisition and raw-recording scope.**

The target-PC 120-second recording at requested 480 Hz completed with an 800-byte payload and the following final accounting:

| Metric | Result |
|---|---:|
| Acquired snapshots | 46,717 |
| Persisted snapshots | 46,717 |
| Acquisition rejects | 0 |
| Recorder queue rejects | 0 |
| Recorder write failures | 0 |
| Pending records | 0 |
| Reconciliation delta | 0 |
| Checkpoint writes / failures | 121 / 0 |
| Recorder queue high-water | 2 |
| Maximum persist/block-write duration | 3.9 ms |
| CPU (one core) | 13.84% |

Offline inspection covered all 46,717 snapshots (212 components: 135 varying, 77 constant). An independent parser checked recording block CRCs and decoded 16 selected fields directly from raw bytes using explicit offsets/types. All 16 raw min/max results matched the inspector CSV; 45,253 valid blocks were checked. This validates recording integrity and the selected raw-to-inspector comparisons, not the complete semantic meaning of all 82 fields.

Physics offsets 672 and 676 are intervention indicators (`tc_in_action` and `abs_in_action`), not selected setup levels. They remained zero in this capture.

**Closure limits:** no claim that every Physics field has fully validated semantics or calibrated units; no claim of official Kunos header confirmation; no source-level zero-loss guarantee. The 800-byte Physics layout is the only supported recording layout.

**Scope freeze:** Physics remains a standalone page and layer. Do not add Graphics or Static fields/readers, do not merge page structures, and do not change the Physics layout as part of subsequent Graphics work. Graphics and Static acquisition remain unimplemented and outside this closure.


## Graphics structure reference cross-check — 9 November 2026

**Status: Stage 5.1 reference comparison completed; target Shared Memory 1.9 ABI remains not signed off.**

The existing Graphics investigation, read-only probe, 18,000-sample full-mapping recording and field-coverage audit were reviewed. RaceIQ and Pro Engineer were then inspected directly at pinned revisions. Both declare `Local\\acpmf_graphics` as 1,588 bytes. RaceIQ's 44 explicit offset descriptors align with the corresponding Pro Engineer members; Pro Engineer provides the complete 87-field sequence through offset 1584. RaceIQ's offset map stops at offset 1488 and its 1,320-byte parser minimum is legacy compatibility only.

The existing target capture preserves the full 4,096-byte mapping allocation; the final 2,508 bytes were observed zero throughout the 18,000 samples. Keep those bytes in raw capture as opaque tail; do not reinterpret them as extra fields. The first 1,588 bytes remain a strongly corroborated candidate logical structure, not official Kunos Shared Memory 1.9 confirmation.

No production Graphics reader, decoder, recorder or Physics change was made in this reference cross-check. That was the next gate at the time of the reference comparison; it is superseded by the raw-only implementation recorded below. The remaining gate is automated CI and target-PC validation of that implementation. Do not repeat already-confirmed lap/sector/validity tests or create a new capture unless a specific unresolved field requires a controlled event.


## Graphics raw-only acquisition implementation — 9 November 2026

**Status: Implemented — automated CI passed; target-PC validation pending.**

A dedicated `src/race_engineer_acquisition/graphics.py` module and `scripts/record_acc_graphics.py` runner have been added. The Graphics source opens `Local\\acpmf_graphics` read-only, queries the mapping allocation size, and copies the entire allocation. It checks the packet ID before the copy, in the copied bytes and after the copy as a best-effort consistency check. Every consistent poll is published and recorded, including repeated packet IDs; duplicate IDs are counted but not filtered out. Inconsistent reads are retried; packet gaps/regressions and buffer rejects are counted.

Graphics uses its own immutable snapshot type, acquisition metrics, recorder magic/schema, CRC-protected blocks, recovery function, queues and checkpoint report. It reuses only the generic bounded ring buffer and checkpoint worker. The candidate 1,588-byte struct is not imported or used by the acquisition/recording path. The current 4,096-byte mapping allocation is therefore preserved in full, including the opaque 2,508-byte tail. No Physics source, structure, recorder, tests or file format were changed.

Two new test modules cover retry/duplicate/gap accounting, complete payload retention, CRC recovery, page-size enforcement and recorder queue draining. GitHub Actions run 42598727306 passed 60/60 acquisition tests on Ubuntu and 60/60 on Windows; the workflow also compiled the new Graphics runner. The runner is currently standalone and is not yet wired into normal application startup. Target-PC live execution remains required before this stage can be marked validated.
