# Race Engineer ACC — Greenfield Architecture Proposal

**Document type:** Technical Architecture and Development Proposal  
**Project:** Race Engineer ACC — New Application  
**Status:** Proposed architecture — implementation not yet started  
**Primary objective:** Reliable, high-resolution ACC telemetry acquisition and lap-data recording

---

## 1. Why We Are Starting Again

The existing application has accumulated multiple layers of functionality, fixes and changes. Continuing to modify it risks carrying forward architectural limitations that were not designed for high-resolution telemetry acquisition.

The new application is not another iteration of the old application. We will build a clean application with explicit subsystem priorities:

**Within the telemetry pipeline, acquisition and data integrity come first.** The desktop shell, design system, UI-only Overview migration and independent Hardware workspace can be developed in parallel because they do not depend on ACC acquisition. Telemetry-connected pages and coaching consumers remain downstream of validated acquisition and recording.

We can reuse verified knowledge, algorithms and decisions from the existing project, but we should not blindly copy its architecture or accumulated implementation.

The new application should:
- Capture ACC telemetry at the highest reliable rate available.
- Detect and account for missing source updates.
- Never silently discard telemetry already acquired.
- Record raw telemetry independently of the UI and coaching systems.
- Reconstruct accurate laps, sectors and lap validity.
- Support future analysis and coaching without compromising acquisition.

## 2. Important Technical Limitation

ACC Shared Memory exposes the latest available telemetry state. It is not a guaranteed delivery queue containing every historical Physics update.

This creates an important distinction:

1. **Source-level updates:** Updates published by ACC.
2. **Acquired samples:** Updates actually observed and copied by our application.
3. **Persisted samples:** Acquired samples successfully written to storage.

If ACC publishes several updates between two application reads, intermediate states may already have been overwritten.

Therefore, we must not promise absolute zero source-level packet loss using the Shared Memory interface alone.

Our engineering target is:
- Observe every available source update that our reader can access.
- Detect packet-ID advances and account for unobserved updates.
- Never silently overwrite an acquired sample.
- Ensure every acquired sample is either persisted or explicitly accounted for as a failure.
- Keep acquisition independent of downstream application workloads.

If the source interface itself is insufficient, we will investigate whether a different acquisition mechanism is available. Faster polling alone does not guarantee lossless capture.

## 3. Proposed Architecture

The application will be a **hybrid standalone Windows desktop application**. The main application window will be a native PySide6 host containing QtWebEngine, which renders a locally bundled React + TypeScript frontend. Native Qt remains responsible for floating overlays and the Hardware Companion initially.

The architecture has distinct presentation, service and data layers:

```text
Race Engineer ACC
│
├── Desktop Runtime — Python + PySide6
│   ├── Main window and lifecycle
│   ├── QtWebEngine host
│   ├── Native floating overlays
│   └── Hardware Companion (initially)
│
├── Main Frontend — React + TypeScript + Vite
│   ├── Shared Material Design 3 system
│   ├── Overview
│   ├── Hardware workspace
│   └── Future telemetry-connected pages
│
├── Python Backend
│   ├── HTTP API and SSE event stream
│   ├── Hardware services
│   ├── ACC acquisition
│   ├── Raw recording
│   ├── Lap and sector processing
│   └── Published application state
│
└── User Data
    ├── Configuration
    ├── Raw recordings
    ├── Processed session/lap database
    └── Logs
```

### 3.1 Presentation boundaries

**Main desktop application:** PySide6 owns the Windows application window and lifecycle. QtWebEngine hosts the local frontend. The main application must not open its primary UI in an external browser.

**Browser frontend:** React + TypeScript + Vite owns the main application navigation, pages, shared components, themes and browser-side interaction. It communicates with Python through documented local HTTP APIs and SSE.

**Native Qt surfaces:** Floating overlays remain native Qt/QPainter surfaces to preserve always-on-top, transparency, click-through and compact rendering behaviour. The Hardware Companion also remains native Qt initially. Browser-only layout or effects must not be forced onto these surfaces.

