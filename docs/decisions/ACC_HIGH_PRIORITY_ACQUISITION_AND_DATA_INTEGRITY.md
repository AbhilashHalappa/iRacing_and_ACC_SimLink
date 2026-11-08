# ACC High-Priority Acquisition and Data Integrity — Technical Decision

**Project:** Race Engineer ACC New  
**Decision date:** 7 November 2026  
**Status:** Source-independent acquisition core and Windows Physics adapter implemented; initial sustained benchmark sweep completed; Windows timer-resolution retest pending  
**Priority:** Highest — no UI, coaching or lap-processing work precedes acquisition validation

## 1. Objective and source limitation

ACC Shared Memory is a latest-state interface, not a guaranteed delivery queue. The application cannot recover a Physics update that ACC overwrote before the reader observed it. Therefore, the project must not promise zero source-level packet loss.

The engineering objectives are:

1. Observe source packet-ID progression as frequently and reliably as the interface allows.
2. Detect and report packet-ID advances between observations.
3. Never silently overwrite a sample already acquired by the application.
4. Persist acquired samples independently of downstream processing.
5. Reconcile acquired, rejected and persisted samples at recording finalization.

Keep these stages distinct: ACC publication, application acquisition and application persistence.

## 2. Acquisition critical path

The acquisition loop is limited to:

- Read the ACC Physics page through a dedicated source adapter.
- Read the Physics packet ID immediately before and after copying the page.
- Timestamp the read start and completion with time.perf_counter_ns().
- Reject/retry a snapshot when the bracketing packet IDs differ.
- Copy the resulting page into application-owned immutable bytes.
- Assign a monotonically increasing capture_sequence.
- Record the observed ACC Physics packet ID.
- Publish the snapshot to the bounded acquisition buffer without waiting for a consumer.

It must not decode channels, update application state, process laps, run coaching, update the UI, serialize JSON, access a database or write to disk.

The before/copy/after consistency check is a best-effort validation. It must be implemented only after confirming the atomicity and layout of ACC's packet-ID field. It is not a claim that every possible concurrent-write race is eliminated.

## 3. Sample identity and timing

Every accepted observation carries:

| Field | Meaning |
|---|---|
| capture_sequence | Application-generated monotonically increasing sequence |
| acc_physics_packet_id | ACC Physics packet ID observed for this copied page |
| read_start_ns | Monotonic timestamp immediately before the read/copy attempt |
| read_complete_ns | Monotonic timestamp immediately after the read/copy attempt |
| capture_timestamp_ns | Monotonic acquisition timestamp; initially equal to read completion |
| persist_timestamp_ns | To be added by the recorder when persistence is implemented |

Use UTC wall-clock timestamps in recording/session metadata and filenames, not as a replacement for monotonic interval measurements.

## 4. Buffer contract

The first implementation provides a preallocated bounded single-producer/single-consumer ring-buffer primitive. It does not silently overwrite unread records. The producer uses a non-blocking insertion attempt. Full-buffer rejection and lock contention are explicitly counted, with first and last rejected capture sequences retained.

The initial ring buffer is deliberately SPSC. Independent multi-consumer delivery must be implemented as an explicit fan-out layer with per-consumer capacity, ownership and loss policy. Do not treat one destructive SPSC queue as a broadcast mechanism.

Capacity is a measured configuration, not a fixed assumption. A 100,000-slot example at 56 Hz is approximately 29.8 minutes, but production capacity must be selected from measured sample rate, record size, available memory and worst-case recorder delay.

## 5. Loss accounting

Maintain separate metrics for:

- Source packet-ID gaps between successful observations.
- Inconsistent snapshot attempts and retries.
- Capture sequence count.
- Buffer full rejections.
- Buffer lock-contention rejections.
- Buffer occupancy high-water mark.
- Buffer occupancy and high-water mark.
- Acquisition duration and start-to-start interval.
- Recorder queue depth, write latency, failures and persisted count (recorder stage).

At recording finalization, reconcile:

**acquired snapshots = persisted snapshots + explicitly accounted application losses + snapshots still pending final drain**

The final drain must complete before final reconciliation. Source packet-ID gaps are reported separately and must not be added to application loss counts. A packet-ID delta greater than one is evidence of unobserved counter progression, not proof that the ring buffer dropped records.

## 6. Storage direction

