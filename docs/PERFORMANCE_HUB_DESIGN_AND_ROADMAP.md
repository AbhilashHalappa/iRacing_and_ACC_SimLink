# Performance Hub — Architecture and Implementation Roadmap

**Status:** Phase 0 source audit completed; bounded lap-retention decision accepted  
**Branch:** `feature/performance-hub`  
**Base branch:** `feature/fuel-strategy`

## 1. Objective

Build a complete, Track Titan-style ACC performance analysis experience using the existing high-resolution Physics recordings, and bring the existing Live Corner Coach under Performance Hub.

Performance Hub must support both:
- Detailed post-lap and post-session analysis from the existing high-resolution recordings.
- Live coaching from the existing decoded telemetry distribution.

This document records the agreed target design and proposed implementation roadmap. It does not claim that every component or data channel described below has already been verified in the current source.

## 2. Architectural principles

1. Preserve the existing Stage 1 raw-data fan-out.
2. Preserve the existing high-resolution recorder; do not create a second recorder.
3. Preserve the existing ACC acquisition and decoder implementations.
4. Stage 2 remains the decoded-data fan-out.
5. Overview and Race Strategy remain independent consumers and retain their current behaviour.
6. Performance Hub is a hybrid consumer: it reads persisted high-resolution recordings for analysis and consumes decoded live data for live coaching/integration.
7. Existing Corner Coach logic is integrated under Performance Hub; do not rewrite proven coaching logic merely to change its ownership or presentation.
8. Performance Hub must not depend on Overview or Race Strategy, and neither of those systems may depend on Performance Hub.
9. Do not substitute low-resolution decoded telemetry for high-resolution analysis.
10. Verify actual recording channels, metadata and existing code paths before implementing features that depend on them.

## 3. Target architecture

```text
                       ACC SHARED MEMORY
                              |
                   STAGE 1 — RAW DATA FAN-OUT
                              |
                    +---------+----------+
                    |                    |
             Existing Recorder     Existing Decoder
                    |                    |
             High-resolution              |
             Physics recordings           |
                    |                     |
                    |          STAGE 2 — DECODED DATA FAN-OUT
                    |                     |
                    |          +----------+----------+
                    |          |                     |
                    |       Overview             Race Strategy
                    |       (unchanged)           (unchanged)
                    |                               
                    +----------------+---------------+
                                     |
                              PERFORMANCE HUB
                                     |
                    +----------------+----------------+
                    |                |                |
              Recorded-data     Lap/session      Decoded live
                 analysis       association       telemetry
                    |                |                |
                    +----------------+----------------+
                                     |
                         PERFORMANCE ANALYSIS ENGINE
                                     |
                 +-------------------+-------------------+
                 |                   |                   |
            Lap Comparison      Corner Analysis      Racing Line
                 |                   |                   |
                 +-------------------+-------------------+
                                     |
                            COACHING INTELLIGENCE
                                     |
                         +-----------+-----------+
                         |                       |
                    Analysis Coach          Live Coach
                                                 |
                                      Existing Corner Coach
                                                 |
                                         Voice / UI feedback
                                     |
                              PERFORMANCE HUB UI
```

The diagram shows logical data ownership and inputs, not a new acquisition pipeline. The recorder remains on the existing Stage 1 raw-data path. Performance Hub reads the recorder's persisted output; it does not read raw shared-memory pages directly.

### 3.1 Data paths into Performance Hub

**A. High-resolution analysis path**

1. Existing Stage 1 raw-data fan-out feeds the existing recorder.
2. The existing recorder persists high-resolution Physics samples.
3. Performance Hub's analysis reader reads those persisted recordings.
4. Analysis uses the high-resolution samples for telemetry comparison, corner analysis and spatial/racing-line work, subject to verified channel availability.

**B. Lap/session identity and classification path**

Performance Hub associates recorded samples with the correct session and lap using existing lap/session metadata and classification information. The implementation must respect existing lap validity and out-lap rules. The precise source and join keys must be confirmed during the audit.

**C. Live coaching path**

1. Existing decoded telemetry continues through Stage 2.
2. The Live Coach component under Performance Hub consumes the appropriate decoded live feed.
3. Existing Corner Coach logic and voice behaviour are retained.
4. Analysed reference laps and coaching insights may be supplied to Live Coach through an explicit integration contract.

## 4. Component responsibilities and ownership

