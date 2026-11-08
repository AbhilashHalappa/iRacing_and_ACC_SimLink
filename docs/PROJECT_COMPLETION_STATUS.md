# Race Engineer ACC New — Project Completion Status

**Last updated:** 8 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Project phase:** Greenfield acquisition foundation  
**Status:** Stage 2 implementation started — controlled polling and a live benchmark harness are committed; target-PC cadence sweep is pending.

This is the project-level status record. Update it whenever a stage reaches a new evidence-backed state. Keep implementation, automated tests, live validation and release readiness as separate claims.

## 1. Executive status

The project is being built from a clean foundation, with reliable telemetry acquisition and data integrity taking priority over UI, coaching and lap analysis.

The current implementation can connect to ACC's Windows Physics shared-memory mapping, copy the raw Physics page and pass the source-independent acquisition tests. A live ACC test confirmed the expected page size and advancing packet IDs.

**The project is not complete.** It currently acquires only the Physics page. Graphics and Static page acquisition, sustained end-to-end acquisition measurement, raw recording, crash recovery, reconciliation, and downstream application features remain outstanding.

### Current evidence

| Area | Status | Evidence / limitation |
|---|---|---|
| Source-independent acquisition models | Implemented | Immutable raw observation and snapshot models |
| Bounded SPSC buffer | Implemented | FIFO, wraparound and reject-without-overwrite unit tests |
| Physics acquisition loop | Implemented | Injectable source/clock, monotonic timestamps, sequence assignment and retry/accounting metrics |
| Windows ACC Physics adapter | Implemented; live connection verified | Read-only `Local\\acpmf_physics` mapping |
| Automated acquisition tests | Passed | User-reported result: 13/13 tests passed using the documented unittest command |
| Live ACC page copy | Passed for a short smoke test | 100 reads; expected and actual page size both 784 bytes; 100 unique packet IDs; one bracketed read was inconsistent |
| Sustained driving acquisition | Not yet validated | Stage 2 live benchmark harness is ready; no target-PC run has yet been reported |
| Polling cadence / CPU baseline | Instrumentation implemented; baseline pending | Configurable monotonic cadence and benchmark reporting are implemented; live measurements are still required |
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

**Status: Implemented — live and sustained validation pending**

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
- [x] Automated tests: 13/13 passed in the user's local run.
- [x] Live ACC smoke test: 100 page copies; expected page size 784 bytes matched actual page size 784 bytes.
- [x] Live ACC smoke test observed 100 unique packet IDs, advancing from 4066 to 6320.
- [x] One of 100 bracketed reads observed a packet-ID change during copying; this confirms why consistency retry handling is required.
- [ ] Validate packet-ID field atomicity and consistency behavior more thoroughly on the target Windows environment.
- [ ] Exercise the actual `PhysicsAcquirer` and ring buffer together during sustained ACC driving.
- [ ] Confirm no unexplained application buffer rejections and quantify source packet gaps under driving load.
- [ ] Establish measured acquisition cadence, read duration, CPU use and buffer high-water behavior.

**Interpretation of the live test:** It proves that the Windows process can open the ACC Physics mapping, copy a page of the expected size and observe packet-ID progression. It does not prove that every ACC publication was observed, that the full acquisition pipeline is loss-free, or that sustained recording works.

**Stage exit gate:** A controlled sustained live test of the acquirer plus buffer, with documented cadence, retries, source packet gaps, buffer rejects, occupancy/high-water and CPU impact. Any losses must be explicitly accounted for.

### Stage 2 — Sustained acquisition measurement and cadence baseline

**Status: In progress — benchmark implementation committed; live cadence sweep pending**

