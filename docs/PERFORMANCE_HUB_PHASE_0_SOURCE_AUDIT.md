# Performance Hub — Phase 0 Source and Data Audit

**Branch:** `feature/performance-hub`  
**Audit date:** 18 November 2026  
**Scope:** Read-only audit of the greenfield ACC repository and the legacy F1 application's Corner Coach source.  
**Code changes:** None. This document records verified source facts and implementation gaps; it does not claim the audit is a live ACC runtime validation. The bounded per-lap retention policy is now accepted in `docs/decisions/PERFORMANCE_HUB_BOUNDED_LAP_RETENTION.md`.

## 1. Executive findings

1. The greenfield app already has a working *track-outline learning path* in the Overview UI. It uses decoded ACC Graphics `normalized_car_position` and `player_world_position`, captures a completed valid lap, and caches one learned layout per track/configuration in browser `localStorage`.
2. That path does **not** retain an independently selectable trajectory for every lap. It therefore cannot yet support a historical lap-to-lap racing-line comparison.
3. The decoded Graphics candidate contains the player's world position and normalized track progress. The raw Graphics recorder also preserves complete raw Graphics pages. The raw Physics recorder preserves Physics pages, but the reviewed Physics decoder is not the source used by the current Overview map.
4. The compact Strategy Lap History stores one compact record per completed lap and explicitly reports `high_resolution_telemetry_stored: false`. It is not a Performance Hub telemetry store.
5. The raw Physics/Graphics recorder classes and scripts exist, but the normal Qt runtime factory does not instantiate a recorder worker. The separate strategy data contract says normal product runtime does not continuously archive every high-frequency sample. This conflicts with the current Performance Hub roadmap's assumption that persisted high-resolution Physics recordings are already available to the product. That assumption must be resolved before Phase 1; do not silently add a second recorder or turn on continuous recording.
6. The greenfield frontend's Performance Coach, Corner Coach and Replay & Analysis navigation items currently render the generic `NOT INTEGRATED` placeholder. The legacy F1 repository's `main` branch does contain the Corner Coach engine, live coaching integration and TTS implementation. These are migration sources, not existing ACC greenfield components.
7. The current app publishes decoded Physics/Graphics/Static snapshots through Stage 2 and a 50 ms Qt-to-frontend snapshot timer. Historical analysis must be added as a separate service and must not run on acquisition, decoder, broker or Overview rendering paths.

## 2. Verified source inventory

| Area | Verified source | Finding |
|---|---|---|
| Raw Physics recording | `src/race_engineer_acquisition/recorder.py` | Versioned, CRC-blocked raw Physics writer/reader; preserves capture sequence, packet ID, timestamps and complete raw payload; v1/v2 recovery |
| Raw Graphics recording | `src/race_engineer_acquisition/graphics.py` | Separate versioned, CRC-blocked raw Graphics writer/reader; preserves complete Graphics mapping pages and capture metadata |
| Physics decoding | `src/race_engineer_acquisition/physics_decoder.py` | Downstream decoder for Physics; not used by current track map |
| Graphics decoding | `src/race_engineer_acquisition/graphics_decoder.py` | Candidate 1,588-byte Graphics layout; exposes `normalized_car_position`, `player_world_position`, `completed_laps`, `is_valid_lap`, session identifiers and player car ID |
| Decoded Graphics consumer | `src/race_engineer_acquisition/graphics_consumer.py` | Drains its own Graphics ring and publishes the latest decoded snapshot and capture timestamp |
| Stage 2 broker | `src/race_engineer_acquisition/decoded_distribution.py` | Independent coalescing latest-state subscriptions plus a separate bounded event channel; does not read raw rings/shared memory |
| Lap events | `src/race_engineer_acquisition/lap_events.py` | Completed-lap events use decoded Graphics lap counter/timing/validity; gaps are explicit and missing laps are not fabricated |
| Compact strategy history | `src/race_engineer_acquisition/strategy_lap_history.py` | SQLite compact per-lap metadata/selected measurements; bounded history; no high-frequency telemetry |
| Qt host | `src/desktop/qt_host.py` | Owns runtime and Race Engineer service; publishes detached decoded snapshots; stores strategy history under `user_data/strategy/` |
| HTTP/SSE bridge | `src/desktop/bridge.py` | Serves static frontend and latest published snapshot; no shared-memory access or decoding |
| Existing track map UI | `frontend/src/TrackMapTile.tsx` | Reads Graphics world position/progress; learns one valid track outline and stores it in browser localStorage |
| Track geometry helpers | `frontend/src/trackMap.js` | Track identity, projection and layout validation |
| Track capture state | `frontend/src/trackMapCapture.js` | Lap-gated capture; rejects invalid/out-lap/teleport/discontinuous candidates; requires minimum point count and near-full progress coverage |
| Frontend page routing | `frontend/src/App.tsx` | Overview exists; Performance Coach, Corner Coach and Replay & Analysis currently fall through to generic placeholder |
| Legacy Corner Coach | `Race-Engineer-ACC/src/corner_coach.py` on `main` | Large established Corner Coach engine with live corner state, reference trace, zone handling, voice controls and validation instrumentation |
| Legacy live coaching | `Race-Engineer-ACC/src/coaching_live.py` on `main` | `IntegratedLiveCoach` coordinates pre-/post-corner advice and reference-based guidance |
| Legacy TTS | `Race-Engineer-ACC/src/tts.py` on `main` | Dedicated speech worker, message-family gates, queue/deadline handling and explicit Corner Coach message isolation |