| Component | Primary input | Responsibility | Change policy |
|---|---|---|---|
| Stage 1 raw-data fan-out | ACC shared memory | Existing raw-data distribution | Do not modify |
| Existing recorder | Stage 1 raw stream | Persist high-resolution Physics recordings | Reuse; do not duplicate |
| Existing decoder | Stage 1 raw stream | Decode each stream once | Preserve |
| Stage 2 decoded-data fan-out | Decoded snapshots/events | Distribute decoded data to consumers | Modify only if a proven integration need exists |
| Overview | Stage 2 decoded data | Existing live dashboard | Do not modify implementation or behaviour |
| Race Strategy | Stage 2 decoded data and its existing strategy state | Race/fuel strategy | Preserve existing implementation and behaviour |
| Performance Hub analysis | Persisted high-resolution recordings | Post-lap/session analysis | New capabilities |
| Lap/session association | Existing lap/session metadata and events | Identify and classify recorded laps | Reuse existing source of truth |
| Performance Hub Live Coach | Stage 2 decoded data | Live coaching under Performance Hub | Integrate existing Corner Coach |
| Coaching intelligence | Analysis results and live coaching context | Prioritized improvement feedback | New integration/capabilities |
| Performance Hub UI | Performance Hub services | Present analysis and coaching | New UI surface |

## 5. Performance Hub feature scope

### 5.1 Session and lap overview
- Session summary and lap history.
- Personal best, last lap and valid/invalid classification.
- Consistency and session trends.
- Data-quality indicators for recordings and laps.

### 5.2 Lap comparison
- Select and compare two valid laps.
- Compare against personal best or a selected reference.
- Distance-aligned telemetry comparison and time-delta trace.
- Speed, throttle, brake, steering, gear and RPM comparisons where recorded.
- Identify where time is gained and lost.
- Theoretical best where the available data supports a defensible calculation.

### 5.3 Corner-by-corner analysis
- Braking point and initial brake application.
- Brake pressure and release profile.
- Trail-braking behaviour where measurable.
- Turn-in point and steering response.
- Minimum speed and apex behaviour.
- Throttle pickup and corner exit.
- Corner-level time gain/loss against the reference.

### 5.4 Racing-line analysis
- Track layout from recorded position data.
- Compare lines between selected laps.
- Corner entry, apex and exit positioning.
- Spatial differences and their relationship to time delta.

Position accuracy and channel availability must be qualified before promising detailed line analysis.

### 5.5 Coaching
**Analysis Coach**
- Reviews completed laps.
- Finds and ranks the largest opportunities.
- Explains the driving behaviour associated with time loss.
- Tracks recurring patterns and improvement over sessions.

**Live Coach**
- Existing Corner Coach functionality presented as part of Performance Hub.
- Continues to use decoded live telemetry.
- Can use analysed reference laps where appropriate.
- Retains existing voice integration and proven coaching calculations.

## 6. Proposed UI navigation

1. **Overview** — session summary, personal best, consistency, lap history and key indicators.
2. **Lap Comparison** — telemetry graphs, delta trace and channel comparisons.
3. **Corner Analysis** — braking, turn-in, apex, throttle pickup and time-loss breakdown.
4. **Racing Line** — track map, line comparison and spatial differences.
5. **Live Coach** — existing Corner Coach, live feedback, voice output and reference selection.
6. **Coaching Report** — prioritized opportunities, recurring mistakes and progress over time.

The UI should follow the existing desktop application's architecture and conventions. Build it after the analysis services and their data contracts are established.

## 7. Implementation roadmap

### Phase 0 — Read-only source and data audit

Inspect the current base branch and document verified facts before implementation.

Audit:
- Stage 1 raw-data fan-out and recorder wiring.
- Recorder format, sample frequency, timestamps, channels and loss/truncation indicators.
- Decoder outputs and Stage 2 subscription/queue semantics.
- Lap/session identity, lap boundaries, validity and out-lap classification.
- Existing Overview consumer and its contracts.
- Existing Race Strategy consumer and its dependencies.
- Existing Corner Coach calculations, reference learning, geometry and voice integration.
- Existing documentation and tests relevant to these paths.

**Deliverables**
- Verified source architecture and data-flow diagram.
- Recording format and channel inventory.
- Recording-to-lap association specification.
- Existing Corner Coach integration map.
- Gap list distinguishing existing functionality from new work.

**Guardrail:** No code changes in this phase.

### Phase 1 — Bounded per-lap capture and persistence

