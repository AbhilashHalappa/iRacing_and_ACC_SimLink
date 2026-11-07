# ACC Lap Time, Sector Time and Lap Validity — Technical Decision

**Project:** Race-Engineer-ACC Lite / Race Engineer ACC New  
**Decision date:** 7 November 2026  
**Status:** Validated against ACC  
**Scope:** High-resolution telemetry recording, lap timing reconstruction, lap-boundary correlation and validity classification

---

## 1. Decision

ACC Shared Memory is the authoritative source for lap timing, sector timing and track-rule lap validity.

The application must capture ACC's original timing and validity information and reconstruct individual sector durations from ACC Graphics updates. It must not independently decide that an ACC-invalid lap is valid.

High-resolution recording is the common telemetry foundation for future lap analysis and performance features. Raw observations and the relationship between completed laps and recording fragments must remain traceable.

This is a validated engineering requirement, not an optional algorithm or a proposed estimate.

## 2. ACC Source Fields and Recording Contract

The validated high-resolution JSONL recording contains a top-level lap record with separate `graphics_updates` and `samples` collections.

The following ACC Graphics fields are relevant and must be retained in the raw recording:

| ACC field | Purpose |
|---|---|
| `sector` | Current ACC sector index (0, 1 or 2) |
| `last_sector_time_ms` | ACC timing value observed at sector transitions |
| `current_time_ms` | Current lap elapsed time |
| `last_time_ms` | Completed lap time |
| `is_valid_lap` | ACC lap validity flag |
| `current_time_str` | Human-readable current lap time |
| `last_time_str` | Human-readable completed lap time |

The completed lap record must also retain:

- `lap_time_ms`
- `lap_valid`
- `validity_observations`
- `lap_number`
- `native_lap_number`
- `lap_sequence`
- `finish_reason`

Do not reduce the recording to reconstructed values alone. Original Graphics observations, timing values, validity observations and lap-boundary metadata are required for traceability and future reprocessing.

## 3. Sector Time Reconstruction

ACC's recorded sector-boundary timing values are cumulative elapsed times in the observed recording. They must not be interpreted directly as individual sector durations.

Let:

- `T1` = cumulative elapsed time at the end of Sector 1.
- `T2` = cumulative elapsed time at the end of Sector 2.
- `TL` = ACC completed lap time.

Calculate individual sector durations in milliseconds:

**Sector 1**

`S1 = T1`

**Sector 2**

`S2 = T2 - T1`

**Sector 3**

`S3 = TL - T2`

Only format the results for display after the millisecond calculations.

### 3.1 Validated Lap 1 example

- Completed lap time: 117,042 ms
- End of Sector 1: 37,752 ms
- End of Sector 2: 78,500 ms

Therefore:

| Sector | Calculation | Duration |
|---|---:|---:|
| S1 | 37,752 | 37.752 s |
| S2 | 78,500 − 37,752 | 40.748 s |
| S3 | 117,042 − 78,500 | 38.542 s |

The three sector durations must sum exactly to the completed lap time in milliseconds.

If a required sector boundary or completed lap time is unavailable or unreliable, the affected sector must remain unavailable. Do not invent, interpolate or estimate a split and do not silently substitute a value derived from unrelated samples.

## 4. Lap 3 Boundary Correction

The validation recording exposed a special lap-boundary case. Lap 3 was represented by two records:

| Record | Native lap | Sequence | Samples | Recorded lap time |
|---|---:|---:|---:|---:|
| Main record | 3 | 3 | 5,541 | 1:53.780 |
| Boundary fragment | 3 | 4 | 1 | 1:53.105 |

The main record finished with:

`finish_reason = normalized_start_finish_wrap`

The one-sample boundary fragment finished with:

`finish_reason = native_lap_number_change`

The ACC timing associated with the boundary fragment supplied the correct completed Lap 3 time: **1:53.105**.

The correct Lap 3 sector reconstruction uses:

- S1 cumulative boundary: 36,225 ms
- S2 cumulative boundary: 76,137 ms
- Completed lap time: 113,105 ms

Therefore:

| Sector | Calculation | Duration |
|---|---:|---:|
| S1 | 36,225 | 36.225 s |
| S2 | 76,137 − 36,225 | 39.912 s |
| S3 | 113,105 − 76,137 | 36.968 s |

All three sectors sum to **113,105 ms (1:53.105)**.

### 4.1 Required boundary-correlation behaviour

Lap-boundary records must be correlated before treating each record as an independent completed lap.

A one-sample boundary fragment must not automatically become an additional lap in Lap History, best-lap selection or session statistics. Its ACC timing information must be associated with the correct completed lap.

The implementation must preserve both raw records and their original metadata, while producing one correctly correlated completed-lap result. Correlation must use explicit lap identity/sequence, native lap number, finish reason and the observed ACC timing context; it must not rely on sample count alone or discard the fragment.

This exact normalized start/finish wrap followed by a one-sample native-lap-number-change fragment is a mandatory automated regression case.

## 5. Lap Validity Decision

ACC's validity flag is authoritative for track-rule validity.

| ACC validity | Application classification |
|---|---|
| `true` | Eligible for further quality evaluation |
| `false` | Ineligible — ACC invalidated the lap |
| `null` / unknown | Review — validity cannot be established |

Additional telemetry quality checks may downgrade an ACC-valid lap. They must never upgrade an ACC-invalid or unknown lap.

