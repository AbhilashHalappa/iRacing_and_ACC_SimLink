# ACC Raw Recording Format

**Updated:** 10 November 2026  
**Status:** Physics, Graphics, and Static writers emit format version 2. Physics and Graphics readers/recovery accept versions 1 and 2; Static has its own version-2 reader/recovery.

## Scope and invariants

Physics and Graphics are recorded independently as raw snapshots. Recording runs downstream of acquisition. The acquisition workers do not generate persistence timestamps, encode recording records, wait for consumers, or perform disk I/O.

For every Physics and Graphics sample written in format version 2:

- Preserve capture sequence, ACC source packet ID, local read-start/read-complete timestamps, capture timestamp, and complete raw payload.
- Add a per-sample `persistence_timestamp_ns`.
- Do not replace or rewrite any capture/source metadata.
- Keep Physics and Graphics timestamps in their own stream records. They do not establish cross-stream synchronization.
- Use a monotonic process-local clock (`time.perf_counter_ns`), not wall-clock time, for persistence timestamps.

## Persistence timestamp semantics

A timestamp cannot be sampled after the block's successful `fsync` and also be included in the same bytes whose `fsync` has already completed. The format therefore defines a precise recorder-boundary timestamp:

1. The recorder worker assembles and validates a batch downstream of acquisition.
2. The writer samples one monotonic timestamp immediately before encoding/writing that batch's block.
3. That same value is stored on every sample in the batch.
4. The block is considered persisted only after its complete bytes have been written, flushed, and `fsync` has returned successfully.
5. If writing, flushing, or `fsync` fails, the batch is not counted as persisted. Any incomplete/corrupt tail remains subject to the existing CRC recovery/truncation rules.

Consequently, `persistence_timestamp_ns` is the batch's recorder commit-boundary entry time, not a claim that the timestamp equals the later instant at which the operating system completed durable storage. The successful writer return and persisted counters are the confirmation of persistence.

All samples in one batch intentionally share the same timestamp. Timestamps are non-decreasing across successive batches in a stream. They are not required to be unique, and timestamps from separate Physics and Graphics files must not be compared as a synchronization mechanism.

## Version 2 record layout

The file header and block framing remain the same size and retain their existing magic values. The file header version is now `2`.

Version 2 extends each record header from six fields to seven little-endian fields:

| Field | Type | Meaning |
|---|---|---|
| capture sequence | uint64 | Application-local sequence for this stream |
| source packet ID | uint64 | ACC Physics or Graphics packet ID |
| read start | uint64 | Local monotonic read-start time |
| read complete | uint64 | Local monotonic read-complete time |
| capture timestamp | uint64 | Existing local monotonic capture time |
| persistence timestamp | uint64 | Recorder batch-boundary timestamp |
| payload length | uint32 | Number of raw payload bytes following the header |

Physics uses the existing `ACCPHY01` file and `PHBK` block magic. Graphics uses `ACCGFX01` and `GFXB`. The block CRC covers the complete version-specific record headers and raw payloads, including the persistence timestamp.

## Backward compatibility and recovery

- New Physics and Graphics recordings are written as version 2.
- Existing version 1 files remain readable and recoverable.
- A version 1 record has no persistence timestamp; readers expose it as `None` rather than inventing one.
- Version 2 recovery validates that every record has a timestamp and that timestamps are non-decreasing within and across valid blocks.
- CRC, block sequence, capture sequence, payload-size, incomplete-tail and truncation checks remain in force.
- Physics offline inspection accepts both versions and reports the file format version.

## Static stream

Static persistence is implemented independently in `static_recording.py` and
documented in [ACC Static Acquisition](ACC_STATIC_ACQUISITION.md). It uses the
same version-2 file-header and block framing structures, with stream-specific
magic values `ACCSTA01` and `STBK`. Its version-2 record header is:

| Field | Type | Meaning |
|---|---|---|
| capture sequence | uint64 | Application-local Static observation sequence |
| read start | uint64 | Local monotonic read-start time |
| read complete | uint64 | Local monotonic read-complete time |
| capture timestamp | uint64 | Existing local monotonic capture time |
| persistence timestamp | uint64 | Recorder batch-boundary timestamp |
| payload length | uint32 | Number of raw mapping bytes following the header |

Static deliberately has no source packet ID field because the documented
Static layout does not define one. Source packet ID and source timestamp remain
absent; no Physics/Graphics metadata is attached. The complete mapping page is
stored without decoding or truncation. Only the initial and byte-changed pages
are recorded; unchanged refreshes are not queued or persisted.

The Static writer timestamps each batch downstream of acquisition and counts
the block persisted only after write, flush, and `fsync` succeed. Its recovery
reader validates version, page size, block sequence, capture sequence,
timestamp ordering, and CRC, and can truncate an invalid tail. The dedicated
worker drains a bounded recorder queue on stop and reports failed batches.

## Acquisition performance boundary

Persistence timestamps are generated only in the recorder writer after batch assembly and stored in separate decoded-record types. The live PhysicsSnapshot and GraphicsSnapshot acquisition objects do not gain a persistence field or extra per-sample slot. Acquisition hot loops do not call the persistence clock or perform additional serialization, queueing, or disk operations. Existing acquisition payloads, polling cadence, packet consistency checks, and capture timestamps are unchanged.


## Downstream consumer fan-out

Physics acquisition remains SPSC. Independent bounded consumer queues and the
out-of-loop dispatcher are specified in
[ACC Downstream Fan-out Queues](ACC_DOWNSTREAM_FANOUT.md). The Physics recorder
acknowledges samples only after successful batch write, flush, and fsync; queue
rejections and processing failures remain explicit and prevent a successful
recording validation result.


## Required recording completion

The Physics recorder is the required consumer in the current fan-out topology.
Queue overflow, failed processing, a writer error, non-zero pending/in-flight
work, shutdown timeout, failed checkpoint, or failed recovery/CRC validation
makes the run incomplete. A recoverable valid prefix is salvage data and does
not make an incomplete run successful. The deterministic completion rules and
optional-consumer isolation policy are documented in
[ACC Downstream Fan-out Queues](ACC_DOWNSTREAM_FANOUT.md) and enforced by
`recording_policy.py`.