## 3. Racing-line data audit

### 3.1 Existing live source

The current Overview map obtains:
- `graphics.normalized_car_position` as lap progress.
- `graphics.player_world_position` as the player's world coordinate.
- `graphics.completed_laps`, `graphics.is_valid_lap`, `graphics.last_time_ms` and the current out-lap status to qualify a candidate.

The map converts the three-dimensional position to an X/Z point. The capture state:
- starts a candidate around the start/finish wrap;
- samples points as normalized progress advances;
- rejects world-coordinate jumps above its configured threshold;
- rejects discontinuous progress;
- latches lap validity and out-lap status;
- commits only after the completed-lap counter and lap time confirm the candidate;
- requires at least 80 points and near-complete progress coverage.

### 3.2 Current limitation

The committed object is a `TrackLayout` with one `points` array, keyed by track and configuration. It is cached under `acc-track-map-v2:<track/configuration>`. A later valid lap replaces the cached layout. The UI draws that one polyline as the circuit outline and shows the current car marker.

Consequently, the current map is not:
- a lap archive;
- a selectable per-lap driven-line view;
- a two-lap overlay;
- an ideal/professional driver racing line;
- proof of calibrated spatial accuracy.

### 3.3 Required Performance Hub model

The Racing Line feature should retain a separate trajectory for each completed, eligible lap. At minimum, each point needs:
- session identity and lap identity;
- normalized progress;
- world X/Z position (retain Y if useful for diagnostics, but do not use it as the 2D track plane);
- source Graphics capture sequence and timestamp;
- data-quality/continuity flags.

A trajectory record also needs track/configuration, car identity, lap time, ACC validity, out-lap classification, point count, progress coverage and capture-quality summary.

