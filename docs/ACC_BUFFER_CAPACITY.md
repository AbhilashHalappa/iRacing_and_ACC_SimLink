# ACC Acquisition Buffer Capacity Rationale

**Status:** Provisional engineering rationale; production defaults unchanged.
**Branch:** `feature/acquisition-foundation`
**Updated:** 10 November 2026

## Decision summary

Keep the current validation-runner defaults:

| Stream | Acquisition queue | Recorder queue | Batch size |
|---|---:|---:|---:|
| Physics | 100,000 | 100,000 | 128 |
| Graphics | 10,000 | 10,000 | 64 |
| Static | 64 | 64 | 16 |

These are bounded loss-detecting queues, not overwrite buffers. A full queue rejects the new item and increments explicit rejection/loss accounting. A zero-rejection run demonstrates only that the tested workload fit; it does not establish unlimited headroom.

The defaults are retained because they provide substantial delay tolerance and the Physics/Graphics payload-memory bounds are finite and quantifiable. This is not a claim that the values are mathematically optimal. The Graphics fault-injection measurements below are useful calibration, but the current evidence does not justify reducing the defaults.

## Sizing method

For a stream with arrival rate (R) items/second and a tolerated consumer stall (T) seconds, the minimum backlog capacity implied by that stall is:

`C_{stall} = ceil(R × T)`

A production capacity should then include an explicit engineering margin:

`C_{design} = ceil(C_{stall} × (1 + M))`

where `M` is a documented margin selected from the application's recovery objective and observed variability. No universal value of `M` is asserted here: the project has not yet specified a maximum recorder outage/recovery objective for every stream. The time-equivalent capacity calculations below are therefore coverage figures, not an outage guarantee.

Queue capacity means outstanding items. For the Physics fan-out consumer it includes queued plus in-flight items until acknowledgement. For the Graphics and Static recorder ring buffers, a worker removes items into its batch before writing; that in-flight batch is reported separately and is not part of the ring's pending count.

## Per-stream capacity and memory

### Physics

- Configured acquisition rate: 480 polls/second.
- Acquisition queue: 100,000 snapshots.
- Required recorder consumer queue: 100,000 outstanding snapshots.
- Raw Physics payload: 800 bytes per snapshot (`PHYSICS_SIZE`).
- Batch size: 128.
- Conservative queue payload bound: `(100,000 + 100,000) × 800 = 160,000,000 bytes` (160 MB decimal, approximately 152.6 MiB).
- At the configured 480 Hz rate, each 100,000-item queue represents approximately 208.3 seconds of arrivals.

The independent 600-second supervised parity run measured 479.12 polls/second and 232,697 accepted/consumed snapshots (387.83 snapshots/second), with zero rejects, zero pending items, and exact reconciliation. The 480 Hz configured rate is used for conservative time coverage rather than substituting the lower unique-capture throughput.

The two queue capacities are separate stages: the acquisition SPSC queue protects the hand-off to the dispatcher; the required recorder queue protects durable recording from a slow writer. The recorder queue's capacity includes its in-flight acknowledgements, preventing dequeue from falsely freeing capacity before persistence.

### Graphics

- Configured poll rate: 100 polls/second.
- Acquisition queue: 10,000 snapshots.
- Recorder queue: 10,000 snapshots.
- Observed complete raw mapping allocation: 4,096 bytes per snapshot.
- Batch size: 64.
- Conservative queue payload bound: `(10,000 + 10,000) × 4,096 = 81,920,000 bytes` (81.92 MB decimal, approximately 78.1 MiB).
- At 100 snapshots/second, each 10,000-item queue represents 100 seconds of arrivals.

The 4,096-byte value is the complete mapping allocation observed in the user's live recording report; capture preserves the whole mapping, not the smaller candidate struct.

#### Graphics slow-recorder measurements

All runs used the same live ACC Graphics source, 100 Hz polling, 30-second requested capture, batch size 64, and a simulated sleep immediately before each recorder batch write. The delay is applied once per batch in the recorder worker; it is not a per-snapshot delay and does not emulate every possible disk/OS failure mode.

