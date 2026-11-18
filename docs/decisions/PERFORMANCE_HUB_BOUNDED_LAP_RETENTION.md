# Performance Hub — Bounded Per-Lap Retention Decision

**Project:** Race Engineer ACC New  
**Decision date:** 18 November 2026  
**Status:** Accepted for Performance Hub  
**Branch:** `feature/performance-hub`  
**Supersedes:** The normal-runtime retention scope in `docs/decisions/ACC_LIVE_DATA_CONSUMERS_AND_BEST_LAP_REFERENCE.md`, only for Performance Hub historical analysis. The existing best-lap reference behaviour remains in force for live coaching unless explicitly changed later.

## 1. Decision

Performance Hub will use **bounded per-lap retention** of completed eligible laps. It will not depend on continuous all-session raw recording, and it will not create a second recorder or a second ACC shared-memory reader.

This decision expands the earlier product persistence contract, which retained only the best lap for each car/track/weather combination. That best-lap reference remains available for existing live coaching. Performance Hub additionally retains a bounded history of eligible lap traces so users can compare selected laps and measure progress across sessions.

## 2. Retention policy

For each car + track + track-configuration combination:

- Retain the **30 most recent completed eligible laps** with full analysis traces.
- Retain the personal-best eligible lap as a **pinned reference**, even when it falls outside the 30 most recent laps.
- A pinned personal-best lap that is already among the 30 recent laps is stored only once.
- Keep compact metadata for invalid laps and out-laps, but do not retain their full high-resolution traces by default.
- Do not retain incomplete, interrupted or unclassifiable candidate traces as completed laps.
- Preserve session identity, session date/time and weather metadata for every retained lap.
- Weather remains metadata for filtering and contextual analysis; it does not create a separate archive partition. The existing live-coaching best-lap reference may continue to use its established car + track + weather identity.

The archive is also subject to a **2 GiB configurable global storage budget** and a **365-day default age limit**. The pinned personal-best reference is protected from ordinary age/count eviction, but it remains subject to explicit user deletion and integrity/recovery rules. When the global budget is reached, evict the oldest non-pinned eligible traces first. If the budget cannot be met without deleting a pinned reference, stop accepting additional traces and report a storage-limit status; never silently delete the pinned reference.

These are initial defaults and must be configuration-backed, visible in diagnostics, and covered by tests.

## 3. Data retained per eligible lap

A retained lap must include enough data to support the committed Performance Hub scope.

### 3.1 Identity and classification

- Stable session/run ID.
- ACC session index and session type as source metadata, not as globally unique identity.
- Completed-lap number within the session.
- Car model/identity.
- Track and track configuration.
- Weather/track-condition snapshot and source timestamps where available.
- Lap time and sector times where authoritative.
- ACC lap validity and existing out-lap classification.
- Completion timestamp and software/schema version.

### 3.2 Physics trace

Retain the existing decoded high-resolution Physics channels required and verified for analysis, including speed, throttle, brake, steering, gear and RPM when present. Preserve each source capture sequence and capture timestamp. Do not fabricate missing channels or interpolate across unmarked gaps.

### 3.3 Graphics trajectory

Retain per-sample normalized track progress and world position (X/Z for the 2D track plane; preserve Y if useful for diagnostics), plus source capture sequence and timestamp. The trajectory must support an overlay of a selected driven lap and a selected reference lap.

The reference line initially means another retained user-driven lap, normally the personal best. Do not label it an ideal or professional-driver line.

### 3.4 Quality and loss metadata

Record:
- Expected and observed sample counts per source stream.
- Missing sequence ranges / queue rejections where detectable.
- Progress coverage, duplicate progress samples and discontinuities.
- Coordinate outliers and rejected points.
- Physics/Graphics association confidence.
- Completeness status and reasons a lap is not eligible for analysis.

A trace with material gaps must be marked degraded or unavailable for affected analysis; it must not be presented as complete.

## 4. Capture and processing architecture

1. Stage 1 remains unchanged.
2. Existing acquisition and decoders remain the only ACC shared-memory acquisition and decode path.
3. Performance Hub adds an independent **bounded Stage 2 decoded-sample consumer** for candidate-lap capture. It must receive the required per-sample observations, not merely the coalesced latest UI snapshot.
4. The consumer uses bounded queues and explicit loss accounting. It must never block acquisition, decoder workers, Overview, Race Strategy or the live coaching path.
5. Candidate traces are assembled temporarily while a lap is in progress.
6. Existing completed-lap events, ACC validity and the existing out-lap observer are the classification authority. Do not add another lap-validity or out-lap detector.
7. On confirmed lap completion, finalize the candidate only when identity, classification, sample coverage and stream association are sufficiently reliable.
8. Persist eligible candidates asynchronously through a single Performance Hub storage owner.
9. Apply count, age and global-size retention after successful durable commit.
10. Expose archive queries through a Performance Hub service. The UI must never open telemetry files or databases directly.