The browser and native Qt surfaces should share the same semantic design-token vocabulary where practical. Native widgets and overlays retain geometry and rendering appropriate to their workflows.

### 3.2 Frontend and design-system boundary

Material Design 3 is the component, layout, typography, interaction and accessibility standard for the main frontend. The approved purple/teal palette in Section 11 of the source project's `docs/UI_REBUILD_ROADMAP.md` remains authoritative and must not be replaced by a generated Material You palette.

The detailed design contract is maintained in [Material Design 3 UI Design System](../design/MATERIAL_DESIGN_3_UI_SPECIFICATION.md). The architecture document references that specification rather than duplicating its colour and component decisions.

### 3.3 Independent backend subsystems

The backend is modular and service-oriented, but remains a single-user desktop application's local runtime. Do not introduce distributed microservices, a network broker or infrastructure such as Kafka/Redis without measured need.

- **Hardware service:** Owns physical device discovery, serial communication, gamepad polling, configuration, calibration and command/status readback. It has no ACC telemetry dependency and must work when ACC is closed.
- **ACC acquisition:** Owns Physics, Graphics and Static Shared Memory reads, timestamps, packet tracking and sample buffering.
- **Raw recorder:** Independently consumes acquired samples and persists raw recordings.
- **Lap processor:** Independently processes completed laps, sectors, validity and quality.
- **Application state:** Publishes typed, read-only state snapshots to frontend and native overlay subscribers. It must not become a second source of telemetry truth.

Hardware operations must never run inside or block the ACC acquisition loop. UI failures must not stop acquisition or recording. A failure in one downstream subsystem must be isolated from unrelated subsystems.

### 3.4 Communication contracts

- React frontend to Python backend: local HTTP for commands, configuration and request/response operations.
- Python backend to browser: SSE for live state and service-status updates.
- Acquisition to recorder/processor: bounded internal queues or buffers with explicit overflow accounting.
- Native Qt components to backend services: direct service interfaces and Qt signals/slots where appropriate; do not duplicate domain logic in widgets.
- Frontend and backend exchange typed, versioned schemas. UI components must not import backend implementation details.

Bind the local server to loopback by default. LAN exposure, if ever required, must be an explicit opt-in and is outside the initial shell requirement.

### 3.5 Service failure and lifecycle behaviour

The desktop host owns orderly startup and shutdown of the local server, backend services, QtWebEngine window and native surfaces. Renderer reload/crash must not terminate the Python runtime or interrupt recording. The frontend must be able to reconnect and retrieve a fresh state snapshot after reload.

Acquisition and raw recording health must be observable independently of frontend health. Non-critical page or hardware-service failures must not take down the entire application.

## 3.6 Live Data Consumers and Selective Best-Lap Persistence

**Authoritative runtime consumer and retention decision:** [ACC Live Data Consumers and Best-Lap Reference — Architecture Decision](../decisions/ACC_LIVE_DATA_CONSUMERS_AND_BEST_LAP_REFERENCE.md).

The application is live-data driven. Overview, native Overlays, live processing and live coaching consume current live Physics, Graphics and Static data through independent downstream consumers and published application state. They do not read recorded session files to obtain current telemetry.

Normal product runtime does not continuously archive every Physics, Graphics and Static sample or every lap/session. Candidate lap data is assembled temporarily from live observations. Only the best eligible lap for each car, track and weather-condition combination is retained as a coaching reference; a better eligible candidate replaces the existing reference.

The existing raw acquisition/recording infrastructure remains available for explicit engineering validation, regression and diagnosis. It is not the normal product session archive and is not the source for live UI or coaching data. The linked decision defines consumer responsibilities, candidate capture, reference replacement, failure isolation and unresolved weather-compatibility details.

## 4. Acquisition Layer — Highest Priority

This is the most important subsystem in the application.

