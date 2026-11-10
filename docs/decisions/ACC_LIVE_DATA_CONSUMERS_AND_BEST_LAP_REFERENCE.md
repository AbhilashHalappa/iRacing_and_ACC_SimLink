# ACC Live Data Consumers and Best-Lap Reference — Architecture Decision

**Project:** Race Engineer ACC New  
**Decision date:** 10 November 2026  
**Status:** Accepted  
**Scope:** Runtime data consumers, live telemetry processing, selective lap capture, best-lap persistence and coaching reference data

---

## 1. Decision Summary

Race Engineer ACC New is a **live-data-driven application**.

Physics, Graphics and Static data acquired from ACC are distributed to live application consumers. Overview, native Overlays, live processing and live coaching consume current live data; they do not read recorded session files to obtain current telemetry.

The application does **not** continuously persist every Physics, Graphics and Static sample or archive every lap/session as part of normal runtime operation.

Instead, it temporarily captures candidate lap data from the live streams and persistently retains only the best eligible lap for each reference combination:

**Car + Track + Weather Conditions**

When a newly completed eligible lap is better than the stored reference for the same combination, it replaces that reference. Otherwise, the candidate is discarded after evaluation.

The retained best lap is reference data for live coaching and comparison. It is not the source of current vehicle, lap, session or UI state.

---

## 2. Architectural Principles

1. Live ACC telemetry is the primary runtime data source.
2. Physics, Graphics and Static remain independent acquisition streams.
3. Raw acquisition and live processing are separate downstream paths.
4. A slow or failed live consumer must not block acquisition or compromise another consumer.
5. Overview and native Overlays consume published live application state.
6. Live coaching consumes current live telemetry and may consult the stored best-lap reference.
7. Candidate lap capture is temporary; durable persistence is selective.
8. The application retains one best-lap reference per car, track and weather-condition combination, replacing it only when a better eligible lap is accepted.
9. Stored best-lap data must not be replayed as if it were current live telemetry.
10. Engineering raw-recording and validation tools remain separate from normal product runtime persistence.

---

## 3. Logical Data-Processing Layers

These are logical responsibilities, not a requirement to create one process or service per layer.

### Layer 1 — ACC Acquisition

Independent acquisition of:

- Physics — target 480 Hz.
- Graphics — target 100 Hz.
- Static — startup and change/refresh driven, nominally 1-second polling where applicable.

Acquisition copies source observations into application-owned snapshots and maintains stream-specific timestamps, packet tracking and health.

The acquisition hot path must not perform coaching, lap reconstruction, UI publishing, serialization, database work or disk I/O. It must not wait for downstream consumers.

### Layer 2 — Data Distribution

Each stream has independent bounded delivery to its downstream consumers.

The logical destinations are:

- Live processing consumers.
- Temporary candidate-lap capture.
- Engineering raw-recording tools when explicitly enabled for validation or diagnosis.

The distribution design must preserve independent consumer progress and explicit queue/loss accounting. A live consumer must not share a blocking delivery path with another consumer.

The existence of a live consumer does not justify changing the already validated acquisition hot loop or weakening the recording/integrity guarantees of engineering validation tools.

### Layer 3 — Live Telemetry Processing

Consumes live Physics, Graphics and Static observations and produces typed, time-aware live data.

Responsibilities include:

- Stream-specific decoding where supported by validated field definitions.
- Latest vehicle telemetry and derived live values.
- Graphics-derived lap, sector, validity and session observations.
- Static vehicle, track and configuration context.
- Freshness, availability and association metadata.

Do not invent synchronization between independent streams. Preserve source timestamps and packet identifiers where available. Unknown or unsupported fields remain unavailable/opaque rather than being guessed.

### Layer 4 — Domain Processing

Consumes live processed data and maintains application-domain state, including:

- Lap and sector processing.
- Lap-boundary correlation.
- ACC lap validity and out-lap classification.
- Vehicle dynamics.
- Session and pit state.
- Corner, braking and driving-event context.

The validated requirements in [ACC Lap Time, Sector Time and Lap Validity — Technical Decision](ACC_LAP_TIMING_SECTOR_RECONSTRUCTION_AND_VALIDITY.md) remain authoritative for lap timing, sector reconstruction, boundary-fragment correlation and validity. This decision does not replace or weaken them.

### Layer 5 — Live Intelligence and Coaching

Consumes current live telemetry and domain state.

Responsibilities include:

- Live Performance Coach.
- Corner Coach.
- Live comparison against the applicable stored best-lap reference.
- Driving feedback and recommendations.

The coach must distinguish current live measurements from reference-lap measurements. Reference data provides a comparison baseline; it does not replace missing or stale live data.

### Layer 6 — Application State and Publishing

Publishes typed, read-only application state to UI subscribers.

Published state may include:

- Current vehicle telemetry.
- Current lap and sector state.
- Session, pit and track state.
- Coaching messages and recommendations.
- Acquisition/consumer health.
- Data freshness, stale, unavailable and error states.

The application-state layer is not another source of telemetry truth. It must expose the origin and freshness of the values it publishes.

### Layer 7 — Presentation

Presentation consumers subscribe to published state and service interfaces.

- Overview consumes live application state.
- Native Overlays consume live application state.
- Performance Hub may display the current live session state and the stored best-lap reference.
- Hardware Workspace consumes the independent Hardware service and has no dependency on ACC telemetry.

UI rendering cadence may be lower than acquisition cadence. The UI does not need every acquired sample and must never block acquisition or live processing.

---

## 4. Selective Best-Lap Capture and Persistence

### 4.1 Candidate capture

Candidate lap data is assembled from the live streams while a lap is in progress.

The candidate capture must retain the data required by the accepted lap-processing and coaching requirements, including:

- Relevant Physics observations.
- Relevant Graphics observations and ACC timing/validity information.
- Applicable Static vehicle/track configuration context.
- Lap identity, boundary and timing metadata.
- Weather-condition metadata required to identify the reference combination.

Candidate capture is temporary until the lap is complete and evaluated. It must not require a durable all-session raw recording.

### 4.2 Eligibility and comparison

A candidate must first be a completed lap and pass the established lap eligibility rules.

ACC remains authoritative for track-rule validity. An ACC-invalid or unknown-validity lap must not become an eligible best-lap reference. The existing lap/sector technical decision governs validity, sector calculations and boundary-fragment handling.

For an eligible candidate, compare it with the existing reference for the same car/track/weather combination.

- No existing reference: accept and persist the eligible candidate.
- Candidate is better: replace the existing reference.
- Candidate is not better: discard the candidate after evaluation.
- Candidate is incomplete, invalid or cannot be classified reliably: do not replace the reference.

“Better” is based on the accepted lap-selection policy; the initial intended comparison is the fastest eligible lap time. Any additional quality ranking or tie-breaking must be explicitly specified before implementation rather than inferred.

### 4.3 Reference identity

The logical reference key is:

**Car + Track + Weather Conditions**

The reference record must retain enough metadata to identify the combination and verify compatibility when coaching selects it.

The exact weather signature, condition bucketing/tolerance, and behaviour when weather changes during a session remain open design details. Do not silently treat materially different conditions as equivalent.

### 4.4 Replacement and retention

For each reference key, retain one active best-lap reference.

When a better eligible candidate is accepted, replace the active reference for that key. The application is not intended to maintain an unlimited history of prior best laps or all completed laps.

Atomic replacement or an equivalent recoverable update is required so an interrupted write cannot leave the reference unusable. The exact storage format is an implementation decision.

---

## 5. Consumer Data-Source Contract

