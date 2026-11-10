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

The live 30-second Static validation observed 31 reads, one changed page (the initial page), 30 unchanged reads, one persisted page, zero rejects, and zero pending items. This validates the unchanged-page suppression path, not a worst-case rapid-change rate. Static's small page payload makes the current 64-entry bound inexpensive, but a future source-change-rate requirement should be used if Static can change repeatedly during a consumer stall.

## Aggregate queue payload budget

Using the configured capacities and observed raw payload sizes, the conservative sum of queue payload bytes is:

| Stream | Queue payload bound |
|---|---:|
| Physics | 160,000,000 bytes |
| Graphics | 81,920,000 bytes |
| Static | 524,288 bytes |
| **Total** | **242,444,288 bytes (about 242.4 MB / 231.3 MiB)** |

This is a payload-only bound, not a prediction of process RSS. It excludes Python snapshot objects, list slots and references, locks, dictionaries, allocator fragmentation, writer batch lists/encoding buffers, transient dispatcher items, and other application memory. For Graphics and Static, a recorder batch can be held outside the recorder ring while it is being written; the batch sizes are 64 and 16 respectively. The Static acquirer also retains its previous raw page for change detection. The Physics fan-out queues retain snapshot references; payload bytes are not copied once per consumer.

The three validation scripts are independent and need not run simultaneously. The aggregate is a conservative topology-wide comparison, not a claim that all three scripts currently allocate this amount in one process.

## What the evidence does and does not establish

Established:
- Every configured queue is bounded and rejects explicitly rather than overwriting unread data.
- The current capacities have explicit count, rate-coverage, and payload-only memory calculations.
- Physics has a 600-second supervised acquisition parity result.
- Graphics has repeatable 30-second slow-recorder measurements at 750 ms and a more severe 1,000 ms pre-batch delay, with high-water and end-to-end reconciliation recorded.
- Static emits only initial/changed pages and has a live no-change validation result.
- No production defaults were changed during this investigation.

Not yet established:
- A maximum tolerated real disk outage for each stream.
- A target-PC Physics recorder stall/high-water measurement under controlled slow storage.
- A worst-case Static page-change rate during a stalled recorder.
- A full-process RSS measurement including Python/runtime overhead.
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

## Follow-up required before final capacity sign-off

1. Specify a tolerated downstream stall/recovery objective for each required recorder.
2. If Physics capacity is to be reduced, run a controlled Physics recorder-delay test and measure queue high-water, while preserving the 480 Hz acquisition performance gate and all completion/recovery checks.
3. Define whether Static must tolerate a specified burst of changed pages; if so, test that burst against both 64-entry queues.
4. Measure process RSS on the target PC if a strict memory budget is required.
5. Revisit capacities only if those objectives and measurements show a mismatch.

Until then, retain the existing defaults. This closes the documentation/calculation portion of capacity justification but leaves the unmeasured cases explicit rather than implying they have passed.