It will have a dedicated acquisition thread or process, with no unnecessary work inside its critical loop.

### 4.1 Responsibilities

The acquisition layer will:
- Read ACC Physics data.
- Read Graphics data independently.
- Read Static data at startup and when required.
- Capture the Physics packet ID.
- Timestamp each observation.
- Copy acquired data into an application-owned snapshot.
- Detect packet-ID changes.
- Publish the snapshot into the acquisition buffer.
- Monitor its own execution time and failures.

### 4.2 What It Must Not Do

The acquisition loop must not:
- Update the dashboard.
- Render maps.
- Run coaching calculations.
- Reconstruct laps.
- Calculate lap validity.
- Serialize JSON.
- Write individual samples to disk.
- Perform database operations.
- Wait for downstream consumers.
- Acquire application-wide locks.

The objective is to keep the acquisition path short and predictable.

### 4.3 Timestamping

Every acquired sample should have:

| Field | Purpose |
|---|---|
| `capture_sequence` | Application-generated monotonic sequence number |
| `acc_physics_packet_id` | Physics packet ID observed from ACC |
| `read_start_ns` | Start of the acquisition read |
| `read_complete_ns` | Completion of the read |
| `capture_timestamp_ns` | Monotonic capture timestamp |
| `persist_timestamp_ns` | Time the sample was persisted, recorded separately |

Use a monotonic high-resolution clock for measuring intervals and execution duration.

Wall-clock UTC timestamps should also be available in recording metadata and filenames so recordings can be identified and correlated with test sessions.

## 5. Acquisition Buffer

A preallocated bounded ring buffer will separate telemetry acquisition from downstream processing.

### Requirements
- Fixed capacity configured for the expected acquisition rate and worst-case consumer delays.
- No silent overwrite of unread samples.
- Explicit overflow detection and counters.
- Queue depth and high-water-mark monitoring.
- Independent consumers.
- Predictable memory usage.
- Clear shutdown and drain behaviour.

If the buffer becomes full, the application must report the failure explicitly. It must not silently discard old or new samples and report a successful recording.

The buffer size should be selected through measured load testing, not guesswork.

## 6. Independent Telemetry Streams

Physics, Graphics and Static data have different update characteristics and should not be treated as one uniform stream.

### Physics

Highest acquisition priority. Capture:
- Physics packet ID.
- Vehicle speed.
- Position and motion data.
- Steering.
- Throttle and brake.
- Gear and RPM.
- Tyre and suspension values where available.
- Other useful Physics fields.

### Graphics

Capture independently and preserve:
- Graphics packet ID.
- Current lap information.
- Completed lap information.
- Sector boundary timing.
- Session state.
- Track status.
- ACC-provided lap validity.
- Other relevant Graphics fields.

### Static

Read at startup and refresh only when necessary. Capture:
- Car information.
- Track information.
- Session configuration.
- Available vehicle and track metadata.

The application must preserve the original timestamps and packet IDs for each stream. It must not invent synchronization between Physics and Graphics observations.

## 7. Raw Telemetry Recorder

Raw telemetry recording is an independent consumer of the acquisition buffer. It must not block the acquisition thread.

### 7.1 Storage Format

Use an append-oriented binary recording format for high-frequency raw samples. Avoid writing one JSON object per sample during the critical acquisition path.

The recorder should:
- Batch records into blocks.
- Preserve capture sequence numbers.
- Preserve ACC packet IDs.
- Store timestamps.
- Include block sequence numbers and integrity checks.
- Flush data in controlled batches.
- Recover complete blocks after an interrupted recording.
- Report write failures and retries.

Human-readable JSON summaries and CSV exports can be generated after recording.

### 7.2 Recording Priority

The raw telemetry recorder has higher priority than dashboard updates, map processing, coaching, visualizations and optional analysis.

The recorder must receive acquired data independently, so a slow dashboard or coaching calculation cannot cause it to miss data.

### 7.3 Recording Metadata

