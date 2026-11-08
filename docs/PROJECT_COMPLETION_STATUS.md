# Race Engineer ACC New — Project Completion Status

**Last updated:** 8 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Project phase:** Greenfield acquisition foundation  
**Status:** Stage 2 complete; Stage 3 raw recorder implementation added and validation pending. The selected benchmark operating cadence is 480 Hz polling, yielding approximately 388.5 unique snapshots/s in the 10-minute trial.

This is the project-level status record. Update it whenever a stage reaches a new evidence-backed state. Keep implementation, automated tests, live validation and release readiness as separate claims.

## 1. Executive status

The project is being built from a clean foundation, with reliable telemetry acquisition and data integrity taking priority over UI, coaching and lap analysis.

The current implementation can connect to ACC's Windows Physics shared-memory mapping, copy the raw Physics page and pass the source-independent acquisition tests. A live ACC test confirmed the expected page size and advancing packet IDs.

**The project is not complete.** It currently acquires only the Physics page. Graphics and Static page acquisition, raw recording, crash recovery, recorder-level reconciliation, and downstream application features remain outstanding.

### Current evidence

| Area | Status | Evidence / limitation |
|---|---|---|
| Source-independent acquisition models | Implemented | Immutable raw observation and snapshot models |
| Bounded SPSC buffer | Implemented | FIFO, wraparound and reject-without-overwrite unit tests |
| Physics acquisition loop | Implemented | Injectable source/clock, monotonic timestamps, sequence assignment and retry/accounting metrics |
| Windows ACC Physics adapter | Implemented; live connection verified | Read-only `Local\\acpmf_physics` mapping |
| Automated acquisition tests | Passed locally | User reported 22/22 tests passing on 8 November 2026, including Windows timer-resolution lifecycle tests |
| Live ACC page copy | Passed for a short smoke test | 100 reads; expected and actual page size both 784 bytes; 100 unique packet IDs; one bracketed read was inconsistent |
| Sustained driving acquisition | Controlled sweep and 10-minute soak passed | Three 120-second post-timer trials plus one 600-second 480 Hz trial; all had zero buffer rejects and zero reconciliation delta |
| Polling cadence / CPU baseline | Validated; 480 Hz selected for acquisition polling | 600-second trial: 479.672 polls/s, 233,102 unique snapshots (388.50/s), 4.69% CPU, 54,702 duplicate observations, 6,899 source packet gaps, zero buffer rejects and zero reconciliation delta |
| Graphics and Static acquisition | Not implemented | Current adapter reads Physics only |
| Raw binary recorder | Not implemented | No durable raw recording or recovery guarantee |
| End-of-session reconciliation | Not implemented | Requires recorder and final-drain logic |
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
- [x] Live ACC smoke test: 100 page copies; expected page size 784 bytes matched actual page size 784 bytes.
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

**Status: Implemented — 28/28 automated tests passed on Ubuntu and Windows; live ACC recording validation pending**

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
- [x] Add a three-thread live runner: acquisition, queue dispatcher, and recorder.
- [x] Add final-drain accounting for acquired, persisted, both queue rejection stages, recorder write failures and pending records.
- [x] Run the expanded automated tests in GitHub Actions on Ubuntu and Windows: 28/28 passed on both platforms.
- [ ] Run live ACC recordings at the selected 480 Hz polling cadence.
- [ ] Exercise slow storage, disk-full/write failures and abrupt shutdown on the target Windows PC.

**Stage exit gate:** Automated format/recovery tests have passed on Ubuntu and Windows. Live recordings must still be validated and reconciled after normal and interrupted sessions before Stage 3 is complete.

### Stage 4 — Reliability diagnostics and fault testing

**Status: Not started**

Planned work:
- [ ] Consolidate source, acquisition, buffer and recorder metrics.
- [ ] Expose sequence ranges, queue depth/high-water and explicit failure reasons.
- [ ] Add long-duration soak tests.
- [ ] Inject slow consumers and storage failures.
- [ ] Test shutdown during active acquisition and recording.
- [ ] Verify reconciliation after normal and abnormal termination.

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
- `tests/acquisition/test_recorder.py` — recorder format, recovery and worker tests.
- `tests/acquisition/` — unit tests for buffer, acquirer and Windows source adapter.

The adapter copies the Physics page as raw bytes. It does not decode all Physics fields, read Graphics or Static, record to disk, or feed UI/coaching/lap-analysis consumers.

## 5. Known limitations and decisions

1. ACC shared memory exposes the latest state. Updates overwritten before observation cannot be reconstructed by this reader.
2. A packet-ID gap indicates counter progression between observations; it is not proof of an application ring-buffer drop.
3. Packet-ID bracketing is best-effort consistency validation, not an atomic snapshot guarantee.
4. The direct 100-read live test did not exercise `PhysicsAcquirer` or the ring buffer.
5. The run loop supports configurable monotonic polling. The initial sweep observed approximately 64.5 Hz for all three requested rates. With the benchmark's balanced 1 ms WinMM timer-resolution request, the second sweep achieved 119.999/239.999/479.206 polling cycles/s. A 600-second 480 Hz trial then achieved 479.672 polling cycles/s and accepted 233,102 unique snapshots (388.50/s), with 54,702 duplicate observations rejected and 6,899 source packet gaps. The 480 Hz polling cadence is selected for the next acquisition/recorder stage based on these measurements; ACC's exact publication rate is not guaranteed.
6. The initial queue is SPSC. Multiple consumers require explicit fan-out and independent loss accounting.
7. A raw recorder and recovery implementation now exist, but persistence/recovery guarantees are not claimed until automated and live validation pass.
8. No downstream lap/sector logic, coaching, UI or other application feature should be allowed to compromise the acquisition critical path.

## 6. Latest verified baseline and next action

**Latest Stage 3 implementation update:** the recorder, bounded handoff, checksummed binary format, recovery scanner and live recording runner have been added. GitHub Actions passed all 28 acquisition/recorder tests on Ubuntu and Windows (run 42471304364); live ACC validation remains pending. The acquisition implementation remains on `feature/acquisition-foundation`.  
**Branch:** `feature/acquisition-foundation`

**Latest automated test:** GitHub Actions passed 28/28 tests on both Ubuntu and Windows on 8 November 2026, including recorder writer, recovery, corruption and worker tests. Earlier user-reported baseline was 22/22 locally.

**Latest user-reported live ACC smoke test (Stage 1):**
- Expected Physics page: 784 bytes
- Actual copied page: 784 bytes
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

**Next action:** Validate Stage 3 recorder tests and run a live ACC raw recording. The selected starting cadence remains 480 Hz; the acquisition core is intentionally unchanged by the recorder implementation.

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
