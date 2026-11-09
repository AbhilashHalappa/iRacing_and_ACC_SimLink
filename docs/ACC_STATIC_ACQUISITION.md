# ACC Static Acquisition — Specification and Implementation Status

**Updated:** 9 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Status:** Raw-only adapter and change-detected acquisition implemented; automated tests added; target-PC live validation pending.

## Scope

Read the ACC Static shared-memory page at startup, then refresh at a low cadence only to detect a change in the page. Publish the initial page and subsequent changed pages. The acquisition path copies the complete Windows mapping allocation and does not decode or truncate it.

The captured raw page is the source for later extraction of:
- Car information.
- Track information.
- Session configuration.
- Available vehicle and track metadata.

## Stream identity and time provenance

Static is an independent stream. It must never borrow Physics or Graphics packet IDs, timestamps, sequence numbers, or inferred synchronization.

The documented `SPageFileStatic` layout does not define a packet ID or source timestamp member. Therefore:
- `source_packet_id` is explicitly `null`.
- `source_timestamp_ns` is explicitly `null`.
- `capture_sequence` is an application-local sequence identifying emitted Static observations only.
- `read_start_ns`, `read_complete_ns`, and `capture_timestamp_ns` are local monotonic acquisition timestamps. They are not represented as original ACC timestamps.
- Raw bytes are retained unchanged so no source metadata is discarded.

Do not substitute the latest Physics or Graphics packet ID/timestamp. Do not claim that a Static observation is synchronized with either stream.

## Change detection

The first successful read is always emitted. Later reads are emitted only when the complete raw mapping bytes differ from the previous read. The default refresh interval is one second and is configurable. This is byte-change detection, not an assertion that ACC publishes a formal Static update counter.

## Implementation

- `src/race_engineer_acquisition/static.py`
  - Read-only `Local\\acpmf_static` mapping.
  - Mapping allocation size queried at runtime.
  - Full-allocation raw copy.
  - Initial plus changed-page acquisition.
  - Separate Static snapshot and metrics types.
  - No field decoder and no guessed packet ID/timestamp.
- `scripts/validate_acc_static_live.py` — focused 90-second live check; prints mapping size, raw-page hashes, per-capture local read timestamps, unchanged-read counts and rejection counts without dumping the page.\n- `tests/acquisition/test_static.py`
  - Initial/unchanged/changed-page behavior.
  - Explicit absent source packet ID and source timestamp.
  - Local monotonic timestamp preservation.
  - Full mapping copy and clean close through an injected mapping.

## ABI and validation limitations

The implementation deliberately does not declare a ctypes `SPageFileStatic` layout or field offsets. Third-party ACC Shared Memory references identify the mapping name and describe Static as session/car metadata initialized at session start, but the target project's exact ACC v1.9 layout, mapping size, field offsets, string encoding, and semantics still require provenance review and target-PC evidence. The raw adapter is independent of those candidate layouts.

Automated tests are not a substitute for a live ACC read. Before Static acquisition can be marked validated:
1. Run `python scripts/validate_acc_static_live.py` on the target Windows PC with ACC active.
2. Record the observed mapping size and verify repeated complete-page copies.
3. Confirm the first snapshot is emitted and unchanged reads are suppressed.
4. Trigger or observe a genuine Static-page change (for example, a session/car/track change) and verify a new snapshot is emitted.
5. Verify the raw bytes and per-observation local read timestamps are preserved.
6. Verify the Static record contains no fabricated source packet ID or source timestamp and no Physics/Graphics synchronization metadata.

No further Physics or Graphics recording is required for this validation.