Every recording should include:
- Unique recording ID.
- UTC start and end timestamps.
- Application version.
- Recording format version.
- ACC session information.
- Car and track information when available.
- Sample counts.
- Packet-ID range.
- Buffer overflow count.
- Recorder error count.
- Finalization status.

Recording filenames should include a timestamp and unique identifier.

## 8. Lap and Sector Reconstruction

**Authoritative technical decision:** The validated ACC lap timing, sector reconstruction, lap-boundary correlation, validity rules, five-lap regression fixture and storage-migration safeguard are specified in [ACC Lap Time, Sector Time and Lap Validity — Technical Decision](../decisions/ACC_LAP_TIMING_SECTOR_RECONSTRUCTION_AND_VALIDITY.md). That decision governs detailed lap-processing behaviour and must be preserved by future implementations and migrations. The summary below is not a substitute for its exact requirements.

Lap processing must operate downstream from acquisition and raw recording. It must never control or interrupt the acquisition loop.

### 8.1 Authoritative ACC Information

Use ACC Shared Memory as the authority for:
- Completed lap time.
- Cumulative sector boundary times.
- ACC track-rule validity.

The application should not replace authoritative ACC timing with a reconstructed estimate when ACC has supplied the completed result.

### 8.2 Sector Calculation

Given cumulative sector boundaries:
- S1 = C1
- S2 = C2 − C1
- S3 = Lap time − C2

Calculate in milliseconds before converting to display format.

### 8.3 Boundary Handling

Lap boundaries may not always align neatly with recording boundaries.

The application must:
- Preserve boundary metadata.
- Associate partial fragments with the correct completed lap.
- Avoid counting a boundary fragment as an additional completed lap.
- Preserve raw samples even when lap classification is uncertain.

### 8.4 Lap Validity

ACC validity must never be upgraded by application-side calculations.

| ACC validity | Application quality | Final classification |
|---|---|---|
| Invalid | Any | Ineligible |
| Unknown | Any | Review |
| Valid | Pass | Eligible |
| Valid | Fail | Ineligible |
| Valid | Inconclusive | Review |

Out laps should remain available in raw recordings for debugging but should not automatically appear as completed timed laps in lap history.

## 9. Data Integrity and Loss Accounting

This application must make data loss measurable.

The following counters should be maintained:

| Metric | What it tells us |
|---|---|
| ACC packet-ID advances | Observed source counter progression |
| Capture sequence count | Samples acquired by the application |
| Packet-ID gaps | Potentially unobserved source updates |
| Buffer overflow count | Samples lost before downstream consumption |
| Recorder write failures | Persistence problems |
| Persisted sample count | Samples successfully written |
| Block checksum failures | Recording integrity problems |
| Consistency retries | Reads requiring additional verification |
| Queue high-water mark | Maximum buffer usage |
| Acquisition duration | Time spent acquiring a sample |
| Acquisition interval | Time between reader iterations |

The application must distinguish:

**Source-level missed updates:** ACC's packet ID advanced between observations.

**Application-level dropped samples:** A sample was acquired but subsequently lost inside our application.

These are different problems and must never be reported as the same metric.

### Required Reconciliation

At recording finalization:

`Acquired samples = Persisted samples + Explicitly accounted application losses`

Any mismatch must be reported as a recording-integrity failure.

Packet-ID gaps should be reported separately. A packet-ID difference greater than one is not automatically proof of packet loss because the source counter may advance faster than the application's sampling cadence.

## 10. Main Frontend and Live Application

The main application UI is a React + TypeScript frontend built with Vite and hosted inside the PySide6/QtWebEngine desktop window. It is not an external-browser application.

The frontend has two distinct operating stages:

1. **UI migration stage:** Overview and Hardware pages can be developed and accepted independently using mock data/local state or their independent hardware service. They do not need ACC acquisition to be implemented first.
2. **Telemetry integration stage:** After acquisition and recording pass reliability validation, telemetry-connected pages can subscribe to published application state through the API/SSE boundary.