| Simulated pre-batch delay | Queue capacity | Recorder queue high-water | Acquired / persisted | Rejections | Reconciliation delta |
|---:|---:|---:|---:|---:|---:|
| 750 ms | 2,048 | 504 | 3,001 / 3,001 | 0 | 0 |
| 750 ms | 768 | 503 | 3,000 / 3,000 | 0 | 0 |
| 750 ms | 640 | 504 | 3,001 / 3,001 | 0 | 0 |
| 750 ms | 576 | 504 | 3,001 / 3,001 | 0 | 0 |
| 750 ms | 544 | 504 | 3,001 / 3,001 | 0 | 0 |
| 1,000 ms | 2,048 | 1,143 | 3,000 / 3,000 | 0 | 0 |

Recovery and checkpoint validation passed in each reported run. The 750 ms backlog was stable at approximately 504 snapshots across five tested capacities. At 1,000 ms the peak rose to 1,143 snapshots. The 2,048-item recorder queue therefore reached 55.8% utilisation in the more severe of these two tested profiles, with 905 slots unused.

The 544-item test passed but reached 504/544 (92.6%) occupancy, leaving only 40 slots. This is evidence against selecting 544 as a production capacity. The tests support retaining 10,000; they do not establish that 2,048 or any smaller value is sufficient for all real storage stalls.

A previous normal 30-second live run acquired and persisted 3,000 snapshots with queue high-water marks of 1 for both acquisition and recorder queues, zero rejects, and exact reconciliation.

### Static

- Refresh interval: 1 second by default.
- Acquisition queue: 64 changed-page snapshots.
- Recorder queue: 64 changed-page snapshots.
- Observed complete mapping page: 4,096 bytes.
- Batch size: 16.
- Queue payload bound: `(64 + 64) × 4,096 = 524,288 bytes` (0.5 MiB).

Static is change-driven: the acquirer emits the initial page and later pages only when raw bytes change. Unchanged 1 Hz refreshes are not queued. Therefore, converting 64 entries into “64 seconds of coverage” would be incorrect; capacity is 64 pending changed-page observations at each queue stage.

The live 30-second Static validation observed 31 reads, one changed page (the initial page), 30 unchanged reads, one persisted page, zero rejects, and zero pending items. This validates the unchanged-page suppression path, not a worst-case rapid-change rate. A deterministic unit test now fills a 64-entry Static queue with 64 distinct changed-page snapshots, verifies that the 65th is rejected and recorded as lost, and drains all original 64 snapshots in FIFO order with payloads intact. The test passed as part of the user's focused Static recording suite (6 tests, 0.054 seconds). This verifies the configured queue boundary and no-overwrite behaviour; it does not claim ACC produces 64 changed pages in one second. Static's small page payload makes the current 64-entry bound inexpensive.

## Aggregate queue payload budget

Using the configured capacities and observed raw payload sizes, the conservative sum of queue payload bytes is:

| Stream | Queue payload bound |
|---|---:|
| Physics | 160,000,000 bytes |
| Graphics | 81,920,000 bytes |
| Static | 524,288 bytes |
| **Total** | **242,444,288 bytes (about 242.4 MB / 231.3 MiB)** |

This is a payload-only bound, not a prediction of process working set. The six preallocated ring-buffer slot arrays contain 220,128 references in total (200,000 Physics + 20,000 Graphics + 128 Static). On the 64-bit target, the reference slots alone account for approximately 1,761,024 bytes (1.68 MiB), plus small per-list headers. This slot-array estimate is separate from the payload bound. The combined figures exclude Python snapshot objects, locks, dictionaries, allocator fragmentation, writer batch lists/encoding buffers, transient dispatcher items, and other application memory. For Graphics and Static, a recorder batch can be held outside the recorder ring while it is being written; the batch sizes are 64 and 16 respectively. The Static acquirer also retains its previous raw page for change detection. The Physics fan-out queues retain snapshot references; payload bytes are not copied once per consumer.

### Synthetic process-memory measurement (10 November 2026)

The user ran `python scripts/measure_acc_buffer_memory.py` on the Windows development PC. The diagnostic allocated all six queues at their configured default capacities and populated them with synthetic Physics, Graphics, and Static snapshot objects. It did not connect to ACC or write recordings. Payload objects were deliberately shared per stream so the measurement isolates snapshot/reference and queue overhead; the conservative payload budget above continues to assume a distinct full payload for every retained snapshot.

