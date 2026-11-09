# ACC Static Acquisition — Specification and Implementation Status

**Updated:** 9 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Status:** Raw-only adapter and change-detected acquisition implemented; automated tests added; target-PC 90-second stable-page acquisition check passed. Candidate field-layout audit is documented separately; live value qualification remains pending.

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
- `scripts/validate_acc_static_live.py` — focused 90-second live check; prints mapping size, raw-page hashes, per-capture local read timestamps, unchanged-read counts and rejection counts without dumping the page.
- `scripts/inspect_acc_static_candidate.py` — read-only compact inspector for the common-prefix candidate and both 15-/33-character TrackConfiguration tail layouts.
- `docs/ACC_STATIC_FIELD_LAYOUT_AUDIT.md` — candidate offsets, competing layouts, semantic disposition and evidence gates.
- `tests/acquisition/test_static.py`
  - Initial/unchanged/changed-page behavior.
  - Explicit absent source packet ID and source timestamp.
  - Local monotonic timestamp preservation.
  - Full mapping copy and clean close through an injected mapping.

## ABI and validation limitations

The implementation deliberately does not declare a production `SPageFileStatic` layout or field decoder. The target PC confirmed a 4,096-byte mapping allocation, but public candidate references disagree on whether `TrackConfiguration` is 15 or 33 UTF-16 code units. That difference changes the candidate logical structure size from 784 to 820 bytes and shifts every subsequent field. The 4,096-byte allocation does not resolve this ABI discrepancy. See `docs/ACC_STATIC_FIELD_LAYOUT_AUDIT.md`.

Automated tests are not a substitute for a live ACC read. The raw acquisition smoke test passed on the target PC (90 reads, one initial snapshot, 89 unchanged reads, zero buffer rejections). This validates stable-page acquisition only. Before Static field decoding can be marked validated:
1. Run `python scripts/inspect_acc_static_candidate.py` on the target Windows PC with ACC active.
2. Compare the common-prefix strings and numeric values with the car, track and session shown in ACC.
3. Resolve the 15-vs-33 UTF-16 code-unit `TrackConfiguration` candidate and confirm tail offsets for car skin, pit window, online state and dry/wet tyre names.
4. Confirm field types/units where references conflict; leave uncertain fields raw-only.
5. Keep the full 4,096-byte raw page and independent local acquisition timestamps.
6. Keep source packet ID/timestamp null and do not attach Physics/Graphics synchronization metadata.

No further Physics or Graphics recording is required for this validation.