Implement the approved policy in `docs/decisions/PERFORMANCE_HUB_BOUNDED_LAP_RETENTION.md`. This supersedes the earlier assumption that the existing raw Physics recorder is continuously active in normal product runtime.

Requirements:
- Add an independent bounded Stage 2 decoded-sample consumer; do not use the coalesced latest-value UI subscription as a historical capture source.
- Preserve full-rate decoded Physics samples and Graphics position/progress samples with source sequences and timestamps.
- Assemble temporary candidate laps and finalize only after the existing completed-lap event and classification authority confirm the boundary and eligibility.
- Record overflow, gaps, alignment confidence and data-quality metrics; do not silently interpolate or fabricate missing samples.
- Retain the 30 most recent eligible laps per car/track/configuration plus a separately pinned PB when outside that set.
- Keep invalid laps/out-laps as compact diagnostic metadata only.
- Enforce the 2 GiB global storage budget and 365-day default age limit without evicting pinned PB references.
- Use atomic finalization, crash recovery and a single storage owner.
- Expose read-only lap queries through a Performance Hub service.
- Keep capture and storage off Stage 1, acquisition, decoder hot paths, Overview, Race Strategy and live coaching.

**Deliverable:** A tested bounded archive of identifiable, quality-qualified per-lap Physics traces and Graphics trajectories, with retention and recovery.

### Phase 2 — Lap and session reconstruction

Associate recorded samples with existing ACC session and lap identity.

Requirements:
- Reconstruct session and lap boundaries.
- Join recorded sample ranges to existing lap/session metadata.
- Respect the existing valid/invalid and out-lap classification.
- Keep invalid/out-lap data available for diagnostics but exclude it from valid-lap rankings.
- Handle pit entry/exit, session transitions and interrupted recordings.
- Make uncertain associations explicit rather than silently guessing.

**Deliverable:** A reliable collection of individually identifiable and classified recorded laps.

### Phase 3 — Telemetry normalization and data quality

Prepare comparable telemetry from the high-resolution source.

Initial channel candidates (availability must be verified in Phase 0):

| Channel | Intended analysis |
|---|---|
| Speed | Braking, corner speed and acceleration |
| Throttle | Application and pickup |
| Brake | Initial braking, release and trail braking |
| Steering | Turn-in and steering corrections |
| Gear | Gear selection and shift behaviour |
| RPM | Engine operating range |
| Position | Track map and racing-line analysis |
| Time / distance | Lap alignment and comparison |

Requirements:
- Normalize units and coordinate conventions.
- Handle missing, invalid and discontinuous samples.
- Establish consistent lap distance/progress.
- Align channels to a common analysis reference.
- Attach data-quality metadata to every lap.
- Prevent unsupported channels from appearing as valid analysis.

**Deliverable:** A normalized lap telemetry model shared by analysis modules.

### Phase 4 — Track model and corner identification

Requirements:
- Establish a track coordinate reference from qualified position data.
- Generate a reusable track layout.
- Identify straights, corners and corner regions.
- Determine corner entry, apex and exit regions.
- Associate braking zones with corners where evidence supports it.
- Maintain stable corner identities across sessions.

**Deliverable:** A reusable track model with identifiable analysis regions.

### Phase 5 — Lap comparison engine

Build the central analysis capability.

Requirements:
- Compare any two eligible laps.
- Compare against personal best or a selected reference.
- Produce a lap time-delta trace.
- Compare speed, throttle, brake, steering, gear and RPM where available.
- Identify braking, minimum-speed and throttle-pickup differences.
- Attribute time gains/losses to lap regions.
- Calculate theoretical best only when the method and source data support it.

**Deliverable:** A tested comparison engine that identifies where time was gained or lost.

### Phase 6 — Corner-by-corner analysis

Build on the track model and comparison engine.

For each corner, calculate supported metrics for:
- Braking point and brake intensity.
- Brake release and trail braking.
- Turn-in.
- Minimum speed and apex.
- Throttle pickup.
- Exit acceleration and speed.
- Time gained/lost against the selected reference.

**Deliverable:** A corner report explaining measurable driving differences and their time impact.

### Phase 7 — Racing-line analysis

Requirements:
- Visualize the recorded track path.
- Compare trajectories between laps.
- Compare corner entry, apex and exit positions.
- Quantify spatial differences.
- Relate line differences to telemetry and time delta where possible.

**Deliverable:** Interactive racing-line comparison, gated by verified position accuracy.

### Phase 8 — Coaching intelligence

