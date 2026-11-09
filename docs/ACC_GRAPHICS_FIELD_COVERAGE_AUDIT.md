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
3. The 2026-11-09 full-lap recording strongly correlates candidate offsets `0x004` (status), `0x084` (completed_laps), `0x0A4` (sector), and `0x580` (is_valid_lap) with observed game events.
4. The pit-state distinction is supported by the earlier user-confirmed pit-lane probe: `0x0A0` was zero while `0x4D4` was one.
5. The candidate `0x578` (`is_delta_positive`) changed from 0 to 1 in the full-lap recording, but there was no user-confirmed delta-sign event. It is observation-only, not semantically validated.
6. The 4,096-byte mapping allocation does not establish a 4,096-byte logical struct. The 1,588-byte candidate remains unverified for Shared Memory 1.9.

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
| 17 | `last_sector_time` / `last_sector_time_ms` | `int32` | `0x0A8` | A/B — S1/S2/S3 timing live-confirmed; consumed at sector boundaries | D — no numeric duration correlation in this recording | Prior behaviour established; raw numeric offset still needs correlation |
| 18 | `number_of_laps` | `int32` | `0x0AC` | B — decoded | D | Compare against known session lap limit |
| 19 | `tyre_compound` | `uint16[33]` | `0x0B0` | B — decoded as UTF-16 string | D | Compare selected compound; verify encoding/termination |
| 20 | `replay_time_multiplier` | `float32` | `0x0F4` | R — candidate layout member retained as unused | D | Preserve for ABI; no application behaviour claim |
| 21 | `normalized_car_position` | `float32` | `0x0F8` | B — consumed by ACC lap anchoring | D | Previous use established; raw offset/value range not independently checked here |
| 22 | `active_cars` | `int32` | `0x0FC` | B — decoded and bounds coordinate/ID arrays | D | Validate count against known grid size |
| 23 | `car_coordinates[60][3]` | `float32[60][3]` | `0x100` | B — decoded for active cars and player position | D | Needs multi-car movement/coordinate correlation |
| 24 | `car_id[60]` | `int32[60]` | `0x3D0` | B — decoded for active cars/player lookup | D | Needs player/other-car ID correlation |
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
| 52 | `used_fuel` | `float32` | `0x52C` | B — decoded as `used_fuel_l`; previous log documents live fuel projection | D | Previous app feature use; raw offset still needs value correlation |
| 53 | `delta_lap_time` | `uint16[15]` | `0x530` | R — candidate layout member not projected by previous decoder | D | Retain for layout; compare with numeric delta field |
| 54 | `i_delta_lap_time` | `int32` | `0x550` | B — decoded as `delta_lap_time_ms` | D | Compare sign/magnitude against reference delta |
| 55 | `estimated_lap_time` | `uint16[15]` | `0x554` | R — candidate layout member not projected by previous decoder | D | Retain; compare with numeric estimate if needed |
| 56 | `i_estimated_lap_time` | `int32` | `0x574` | B — decoded as `estimated_lap_time_ms` | D | Compare against ACC estimated lap |
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

## Next validation actions — offline first

1. Use the existing 18,000-sample recording to extract candidate fields at `0x0F8`, `0x0A8`, `0x08C`, `0x090`, `0x094`, `0x52C`, `0x550`, `0x574`, and the car-array ranges. Compare against existing CSV timestamps and known lap/sector boundaries. Do not require another live capture for this pass.
2. Inspect all bytes from candidate structure end `0x634` (1,588 decimal) through the 4,096-byte mapping allocation separately. Do not label them structure fields without independent evidence.
3. Verify candidate field ordering/types against independent Shared Memory 1.9 evidence if obtainable. The current third-party references are v1.8.12-derived and cannot alone sign off v1.9.
4. Add offset/size regression tests only after the layout has been independently justified. Preserve the complete 4,096-byte raw page and unknown bytes in the acquisition/recording design.
5. For fields not recoverable from this recording, request only targeted short captures when a specific controlled game event is necessary (for example, pit-box true, flag changes, MFD changes, multi-car position/coordinates). Do not repeat the already-confirmed lap/sector/validity tests.

## ABI sign-off status

**NOT SIGNED OFF.** The recording provides strong empirical correlations for several high-value fields, but the candidate structure is still derived from a v1.8.12 transcription while the target reports Shared Memory 1.9. This audit is a coverage/evidence map, not a declaration that the candidate 1,588-byte structure is the exact v1.9 ABI.