| ACC validity | Quality result | Final classification |
|---|---|---|
| Valid | Pass | Eligible |
| Valid | Fail | Ineligible |
| Valid | Inconclusive | Review |
| Invalid | Any | Ineligible |
| Unknown | Any | Review |

Lap timing and lap validity are separate concepts. An invalid lap can still have complete and useful timing and telemetry data. Preserve and expose its timing where available while keeping its validity classification ineligible.

For the five-lap validation recording, Lap 4 must remain invalid because ACC reported it as invalid.

## 6. Five-Lap Validation Fixture

**Recording:** `high_resolution_lap_samples_20261107_154001_423382_utc.jsonl`

The following values were reconstructed from recorded ACC timing information and confirmed against ACC's timing display.

| Lap | Lap time | Sector 1 | Sector 2 | Sector 3 | ACC validity |
|---:|---:|---:|---:|---:|---|
| 1 | 1:57.042 | 37.752 s | 40.748 s | 38.542 s | Valid |
| 2 | 1:53.780 | 36.047 s | 40.088 s | 37.645 s | Valid |
| 3 | 1:53.105 | 36.225 s | 39.912 s | 36.968 s | Valid |
| 4 | 1:54.925 | 36.775 s | 41.025 s | 37.125 s | Invalid |
| 5 | 1:54.510 | 36.272 s | 40.358 s | 37.880 s | Valid |

### 6.1 Validation outcome

- All five lap times match ACC.
- All fifteen reconstructed sector times match ACC.
- Lap 4's invalid status matches ACC.
- Lap 3's boundary-fragment timing discrepancy has been identified and reconciled.
- Sector reconstruction uses recorded ACC timing data, not estimated sector durations.

These values must be preserved as deterministic regression-test expectations. A future implementation or storage migration must not silently change them. Any intentional change requires new ACC evidence and an explicitly reviewed decision.

## 7. Raw Data, Storage and Future Consumers

The high-resolution recording must preserve:

1. Original ACC Graphics updates.
2. Original ACC timing values.
3. Original ACC validity observations.
4. Completed lap timing.
5. Reconstructed sector timing, where available.
6. Lap sequence and boundary metadata.
7. The relationship between boundary fragments and completed laps.
8. The distinction between unavailable, unknown and measured values.

Out laps must remain available in raw recordings for debugging but must not appear as completed timed laps in Lap History or Session Summary.

The reconstructed timing and validity data will eventually support:

- Lap History.
- Best-lap selection.
- Performance Hub.
- Corner Coach.
- Telemetry graphs.
- Performance comparisons.
- Overlay timing displays.

### 7.1 Existing 5-metre telemetry storage migration safeguard

The existing 5-metre telemetry storage must not be removed merely because high-resolution capture or a new lap-timing pipeline has been introduced.

Retain it until every relevant consumer has migrated to the replacement data source and its behaviour and tests have been verified. Removal requires an explicit migration decision, consumer-by-consumer coverage and passing regression tests. The high-resolution recording and this lap-timing decision do not by themselves authorize removal of the existing storage.

## 8. Required Automated Tests

The implementation must include automated tests for all of the following:

1. Correct extraction and retention of ACC completed lap times.
2. Sector 1 extraction from the first cumulative boundary.
3. Sector 2 calculation from the difference between cumulative boundaries.
4. Sector 3 calculation from completed lap time minus the second cumulative boundary.
5. Reconstructed sector sum equals completed lap time in milliseconds.
6. ACC-invalid laps remain invalid regardless of quality results.
7. Unknown ACC validity remains Review.
8. Missing or unreliable sector data remains unavailable rather than fabricated.
9. Lap 3-style normalized start/finish wrap and one-sample boundary-fragment correlation.
10. Boundary fragments are not counted as additional completed laps in Lap History or session statistics.
11. Lap timing remains available for ACC-invalid laps when ACC timing is present.

The five-lap fixture in Section 6 must be used as regression data. Tests must assert the exact lap times, all fifteen sector durations and the validity of each lap. The boundary-fragment test must assert that the two raw records produce the single correct Lap 3 result of 1:53.105, not an extra completed lap.

## 9. Final Engineering Decision

**ACC is the authority for lap timing, cumulative sector boundaries and track-rule validity.**

The application reconstructs individual sector durations from ACC's cumulative sector-boundary timing and ACC's completed lap time. It retains the original observations and correlates boundary fragments before producing completed-lap records.

The five-lap validation confirms that this approach reproduces the timing shown by ACC, including the special Lap 3 boundary case and Lap 4 invalid status.

This behaviour is a validated requirement and must be preserved during future high-resolution capture, storage, processing and consumer migrations. The five-lap results and boundary case are regression fixtures, not illustrative values that may be changed without evidence.

---

## 10. Relationship to the Greenfield Architecture

This decision is authoritative for the lap-processing subsystem described in [GREENFIELD_ARCHITECTURE_PROPOSAL.md](../architecture/GREENFIELD_ARCHITECTURE_PROPOSAL.md).

The architecture proposal defines subsystem boundaries and acquisition/recording priorities. This technical decision defines the validated ACC lap timing, sector reconstruction, boundary correlation, validity and storage-migration requirements. If a general architecture summary is less specific than this decision, this decision governs lap-processing behaviour.