The existing raw Physics and Graphics recorder formats remain engineering/validation tools. This decision does not enable continuous raw recording in normal runtime and does not route Performance Hub through a second raw recorder.

## 5. Physics/Graphics association

Physics and Graphics are independent source streams with different sampling rates and timestamps. Do not join them by array index or assume they were captured simultaneously.

Every sample retains its source timestamp and sequence. The lap-capture layer associates observations with the same logical session/lap using the existing lap-boundary source and validated timestamp/progress rules. Any time-based alignment used for graphs must preserve the original source observations and report interpolation or alignment uncertainty.

For Racing Line, Graphics position is the direct spatial source. Physics channels are aligned for interpretation of braking, throttle, steering and speed at corresponding progress positions. The system must not imply spatial accuracy beyond the measured Graphics coordinate quality.

## 6. Storage and integrity

The storage implementation must provide:
- A versioned schema and explicit migration path.
- Atomic lap finalization: incomplete writes never appear as complete laps.
- Crash recovery and integrity checks.
- One storage writer/owner; analysis readers use read-only access or service queries.
- Bounded memory during capture and analysis.
- Explicit status for storage full, write failure, corrupt lap and recovery.
- Deletion/eviction that never leaves dangling personal-best references.
- A user-visible way to inspect and manage retained-lap storage before adding automatic cleanup controls.

The exact physical representation (SQLite metadata plus compressed trace files, or an equivalent transactional layout) is an implementation choice to be validated against expected write rate, query latency and storage footprint. Do not commit to a format before measuring a representative lap.

## 7. Required acceptance tests

1. A completed valid lap is retained with correct session/lap identity.
2. The existing ACC-invalid and out-lap classifications are respected; those laps do not enter valid-lap rankings.
3. Physics and Graphics capture loss is measurable and appears in lap quality metadata.
4. Candidate capture cannot block Stage 1, decoders, Overview, Race Strategy or live coaching.
5. A lap is not marked complete until all required trace writes are durable.
6. Restart/crash during candidate capture does not create a false completed lap.
7. Restart/crash during finalization recovers either the previous committed state or the new complete lap, never a partial one.
8. The archive retains no more than 30 recent eligible laps per car/track/configuration, plus a separately pinned PB only when it is not already in that set.
9. Global storage and age limits evict only eligible non-pinned traces.
10. Storage exhaustion preserves the pinned PB and reports that new retention has stopped.
11. A selected lap can be read back with sample order, timestamps, channels and quality metadata intact.
12. A lap compared with itself yields a zero/near-zero time and spatial delta within defined tolerances.
13. The racing-line view can overlay two retained user laps in the same track coordinate frame.
14. Existing Overview, Race Strategy and live coaching regression tests remain unchanged and pass.

## 8. Implementation sequence

1. Define the typed candidate-lap and retained-lap data contracts.
2. Design the bounded Stage 2 per-sample delivery contract and overflow/loss reporting.
3. Implement the candidate-lap assembler using existing lap events and classification.
4. Validate Physics/Graphics association and coordinate quality with controlled ACC runs.
5. Benchmark representative per-lap storage and select the physical persistence format.
6. Implement atomic storage, read-only query service, retention and recovery.
7. Implement analysis readers and the Racing Line overlay.
8. Add multi-session progress and coaching consumers after the archive contract is stable.

## 9. Non-negotiable constraints

- No Stage 1 changes.
- No second ACC shared-memory reader.
- No second decoder.
- No second recorder.
- No use of the coalesced UI snapshot as a lossless high-rate capture source.
- No blocking disk/database work on acquisition, decoder or UI threads.
- No change to Overview or Race Strategy behaviour.
- No replacement of the existing lap-validity or out-lap authorities.
- No unsupported claims of spatial precision or telemetry completeness.

**Decision summary:** Performance Hub retains a bounded, quality-qualified history of completed eligible laps, plus a pinned personal best. This enables selected-lap comparison, racing-line overlays and multi-session progress while preserving the existing live-data architecture and avoiding unlimited session recording.