The Racing Line UI should allow a user to select a driven lap and a reference lap (for example, the user's personal best) and overlay both paths on the same track coordinate frame. Spatial separation should be measured at matched progress positions and displayed by corner/entry/apex/exit once stable corner regions exist.

**Reference-line meaning:** the initial supported reference should be another recorded user lap, such as the personal best. Do not label it an ideal or professional driver's line. A true ideal/external reference requires a separately sourced and licensed dataset or user-provided reference.

### 3.4 Quality gates still required

The existing 80-point threshold is only a capture minimum, not a validated spatial-accuracy guarantee. Before presenting quantitative distance differences, validate:
- Graphics sample cadence and effective point spacing under real driving;
- coordinate stability and axis/orientation consistency across sessions;
- progress monotonicity and wrap behaviour;
- duplicate/coalesced snapshot behaviour in the latest-value Stage 2 path;
- world-coordinate jitter and outlier rejection;
- lap/session identity across restarts and session changes;
- repeatability when driving the same line on repeated laps.

The latest-value broker intentionally coalesces snapshots. It is suitable for current UI state but cannot guarantee delivery of every Graphics sample to a historical trajectory recorder. If the existing Graphics raw recording is used as the lossless source, its reader must associate raw samples with completed laps without changing Stage 1 or blocking acquisition. If product runtime is to retain per-lap trajectories directly from live Graphics, it needs a separately designed bounded consumer path with explicit loss accounting—not a UI effect that assumes every snapshot arrives.

## 4. Recording and persistence decision gap

The Performance Hub roadmap currently says analysis reads existing persisted high-resolution Physics recordings. The repository contains raw Physics and Graphics recorder implementations and dedicated recording/inspection scripts. However:
- `create_acc_acquisition_runtime()` in `src/race_engineer_acquisition/supervisor.py` does not instantiate the raw recorder workers;
- `src/desktop/qt_host.py` starts the acquisition runtime and Race Engineer service, not a continuous raw recorder;
- `StrategyLapHistory.snapshot()` explicitly says `high_resolution_telemetry_stored: false`;
- `docs/STRATEGY_LIVE_DATA_AND_COMPACT_LAP_HISTORY.md` says normal product runtime does not continuously archive every Physics/Graphics sample and retains compact lap history only;
- `docs/decisions/ACC_LIVE_DATA_CONSUMERS_AND_BEST_LAP_REFERENCE.md` defines selective candidate capture and best-lap reference retention rather than unlimited raw-session retention.

**Decision resolved:** Performance Hub uses bounded per-lap retention as defined in `docs/decisions/PERFORMANCE_HUB_BOUNDED_LAP_RETENTION.md`. It captures eligible laps from an independent, bounded Stage 2 decoded-sample consumer; it does not enable continuous raw session recording or create another raw recorder. This extends the earlier best-lap-only persistence contract for Performance Hub history while preserving the existing live-coaching best-lap reference.

The implementation still must prove a loss-accounted per-sample delivery path. The existing latest-value Stage 2 subscription is coalescing and is not a valid lossless source for historical traces.

For Racing Line specifically, Graphics position is the direct source. Physics data is needed for braking/throttle/steering/speed analysis and must be correlated using source metadata and a verified lap-boundary association. Physics and Graphics files have independent timestamps; do not infer sample-level synchronization from their persistence timestamps.

## 5. Lap identity and classification

Verified current sources:
- Completed-lap events are derived from fresh decoded Graphics observations.
- ACC Graphics `is_valid_lap` is the validity authority.
- Out-lap state is owned by the existing broker's single `ACCOutLapObserver`; consumers must reuse its classification, not create another detector.
- Session history uses a run-scoped session identity rather than treating ACC `session_index` and session type as globally unique.
- Event gaps and counter jumps mark history incomplete; missing laps are not synthesized.

Performance Hub must use this existing source of truth and preserve the established ACC lap-boundary and validity decision in `docs/decisions/ACC_LAP_TIMING_SECTOR_RECONSTRUCTION_AND_VALIDITY.md`.

## 6. Corner Coach migration audit

The greenfield repository has no `corner_coach.py`, `coaching_live.py` or `tts.py` implementation. Its frontend navigation labels exist, but those pages currently render a placeholder.

The legacy F1 application's `main` branch contains:
- `src/corner_coach.py` — `CornerCoachEngine`, reference trace and coaching-zone state, per-lap state, feature toggles and validation recorder;
- `src/coaching_live.py` — `IntegratedLiveCoach`, pre-corner reference guidance and post-corner advice scheduling;
- `src/tts.py` — speech worker and Corner Coach message-family handling;
- supporting modules including `corner_coach_models.py`, `corner_coach_validation.py`, `coaching_analysis.py`, `post_corner_coach.py`, `reference_model.py` and related geometry/performance modules.

This is a migration, not a drop-in UI move. Before porting, trace the legacy runtime wiring, telemetry input contract, reference model/storage, settings, TTS lifecycle and dependencies. Then define an ACC adapter using the greenfield Stage 2 decoded feed. Do not copy F1-specific assumptions or rewrite proven coaching calculations merely to fit the new navigation.

## 7. Architecture guardrails confirmed

- Stage 1 raw acquisition/fan-out remains unchanged.
- Existing Physics and Graphics decoders remain unchanged unless a separately proven missing field requires an explicitly reviewed change.
- Stage 2 remains the decoded distribution layer; add a new independent subscriber only if the chosen data contract requires it.
- Overview remains unchanged.
- Race Strategy remains unchanged and is not a Performance Hub analysis dependency.
- The UI is not a telemetry recorder.
- Historical analysis runs in a separate service/worker and cannot block live processing.
- Reuse existing lap validity, out-lap and completed-lap authorities.
- Every metric must expose unavailable/low-confidence states rather than fabricate values.

## 8. Phase 0 deliverables and open decisions

| Deliverable / decision | Audit status |
|---|---|
| Existing raw Physics/Graphics recording formats | Source verified; product-runtime availability not enabled |
| Decoded live Graphics position source | Source verified |
| Existing track-outline capture and cache | Source verified |
| Per-lap racing-line archive | Not implemented |
| Quantified spatial accuracy | Requires live validation |
| Completed-lap/validity/out-lap source | Source verified |
| Compact Strategy Lap History | Source verified; not suitable for high-resolution analysis |
| Performance Hub frontend shell | Not implemented; placeholder navigation exists |
| Legacy Corner Coach source | Located in old repository `main`; migration audit still required |
| Product high-resolution retention policy | Accepted: bounded per-lap retention; see decision record |
| Physics/Graphics lap association and synchronization | **Open technical specification** |
| Corner Coach ACC adapter and runtime lifecycle | **Open migration specification** |

## 9. Recommended next implementation sequence

1. Design the bounded Stage 2 decoded-sample delivery path and its overflow/loss accounting. The existing coalesced latest-value mailbox is not sufficient.
2. Define the typed candidate-lap contract and lap/session association using existing completed-lap events and classification authority.
3. Implement candidate assembly and validate Physics/Graphics association and spatial quality with controlled ACC runs.
4. Benchmark representative lap storage, then implement atomic persistence, recovery, retention and read-only queries.
5. Implement the analysis reader and lap reconstruction against the approved persistence contract.
6. Build telemetry normalization, quality reporting, lap comparison and corner analysis.
7. Add per-lap racing-line overlay and spatial comparison using the existing track-map projection helpers.
8. Migrate the legacy Corner Coach behind an ACC-specific adapter, preserving its voice path.
9. Build the Performance Hub UI on the established service contracts.

**Phase 0 status:** source-level audit completed for the main recording, decoded distribution, lap-history, track-map and Corner Coach entry points. The bounded per-lap retention policy is accepted. The Stage 2 loss-accounted sample-delivery design, cross-stream association, live spatial accuracy and detailed legacy Corner Coach dependency/runtime tracing remain open. No application source code was changed during this audit.