| Measurement | Result |
|---|---:|
| Queue slots | 220,128 |
| Theoretical reference-slot arrays | 1,761,024 bytes (1.68 MiB) |
| Traced queue-storage increment | 1,766,119 bytes (1.68 MiB) |
| Traced snapshot-population increment | 47,533,655 bytes (45.33 MiB) |
| Traced current / peak allocation | 49,299,774 / 49,299,870 bytes (47.02 MiB) |
| Snapshot population increment per retained item | 215.94 bytes |
| Process working set before allocation | 20,738,048 bytes (19.78 MiB) |
| Process working set after empty queues | 22,614,016 bytes (21.57 MiB) |
| Process working set after population | 197,742,592 bytes (188.54 MiB) |
| Process private usage after population | 195,956,736 bytes (186.87 MiB) |
| Peak process working set | 207,925,248 bytes (198.24 MiB) |
| Conservative payload + traced queue/snapshot overhead | 291,744,062 bytes (278.23 MiB) |

The process working set/private usage are process-level observations and include the interpreter, imported modules, allocator behaviour, and other runtime costs; they are not queue-only measurements. The traced snapshot increment is an average for this synthetic object mix and must not be treated as a universal per-sample constant. The 278.23 MiB combined figure is a conservative payload-plus-traced-overhead planning estimate, not measured process RAM and not a strict upper bound on the complete application. The diagnostic is reproducible with `python scripts/measure_acc_buffer_memory.py` after setting `PYTHONPATH=src` in PowerShell.

The three validation scripts are independent and need not run simultaneously. The aggregate is a conservative topology-wide comparison, not a claim that all three scripts currently allocate this amount in one process.

## Provisional stall and recovery objectives

The following are proposed engineering service objectives derived from the configured default capacities. They are deliberately conservative planning targets with approximately 10% queue headroom for the continuous-rate streams. They are not yet validated guarantees and do not change production capacities.

| Stream | Required queue | Arrival-rate basis | Provisional maximum downstream stall | Queue occupancy at target | Remaining capacity |
|---|---:|---:|---:|---:|---:|
| Physics | 100,000 | 480 snapshots/second | 180 seconds | 86,400 | 13,600 (13.6%) |
| Graphics | 10,000 | 100 snapshots/second | 90 seconds | 9,000 | 1,000 (10%) |
| Static | 64 changed-page snapshots | Change-driven; no validated continuous worst-case rate | 48 changed-page events | 48 | 16 events (25%) |

For Physics and Graphics, the stall calculation is arrival rate multiplied by stall duration; the configured poll rate is used conservatively. For Static, the objective is event-count based. A time-based Static stall claim is prohibited until the maximum changed-page burst rate is measured or a source-level bound is established.

**Recovery objective (provisional):** after the downstream writer becomes available again, the required recorder queue must drain back to zero within a period no longer than the preceding tolerated stall, while acquisition continues at its configured rate. During recovery there must be no new required-delivery rejection, no unexplained sequence gap, and final persisted/rejected/pending accounting must reconcile exactly. This requires sustained writer throughput above the live arrival rate; to meet the equal-duration recovery deadline, net drain throughput must at least match the backlog accumulated during the stall. The current tests do not yet establish this recovery rate, so it remains an acceptance target to measure, not a passed result.

The 180-second Physics and 90-second Graphics objectives are below the nominal capacity coverage (208.3 and 100 seconds respectively) to retain headroom. They are selected as initial validation targets, not as proof that all real disk/OS pauses have these durations. If a future product requirement demands longer stalls, recalculate capacity from that requirement and revalidate memory and acquisition performance before changing defaults.
## What the evidence does and does not establish

Established:
- Every configured queue is bounded and rejects explicitly rather than overwriting unread data.
- The current capacities have explicit count, rate-coverage, and payload-only memory calculations.
- Physics has a 600-second supervised acquisition parity result.
- Graphics has repeatable 30-second slow-recorder measurements at 750 ms and a more severe 1,000 ms pre-batch delay, with high-water and end-to-end reconciliation recorded.
- Static emits only initial/changed pages and has a live no-change validation result.
- No production defaults were changed during this investigation.

Not yet established:
- Validation of the provisional 180-second Physics / 90-second Graphics stall objectives and equal-duration backlog recovery objective under controlled downstream stalls; the current overload tests do not prove these targets.
- A maximum tolerated real disk outage for each stream.
- A worst-case Static page-change rate during a stalled recorder.
- A production-load process working-set measurement while ACC is running and recording; the synthetic process-level measurement is available, but it is not a live workload measurement.
- A long-duration Graphics stress profile or a realistic OS/storage fault distribution.

