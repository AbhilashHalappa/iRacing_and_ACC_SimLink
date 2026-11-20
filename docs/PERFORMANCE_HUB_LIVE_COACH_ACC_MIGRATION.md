# Performance Hub Live Coach — ACC Migration Contract

**Roadmap phase:** Phase 8 — Coaching Intelligence  
**Branch:** `feature/performance-hub`  
**Status:** ACC source-contract foundation implemented; Corner Coach runtime and voice delivery are not yet migrated.

## 1. Purpose

Bring the proven Corner Coach from `AbhilashHalappa/Race-Engineer-F1-2026` (`main`) under Performance Hub ownership without changing its measured coaching decisions or its voice behaviour. ACC must provide an explicit adapter; F1 state, recorder, lap-number, distance, and session-clock assumptions must not leak into the ACC application.

This document records the first migration slice and the remaining contract work. It does not claim that Live Coach is already running in ACC.

## 2. Verified source findings

### F1 Corner Coach contract

The existing `CornerCoachEngine.observe(recorder, state, now)` path expects:

- `recorder.current_reference_lap()` to return the selected reference in the F1 reference-lap format.
- A current-lap trace through `recorder.current_lap_trace_snapshot(state)`, with fallback to `current_lap_snapshot(state)`.
- Recorder metadata including `reference_mode`, optional `external_reference_meta`, `event_context`, and `samples`.
- State fields for session track identity, session time, session UID, ended/total-lap state, player lap number, lap distance, current/previous lap time, lap validity, pit status, speed, brake, steering, and throttle.
- The engine emits `EngineerMessage` values carrying priority, key, text, monotonic creation time, session time, optional playback deadline, estimated speech duration, and a `speak` flag.

The engine is not a standalone file. Its current `main`-branch imports include the Corner Coach models and validation recorder, distance-performance model, engineer message model, reference-model compiler, performance scoring, and lap/stint intelligence. Diagnosis also uses corner geometry metrics. These dependencies must be audited and ported selectively; copying the F1 package wholesale would introduce F1-only assumptions.

### Voice contract

The F1 `SpeechOutput` is a non-blocking priority speech worker. It supports message-family gates, cancellation/pre-emption, stale/deadline checks, spoken-duration validation, and independent `corner:` message handling. Its `EngineerMessage` model is part of that contract.

The current ACC Greenfield branch does not yet contain the F1 `engineer.models` or `tts.SpeechOutput` modules. The ACC Qt host currently publishes decoded telemetry and service snapshots; it does not yet own a Live Coach or voice worker. Voice migration therefore needs to be an explicit, independently testable slice—not an assumption that the F1 worker is already present in ACC.

## 3. ACC-native source contract implemented

New module: `src/race_engineer_acquisition/live_coach_adapter.py`

New tests: `tests/acquisition/test_live_coach_adapter.py`

The adapter consumes the existing freshness-aware `RaceEngineerTelemetrySnapshot` and broker out-lap status. It exposes a detached `live_coach_source` object from `RaceEngineerService.snapshot()` with:

- Independent Physics, Graphics, and Static freshness, capture sequences, and capture timestamps.
- ACC-native Physics values: speed, throttle, brake, raw steering angle, raw gear, and RPM.
- ACC-native Graphics candidates: status, session index, completed-lap count, current/last time milliseconds, validity, pit flags, distance travelled, normalized car position, and sector.
- Fresh Static identity: car model, track, and track configuration.
- Explicit fresh/active out-lap state.

The adapter does not subscribe to shared memory, add a decoder, consume a second acquisition queue, or alter the existing broker. It does not modify Stage 1, Overview calculations, Race Strategy, or the proven F1 Corner Coach.

## 4. Explicit retained-reference selection implemented

New module: `src/race_engineer_acquisition/live_coach_reference.py`

New tests: `tests/acquisition/test_live_coach_reference.py`

The service now exposes:
- `list_live_coach_reference_candidates(...)`: lists only retained full traces with valid, non-out classification, complete car/track/configuration identity, and both Physics and Graphics sample counts. Filters are exact car/track/configuration matches and can be narrowed to one session.
- `load_live_coach_reference(...)`: loads a caller-selected session/lap pair, rechecks classification and exact identity, and rejects missing/corrupt/incomplete traces.

The returned reference keeps original ACC Physics and Graphics sample envelopes, including independent capture sequences and timestamps. It is deliberately not translated into the F1 reference-lap schema. No automatic "best lap" choice or mutable selected-reference state is introduced yet; the consumer must explicitly select a candidate.

## 4. Semantics deliberately not guessed

The adapter preserves candidate fields with raw names and provenance. It does not currently map them into the F1 engine's state shape because these ACC meanings still need explicit confirmation:

1. **Lap-local distance:** `distance_traveled_m` is retained as an ACC candidate; it is not silently treated as F1 `lap_distance_m`.
2. **Current lap clock:** `current_time_ms` is retained as an ACC candidate; it is not silently treated as F1 `current_lap_time_s`.
3. **Session clock:** `session_time_left_ms` is not inverted or treated as elapsed session time.
4. **Steering:** ACC `steering_angle` is retained raw; it is not normalized into the F1 `steering` threshold domain.
5. **Lap identity:** no F1-specific `native_lap_number` or `lap_sequence` fields are introduced.
6. **Reference lap:** a canonical geometry model is not a substitute for a selected, high-resolution telemetry reference lap.
7. **Current-lap trace:** the existing archive capture path must be reused; no second persistent recorder may be created.
8. **Pit/out-lap eligibility:** ACC's existing out-lap observer remains the authority; F1 pit-state heuristics must not override it.