The raw recorder will be an independent consumer. It will batch append-only binary records and preserve sequence numbers, packet IDs, monotonic timestamps, block sequence numbers and integrity checks. Recovery must identify complete blocks after interrupted writes. Human-readable JSON summaries and CSV exports are post-recording outputs, never acquisition-loop operations.

The raw Physics recording remains the source for later decoding and analysis. A decoder or summary failure must not invalidate already persisted raw blocks.

## 7. Implementation sequence and gates

### Stage 1 — Acquisition core

- [x] Immutable acquisition record types.
- [x] Preallocated bounded SPSC ring buffer.
- [x] Non-blocking insertion and explicit rejection accounting.
- [x] Physics acquisition loop with injectable source.
- [x] Bracketing packet-ID consistency contract and retry counters.
- [x] Packet-ID gap accounting.
- [x] Deterministic unit tests using a fake source and clock.
- [x] Implement the Windows ACC Shared Memory Physics adapter using the audited ACC Physics page layout.
- [x] Verify that the Windows adapter opens the live ACC Physics mapping and copies the expected-size page (100 reads; 784 bytes expected and actual; 100 unique advancing packet IDs).\n- [ ] Verify packet-ID read atomicity and snapshot consistency behaviour more thoroughly on Windows with ACC running. The smoke test observed one inconsistent bracketed read out of 100.

### Stage 2 — Acquisition measurement

The acquirer now supports a configurable monotonic polling interval. A zero interval is an explicit maximum-throughput mode; a positive interval uses deadline-based waiting and skips missed deadlines rather than issuing catch-up bursts. Poll start-to-start cadence is measured separately from individual read-attempt duration, and schedule lateness/overruns are counted.

The live benchmark at scripts/benchmark_acc_physics.py exercises the Windows Physics adapter, PhysicsAcquirer, SPSC buffer and a separate draining consumer. It writes a timestamped JSON report only after acquisition stops. Initial 120-second live trials at requested 120/240/480 Hz observed 64.47/64.52/64.53 Hz respectively, with 0 buffer rejections and 0 reconciliation delta in all three. CPU use was 2.02–2.71% of one core. The nearly fixed cadence suggests ordinary Windows wait granularity is limiting the loop. The benchmark now requests a balanced 1 ms WinMM timer resolution by default; repeat the same sweep and compare against this baseline. This request improves available timer granularity but does not guarantee exact wake-up timing. The initial requested rates remain measurement points, not production targets.

Measure read start-to-start intervals, read/copy duration, observed packet rate, packet-ID deltas, retry rate, buffer high-water/rejections and CPU use under real ACC driving conditions. Establish a baseline before optimizing. Application reconciliation must be reported separately from source packet-ID gaps.

### Stage 3 — Independent persistence

Add a recorder worker, bounded recorder handoff, batched binary blocks, checksums, flush policy, crash recovery and end-of-session reconciliation. Recorder work must never execute in the acquisition loop.

### Stage 4 — Reliability diagnostics

Expose acquisition and recorder counters, high-water marks, sequence ranges and explicit failure reasons. Run sustained sessions and deliberately inject slow consumers, disk failures and shutdown interruption.

### Stage 5 — Optimization and validation

Only after measurement, decide whether faster polling, a native C++/Rust reader or process isolation is justified. Re-run packet-gap, application-loss, persistence and sustained-session tests after each change.

## 8. Native implementation policy

Start with the narrow Python acquisition boundary and measure it. A native C++ or Rust component is justified only if profiling proves Python is the limiting factor or cannot meet a defined reliability target. Do not rewrite the application or introduce another process without measured benefit.

## 9. Current implementation boundary

The package under src/race_engineer_acquisition/ includes the source-independent acquisition core and a Windows adapter for the audited ACC Physics mapping and page layout. The adapter performs packet-ID-before, page-copy, packet-ID-after reads. A live ACC smoke test confirmed successful mapping access, the expected 784-byte page size and advancing packet IDs over 100 reads. One read had differing bracketing IDs. This does not validate the full PhysicsAcquirer-plus-buffer pipeline, sustained sampling cadence, source-level completeness or persistence. No live sampling-rate or persistence guarantee is claimed.

## 10. Relationship to the Greenfield Architecture

This decision supplements [GREENFIELD_ARCHITECTURE_PROPOSAL.md](../architecture/GREENFIELD_ARCHITECTURE_PROPOSAL.md). The architecture proposal defines the system boundaries; this document defines the acquisition core, consistency contract, buffer semantics and data-integrity gates. The validated lap/sector decision remains downstream and authoritative for lap processing.