The Overview UI migration is visual and interaction-focused: tile layout/editor, themes, selection, ordering, pinning, resizing and visual states. During this stage it must use mock values/local UI state and must not connect to ACC Shared Memory, session history, lap processing or a legacy dashboard API.

The Hardware workspace is complete and independent. It includes pedal setup and physical readings, pedal curves, calibration, sensor configuration, C3 handbrake setup, gamepad input testing, serial receiver discovery/connection/reconnection, device management, command dispatch and status readback. It communicates with physical hardware through the Hardware service and never consumes ACC game telemetry.

When live telemetry integration is introduced, the frontend should:
- Display current vehicle/session/lap state and relevant telemetry.
- Show acquisition and recording health.
- Distinguish live, stale, disconnected, unavailable and error states.
- Reconnect without restarting acquisition or recording.
- Render at a suitable UI cadence (for example 20–30 FPS) without requiring every acquired sample to be drawn.

The UI remains a downstream consumer. It must never enter the acquisition critical path.

## 11. Technology Strategy

Start with a clean Python application and a well-defined acquisition boundary.

Python can initially be used for:
- ACC Shared Memory integration.
- Acquisition orchestration.
- Ring buffer implementation.
- Raw recording.
- Lap reconstruction.
- Data processing.
- Dashboard integration.

A native C++ or Rust acquisition component should only be introduced if profiling proves that Python cannot meet the required acquisition performance.

If that becomes necessary, the native component should have a narrow interface and pass acquired snapshots or batches to the rest of the application.

Do not rewrite the entire application in C++ or Rust without measured justification.

## 12. Proposed Project Structure

The following is the proposed physical layout. Keep subsystem ownership explicit while allowing implementation details to evolve.

```text
Race-Engineer-ACC-New/
├── src/
│   ├── app/
│   │   ├── main.py
│   │   ├── desktop_host.py
│   │   └── lifecycle.py
│   ├── api/
│   │   ├── routes/
│   │   ├── schemas/
│   │   └── events.py
│   ├── hardware/
│   │   ├── services/
│   │   ├── protocols/
│   │   ├── models/
│   │   ├── configuration/
│   │   └── tests/
│   ├── acc/
│   │   ├── shared_memory/
│   │   ├── acquisition/
│   │   ├── models/
│   │   └── tests/
│   ├── recording/
│   ├── processing/
│   ├── storage/
│   ├── application_state/
│   ├── overlays/
│   └── common/
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── design-system/
│   │   │   ├── tokens/
│   │   │   ├── components/
│   │   │   └── theme/
│   │   ├── pages/
│   │   │   ├── overview/
│   │   │   ├── hardware/
│   │   │   └── future/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── components/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
│
├── user_data/
│   ├── config/
│   ├── recordings/
│   ├── database/
│   └── logs/
├── tests/
├── docs/
└── requirements*.txt
```

### 12.1 Storage ownership

- Hardware and application preferences: versioned JSON configuration.
- Raw ACC telemetry: append-oriented binary recordings with metadata, integrity checks and recovery.
- Processed sessions, laps and sectors: SQLite.
- Logs: rotating files.
- Frontend build output: bundled static assets loaded by the desktop host.

Keep user-generated recordings, databases and logs outside version control. Do not store high-frequency raw samples as individual JSON objects.

## 13. Development Roadmap

The desktop shell and UI migration are a separate delivery track from the telemetry foundation. They may progress independently, provided the defined service boundaries are respected.

### Phase 1 — Desktop Host and Frontend Proof of Concept

Build:
- PySide6 main window.
- QtWebEngine embedded view loading a local bundled shell route.
- Local static asset strategy and frontend routing.
- Python host lifecycle and orderly shutdown.
- Renderer reload/crash isolation.
- Windows QtWebEngine runtime and packaging proof.

**Acceptance criteria:**
- Main application opens inside its own Windows window.
- No external browser is required for the main UI.
- Frontend reload does not terminate the Python host.
- QtWebEngine dependencies work in a Windows release-style build.