The simulated Graphics delay is intentionally narrow: it sleeps before each batch and then performs the normal writer operation. It does not reproduce device cache behavior, filesystem pauses, antivirus interference, disk-full conditions, or arbitrary thread scheduling delays. It should not be described as a universal storage benchmark.

## Reproduction commands

Graphics baseline:
```powershell
python scripts/record_acc_graphics.py --duration-seconds 30 --poll-hz 100 --acquisition-buffer-capacity 10000 --recorder-buffer-capacity 10000 --batch-size 64
```

Graphics 750 ms recorder delay:
```powershell
python scripts/record_acc_graphics.py --duration-seconds 30 --poll-hz 100 --acquisition-buffer-capacity 2048 --recorder-buffer-capacity 2048 --batch-size 64 --simulated-write-delay-ms 750
```

Graphics 1,000 ms recorder delay:
```powershell
python scripts/record_acc_graphics.py --duration-seconds 30 --poll-hz 100 --acquisition-buffer-capacity 2048 --recorder-buffer-capacity 2048 --batch-size 64 --simulated-write-delay-ms 1000
```

Physics default recording validation:
```powershell
python scripts/record_acc_physics.py --duration-seconds 120 --poll-hz 480 --timer-resolution-ms 1
```

Static default recording validation:
```powershell
python scripts/record_acc_static.py --duration-seconds 120 --refresh-seconds 1
```

For each run, retain the JSON report and inspect both queue high-water marks, rejection counts, pending/in-flight counts, reconciliation delta, writer failures, and recovery/checkpoint results. A `completed` status is necessary but queue sizing review should use the detailed report.

## Controlled Physics stall-and-recovery validation

`scripts/record_acc_physics.py` now supports the test-only `--simulated-initial-recorder-stall-seconds` option. It pauses the first recorder batch once, on the recorder worker only, while Physics acquisition and downstream dispatch continue. The runner observes the required recorder queue after the pause, then requires it to remain empty for 500 ms while acquisition is still running. Recovery time is measured from stall release to the first empty-queue observation. The run fails its completion gate if no backlog accumulated, recovery does not complete within the same duration as the injected stall, acquisition or recorder queues reject samples, or recovery does not happen while acquisition is active.

The intended target-PC validation for the provisional Physics objective is:

```powershell
python scripts/record_acc_physics.py `
    --duration-seconds 361 `
    --poll-hz 480 `
    --acquisition-buffer-capacity 100000 `
    --recorder-buffer-capacity 100000 `
    --batch-size 128 `
    --simulated-initial-recorder-stall-seconds 180
```

The duration provides a 180-second stall plus an equal 180-second recovery window and a one-second margin. The runner may stop earlier after it observes a stable empty queue during live acquisition. Review `stall_recovery_validation`, recorder high-water, acquired/persisted counts, all rejection and pending counts, reconciliation delta, recovery/CRC, checkpoint, and the final completion reasons. This is a controlled software pause before recorder writes, not a physical disk outage; it validates bounded backlog and recovery throughput without claiming to emulate every storage fault.

Focused unit coverage for the one-time stall injection is in `tests/acquisition/test_recorder.py` (`test_one_time_initial_recorder_stall_is_measured_and_then_drains` and negative-duration validation). These tests and the live target-PC run must pass before the provisional Physics objective can be marked validated.
## Follow-up required before final capacity sign-off

1. Validate the provisional Physics (180 seconds), Graphics (90 seconds), and Static (48 changed-page events) stall objectives, including backlog recovery to zero within the preceding stall duration while acquisition continues.
2. Run the controlled 180-second Physics stall-and-recovery validation above. The deliberate Physics overload test verifies full-queue high-water, explicit rejection, exact reconciliation, and failed completion, but does not prove successful recovery from the provisional tolerated stall.
3. Define whether Static must tolerate a specified real-source burst of changed pages; the deterministic 64-entry queue boundary is tested, but source burst rate under ACC has not been measured.
4. If a strict memory budget is required, measure process working set/private usage during a representative live ACC recording workload; the current synthetic process-level measurement is not a substitute.
5. Revisit capacities only if those objectives and measurements show a mismatch.

Until then, retain the existing defaults. This closes the documentation/calculation portion of capacity justification but leaves the unmeasured cases explicit rather than implying they have passed.
