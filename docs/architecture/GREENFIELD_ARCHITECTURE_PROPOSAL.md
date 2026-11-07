# Race Engineer ACC — Greenfield Architecture Proposal

**Document type:** Technical Architecture and Development Proposal  
**Project:** Race Engineer ACC — New Application  
**Status:** Proposed architecture — implementation not yet started  
**Primary objective:** Reliable, high-resolution ACC telemetry acquisition and lap-data recording

---

## 1. Why We Are Starting Again

The existing application has accumulated multiple layers of functionality, fixes and changes. Continuing to modify it risks carrying forward architectural limitations that were not designed for high-resolution telemetry acquisition.

The new application is not another iteration of the old application. We will build a clean application with a different priority:

**Telemetry acquisition and data integrity come first. Everything else comes afterwards.**

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

The application will use separate subsystems with clearly defined responsibilities.

```text
                 ASSETTO CORSA COMPETIZIONE
                           |
                  ACC Shared Memory
                           |
                           v
              +------------------------+
              |  ACC Acquisition Layer |
              | Physics reader         |
              | Graphics reader        |
              | Static data reader     |
              | Packet ID tracking     |
              | Timestamping           |
              +------------------------+
                           |
                           v
              +------------------------+
              |   Acquisition Buffer   |
              | Preallocated ring      |
              | Capture sequence       |
              | Packet ID              |
              | Monotonic timestamps   |
              | Overflow monitoring    |
              +------------------------+
                           |
                 Independent consumers
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       Raw Recorder   Lap Processor   Live State
             |             |             |
             v             v             v
       Binary Files    Lap/sector     Dashboard
                       reconstruction   UI
             |             |
             v             v
       File Validator  Quality Evaluator
                           |
                           v
                    Analysis / Coaching
```

The acquisition subsystem must not depend on the dashboard, lap processor, coaching engine or storage implementation.

A failure in one downstream subsystem must not stop telemetry acquisition.

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

## 10. Dashboard and Live Application

The UI will be a consumer of the latest published application state. It must never be in the acquisition path.

The dashboard should:
- Display live telemetry.
- Show current lap and lap state.
- Display RPM and shift information.
- Show pedal and steering values.
- Display relevant vehicle and session information.
- Show acquisition and recording health.
- Indicate when telemetry is stale or recording has failed.

The UI may update at a lower frequency than telemetry acquisition. For example, the acquisition system may observe data at a higher rate while the dashboard renders at 20–30 FPS.

This is intentional. The dashboard does not need to display every acquired sample.

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

```text
race-engineer-acc/
|
+-- app/
|   +-- main.py
|   +-- application.py
|   +-- lifecycle.py
|
+-- acquisition/
|   +-- acc_connection.py
|   +-- physics_reader.py
|   +-- graphics_reader.py
|   +-- static_reader.py
|   +-- snapshot.py
|   +-- acquisition_buffer.py
|   +-- packet_tracker.py
|   +-- diagnostics.py
|
+-- recording/
|   +-- binary_writer.py
|   +-- binary_reader.py
|   +-- block_format.py
|   +-- integrity.py
|   +-- recovery.py
|   +-- metadata.py
|
+-- processing/
|   +-- lap_detector.py
|   +-- lap_reconstruction.py
|   +-- sector_timing.py
|   +-- lap_validity.py
|   +-- out_lap_detection.py
|
+-- telemetry/
|   +-- models.py
|   +-- conversion.py
|   +-- live_state.py
|
+-- dashboard/
|   +-- frontend/
|   +-- backend/
|
+-- analysis/
|   +-- lap_quality.py
|   +-- telemetry_comparison.py
|
+-- tests/
|   +-- acquisition/
|   +-- recording/
|   +-- processing/
|   +-- integration/
|
+-- docs/
    +-- architecture/
    +-- decisions/
    +-- validation/
```

This is a proposed logical structure. We can adjust the physical layout as implementation details become clearer.

## 13. Development Roadmap

Development should proceed in controlled stages. Each stage must be tested before the next one begins.

### Phase 1 — ACC Acquisition Prototype

Build only:
- ACC connection.
- Physics reader.
- Graphics reader.
- Static reader.
- Packet-ID tracking.
- Timestamping.
- Acquisition diagnostics.

No dashboard, coaching or lap analysis.

**Acceptance criteria:**
- Stable ACC connection and reconnection.
- Measured reader frequency and execution time.
- Packet-ID progression recorded.
- No unexplained acquisition-thread exceptions.
- Repeatable diagnostic results across multiple sessions.

### Phase 2 — Buffer and Raw Recording

Implement:
- Preallocated acquisition buffer.
- Independent raw recorder.
- Binary recording format.
- Block checksums.
- Recording metadata.
- Recovery and finalization.

**Acceptance criteria:**
- Buffer never silently overwrites unread samples.
- Recorder can operate under simulated slow disk conditions.
- Every acquired sample is persisted or explicitly accounted for.
- Interrupted recordings can be recovered to the last complete valid block.
- Recorder performance does not block acquisition.

### Phase 3 — Recording Validation

Build offline tools to inspect recordings.

Validate:
- Sample counts.
- Packet-ID progression.
- Timestamp intervals.
- Missing source updates.
- Buffer overflow.
- Persistence integrity.
- Physics and Graphics stream behaviour.

Test with long sessions and deliberately introduced downstream delays.

**Acceptance criteria:**
- Reliable loss accounting.
- Reproducible reports.
- No unexplained mismatch between acquired and persisted samples.

### Phase 4 — Lap and Sector Processing

Implement:
- Lap boundary detection.
- Completed lap association.
- Sector timing.
- Lap validity.
- Out-lap classification.
- Partial-record handling.

**Acceptance criteria:**
- Lap times match ACC.
- Sector times match ACC.
- ACC validity is preserved.
- Boundary fragments are not counted as extra laps.
- Out laps do not become timed laps.

### Phase 5 — Live Dashboard

Only after acquisition and recording are proven stable, implement the live UI.

**Acceptance criteria:**
- UI stalls do not affect acquisition.
- Dashboard can reconnect without restarting the recorder.
- Telemetry freshness is visible.
- Acquisition and recording errors are visible.

### Phase 6 — Analysis and Coaching

Add:
- Lap comparisons.
- Corner analysis.
- Performance Coach.
- Reference laps.
- Driving recommendations.
- Historical analysis.

All analysis must operate on persisted or independently published telemetry, not on the acquisition thread.

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

## 15. Explicit Non-Goals

The first development stage will not include:
- Performance Coach.
- Corner Coach.
- Advanced dashboard.
- Historical analytics.
- Session comparisons.
- Complex maps.
- Hardware configuration.
- RPM LED integration.
- Voice coaching.
- Large UI feature sets.

These features can be developed later without compromising the acquisition foundation.

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

**Final decision:** Build a new application from a clean foundation. Establish acquisition, buffering, recording and integrity validation first. Add lap processing next. Build the dashboard and coaching systems only after the telemetry foundation has passed its reliability tests.