### Phase 2 — Material Design 3 Foundation

Build:
- React + TypeScript + Vite foundation.
- Narrow persistent navigation rail and compact top app bar.
- Light/dark themes using the exact approved Section 11 palette.
- Semantic token model and component token mapping.
- Component showcase for cards, buttons, fields, selectors, tabs, dialogs, tables, chips and tooltips.
- Keyboard, focus, reduced-motion, contrast and DPI review.

**Acceptance criteria:**
- No replacement blue/teal seed palette in the new shell.
- Approved palette values remain exact.
- Component states are demonstrated and reviewed.
- Browser/native semantic token vocabulary is documented.
- Representative window sizes and Windows scaling are reviewed.

### Phase 3 — Overview UI Migration

Migrate the complete Overview UI and its visual interactions:
- Tile layout and editor.
- Tile selection, ordering, pinning and resizing.
- Themes and visual states.
- Mock telemetry values and local UI state only.

**Acceptance criteria:**
- Overview is visually and behaviourally reviewed.
- No ACC telemetry, legacy dashboard API, session history or recording dependency is introduced.

### Phase 4 — Complete Hardware Workspace Migration

Migrate the complete Hardware workspace and independent Hardware service:
- Pedal setup and physical readings.
- Pedal curves and calibration.
- Sensor configuration.
- C3 handbrake setup and calibration.
- Gamepad input testing.
- Serial receiver discovery, connection/reconnection and device management.
- Command dispatch and authoritative status readback.
- Native Hardware Companion integration where required.

**Acceptance criteria:**
- Hardware functions when ACC is closed.
- Hardware UI and Companion share service/protocol logic.
- Hardware operations never run inside the ACC acquisition loop.
- Serial and gamepad workflows pass isolated tests and target-Windows device tests.

### Phase 5 — ACC Acquisition Prototype

Build:
- ACC connection.
- Independent Physics, Graphics and Static readers.
- Packet-ID tracking.
- Timestamping.
- Acquisition diagnostics.

**Acceptance criteria:**
- Stable connection and reconnection.
- Measured reader frequency and execution time.
- Packet-ID progression recorded.
- No unexplained acquisition-thread exceptions.

### Phase 6 — Buffer and Raw Recording

Implement bounded buffers, independent raw recording, binary format, checksums, metadata, recovery and finalization.

**Acceptance criteria:**
- No silent overwrite of unread samples.
- Every acquired sample is persisted or explicitly accounted for.
- Recorder delays do not block acquisition.
- Interrupted recordings recover to the last complete valid block.

### Phase 7 — Recording Validation

Validate sample counts, packet IDs, timestamp intervals, source gaps, buffer overflow, persistence integrity and stream behaviour under long sessions and injected delays.

**Acceptance criteria:**
- Reproducible reports.
- No unexplained acquired/persisted mismatch.
- Source-level gaps and application-level drops remain distinct.

### Phase 8 — Lap and Sector Processing

Implement lap boundaries, completed-lap association, sector timing, ACC validity handling, out-lap classification and partial-record handling.

**Acceptance criteria:**
- Lap times and sector times match ACC.
- ACC validity is preserved.
- Boundary fragments are not counted as extra laps.
- Out laps remain in raw recordings but are excluded from timed lap history.

### Phase 9 — Live Telemetry Integration

Connect telemetry-connected frontend pages and native overlays to published application state through documented interfaces.

**Acceptance criteria:**
- UI stalls do not affect acquisition or recording.
- Frontend reconnects without restarting the recorder.
- Telemetry freshness and acquisition/recording errors are visible.
- Unavailable telemetry is not presented as zero.

### Phase 10 — Analysis and Coaching

Add lap comparisons, corner analysis, Performance Coach, reference laps and historical analysis. These consumers operate on persisted or published data, never on the acquisition critical path.