| Consumer | Primary input | May read best-lap reference? |
|---|---|---:|
| Live Telemetry State | Live Physics, Graphics and Static | No |
| Lap/Sector Processor | Live Graphics with supporting live Physics/context | No |
| Vehicle Dynamics Processor | Live Physics with supporting context | No |
| Session/Pit State Processor | Live Graphics and Static context | No |
| Live Performance Coach | Live telemetry and domain state | Yes |
| Corner Coach | Live telemetry and domain state | Yes |
| Overview | Published live application state | No direct reference-file access |
| Native Overlays | Published live application state | No direct reference-file access |
| Performance Hub | Published live state and reference-service output | Yes, through a service/API |
| Best-Lap Manager | Completed candidate from live processing and existing reference | Yes |
| Diagnostics | Live acquisition and consumer health | No |
| Engineering validation tools | Explicitly created raw recordings | Not applicable |

No normal runtime consumer may use a historical recording as a substitute for the live stream it requires.

---

## 6. Engineering Raw Recordings Versus Product Persistence

The project has raw acquisition and recording infrastructure used to validate acquisition behaviour, buffering, persistence, recovery and data integrity.

That engineering capability remains valuable and may be used explicitly for:

- Acquisition and recorder validation.
- Regression fixtures and controlled investigations.
- Diagnosing a specific data-integrity or field-semantics issue.

It must not be confused with the normal product's lap/session retention policy.

Normal product runtime does not continuously archive every Physics, Graphics and Static sample, and it does not retain every completed lap/session. Its persistent telemetry reference is the selected best lap per car/track/weather combination, together with the metadata needed to identify and use it.

Engineering test recordings and fixtures are not automatically exposed as user session history or used as live UI data sources.

---

## 7. Failure Isolation and Data Freshness

- Acquisition must not wait for live processing, coaching, candidate evaluation, storage or UI.
- A coaching or UI failure must not stop acquisition.
- A candidate-capture or best-lap storage failure must be reported and must not corrupt an existing valid reference.
- Each stream and consumer must expose its own health and backlog/loss accounting.
- Stale, missing, unknown and unavailable values must remain distinguishable.
- A stored reference may remain available when live telemetry is unavailable, but it must never be presented as current live telemetry.

---

## 8. Relationship to Existing Decisions and Architecture

This decision supplements the [Greenfield Architecture Proposal](../architecture/GREENFIELD_ARCHITECTURE_PROPOSAL.md) by defining the runtime consumer and retention policy.

The [ACC Lap Time, Sector Time and Lap Validity — Technical Decision](ACC_LAP_TIMING_SECTOR_RECONSTRUCTION_AND_VALIDITY.md) remains authoritative for ACC timing, sector reconstruction, boundary correlation, validity and its regression requirements.

Where earlier general descriptions imply continuous product persistence of all raw telemetry or make recorded sessions the normal source for application consumers, this accepted decision supersedes that interpretation for normal product runtime. It does not remove the engineering raw-recording tools or invalidate their existing validation evidence.

---

## 9. Open Decisions Before Implementation

The following details are intentionally not invented by this decision:

1. Exact weather-condition signature and compatibility/tolerance rules.
2. Exact candidate-buffer capacity and retention mechanics for a full lap.
3. Exact best-lap comparison tie-breakers and any additional quality criteria beyond established eligibility.
4. Best-lap file/database schema, atomic replacement and recovery implementation.
5. Exact live-consumer queue capacities and update policies, based on consumer requirements and measured workloads.

These details require explicit design decisions before implementation.

---

## 10. Final Decision

**Live data drives the application. A selectively retained best lap provides the coaching reference.**

All normal live application consumers receive live data through independent downstream processing and published application state. Candidate laps are assembled temporarily from live observations. Only the best eligible lap for each car, track and weather-condition combination is retained persistently, and a better eligible lap replaces it.

The application does not use recorded sessions as the normal data source for Overview, Overlays, live telemetry, domain processing or coaching.