The source payload includes unresolved contract identifiers so consumers cannot mistake this foundation for an executable coaching input.

## 5. Remaining Phase 8 implementation slices

1. Validate the ACC lap-distance, lap-clock, session-clock, pit, and track-identity semantics from actual ACC sessions. Use source sequence/timestamp evidence and preserve stream independence.
2. Complete reference-lap selection using the new explicit archive candidate/load API, then define and test the ACC-to-coach reference representation with data-quality gates.
3. Provide a bounded current-lap trace to the coach using the existing Stage 2 decoded-sample fan-out. Do not add another recorder or read shared memory from the coach.
4. Port the generic message model and voice delivery worker with tests for message priority, `corner:` independence, deadline/pre-emption, cancellation, stale messages, and shutdown. Keep voice output off decoder and UI threads.
5. Port/adapt the Corner Coach engine and only the dependencies required by its verified ACC input contract. Keep F1 session/race-control assumptions behind the adapter or replace them with ACC-authoritative behaviour.
6. Integrate the coach service into the Qt host and Performance Hub UI only after the service and voice contracts are stable.

## 6. Acceptance criteria

- Live Coach consumes only existing Stage 2 decoded data and the selected archived reference.
- Physics and Graphics provenance remains independent; no array-index pairing is introduced.
- ACC lap distance, lap time, and session time are derived only from verified ACC semantics.
- Validity and out-lap suppression use ACC's existing classification authority.
- Existing Corner Coach diagnosis and message timing behaviour are retained unless an ACC-specific difference is explicitly documented and tested.
- Voice delivery remains asynchronous and preserves priority, deadline, cancellation, and message-family behaviour.
- Overview, Race Strategy, Stage 1, acquisition, and existing archive behaviour remain unchanged.
- Unit and integration tests pass, followed by local ACC-session validation of actual spoken coaching.



## Bounded current-lap trace provider (implemented; 27-test regression batch passed)

The existing Performance Lap Capture Worker now publishes a detached snapshot of
its active CandidateLapAssembler interval. It uses the worker's existing Stage 2
Physics/Graphics sample subscription and lap-event subscription; it creates no
additional reader, recorder, subscription, or acquisition queue.

The snapshot retains Physics and Graphics as independent ordered sample tuples,
including their original capture sequences and timestamps. It reports per-stream
sample counts and source ranges, bounded capacity, active/waiting/degraded status,
quality reasons, overflow streams, and an explicit coaching-usability gate.
It does not align samples by array index or infer lap-local distance, lap clock,
or session-clock semantics. An active snapshot is never marked complete.

The service exposes this contract through the explicit request-path method
`RaceEngineerService.read_current_lap_trace_snapshot()`. It is deliberately not
embedded in the high-frequency live `snapshot()` payload, avoiding repeated
serialization of the growing trace on the live UI hot path. This completes the current-lap trace-provider foundation;
ACC-session semantic validation and the Corner Coach runtime/voice migration
remain outstanding.

## ACC semantics evidence exporter (implemented; awaiting real-session capture)

New read-only tool: `tools/export_acc_semantics_diagnostic.py`

The exporter reads existing retained Performance Hub traces only. It does not
attach to ACC shared memory, change the recorder, or align Physics and Graphics
by array index. It writes two session-scoped CSV files:

- `acc_semantics_samples_<session>.csv`: long-form raw observations with
  stream name, field, original capture sequence, original capture timestamp,
  archive lap classification, and value.
- `acc_semantics_summary_<session>.csv`: per-lap/per-stream field coverage,
  observed numeric range, increase/decrease counts, value-transition counts,
  and original source sequence/timestamp ranges.

Graphics evidence includes `distance_traveled_m`,
`normalized_car_position`, `current_time_ms`, `last_time_ms`,
`session_time_left_ms`, `clock_s`, `completed_laps`, sector, pit flags,
validity, status, and session index. Physics evidence includes speed, throttle,
brake, steering angle, gear, and RPM. These are observations only; the report
does not label any field as a lap clock, lap-local distance, or monotonic
session clock.

Run after completing and saving at least one valid timed lap in ACC:

```powershell
$env:PYTHONPATH = "src"
python tools/export_acc_semantics_diagnostic.py
```

The default output is under
`user_data/PerformanceHub/monitor_reports/<session-id>/`. The user should
capture a session containing pit exit/out-lap, a complete timed lap, and (if
practical) pit entry/exit during a lap. Full-resolution samples are retained
only for eligible valid non-out laps under the existing archive policy;
compact invalid/out-lap records intentionally do not contain full traces.
Therefore the archive classification records out-lap status, while detailed
field-transition analysis comes from retained eligible traces. Local unit
tests and actual ACC capture are still required before assigning semantics.
