# ACC Graphics Field Coverage Audit

**Target:** ACC 1.10.4; observed shared-memory identifiers `smVersion=1.9`, `acVersion=1.7`  
**Candidate layout:** v1.8.12-derived Graphics structure, pack=4, 87 fields, 1,588 bytes  
**Audit scope:** field coverage and evidence reconciliation only. This document does not sign off the Shared Memory 1.9 ABI and does not authorize production decoding.

## Evidence sources and rules

### Previous ACC application reference — exclusive source

Previous application-level field use and user-confirmed behaviours in this audit are taken **only** from the `diagnostic/high-res-capture-2026-11-07` branch of `AbhilashHalappa/Race-Engineer-ACC`:

- [Diagnostic branch](https://github.com/AbhilashHalappa/Race-Engineer-ACC/tree/diagnostic/high-res-capture-2026-11-07)
- [Project log](https://github.com/AbhilashHalappa/Race-Engineer-ACC/blob/diagnostic/high-res-capture-2026-11-07/docs/PROJECT_LOG.md)
- [Graphics decoder and candidate ctypes layout](https://github.com/AbhilashHalappa/Race-Engineer-ACC/blob/diagnostic/high-res-capture-2026-11-07/src/acc_shared_memory_extended.py)
- [Measured performance consumer](https://github.com/AbhilashHalappa/Race-Engineer-ACC/blob/diagnostic/high-res-capture-2026-11-07/src/measured_performance.py)
- [Lap validity regression tests](https://github.com/AbhilashHalappa/Race-Engineer-ACC/blob/diagnostic/high-res-capture-2026-11-07/tests/test_acc_lap_validity_transitions.py)
- [Graphics decoder fixture test](https://github.com/AbhilashHalappa/Race-Engineer-ACC/blob/diagnostic/high-res-capture-2026-11-07/tests/test_acc_shared_memory_extended.py)

No other historical branch or ACC build is used as prior field-validation evidence.

### Current Greenfield evidence

- Candidate offsets/types are transcribed in [ACC_GRAPHICS_ABI_INVESTIGATION.md](ACC_GRAPHICS_ABI_INVESTIGATION.md). It is explicitly a v1.8.12-derived candidate, not an authoritative Kunos v1.9 header.
- Read-only probe: [probe_acc_graphics.py](../scripts/probe_acc_graphics.py).
- Full-page recording: `acc_graphics_full_lap_20261109T062139_837316Z.graphics-recording.bin`, with matching `.samples.csv` and `.json` in the user's local `user_data/raw_recordings` directory. These binary artefacts are not committed in this documentation change.
- Recording facts: 18,000 samples over 180 seconds; 4,096-byte mapping allocation; 74,088,016-byte recording; 30 packet-ID bracket mismatches. Bracketing is only a consistency heuristic and does not guarantee an atomic copy or zero source-level packet loss.
- User-confirmed capture context: recording began just before the start/finish line and crossed it once. User also confirmed that the lap after the completed valid lap was invalid due to a track-limit violation.
- Earlier read-only probe context in this investigation: user confirmed being in the pit lane while candidate `is_in_pit=0` and `is_in_pit_lane=1`; user-confirmed paused and moving-on-track captures also support the candidate status/pit-state interpretations.

### Classification

- **A — Prior live behaviour confirmed:** explicitly user-confirmed in the previous branch's project log. This is application behaviour evidence, not byte-offset proof.
- **B — Prior application implementation/test evidence:** field exists in the previous branch's decoder and/or is consumed by code or covered by tests. This does not by itself claim live confirmation.
- **C — Current raw correlation:** current Greenfield raw observations correlate with a user-confirmed event or controlled state.
- **O — Raw observation only:** bytes at the candidate offset were inspected, but the semantic meaning has not been independently correlated.
- **R — Retained/reference-only:** candidate structure reserves/retains the field, but the previous decoder does not expose it as a live application value or marks it unused.
- **D — Unverified:** insufficient prior application or raw evidence.

Multiple labels may apply. **None of A/B/C alone certifies the exact v1.9 ABI.** Exact offset/type sign-off requires independent layout evidence and offset/size regression tests against the target build.

## Executive findings

1. The previous branch's project log explicitly records live-confirmed fixes for lap validity/history, track-limit warning, S1/S2/S3 timing, reference-lap validity, PRE-CORNER refresh, overlay update/retention, and Corner Coach reference correctness. These are application-level behaviours. The log does not identify all underlying raw Graphics offsets.
2. The previous branch's decoder and consumers establish broad prior implementation coverage for the Graphics fields listed below. Several candidate structure members are retained for layout correctness but intentionally not projected to application state.
3. The 2026-11-09 full-lap recording strongly correlates candidate offsets `0x004` (status), `0x084` (completed_laps), `0x0A4` (sector), and `0x580` (is_valid_lap) with observed game events. Offline inspection also supports `0x0F8` as normalized track position: values progress through the 0–1 range and wrap near the completed-lap boundary. The first three coordinate floats at `0x100` change throughout the moving portion of the recording; with `active_cars=1`, this is consistent with the sole active car's coordinate triple, though player-ID association is not proven.
4. The pit-state distinction is supported by the earlier user-confirmed pit-lane probe: `0x0A0` was zero while `0x4D4` was one.
5. The candidate `0x578` (`is_delta_positive`) changed from 0 to 1 in the full-lap recording, but there was no user-confirmed delta-sign event. It is observation-only, not semantically validated.
6. Offline inspection found bytes `0x634`–`0xFFF` (2,508 bytes) entirely zero in all 18,000 samples, with no changes. This supports—but does not prove—the 1,588-byte candidate logical-size boundary. The 4,096-byte mapping allocation does not establish a 4,096-byte logical struct, and the candidate remains unverified for Shared Memory 1.9.
7. The 60 candidate car-ID slots remained zero and unchanged in this single-car recording (`active_cars=1`); the car-ID array is therefore unverified, not disproven.

## Complete candidate field inventory

Offsets are hexadecimal byte offsets. Types are the candidate v1.8.12 transcription types. “Prior evidence” refers only to the diagnostic branch identified above.

| # | Candidate field | Candidate type | Offset | Prior evidence | Greenfield evidence | Assessment / remaining gap |
|---:|---|---|---:|---|---|---|
| 1 | `packet_id` | `int32` | `0x000` | B — decoder reads it | C — packet progression sampled; 10,797 unique IDs, 10,796 changes | Packet counter behaviour established; exact struct ABI still candidate |
| 2 | `status` | `int32` | `0x004` | B — decoded | C — PAUSE=3 to LIVE=2 at sample 277; user confirmed pause/resume context | Strong semantic/offset correlation |
| 3 | `session` | `int32` | `0x008` | B — decoded | O — initial probe showed practice value 0 | Other session types/sentinels not correlated |
| 4 | `current_time` | `uint16[15]` | `0x00C` | B — decoded as current-time string | D | Correlate against HUD timer and UTF-16 termination |
| 5 | `last_time` | `uint16[15]` | `0x02A` | B — decoded as last-time string | D | Correlate against completed lap time |
| 6 | `best_time` | `uint16[15]` | `0x048` | B — decoded as best-time string | D | Correlate against known session best |
| 7 | `split` | `uint16[15]` | `0x066` | B — decoded as split-time string | D | Correlate at a known sector boundary |
| 8 | `completed_laps` | `int32` | `0x084` | B — decoded and used by lap/session logic | C — 0→1 at 127.340 s, matching the user's one start/finish crossing | Strong semantic/offset correlation |
| 9 | `position` | `int32` | `0x088` | B — decoded | O — remained 1 for all 18,000 samples | Needs a position change or multi-car comparison |
| 10 | `i_current_time` / `current_time_ms` | `int32` | `0x08C` | B — decoded as `current_time_ms` | D | Correlate numeric milliseconds against HUD |
| 11 | `i_last_time` / `last_time_ms` | `int32` | `0x090` | B — decoded as `last_time_ms` | D | Correlate against a completed lap |
| 12 | `i_best_time` / `best_time_ms` | `int32` | `0x094` | B — decoded as `best_time_ms` | D | Correlate against session best |
| 13 | `session_time_left` | `float32` | `0x098` | B — decoded as `session_time_left_s` | D | Compare known session countdown |
| 14 | `distance_traveled` | `float32` | `0x09C` | B — decoded as `distance_traveled_m` | D | Compare against Physics distance/speed integration |
| 15 | `is_in_pit` | `int32` | `0x0A0` | B — decoded as boolean | C — separate pit-lane probe had pit=0 while pit-lane=1; full lap remained 0 | Strong distinction evidence; pit-box true state not yet captured |
| 16 | `current_sector_index` / `sector` | `int32` | `0x0A4` | A/B — S1/S2/S3 live timing confirmed; decoded and consumed by sector recorder | C — values 0/1/2; 2→0 occurred 40 ms before completed-lap increment | Strong semantic/offset correlation |
| 17 | `last_sector_time` / `last_sector_time_ms` | `int32` | `0x0A8` | A/B — S1/S2/S3 timing live-confirmed; consumed at sector boundaries | O — changed at samples 711, 4502, 8797, 12730, and 16759; transitions align with candidate sector-index transitions | Strong transition correlation with sector changes; numeric interpretation/units remain unverified (observed values include 37,895 and 80,850) |
| 18 | `number_of_laps` | `int32` | `0x0AC` | B — decoded | D | Compare against known session lap limit |
| 19 | `tyre_compound` | `uint16[33]` | `0x0B0` | B — decoded as UTF-16 string | D | Compare selected compound; verify encoding/termination |
| 20 | `replay_time_multiplier` | `float32` | `0x0F4` | R — candidate layout member retained as unused | D | Preserve for ABI; no application behaviour claim |
| 21 | `normalized_car_position` | `float32` | `0x0F8` | B — consumed by ACC lap anchoring | C — 9,740 unique values, range 0–1; sampled progression wraps from 0.928863 at sample 12,000 to 0.030613 at 13,000, near completed-lap increment at 12,734 | Strong empirical support for normalized track position; first wrap also overlaps pause-to-live resumption, so startup/resume behaviour should not be overinterpreted |
| 22 | `active_cars` | `int32` | `0x0FC` | B — decoded and bounds coordinate/ID arrays | D | Validate count against known grid size |
| 23 | `car_coordinates[60][3]` | `float32[60][3]` | `0x100` | B — decoded for active cars and player position | O — only coordinate slots 0, 1, and 2 changed; each changed in about 10,631 samples; `active_cars=1` throughout | Strong support for a changing XYZ triple in the first array entry; player association and full 60×3 array layout still need a multi-car/ID-controlled capture |
| 24 | `car_id[60]` | `int32[60]` | `0x3D0` | B — decoded for active cars/player lookup | O — all 60 slots were zero in the first sample and no slot changed; `active_cars=1` | Unverified; this single-car recording does not exercise meaningful car-ID population |
| 25 | `player_car_id` | `int32` | `0x4C0` | B — decoded and used to locate player coordinates | D | Correlate with car_id array |
| 26 | `penalty_time` | `float32` | `0x4C4` | B — decoded as `penalty_time_s` | D | Requires a known penalty-time state |
| 27 | `flag` | `int32` | `0x4C8` | B — decoded | D | Raw enum values retained; no controlled flag transition |
| 28 | `penalty` | `int32` | `0x4CC` | B — decoded | D | Requires controlled penalty state |
| 29 | `ideal_line_on` | `int32` | `0x4D0` | B — decoded as boolean | D | Toggle and correlate with game setting |
| 30 | `is_in_pit_lane` | `int32` | `0x4D4` | B — decoded independently from `is_in_pit` | C — user-confirmed pit-lane state read 1 while `is_in_pit` read 0 | Strong separate-field evidence |
| 31 | `surface_grip` | `float32` | `0x4D8` | B — decoded | D | Needs known condition progression and range check |
| 32 | `mandatory_pit_done` | `int32` | `0x4DC` | B — decoded as boolean | D | Requires race with mandatory pit completed |
| 33 | `wind_speed` | `float32` | `0x4E0` | B — present in decoder layout/output | D | Compare with ACC weather/session data |
| 34 | `wind_direction` | `float32` | `0x4E4` | B — present in decoder layout/output | D | Compare with ACC weather/session data |
| 35 | `is_setup_menu_visible` | `int32` | `0x4E8` | B — decoded as `setup_menu_visible` | D | Controlled menu visibility correlation |
| 36 | `main_display_index` | `int32` | `0x4EC` | B — decoded | D | Change MFD main display and correlate |
| 37 | `secondary_display_index` | `int32` | `0x4F0` | B — decoded | O — observed as zero in earlier snapshot only | Must not be confused with sector or validity |
| 38 | `tc` | `int32` | `0x4F4` | B — decoded as `tc_level` | D | Change TC setting and correlate |
| 39 | `tc_cut` | `int32` | `0x4F8` | B — decoded | D | Change TC cut setting and correlate |
| 40 | `engine_map` | `int32` | `0x4FC` | B — decoded | D | Change engine map and correlate |
| 41 | `abs` | `int32` | `0x500` | B — decoded as `abs_level` | D | Change ABS setting and correlate |
| 42 | `fuel_x_lap` | `float32` | `0x504` | B — decoded as `fuel_per_lap` | D | Correlate with ACC fuel estimate |
| 43 | `rain_lights` | `int32` | `0x508` | B — decoded as boolean | D | Toggle rain lights |
| 44 | `flashing_lights` | `int32` | `0x50C` | B — decoded as boolean | D | Toggle flashing lights |
| 45 | `lights_stage` | `int32` | `0x510` | B — decoded | D | Toggle light stages |
| 46 | `exhaust_temperature` | `float32` | `0x514` | B — decoded as `exhaust_temp_c` | D | Compare plausible live changes; validate units |
| 47 | `wiper_level` | `int32` | `0x518` | B — decoded | D | Change wiper setting |
| 48 | `driver_stint_total_time_left` | `int32` | `0x51C` | B — decoded as `driver_stint_total_ms` | D | Correlate against stint timer |
| 49 | `driver_stint_time_left` | `int32` | `0x520` | B — decoded as `driver_stint_left_ms` | D | Correlate against driver timer |
| 50 | `rain_tyres` | `int32` | `0x524` | B — decoded as boolean | D | Compare selected tyre set/type |
| 51 | `session_index` | `int32` | `0x528` | B — decoded | D | Compare session progression/index |
| 52 | `used_fuel` | `float32` | `0x52C` | B — decoded as `used_fuel_l`; previous log documents live fuel projection | O — 10,634 unique values; range 2.6816–6.9732 during recording | Dynamic float observation; exact semantics/units not independently correlated with fuel display or consumption |
| 53 | `delta_lap_time` | `uint16[15]` | `0x530` | R — candidate layout member not projected by previous decoder | D | Retain for layout; compare with numeric delta field |
| 54 | `i_delta_lap_time` | `int32` | `0x550` | B — decoded as `delta_lap_time_ms` | O — 1,892 unique values; range −1,042 to 2,518 | Dynamic signed integer; compare with displayed reference delta before semantic sign-off |
| 55 | `estimated_lap_time` | `uint16[15]` | `0x554` | R — candidate layout member not projected by previous decoder | D | Retain; compare with numeric estimate if needed |
| 56 | `i_estimated_lap_time` | `int32` | `0x574` | B — decoded as `estimated_lap_time_ms` | O — 1,893 unique values; range includes `2147483647` sentinel and finite values 119,140–122,583 | Dynamic integer with apparent unavailable sentinel; compare finite values against ACC estimate before semantic sign-off |
| 57 | `is_delta_positive` | `int32` | `0x578` | B — decoded as `delta_positive` | O — 0→1 at sample 14,620; no user-confirmed delta sign at that moment | Candidate offset observed; semantic correlation still needed |
| 58 | `i_split` | `int32` | `0x57C` | B — decoded as `split_ms` | D | Correlate against split display |
| 59 | `is_valid_lap` | `int32` | `0x580` | A/B — lap validity/history and track-limit warning live-confirmed; transition/stickiness regression tests | C — 1→0 at 143.47 s after user-confirmed track-limit violation | Strong semantic/offset correlation; preserve initial-false and sticky-invalid semantics |
| 60 | `fuel_estimated_laps` | `float32` | `0x584` | B — decoded and covered by Graphics decoder fixture test | D | Compare against ACC fuel estimate |
| 61 | `track_status` | `uint16[33]` | `0x588` | B — decoded as UTF-16 string | D | Correlate string and termination with session state |
| 62 | `missing_mandatory_pits` | `int32` | `0x5CC` | B — decoded | D | Requires mandatory-pit race scenario |
| 63 | `clock` | `float32` | `0x5D0` | B — decoded as `clock_s` | D | Compare with session time-of-day |
| 64 | `direction_lights_left` | `int32` | `0x5D4` | B — decoded as `direction_left` | D | Trigger left indicator |
| 65 | `direction_lights_right` | `int32` | `0x5D8` | B — decoded as `direction_right` | D | Trigger right indicator |
| 66 | `global_yellow` | `int32` | `0x5DC` | B — decoded as boolean | D | Needs yellow-flag event |
| 67 | `global_yellow_1` | `int32` | `0x5E0` | B — decoded as boolean | D | Needs sector-specific yellow event |
| 68 | `global_yellow_2` | `int32` | `0x5E4` | B — decoded as boolean | D | Needs sector-specific yellow event |
| 69 | `global_yellow_3` | `int32` | `0x5E8` | B — decoded as boolean | D | Needs sector-specific yellow event |
| 70 | `global_white` | `int32` | `0x5EC` | B — decoded as boolean | D | Needs white-flag event |
| 71 | `global_green` | `int32` | `0x5F0` | B — decoded as boolean | O — raw value remained 1 in inspected snapshots | This is global-green, not lap validity |
| 72 | `global_chequered` | `int32` | `0x5F4` | R — retained in candidate layout; not projected by previous decoder output | D | Retain for offset correctness; flag-event correlation pending |
| 73 | `global_red` | `int32` | `0x5F8` | R — retained in candidate layout; not projected by previous decoder output | D | Retain for offset correctness; flag-event correlation pending |
| 74 | `mfd_tyre_set` | `int32` | `0x5FC` | B — decoded | D | Change MFD tyre-set selection |
| 75 | `mfd_fuel_to_add` | `float32` | `0x600` | B — decoded | D | Change MFD fuel target |
| 76 | `mfd_tyre_pressure_lf` | `float32` | `0x604` | B — decoded into four-pressure tuple | D | Compare MFD LF pressure |
| 77 | `mfd_tyre_pressure_rf` | `float32` | `0x608` | B — decoded into four-pressure tuple | D | Compare MFD RF pressure |
| 78 | `mfd_tyre_pressure_lr` | `float32` | `0x60C` | B — decoded into four-pressure tuple | D | Compare MFD LR pressure |
| 79 | `mfd_tyre_pressure_rr` | `float32` | `0x610` | B — decoded into four-pressure tuple | D | Compare MFD RR pressure |
| 80 | `track_grip_status` | `int32` | `0x614` | B — decoded and fixture-tested | D | Correlate raw enum against known grip state |
| 81 | `rain_intensity` | `int32` | `0x618` | B — decoded and fixture-tested | D | Correlate against weather/rain state |
| 82 | `rain_intensity_10min` | `int32` | `0x61C` | B — decoded as `rain_10min` | D | Correlate forecast interval |
| 83 | `rain_intensity_30min` | `int32` | `0x620` | B — decoded as `rain_30min`; fixture-tested | D | Correlate forecast interval |
| 84 | `current_tyre_set` | `int32` | `0x624` | B — decoded | D | Compare currently fitted set |
| 85 | `strategy_tyre_set` | `int32` | `0x628` | B — decoded | D | Compare selected strategy set |
| 86 | `gap_ahead` | `int32` | `0x62C` | B — decoded as `gap_ahead_ms` | D | Compare with timing tower/gap |
| 87 | `gap_behind` | `int32` | `0x630` | B — decoded as `gap_behind_ms` | D | Compare with timing tower/gap |

## Important offset corrections and interpretation notes

- Candidate `current_sector_index` is at `0x0A4` (164 decimal). `0x4F0` is `secondary_display_index`, not sector.
- Candidate `is_valid_lap` is at `0x580` (1,408 decimal). `0x5F0` is `global_green`, not lap validity.
- Candidate `is_delta_positive` is at `0x578`; its transition was observed but not tied to a user-confirmed delta sign.
- Candidate `is_in_pit` (`0x0A0`) and `is_in_pit_lane` (`0x4D4`) are separate values. Do not merge them.
- The candidate uses 2-byte UTF-16 code units for the fixed-width strings and 4-byte scalar alignment. Confirm against the target v1.9 ABI before production use.
- Previous decoder output names sometimes differ from specification names (for example `current_sector_index` → `sector`, `i_current_time` → `current_time_ms`, `fuel_x_lap` → `fuel_per_lap`). The audit records both where useful.

## Offline inspection results — 2026-11-09 recording

The offline inspector was run against the existing 18,000-sample, 180-second full-page recording. No new live capture was required for these findings.

- `normalized_car_position` (`0x0F8`, `float32`): 9,740 unique values, range 0–1. Samples progress around the normalized lap coordinate and wrap near the completed-lap transition: sample 12,000 = 0.928863; sample 13,000 = 0.030613; `completed_laps` increments at sample 12,734. At sample 0 = 0.960547 and sample 1,000 = 0.030043, the capture also spans a pause-to-live transition, so the first wrap may reflect resume/startup behaviour.
- `last_sector_time_ms` (`0x0A8`, `int32`) changed at samples 711, 4502, 8797, 12730, and 16759. These transitions coincide with the observed sector-index transitions. Values include 37,895 and 80,850; transition correlation is strong, but the numeric meaning/units are not signed off.
- `car_coordinates` (`0x100`): only float slots 0, 1, and 2 changed (about 10,631 changed samples each); their ranges were X −398.624 to 858.446, Y −13.487 to −0.707, Z −1,124.324 to 1,042.786. `active_cars` remained 1. This is consistent with a changing XYZ triple in the first coordinate entry, but player-car association and the full array ordering remain unverified.
- `car_id` (`0x3D0`): all 60 candidate slots were zero initially and no slot changed. With `active_cars=1`, this recording does not validate car-ID population or mapping.
- `used_fuel` (`0x52C`): 10,634 unique float values, range 2.6816–6.9732. Dynamic behaviour observed; semantics/units need comparison with ACC fuel display or a controlled fuel-use measurement.
- `i_delta_lap_time` (`0x550`): 1,892 unique values, range −1,042 to 2,518; dynamic signed integer observed, but displayed-delta correlation remains outstanding.
- `i_estimated_lap_time` (`0x574`): 1,893 unique values; finite range 119,140–122,583 with `2147483647` appearing as an unavailable sentinel candidate. Compare with ACC's estimate before semantic sign-off.
- Trailing bytes `0x634`–`0xFFF`: all 2,508 bytes were zero in every one of the 18,000 samples; no trailing-byte changes were observed. This supports the candidate boundary but does not prove exact logical structure size.

## Next validation actions

1. If the numeric timing fields remain a priority, correlate `0x08C`, `0x090`, `0x094`, `0x550`, and `0x574` against a visible HUD capture or manually noted HUD values from a short controlled session. Existing numeric observations alone do not prove units/semantics.
2. Validate the coordinate and ID arrays with a session containing at least two active cars, and correlate `player_car_id` against populated `car_id` entries and moving coordinate triples.
3. Correlate `used_fuel` and `fuel_estimated_laps` against ACC's displayed fuel values over a controlled interval.
4. Verify candidate field ordering/types against independent Shared Memory 1.9 evidence if obtainable. Current third-party references are v1.8.12-derived and cannot alone sign off v1.9.
5. Add offset/size regression tests only after the layout has been independently justified. Preserve the complete 4,096-byte raw page and unknown bytes in the acquisition/recording design.
6. For other fields, request only targeted short captures when a specific controlled game event is necessary (for example, pit-box true, flag changes, MFD changes). Do not repeat the already-confirmed lap/sector/validity tests.

## ABI sign-off status

**NOT SIGNED OFF.** The recording provides strong empirical correlations for several high-value fields, but the candidate structure is still derived from a v1.8.12 transcription while the target reports Shared Memory 1.9. This audit is a coverage/evidence map, not a declaration that the candidate 1,588-byte structure is the exact v1.9 ABI.


## RaceIQ / Pro Engineer reference reconciliation — 9 November 2026

The complete candidate inventory has been checked against two additional independent projects at pinned revisions:

- [RaceIQ ACC structure definitions](https://github.com/SpeedHQ/RaceIQ/blob/64a34783f706722cf342e18ecb7fc06d29f30f8e/packages/capture-formats/src/acc/structs.ts)
- [Pro Engineer complete ACC structures](https://github.com/Rgosh/ac-pro-engineer/blob/b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26/core/src/games/assetto_corsa_competizione/structs.rs)
- [Pro Engineer capture and validation notes](https://github.com/Rgosh/ac-pro-engineer/blob/b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26/docs/plan-acc.md)

**Results:** both references declare the Graphics mapping as 1,588 bytes. RaceIQ's 44 explicit offset descriptors align with the corresponding Pro Engineer offsets. RaceIQ's current offset map stops at `clock` (1488) and omits explicit descriptors for the final 96 bytes; Pro Engineer supplies the complete 87-member field sequence through `gap_behind` at 1584. RaceIQ's 1,320-byte minimum is a legacy parser-compatibility path, not the complete page, and is not suitable for new raw acquisition.

The 87-field candidate inventory in this audit therefore uses Pro Engineer's complete sequence and RaceIQ's overlapping offsets as a cross-check. This is reference corroboration, not official Kunos Shared Memory 1.9 ABI confirmation. Preserve the complete 4,096-byte mapping capture; treat bytes 1,588–4,095 as opaque mapping tail based on the existing all-zero observation, not as additional declared fields.


## Raw-only acquisition boundary — 9 November 2026

The separate Graphics raw-only reader/recorder has been added. It preserves the complete mapping allocation discovered at runtime (4,096 bytes in the existing target capture) and does not use the candidate 1,588-byte struct to limit acquisition. The 87-field candidate inventory remains an offline interpretation reference only.

Automated tests are present for the Graphics acquisition and recording path; Automated CI passed 60/60 on both Ubuntu and Windows; live target-PC validation remains pending. This does not change the ABI sign-off status above: field offsets/types for Shared Memory 1.9 remain unconfirmed as a complete official contract.


## Graphics raw acquisition automated validation — 9 November 2026

The raw-only Graphics acquisition and recording path now has dedicated automated coverage. GitHub Actions run [42598727306](https://github.com/AbhilashHalappa/Race-Engineer-ACC-New/actions/runs/42598727306) passed **60/60 tests on Ubuntu and 60/60 on Windows**, including the new Graphics acquisition/recorder tests and compilation of the live runner. The source-size test uses a 4,096-byte fake mapping and verifies that every byte is copied and preserved.

The raw acquirer deliberately preserves every consistent poll, including repeated packet IDs. It counts repeated IDs as an observation metric but does not deduplicate them, because a same-ID page could still contain changed bytes. The capture remains a latest-state polling interface, not an ACC event queue; source-level updates between polls can still be missed.

Target-PC validation of the new standalone runner remains pending; it is not yet wired into normal application startup. The earlier 18,000-sample diagnostic capture is existing evidence, not a substitute for validating this new acquisition/recording pipeline.


---

## Six-minute full-page Graphics audit addendum — 9 November 2026

This addendum records the later six-minute dry-condition capture. It supersedes any earlier statement in this document that target-PC Graphics raw acquisition validation was still pending: the separate raw-only recorder was subsequently exercised on the target PC and the complete recording was audited.

**Recording:** `user_data/raw_recordings/acc_graphics_20261109T110805_109825Z.gfxraw`  
**Full report:** `user_data/raw_recordings/acc_graphics_complete_audit.json`  
**Command:** `python scripts/audit_acc_graphics_all_fields.py <recording>.gfxraw --json-out <report>.json`

### Capture and integrity

| Measure | Result |
|---|---:|
| Capture duration | 360.0 s |
| Poll rate | 100 Hz |
| Samples acquired / persisted | 36,001 / 36,001 |
| Mapping page copied | 4,096 bytes per sample |
| Candidate layout decoded offline | 1,588 bytes |
| Opaque mapping remainder | 2,508 bytes |
| Acquisition rejects | 0 |
| Recorder queue rejects | 0 |
| Write failures | 0 |
| Pending at shutdown | 0 |
| Reconciliation delta | 0 |
| CRC, record sequence, packet-ID checks | Passed |
| CPU | 8.33% |
| Conditions | Dry session; user reported a major crash/damage incident during the capture |

The capture validates the raw-only recording path and the ability to run the candidate offline audit against a complete six-minute recording. It does not certify every candidate field's semantics or establish an official Kunos ABI.

### Scalar field results — all 77 members

The existing complete candidate inventory above supplies each field's source type and byte offset. This table records the new capture's exact terminal summary. “Changes” means sample-to-sample value transitions; it is descriptive, not semantic proof.

| Field | First → last | Min…max | Changes |
|---|---:|---:|---:|
| `packet_id` | 623 → 22189 | 623…22189 | 21,566 |
| `status` | 2 → 2 | 2…2 | 0 |
| `session` | 2 → 2 | 2…2 | 0 |
| `completed_laps` | 0 → 1 | 0…1 | 1 |
| `position` | 25 → 25 | 24…25 | 2 |
| `i_current_time` | 0 → 159162 | 0…159162 | 19,125 |
| `i_last_time` | 2147483647 → 154825 | 154825…2147483647 | 1 |
| `i_best_time` | 2147483647 → 2147483647 | 2147483647…2147483647 | 0 |
| `session_time_left` | 1200000 → 880942 | 880942…1200000 | 19,126 |
| `distance_traveled` | 0.681819 → 9940.289063 | 0.681819…9940.289063 | 19,895 |
| `is_in_pit` | 0 → 0 | 0…1 | 4 |
| `current_sector_index` | 0 → 1 | 0…2 | 4 |
| `last_sector_time` | 0 → 102755 | 0…102917 | 4 |
| `number_of_laps` | 0 → 0 | 0…0 | 0 |
| `replay_time_multiplier` | 0 → 0 | 0…0 | 0 |
| `normalized_car_position` | 0.838400 → 0.557969 | 0…1 | 17,906 |
| `active_cars` | 25 → 25 | 25…25 | 0 |
| `player_car_id` | 24 → 24 | 24…24 | 0 |
| `penalty_time` | 0 → 0 | 0…0 | 0 |
| `flag` | 0 → 7 | 0…8 | 15 |
| `penalty` | 0 → 0 | 0…1 | 2 |
| `ideal_line_on` | 1 → 1 | 1…1 | 0 |
| `is_in_pit_lane` | 0 → 0 | 0…1 | 2 |
| `surface_grip` | 0 → 0 | 0…0 | 0 |
| `mandatory_pit_done` | 1 → 1 | 1…1 | 0 |
| `wind_speed` | 0.0165633 → 0.0165605 | 0.0165605…0.0165633 | 1,521 |
| `wind_direction` | 209.646545 → 209.662323 | 209.646545…209.662323 | 1,034 |
| `is_setup_menu_visible` | 0 → 0 | 0…0 | 0 |
| `main_display_index` | 1 → 1 | 1…1 | 0 |
| `secondary_display_index` | 0 → 0 | 0…0 | 0 |
| `tc` | 6 → 7 | 6…7 | 1 |
| `tc_cut` | 6 → 7 | 6…7 | 1 |
| `engine_map` | 7 → 6 | 6…7 | 1 |
| `abs` | 6 → 7 | 6…7 | 1 |
| `fuel_x_lap` | 3.660000 → 3.011387 | 3.011387…3.660000 | 1 |
| `rain_lights` | 0 → 1 | 0…1 | 1 |
| `flashing_lights` | 0 → 0 | 0…0 | 0 |
| `lights_stage` | 0 → 1 | 0…1 | 1 |
| `exhaust_temperature` | 117.939774 → 232.918259 | 117.939774…569.978455 | 21,566 |
| `wiper_stage` | 0 → 1 | 0…1 | 1 |
| `driver_stint_total_time_left` | -1000 → -1000 | -1000…-1000 | 0 |
| `driver_stint_time_left` | -1000 → -320040 | -320040…-1000 | 15,280 |
| `rain_tyres` | 0 → 0 | 0…0 | 0 |
| `session_index` | 0 → 0 | 0…0 | 0 |
| `used_fuel` | 0 → 4.974590 | 0…4.974590 | 19,668 |
| `i_delta_lap_time` | 0 → 0 | 0…0 | 0 |
| `i_estimated_lap_time` | 2147483647 → 2147483647 | 2147483647…2147483647 | 0 |
| `is_delta_positive` | 0 → 0 | 0…0 | 0 |
| `i_split` | 16303 → 56407 | 0…102750 | 21,566 |
| `is_valid_lap` | 1 → 1 | 1…1 | 0 |
| `fuel_estimated_laps` | 16.939890 → 18.936594 | 15.997464…19.443092 | 19,627 |
| `missing_mandatory_pits` | 0 → 0 | 0…0 | 0 |
| `clock` | 61201.304688 → 61561.308594 | 61201.304688…61561.308594 | 21,566 |
| `direction_lights_left` | 0 → 1 | 0…1 | 1 |
| `direction_lights_right` | 0 → 0 | 0…1 | 2 |
| `global_yellow` | 0 → 1 | 0…1 | 13 |
| `global_yellow_1` | 0 → 0 | 0…1 | 4 |
| `global_yellow_2` | 0 → 1 | 0…1 | 9 |
| `global_yellow_3` | 0 → 0 | 0…0 | 0 |
| `global_white` | 0 → 0 | 0…0 | 0 |
| `global_green` | 0 → 0 | 0…1 | 14 |
| `global_chequered` | 0 → 0 | 0…0 | 0 |
| `global_red` | 1 → 0 | 0…1 | 1 |
| `mfd_tyre_set` | 1 → 1 | 1…1 | 0 |
| `mfd_fuel_to_add` | 0 → 0 | 0…0 | 0 |
| `mfd_tyre_pressure_lf` | 26.5 → 28.2 | 25.3…28.2 | 3 |
| `mfd_tyre_pressure_rf` | 26.5 → 28.2 | 25.3…28.2 | 3 |
| `mfd_tyre_pressure_lr` | 25.3 → 27.5 | 24.5…27.5 | 3 |
| `mfd_tyre_pressure_rr` | 25.3 → 27.6 | 24.5…27.6 | 3 |
| `track_grip_status` | 1 → 1 | 1…1 | 0 |
| `rain_intensity` | 0 → 0 | 0…0 | 0 |
| `rain_intensity_in_10min` | 0 → 0 | 0…0 | 0 |
| `rain_intensity_in_30min` | 0 → 0 | 0…0 | 0 |
| `current_tyre_set` | 1 → 1 | 1…1 | 0 |
| `strategy_tyre_set` | 2 → 2 | 2…2 | 0 |
| `gap_ahead` | 0 → 163 | 0…163 | 5 |
| `gap_behind` | 0 → -141180 | -141422…0 | 5 |

### Arrays and strings

The audit reports 8 array members and 2 strings. The scalar terminal table does not summarize full arrays; per-element statistics are in the JSON report.

| Field | Candidate layout | New capture finding |
|---|---|---|
| `current_time` | `uint16[15]` | UTF-16 time string `-:--:---` → `2:39:162`; agrees with `i_current_time=159162` |
| `last_time` | `uint16[15]` | Initial uninitialized-looking value; final `2:34:825`; agrees with `i_last_time=154825` |
| `best_time` | `uint16[15]` | Uninitialized-looking throughout; integer companion remains sentinel |
| `split` | `uint16[15]` | Candidate UTF-16 time string; needs format/companion interpretation |
| `car_coordinates` | `float32[60][3]` | 180 float values (60 XYZ triplets); per-slot detail is in JSON and has not yet been manually reviewed |
| `car_id` | `int32[60]` | 60 values; first/last displayed slot is 24; full ID-to-slot mapping needs review |
| `delta_lap_time` | `uint16[15]` | UTF-16 sentinel string `-:--:---`; integer companion is zero |
| `estimated_lap_time` | `uint16[15]` | Uninitialized-looking throughout; integer companion remains sentinel |
| `tyre_compound` | UTF-16LE, 33 code units | `dry_compound` throughout; populated string observed, transition not tested |
| `track_status` | UTF-16LE, 33 code units | `FAST` throughout; populated string observed, transition not tested |

The six time-like arrays are fixed-width UTF-16 strings, not 15 independent numeric measurements. Their raw first/last u16 elements in the console table are character code units and must not be interpreted as time values.

### Important new interpretations and unresolved items

- **Dry session:** `tyre_compound=dry_compound`, `track_status=FAST`, and all three rain-intensity fields were zero. This is consistent with the user's correction that this was a dry-condition session.
- **Rain lights are not rain:** `rain_lights` changed 0→1; this is a light-control state, not evidence of wet weather.
- **Setup controls:** TC, TC Cut, ABS and Engine Map changed in the six-minute capture. The user-confirmed Engine Map display rule is **UI value = raw Graphics `engine_map` value + 1**; this is a display transformation, not an offset/layout discrepancy. Do not reopen this item.
- **Pit state:** both `is_in_pit` and `is_in_pit_lane` changed. They are separate candidate fields.
- **Race control:** `flag`, `penalty`, global yellow, global green and global red changed. Their event/enum meanings need correlation; these are not damage values.
- **Fuel and tyres:** `used_fuel`, `fuel_estimated_laps`, `fuel_x_lap`, MFD pressures and gap fields populated/changed. Their units, signs and calculations are not all independently validated.
- **Coordinates/IDs:** the subsequent per-slot review maps `player_car_id=24` to `car_id` slot 0, and therefore to coordinate triplet 0 (X/Y/Z). The six-minute capture contains 25 active IDs (0–24) in slots 0–24; the remaining 35 slots are zero. This establishes the player slot for this capture, not the universal ordering rule for every session.
- **No Graphics damage channel:** none of the 87 candidate members is an explicitly named vehicle-damage field. Penalty, flags, coordinates and exhaust temperature must not be presented as damage measurements.

### Crash-context event index

The script generated 46 event-index samples from changes to position, flag, penalty, global flags, pit state, lap count, sector and validity. The index is explicitly a correlation aid, not collision detection. A penalty or flag transition cannot establish that a crash occurred. The complete event list is retained in the local JSON report; it must be correlated with the user's incident timing before assigning meaning.

The Physics audit already documents `car_damage[5]` at offset 224 and the prior controlled pit-service repair observation. That evidence is not repeated here as a Graphics field. The distinct Physics `suspension_damage[4]` at offset 680–695 remains separately classified in the Physics audit and must not be conflated with `car_damage[5]`.

### Updated next steps — reuse existing evidence first

1. Preserve the 2,508-byte post-candidate region as opaque; its all-zero state in this capture does not establish permanent absence.
2. Retain the unresolved semantic items listed below: enum meanings, gap units/sign, coordinate axis convention, and fields that did not change or were not independently correlated in this dry session.
3. Only request a new targeted capture if one named question cannot be answered from existing recordings. A tyre-compound transition is not validated by this dry-only recording, but that gap does not justify repeating unrelated tests.
4. Keep Graphics raw acquisition and offline candidate decoding separate; do not modify Physics as part of this Graphics audit.

**Current conclusion:** the raw-only Graphics recorder has now passed a six-minute target-PC capture with complete accounting and integrity checks. The 87-field candidate audit provides a field inventory and live observations. The candidate layout remains provisional for ACC Shared Memory 1.9; field semantics are individually qualified above.


## Full 87-field output and array interpretation review — 9 November 2026

The existing `acc_graphics_complete_audit.json` was reviewed using the compact summary of all 87 named candidate fields and a focused extraction of the eight arrays. This was an offline review of the existing 36,001-sample recording; no new capture or test was performed.

### Scope and interpretation boundary

- All **77 scalar members** were reviewed using first/last values, min/max, unique-value counts and sample-to-sample transition counts.
- All **8 array members** were checked for their recorded dimensions. The six time-like arrays were decoded as fixed-width UTF-16 character sequences; the 60-entry car-ID array was inspected; the player coordinate triplet was extracted from the mapped slot.
- The two UTF-16 strings, `tyre_compound` and `track_status`, were already represented in the scalar summary as observed strings.
- These are observations from this one dry-condition session. A field that remained constant is classified as **not exercised in this recording**, not as universally constant or invalid.
- Transition counts describe changes between adjacent samples. They do not establish why a field changed.

### Six time-like arrays and integer companions

| Array field | First decoded string | Last decoded string | Integer companion | Cross-check |
|---|---|---|---|---|
| `current_time` | `-:--:---` | `2:39:162` | `i_current_time`: 0 → 159162 | Final value agrees with 159,162 ms |
| `last_time` | `35791:23:647` | `2:34:825` | `i_last_time`: 2147483647 → 154825 | Final value agrees with 154,825 ms; initial value is an unavailable/uninitialized-looking representation |
| `best_time` | `35791:23:647` | `35791:23:647` | `i_best_time`: 2147483647 throughout | No valid best-lap value was established in this capture |
| `split` | `0:16:303` | `0:56:407` | `i_split`: 16,303 → 56,407 | First and last values agree with milliseconds |
| `delta_lap_time` | `-:--:---` | `-:--:---` | `i_delta_lap_time`: 0 throughout | No usable delta was observed |
| `estimated_lap_time` | `35791:23:647` | `35791:23:647` | `i_estimated_lap_time`: 2147483647 throughout | No usable estimate was established |

The final current-time, last-time and split string/integer pairs provide direct cross-field consistency evidence for millisecond interpretation. The repeated `35791:23:647` representation accompanies `2147483647` in the corresponding integer fields and should be treated as an unavailable/sentinel-like representation, **not** as a real lap time. The exact encoding/sentinel contract remains subject to ABI qualification.

### Car ID and coordinate arrays

| Item | Result |
|---|---|
| `car_id` shape | 60 `int32` entries |
| `car_coordinates` shape | 180 `float32` entries = 60 XYZ triplets |
| `active_cars` | 25 throughout |
| `player_car_id` | 24 throughout |
| Matching player ID slot | Slot 0 |
| Player coordinate triplet | Coordinate slot 0: X/Y/Z |

The first 25 ID slots contain the IDs 24, 0, 3, 2, 5, 9, 4, 8, 21, 6, 17, 7, 13, 14, 10, 15, 11, 18, 23, 1, 19, 12, 20, 16, 22. Slots 25–59 contain zero. Because ID 0 is present as an active entry, **zero must not be treated as an empty-slot marker**. The 25 populated entries correspond to the observed `active_cars=25`.

The player ID 24 occurs at slot 0, so the player coordinate triple in this recording is the first XYZ triplet:

| Axis | First | Last | Minimum | Maximum | Unique values |
|---|---:|---:|---:|---:|---:|
| X | -138.203522 | 553.081909 | -395.023682 | 857.976990 | 19,863 |
| Y | -11.752962 | -4.996140 | -13.556785 | -0.718725 | 20,199 |
| Z | 712.673035 | -624.293030 | -1,124.397583 | 1,041.982178 | 20,002 |

This confirms the player ID-to-coordinate-slot association for this recording and confirms that the selected XYZ values vary during the session. It does not establish the coordinate frame, handedness, axis orientation, units, or that slot ordering is invariant across all sessions. The other 59 coordinate triplets remain available in the JSON report; this review did not assign world-coordinate semantics to every car.

### Scalar observations that materially affect interpretation

- **Setup controls:** `tc`, `tc_cut`, `engine_map` and `abs` each changed once. Raw Engine Map was 7 → 6 in this capture. The user-confirmed UI rule is **displayed Engine Map = raw value + 1**. This is resolved display behaviour and is not an outstanding ABI offset issue.
- **Lap validity:** `is_valid_lap` remained 1 for all 36,001 samples. This capture did not exercise invalidation. Earlier user-confirmed track-limit/validity evidence remains separate and must not be overwritten by this constant observation.
- **Race control:** `flag` ranged 0–8 and changed 15 times; `penalty` ranged 0–1 and changed twice; `global_yellow` changed 13 times; `global_yellow_1` four times; `global_yellow_2` nine times; `global_green` 14 times; `global_red` changed once from 1 to 0. `global_yellow_3`, `global_white` and `global_chequered` did not change. Raw numeric ranges do not identify enum labels or prove which race-control event caused each transition.
- **Pit states:** `is_in_pit` ranged 0–1 and changed four times; `is_in_pit_lane` ranged 0–1 and changed twice. They remain distinct fields and must not be merged.
- **Fuel:** `used_fuel` changed from 0 to 4.974590 and had 19,668 transitions; `fuel_estimated_laps` ranged 15.997464–19.443092; `fuel_x_lap` changed from 3.660000 to 3.011387. These observations establish dynamic/populated values, not exact units or formula correctness.
- **Driver stint timers:** `driver_stint_total_time_left` remained -1000; `driver_stint_time_left` ranged -320040 to -1000. Preserve the raw signed values and do not assume the sign/sentinel convention is understood.
- **Gaps:** `gap_ahead` ranged 0–163; `gap_behind` ranged -141422–0. The sign difference is observed, but units, sign convention and conversion to displayed time remain unverified.
- **Flags and damage:** flag/penalty/global-flag transitions are race-control data, not collision or vehicle-damage measurements. No explicitly named vehicle-damage member exists in this 87-field Graphics candidate. The user's reported crash/damage incident must be analysed through the separate Physics damage fields, not inferred from Graphics flags.
- **Weather and lighting:** `tyre_compound=dry_compound`, `track_status=FAST`, and all three rain-intensity fields remained zero. `rain_lights` changed 0→1 and is a lighting control, not a rain measurement. `surface_grip` remained zero in this capture; that does not validate its meaning or prove zero physical grip.
- **MFD pressures:** all four pressure fields changed three times, with observed ranges LF/RF 25.3–28.2, LR 24.5–27.5, RR 24.5–27.6. The numeric values are populated; pressure units and exact relation to the displayed MFD remain to be qualified.
- **Static-in-capture fields:** unchanged fields include `status`, `session`, `number_of_laps`, `active_cars`, `player_car_id`, `ideal_line_on`, `mandatory_pit_done`, `is_setup_menu_visible`, `main_display_index`, `secondary_display_index`, `rain_tyres`, `session_index`, `track_grip_status`, the rain forecast fields, tyre-set selections and several MFD values. This list means only that they did not change in this capture.

### Revised field qualification

**Supported by this recording and cross-field checks**
- Candidate field count and source-derived offsets/types were exercised by the offline audit.
- Six time-like arrays are fixed-width UTF-16 strings; three final string/integer pairs agree at millisecond precision.
- `car_id` has 60 entries; `car_coordinates` has 60 XYZ triplets.
- `player_car_id=24` maps to ID slot 0 and coordinate triplet 0 in this capture.
- Engine Map's UI +1 transformation is user-confirmed and resolved.
- Pit-in and pit-lane fields are distinct; rain-light control and rain-intensity fields are distinct.

**Observed but not semantically signed off**
- `flag`, `penalty`, global-flag enum meanings and event associations.
- `gap_ahead` / `gap_behind` units and sign convention.
- Coordinate frame, axes, units and cross-session slot-order invariance.
- `driver_stint_total_time_left` / `driver_stint_time_left` sentinel and sign conventions.
- Fuel units/formula, pressure units, wind units, surface-grip meaning and track-grip enum.
- Exact semantics of `last_sector_time`, `i_delta_lap_time`, `i_estimated_lap_time` and the delta sign flag beyond the direct string/integer matches described above.

**Not exercised or not established by this recording**
- Invalid-lap transition (the field remained 1); mandatory pit transitions; wet-weather/compound transitions; chequered/white/global-yellow-3 events; pit-box state; MFD navigation changes; non-default rain/forecast values; valid best-lap and estimated-lap values.
- The complete official ACC Shared Memory 1.9 ABI. Third-party references corroborate the 1,588-byte candidate structure but are not an authoritative Kunos ABI declaration.

### Remaining work — no repeat capture by default

1. Keep the official Shared Memory 1.9 ABI qualification open; do not describe the candidate layout as Kunos-confirmed.
2. Do not repeat lap validity, Engine Map, player-slot, time-string or pit-lane checks already supported by evidence.
3. Keep gap units/sign, race-control enums, coordinate frame, stint timer conventions and remaining unexercised states explicitly unresolved.
4. Use existing event-index rows and raw JSON for any further offline correlation before asking for a targeted capture.
5. Do not change Physics acquisition or its completed validation as part of this Graphics documentation update.


## Ten-minute Graphics control, pit, weather and strategy validation — 9 November 2026

**Status: Target-PC raw acquisition and the planned live field-transition evidence pass completed.** This addendum supersedes the earlier six-minute-only scalar observations where the two recordings differ. It supplements, rather than replaces, the 87-field candidate inventory and its ABI caveats.

**Final recording:** `user_data/raw_recordings/acc_graphics_20261109T124256_127746Z.gfxraw`  
**Audit report:** `user_data/raw_recordings/acc_graphics_final_audit.json`  
**Comparison:** final ten-minute recording against `acc_graphics_complete_audit.json`, the earlier six-minute recording.

### Final capture integrity

| Measure | Result |
|---|---:|
| Duration | 599.991 s |
| Samples acquired / persisted | 60,000 / 60,000 |
| Polling rate | 100 Hz |
| Mapping bytes copied per sample | 4,096 |
| Acquisition rejects | 0 |
| Recorder queue rejects | 0 |
| Write failures | 0 |
| Pending at shutdown | 0 |
| Reconciliation delta | 0 |
| Recovery validation | Passed |
| Checkpoint validation | Passed |
| CPU | 8.50% |

This validates the target-PC raw-only Graphics acquisition/recording path for this run. It does not prove that every ACC publication was observed or that every candidate field's ABI/semantics are officially confirmed.

### Controlled/live state transitions observed

| Field(s) | Final recording evidence | Assessment |
|---|---|---|
| `tc` | 8→7→6→5→6→7→8; observed range 5–8 | Setting field changed in both directions |
| `tc_cut` | 7→6→7→8→9; range 6–9 | Setting field changed |
| `engine_map` | 7→6→5→6→7→8; range 5–8 | Setting field changed; user-confirmed UI presentation is raw value + 1 |
| `abs` | Range 5–8; seven transitions | Setting field changed in both directions |
| `rain_lights` | 0→1→0 | Control switched on and off; distinct from weather rain intensity |
| `lights_stage` | 0→1→2 | Two stage transitions |
| `wiper_stage` | 0→1→2 | Two stage transitions |
| `mfd_tyre_set`, `current_tyre_set`, `strategy_tyre_set` | At 567.781 s, respectively 0→1, 0→1 and 0→2 | All changed at the same observed sample; exact numeric meanings are not established |
| `main_display_index` | 1→2 | Display selection changed |
| `is_in_pit` | Two separate active periods; four transitions total | Distinct pit-state signal exercised |
| `is_in_pit_lane` | 0→1 at 447.460 s, 1→0 at 579.811 s | Pit-lane signal exercised separately from `is_in_pit` |
| `track_grip_status` | 5→4 at 114.671 s | Dynamic enum observed; labels for 4/5 not established |
| `rain_intensity` | Constant 2 | Non-zero value observed; no transition |
| `rain_intensity_in_10min` | 2→1 at 272.351 s | Forecast field changed |
| `rain_intensity_in_30min` | Constant 1 | Non-zero value observed; no transition |
| `global_yellow`, `global_yellow_2` | Both activated and cleared | Race-control flags exercised |
| `global_green`, `global_red` | Green and red values transitioned | Race-control flags exercised |
| `flag` | Values 0, 4 and 7 observed | Multiple raw enum values observed; mapping not established |
| `fuel_x_lap` | Four values, range 2.7642–3.6600 | Dynamic field observed |
| `used_fuel` | Range 0–9.0782 | Dynamic field observed |
| `fuel_estimated_laps` | Range 16.0850–21.2977 | Dynamic field observed |
| `wind_speed`, `wind_direction` | Both changed continuously; direction around −43.16° to −43.03° | Dynamic fields observed; units/reference convention not established |
| `gap_ahead`, `gap_behind` | Both changed; `gap_behind` includes negative values | Dynamic fields observed; units/sign convention not established |

The earlier six-minute capture independently showed changes in all four MFD tyre-pressure fields (LF/RF 25.3–28.2; LR 24.5–27.5/27.6). In the final ten-minute capture those four fields remained constant at LF/RF 26.1 and LR/RR 25.4. Together, the recordings establish that the pressure fields can vary, but do not provide a controlled before/after mapping of each tyre service action to each pressure value.

### Fields not exercised or still semantically unresolved

- `flashing_lights`, `secondary_display_index`, `is_setup_menu_visible`, `mfd_fuel_to_add`, `surface_grip`, `driver_stint_total_time_left`, `penalty_time`, `global_yellow_1`, `global_yellow_3`, `global_white` and `global_chequered` did not change in the final capture. This is not evidence that they are invalid.
- `driver_stint_time_left` changed continuously but remained negative (−403,460 to −1,000); units and sentinel/availability semantics remain unresolved.
- `surface_grip` remained zero while `track_grip_status` changed. They must not be conflated.
- `penalty` did not change in the final recording; it did change 0→1→0 in the earlier recording. `penalty_time` remained zero in both.
- `is_valid_lap` remained 1 throughout both recordings. Its invalidation behaviour is covered by the separate user-confirmed track-limit capture and existing lap-validity evidence; these two service/control recordings do not add a new invalid-lap transition.
- Numeric mappings for `flag`, `track_grip_status`, rain intensity, tyre-set identifiers and MFD display indices remain unqualified. Fuel, wind, gap and pressure units/formulas also remain unqualified where no independent display/value correlation exists.
- The recording includes user-reported pit tyre change, damage repair, brake pad/disc changes and other setup/control actions. This is capture context, not proof that every action has a corresponding Graphics field. The candidate Graphics structure contains no named vehicle-damage field; damage and brake telemetry must be validated against the Physics page, not inferred from Graphics.
- The candidate 1,588-byte/87-field layout remains a third-party reference-derived candidate. These recordings validate raw observations at candidate offsets; they do not constitute official Kunos Shared Memory 1.9 ABI sign-off.

### Graphics evidence disposition

The target-PC raw-only acquisition and recording path is **validated for the tested 4,096-byte mapping and the two live runs** (six minutes and ten minutes), with zero application-level recording loss/reconciliation delta in both. The planned live field-transition pass is complete: control settings, lights/wipers, tyre-set identifiers, pit states, weather/track-state fields, fuel estimates, wind, gaps and race-control flags now have live observations as detailed above.

The **Graphics field-coverage audit is complete as an evidence inventory**, but it is not an official ABI or full semantic sign-off. Remaining work is limited to authoritative enum/unit/offset confirmation and the explicitly unexercised fields above; no further broad recording is justified by the current evidence. Do not repeat the completed capture or transition checks unless a specific, named unresolved field requires a targeted experiment.


## Priority Graphics decoder implementation — 11 November 2026

The first downstream Graphics decoder is now implemented for the four Overview priority fields. It reads from the existing independent Graphics acquisition ring; the acquisition worker, 4,096-byte mapping copy and raw recording format remain unchanged.

| Field | Candidate offset | Type | Decoder output | Evidence / presentation |
|---|---:|---|---|---|
| TC setup level | `0x4F4` (1268) | `int32` | `tc_level` | Live target-PC capture changed 8→7→6→5→6→7→8 (observed range 5–8). Display raw ACC level; no +1 correction. |
| ABS setup level | `0x500` (1280) | `int32` | `abs_level` | Live target-PC capture observed range 5–8 with seven transitions. Display raw ACC level; no scaling/correction. |
| Fuel per lap | `0x504` (1284) | `float32` | `fuel_per_lap_l` | Live target-PC capture observed four values, range 2.7642–3.6600. Reference documentation describes this field as average fuel consumed per lap in litres. |
| Estimated laps remaining | `0x584` (1412) | `float32` | `fuel_estimated_laps` | Live target-PC capture range 16.0850–21.2977. Reference documentation describes laps possible with current fuel. |

### Implementation boundary

- `graphics_decoder.py` decodes only these four fields plus packet ID. It requires the payload to extend through byte 1415, preserves finite float values without undocumented scaling/sentinels, and maps non-finite floats to unavailable.
- `graphics_consumer.py` drains the Graphics ring downstream, verifies decoded packet ID against acquisition metadata, and retains the last good sample on decode errors.
- The acquisition supervisor now owns a separate Graphics decode worker and producer-completion signal. Physics and Graphics remain separate streams and separate SPSC rings.
- The Qt host publishes a `graphics` snapshot alongside `physics`; the bridge remains a transport only.
- Overview Fuel now reads fuel per lap and estimated laps from Graphics while remaining fuel continues to come from Physics. The fuel bar remains the existing session-high reference, not tank capacity.
- Overview TC/ABS setup levels now read from Graphics. Physics fields are no longer used as setup-level sources.
- No +1 adjustment is applied to TC/ABS. Values are passed through as raw ACC setup levels.
- Automated decoder/consumer tests were added in `tests/test_graphics_decoder.py`.

### Validation status and caveats

This is an initial implementation based on the candidate v1.8.12-derived field map, independent RaceIQ/Pro Engineer reference agreement, and target-PC raw transition evidence. The 4,096-byte acquisition mapping and 1,588-byte candidate structure are not an official Kunos Shared Memory 1.9 ABI certification.

The target-PC captures establish that the four candidate locations contain dynamic values consistent with their names. They do not record a synchronized HUD-value comparison for every field. The user's next local ACC test should compare:
1. TC and ABS values against the in-game electronics/MFD display while changing each setting independently.
2. Fuel per lap against the in-game fuel-consumption figure.
3. Estimated laps against the in-game laps-remaining figure, including after fuel changes/refuelling.

No frontend build, Python test run or live ACC validation was performed as part of the remote source update. Keep the fields under runtime validation until those checks pass.