This sequence does not require waiting for telemetry completion before building the UI-only Overview or independent Hardware workspace.

## 14. Testing Strategy

Testing must include more than normal driving sessions.

Required scenarios:
1. ACC starts before the application.
2. Application starts before ACC.
3. ACC disconnects during recording.
4. Application closes normally.
5. Application terminates unexpectedly.
6. Dashboard becomes unresponsive.
7. Disk writes become temporarily slow.
8. Downstream processing is deliberately delayed.
9. Acquisition buffer approaches capacity.
10. Long sessions with multiple completed laps.
11. Pit entry and exit.
12. Out laps and invalid laps.
13. Lap-boundary fragments.
14. ACC session changes.

Use synthetic telemetry and controlled fault injection wherever possible. Do not rely exclusively on driving sessions to test reliability.

## 15. Scope Boundaries and Non-Goals

The initial **ACC telemetry foundation** does not implement Performance Coach, Corner Coach, advanced telemetry analysis, historical analytics, session comparisons, complex maps, RPM LED integration or voice coaching.

The phrase "hardware configuration is a non-goal" applies only to the initial ACC acquisition/recording foundation. It does **not** exclude the independently scoped Hardware workspace from the new application.

The application delivery scope includes:
- The hybrid desktop shell and embedded main frontend.
- The Material Design 3 design system.
- The Overview UI migration using mock values/local state.
- The complete independent Hardware workspace and its required physical-device services.
- Native Qt overlays and Hardware Companion boundaries.

The telemetry foundation is developed separately and later connected to telemetry-aware pages through published application state.

Do not interpret the telemetry roadmap's staged dashboard integration as a prohibition on UI-only frontend development.

## 16. Architectural Rules

These rules apply throughout development:

1. Acquisition is the highest-priority subsystem.
2. No dashboard or coaching operation may block acquisition.
3. No acquired sample may be silently discarded.
4. Source-level gaps and application-level drops must be distinguished.
5. Raw telemetry is preserved before optional analysis.
6. ACC lap timing and validity remain authoritative.
7. Every recording must be independently inspectable.
8. Every major subsystem must have isolated tests.
9. Do not introduce complexity without measured need.
10. Do not carry forward old application architecture merely for convenience.
11. Do not change a proven subsystem to solve a problem in an unrelated subsystem.
12. Every architectural decision must be documented.
13. The main application UI runs inside the QtWebEngine desktop host; it must not depend on an external browser.
14. Hardware services are independent of ACC telemetry and share one implementation across browser UI and native Hardware Companion.
15. UI-only Overview development may use mock data and must not wait for telemetry acquisition.
16. The Material Design 3 specification is authoritative for visual and interaction decisions; the approved Section 11 palette must remain unchanged.

## 17. Final Engineering Objective

The finished application should provide a trustworthy telemetry foundation.

When a lap is recorded, we should be able to answer:
- Which ACC Physics updates did we observe?
- Which packet IDs did we observe?
- How frequently did we acquire them?
- Were any source updates apparently missed?
- Did the application lose any acquired samples?
- Were all acquired samples persisted?
- Is the recording intact?
- Can the lap and sector times be reproduced?
- Does the result agree with ACC?

If we cannot answer these questions, the application is not yet ready for advanced coaching or performance analysis.

**Final decision:** Build a hybrid standalone Windows desktop application using a PySide6/QtWebEngine host and a React + TypeScript + Vite frontend. Keep native Qt for floating overlays and the Hardware Companion initially. Develop the M3 frontend foundation, UI-only Overview and independent Hardware workspace without waiting for ACC telemetry. In parallel, establish ACC acquisition, buffering, raw recording and integrity validation; add lap processing next. Connect telemetry-aware pages only after the telemetry foundation has passed its reliability tests. The detailed visual contract is maintained in [MATERIAL_DESIGN_3_UI_SPECIFICATION.md](../design/MATERIAL_DESIGN_3_UI_SPECIFICATION.md).