Create evidence-based recommendations from analysis outputs.

**Analysis Coach**
- Rank the most important improvement opportunities.
- Explain the measured difference and likely driving implication.
- Distinguish strong evidence from tentative interpretation.
- Identify recurring issues across laps and sessions.
- Track whether previously identified issues improve.

**Live Coach integration**
- Bring the existing Corner Coach under Performance Hub ownership/navigation.
- Preserve its proven live calculations and decoded telemetry input.
- Define an explicit interface for supplying analysed reference data.
- Preserve existing voice behaviour.
- Avoid making Live Coach dependent on the UI or on Race Strategy.

**Deliverable:** Integrated post-session coaching and live coaching, with the existing Corner Coach behaviour retained.

### Phase 9 — Performance Hub UI

Build the six proposed navigation areas after service contracts stabilize:
- Overview.
- Lap Comparison.
- Corner Analysis.
- Racing Line.
- Live Coach.
- Coaching Report.

Requirements:
- Use the existing Qt desktop and React/TypeScript/Vite application structure.
- Keep analysis work off the live telemetry hot path.
- Use efficient loading and caching for recorded laps.
- Clearly show unavailable or low-confidence metrics.
- Keep live coaching responsive while historical analysis is running.

**Deliverable:** Complete Performance Hub experience integrated into the existing application.

### Phase 10 — Validation and optimization

Validate first against existing recordings, then with live ACC sessions.

| Validation | Expected result |
|---|---|
| Read an existing recording | Correct sample order, count and available channels |
| Reconstruct a lap | Correct boundaries and session/lap identity |
| Invalid/out-lap handling | Existing classification respected |
| Compare a lap with itself | Near-zero delta within defined numerical tolerance |
| Compare different laps | Plausible delta and channel alignment |
| Corner analysis | Stable corner regions and repeatable metrics |
| Racing-line comparison | Spatial alignment consistent with source data |
| Live Coach | Existing coaching and voice behaviour preserved |
| Overview | No regression |
| Race Strategy | No regression |
| Long-session analysis | Bounded memory and stable processing |

**Deliverable:** Regression evidence and performance measurements for the completed feature set.

## 8. Dependency and isolation rules

- Overview does not depend on Performance Hub.
- Race Strategy does not depend on Performance Hub.
- Performance Hub does not depend on Overview.
- Performance Hub does not depend on Race Strategy.
- Performance Hub analysis reads the existing persisted high-resolution recordings.
- Lap/session association reuses the existing source of truth for identity and classification.
- Live Coach continues to consume decoded live telemetry through the established Stage 2 path.
- Live Coach may consume analysed references through a defined Performance Hub interface.
- Analysis must not block or slow the live telemetry path.

## 9. Non-negotiable implementation constraints

1. Do not modify Stage 1.
2. Do not create another high-resolution recorder.
3. Do not create another ACC shared-memory acquisition reader.
4. Do not rewrite the existing decoder.
5. Do not change the existing Overview implementation or behaviour.
6. Do not change the existing Race Strategy implementation or behaviour.
7. Do not rewrite proven Corner Coach logic merely to integrate it under Performance Hub.
8. Do not use Race Strategy calculations as Performance Hub analysis inputs.
9. Do not use lightweight decoded telemetry as a substitute for high-resolution lap analysis.
10. Do not assume channels, precision or recording-to-lap joins before verifying them.
11. Keep historical analysis isolated from live telemetry processing.
12. Do not claim a feature is complete until its data availability and validation criteria are satisfied.

## 10. Definition of done

Performance Hub is complete when a user can:
- Select a session and inspect its recorded laps.
- Compare any two eligible laps.
- See where time was gained or lost.
- Inspect measurable corner-specific driving differences.
- Compare racing lines when position data supports it.
- Receive prioritized, evidence-backed coaching recommendations.
- Track improvement across sessions.
- Use the integrated Live Coach with existing real-time and voice behaviour.
- Do all of this without regressions to Overview, Race Strategy, Stage 1 or the existing recording pipeline.

## 11. Immediate next step

Phase 0 is recorded in `docs/PERFORMANCE_HUB_PHASE_0_SOURCE_AUDIT.md`. The bounded-retention decision is recorded in `docs/decisions/PERFORMANCE_HUB_BOUNDED_LAP_RETENTION.md`. Begin Phase 1 by specifying and testing the loss-accounted Stage 2 per-sample delivery contract before implementing candidate capture or persistence.
