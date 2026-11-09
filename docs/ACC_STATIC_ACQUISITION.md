# ACC Static Acquisition — Specification and Implementation Status

**Updated:** 9 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Status:** Raw-only change-detected acquisition is implemented and runs as an independently supervised worker. Focused worker lifecycle/failure tests and a supervised live ACC smoke test are documented below. Candidate-B decoder status and ABI limitations remain unchanged.

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
- `src/race_engineer_acquisition/static_decoder.py` — conservative decoder for fields supported by the live-qualified candidate-B offsets. Unresolved fields remain raw-only.
- `tests/acquisition/test_static_decoder.py` — decoder tests for candidate-B offsets, short pages and invalid boolean encodings.
- `docs/ACC_STATIC_FIELD_LAYOUT_AUDIT.md` — candidate offsets, competing layouts, semantic disposition and evidence gates.
- `tests/acquisition/test_static.py`
  - Initial/unchanged/changed-page behavior.
  - Explicit absent source packet ID and source timestamp.
  - Local monotonic timestamp preservation.
  - Full mapping copy and clean close through an injected mapping.

## Supervised worker lifecycle

The Static stream is part of the common acquisition supervisor and runs on its
own worker thread. The runtime registers the existing
`StaticAcquirer.run(stop_event, refresh_interval_ns=...)` entry point with
the supervisor using the configured Static refresh interval (one second by
default).

Worker contract:
- The first successful raw-page read is offered to the Static SPSC buffer.
- Subsequent reads are compared against the last successfully queued page;
  unchanged pages do not emit snapshots.
- If the bounded buffer rejects a changed page, that page is not marked as
  observed. The next refresh retries it, even if the bytes have not changed.
- Source-read exceptions increment the common Static health failure counters
  and propagate to the supervisor. The stream becomes `failed`; the error
  remains visible in supervisor status.
- On worker exit, the supervisor closes the Static source/mapping exactly
  once. A timed-out live worker retains mapping ownership until it exits.
- Static remains independent: no source packet ID or source timestamp is
  added, and no decoding or persistence occurs in the worker.

Focused tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.acquisition.test_static -v
python -m unittest discover -s tests/acquisition -v
```

The focused Static tests cover initial/unchanged/changed observations,
buffer-rejection retry, full mapping copy, supervised worker startup and
shutdown, exactly-once source close, common health lifecycle, and source
failure propagation/counting.

### Existing supervised live ACC evidence

The existing 120-second all-stream Windows validation already exercised
Static through `create_acc_acquisition_runtime()` and the supervisor; no
separate Static-only live recording is needed. Its Static result was:

- Successful reads: **121** (approximately 1 Hz).
- Emitted snapshots: **1** (the initial page).
- Unchanged reads: **120** (derived from reads minus the one initial capture).
- Consumed snapshots: **1**.
- Source read failures: **0**.
- Buffer rejections: **0**; pending records: **0**; reconciliation delta: **0**.
- Worker and health lifecycle: **stopped**; timer resolution released.

This is stable-page live evidence. A changed-page event during a live ACC
session is not claimed by that run; changed-page and full-buffer retry behavior
are covered by deterministic tests. No Physics/Graphics field recordings or
additional 600-second performance benchmark are required for Issue #3.

## ABI and validation limitations

The implementation does not claim official Kunos ABI certification. Target-PC inspection on ACC Shared Memory 1.9 strongly favors candidate B: common-prefix car/track/session values match, and CarSkin plus dry/wet tyre names decode coherently at candidate-B offsets while candidate-A offsets are empty. The conservative decoder exposes only selected fields from candidate B. Pit-window values/units, deprecated members, ambiguous fields and unsupported semantics remain raw-only. The 4,096-byte allocation is not treated as the logical structure size. See `docs/ACC_STATIC_FIELD_LAYOUT_AUDIT.md`.

Automated tests are not a substitute for a live ACC read. The raw acquisition smoke test passed on the target PC (90 reads, one initial snapshot, 89 unchanged reads, zero buffer rejections). This validates stable-page acquisition only. Before Static field decoding can be marked validated:
1. Run `python scripts/inspect_acc_static_candidate.py` on the target Windows PC with ACC active.
2. Compare the common-prefix strings and numeric values with the car, track and session shown in ACC.
3. Resolve the 15-vs-33 UTF-16 code-unit `TrackConfiguration` candidate and confirm tail offsets for car skin, pit window, online state and dry/wet tyre names.
4. Confirm field types/units where references conflict; leave uncertain fields raw-only.
5. Keep the full 4,096-byte raw page and independent local acquisition timestamps.
6. Keep source packet ID/timestamp null and do not attach Physics/Graphics synchronization metadata.

No further Physics or Graphics recording is required for this validation.
