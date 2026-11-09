# ACC Raw Recording Format

**Updated:** 9 November 2026  
**Status:** Physics and Graphics writers emit format version 2. Readers and recovery accept versions 1 and 2. Static persistence is approved by policy but is deferred until its writer is implemented.

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

Static persistence has been approved separately in [ACC Static Acquisition](ACC_STATIC_ACQUISITION.md). Its writer is intentionally deferred until the common timestamped recording contract is established. Static remains independent and must retain its complete raw page and local capture metadata; source packet ID and source timestamp remain absent/null. No Physics/Graphics metadata may be attached to Static.

## Acquisition performance boundary

Persistence timestamps are generated only in the recorder writer after batch assembly. The acquisition snapshot constructors and hot loops do not call the persistence clock or perform additional serialization, queueing, or disk operations. Existing acquisition payloads, polling cadence, packet consistency checks, and capture timestamps are unchanged.