Implemented in this stage:
- [x] Add configurable monotonic polling intervals to `PhysicsAcquirer.run()`; zero retains explicit maximum-throughput mode, positive intervals use deadline-based waiting.
- [x] Skip missed deadlines instead of issuing catch-up bursts.
- [x] Measure poll start-to-start intervals separately from individual shared-memory read durations.
- [x] Record schedule lateness and missed polling deadlines.
- [x] Expose ring-buffer high-water mark and separate full-buffer rejections from lock-contention rejections.
- [x] Add a live Windows benchmark harness exercising the actual adapter, acquirer, SPSC buffer and a separate draining consumer.
- [x] Write benchmark JSON only after acquisition stops, outside the acquisition thread.
- [x] Include acquired/consumed/rejected/pending reconciliation in the report.
- [ ] Run the automated acquisition test suite after these changes.
- [ ] Run target-PC live trials at 120, 240 and 480 requested Hz with comparable durations.
- [ ] Review observed cadence, source packet gaps, retries, buffer rejects/high-water, CPU impact and final reconciliation.
- [ ] Select the operating polling cadence and buffer capacity from the measurements; do not treat the trial rates as production targets.

**Stage exit gate:** A repeatable live benchmark with a documented operating cadence and quantified source-observation gaps and application-level losses. A zero application reconciliation delta does not mean every ACC publication was observed.

### Stage 3 — Independent raw persistence

**Status: Not started**

Planned work:
- [ ] Add an independent recorder consumer; do not write files from the acquisition loop.
- [ ] Add a bounded recorder handoff with explicit overflow/loss policy.
- [ ] Persist append-only binary blocks in batches.
- [ ] Preserve capture sequence, ACC packet ID, monotonic timestamps and block sequence.
- [ ] Add checksums/integrity validation.
- [ ] Define flush and durability policy.
- [ ] Recover complete blocks after interrupted writes.
- [ ] Add UTC timestamps to recording metadata and filenames.
- [ ] Add final drain and acquired-versus-persisted reconciliation.
- [ ] Test slow storage, disk-full/write failures and abrupt shutdown.

**Stage exit gate:** Raw recordings can be validated and recovered, and every acquired sample is either persisted or represented in explicit loss accounting after final drain.

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
- `tests/acquisition/` — unit tests for buffer, acquirer and Windows source adapter.

The adapter copies the Physics page as raw bytes. It does not decode all Physics fields, read Graphics or Static, record to disk, or feed UI/coaching/lap-analysis consumers.

## 5. Known limitations and decisions

1. ACC shared memory exposes the latest state. Updates overwritten before observation cannot be reconstructed by this reader.
2. A packet-ID gap indicates counter progression between observations; it is not proof of an application ring-buffer drop.
3. Packet-ID bracketing is best-effort consistency validation, not an atomic snapshot guarantee.
4. The direct 100-read live test did not exercise `PhysicsAcquirer` or the ring buffer.
5. The run loop now supports a configurable monotonic polling cadence. The suitable production cadence remains unselected until the live 120/240/480 Hz sweep is measured.
6. The initial queue is SPSC. Multiple consumers require explicit fan-out and independent loss accounting.
7. No raw recorder or persistence/recovery guarantee exists yet.
8. No downstream lap/sector logic, coaching, UI or other application feature should be allowed to compromise the acquisition critical path.

## 6. Latest verified baseline and next action

**Latest confirmed acquisition code commit before Stage 2:** `41cc633bb864868aa4f540898a631fcf21290254`  
**Branch:** `feature/acquisition-foundation`

**Latest user-reported automated test:** 13/13 acquisition tests passed.

**Latest user-reported live ACC smoke test (Stage 1):**
- Expected Physics page: 784 bytes
- Actual copied page: 784 bytes
- Reads: 100
- Consistent bracketed reads: 99
- Unique packet IDs: 100
- First/last packet IDs: 4066 / 6320
- Packet ID advanced: yes

**Next action:** Pull the latest branch, run the acquisition tests, then run the live benchmark at 120, 240 and 480 requested Hz for 120 seconds per trial with ACC running. Compare the timestamped JSON reports. Do not begin the raw recorder until the acquisition measurement baseline and loss accounting are trustworthy.

## 7. Stage 2 implementation details

- `PhysicsAcquirer.run(stop_event, poll_interval_ns=...)` now supports an explicit target cadence. It uses monotonic deadlines and skips missed slots rather than trying to catch up in a burst.
- Poll intervals are measured between acquisition cycles, not between consistency retries. Read-attempt duration remains a separate metric.
- The SPSC buffer reports high-water mark, full-buffer rejects, lock-contention rejects and total rejected snapshots independently.
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
