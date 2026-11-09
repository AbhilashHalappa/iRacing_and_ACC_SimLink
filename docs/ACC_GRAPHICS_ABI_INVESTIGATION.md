# ACC Graphics Shared-Memory ABI Investigation

**Stage:** 5.1 — reference and ABI investigation  
**Target game build:** Assetto Corsa Competizione **1.10.4** (user-confirmed)  
**Observed shared-memory identifiers:** `smVersion = 1.9`, `acVersion = 1.7` (from the user's live Physics investigation; these are not the game build number)  
**Status:** Reference inventory established; exact Graphics ABI for the observed Shared Memory 1.9 build is **not yet signed off**.

## Objective

Identify and preserve every field published through `Local\\acpmf_graphics` for the target ACC installation. Graphics acquisition will be raw-only. Semantic decoding and state-machine logic remain downstream.

## Reference evidence and version caveat

The available detailed field-order reference is the ACC Shared Memory **v1.8.12** specification transcription and independent implementations:

- [ACC Shared Memory v1.8.12 C++ implementation](https://github.com/SolusDev-sys/CppAccSharedMemory/blob/main/C%2B%2BAccSharedMemory.cpp) — declares `SPageFileGraphic` under 4-byte packing and identifies its source as the KS Dev Team v1.8.12 specification.
- [ACC shared-memory field inventory](https://github.com/ebnerdm/accshm/blob/main/FIELDS.md) — independent field-order/type inventory.
- [Python ACC shared-memory implementation](https://github.com/rrennoir/PyAccSharedMemory) — another implementation of the documented pages.

These are corroborating third-party transcriptions/implementations, not a Kunos-published header for Shared Memory 1.9. The target installation reports Shared Memory 1.9, so the v1.8.12 field list is a **candidate ABI**, not an asserted exact match. In particular, no production offset or structure size should be locked solely from the older reference.

The C++ reference uses Windows `wchar_t` strings (2 bytes per code unit on Windows) and `#pragma pack(push, 4)`. The candidate field list below is transcribed in order and offsets are calculated with 4-byte maximum alignment. This yields 87 fields and a candidate structure size of **1,588 bytes**. This is a derived candidate size, not yet confirmed against the live v1.9 mapping.

## Directly useful state fields

| Requirement | Candidate Graphics field(s) | Interpretation / limitation |
|---|---|---|
| Game/session paused | `status` | Reference enum: OFF=0, REPLAY=1, LIVE=2, PAUSE=3 |
| In pit | `is_in_pit` | Pit state; preserve separately from pit-lane state |
| In pit lane | `is_in_pit_lane` | Separate pit-lane indicator |
| Out of pit / pit exit | Transition in `is_in_pit_lane`, `is_in_pit`, normalized position and lap/timing fields | Event/state transition; validate against live sequence |
| On track | Combination of session status, pit fields, normalized position and Physics movement | No single documented `on_track` boolean |
| Out lap / in lap / flying lap | Derived observer using pit transitions, completed laps, lap times, sector and validity | No dedicated documented out-lap boolean |
| Lap validity | `is_valid_lap` | Direct candidate timing-validity field |
| Lap/sector progress | `completed_laps`, `number_of_laps`, `current_sector_index`, `i_current_time`, `i_last_time`, `i_best_time`, `i_split`, `last_sector_time` | Some duplicate/legacy-looking fields must be compared live |
| Session end/progress | `session_time_left`, `session`, `session_index`, `status` | Validate transitions and sentinel values |
| Position and field | `position`, `active_cars`, `car_coordinates[60][3]`, `car_id[60]`, `player_car_id` | Includes other cars, not only player car |
| Flags/penalties | `flag`, `penalty`, `penalty_time`, global flag fields | Enumerations and live transitions need validation |
| Track/weather | `track_status`, `track_grip_status`, `surface_grip`, rain intensities, wind fields, `clock` | Preserve raw values before mapping labels |
| Pit strategy/MFD | tyre set, fuel-to-add and four MFD pressures; mandatory pit fields | Preserve all values, validate units and sentinels |
| Car configuration/display | TC, TC cut, engine map, ABS, lights, wiper, exhaust temperature, display indexes | Dynamic settings, not acquisition logic |

## Candidate enum values

### ACC status

| Value | Reference label |
|---:|---|
| 0 | OFF |
| 1 | REPLAY |
| 2 | LIVE |
| 3 | PAUSE |

### Session type

| Value | Reference label |
|---:|---|
| -1 | UNKNOWN |
| 0 | PRACTICE |
| 1 | QUALIFY |
| 2 | RACE |
| 3 | HOTLAP |
| 4 | TIME ATTACK |
| 5 | DRIFT |
| 6 | DRAG |
| 7 | HOTSTINT |
| 8 | HOTSTINT SUPERPOLE |

Other enumerations in the reference include flag, penalty, track-grip status and rain intensity. Their raw integer values will be preserved; semantic mapping is downstream and must be checked against the target build.

## Complete candidate field inventory

Offsets are zero-based byte offsets. Scalar types use 4 bytes; UTF-16 strings use 2 bytes per code unit; arrays are contiguous. Offsets apply only to the v1.8.12-derived candidate under 4-byte packing.

| Field | Candidate type | Offset | Size (bytes) |
|---|---|---:|---:|
| `packet_id` | `int32` | 0 | 4 |
| `status` | `int32` | 4 | 4 |
| `session` | `int32` | 8 | 4 |
| `current_time` | `uint16[15]` | 12 | 30 |
| `last_time` | `uint16[15]` | 42 | 30 |
| `best_time` | `uint16[15]` | 72 | 30 |
| `split` | `uint16[15]` | 102 | 30 |
| `completed_laps` | `int32` | 132 | 4 |
| `position` | `int32` | 136 | 4 |
| `i_current_time` | `int32` | 140 | 4 |
| `i_last_time` | `int32` | 144 | 4 |
| `i_best_time` | `int32` | 148 | 4 |
| `session_time_left` | `float32` | 152 | 4 |
| `distance_traveled` | `float32` | 156 | 4 |
| `is_in_pit` | `int32` | 160 | 4 |
| `current_sector_index` | `int32` | 164 | 4 |
| `last_sector_time` | `int32` | 168 | 4 |
| `number_of_laps` | `int32` | 172 | 4 |
| `tyre_compound` | `uint16[33]` | 176 | 66 |
| `replay_time_multiplier` | `float32` | 244 | 4 |
| `normalized_car_position` | `float32` | 248 | 4 |
| `active_cars` | `int32` | 252 | 4 |
| `car_coordinates` | `float32[60][3]` | 256 | 720 |
| `car_id` | `int32[60]` | 976 | 240 |
| `player_car_id` | `int32` | 1216 | 4 |
| `penalty_time` | `float32` | 1220 | 4 |
| `flag` | `int32` | 1224 | 4 |
| `penalty` | `int32` | 1228 | 4 |
| `ideal_line_on` | `int32` | 1232 | 4 |
| `is_in_pit_lane` | `int32` | 1236 | 4 |
| `surface_grip` | `float32` | 1240 | 4 |
| `mandatory_pit_done` | `int32` | 1244 | 4 |
| `wind_speed` | `float32` | 1248 | 4 |
| `wind_direction` | `float32` | 1252 | 4 |
| `is_setup_menu_visible` | `int32` | 1256 | 4 |
| `main_display_index` | `int32` | 1260 | 4 |
| `secondary_display_index` | `int32` | 1264 | 4 |
| `tc` | `int32` | 1268 | 4 |
| `tc_cut` | `int32` | 1272 | 4 |
| `engine_map` | `int32` | 1276 | 4 |
| `abs` | `int32` | 1280 | 4 |
| `fuel_x_lap` | `float32` | 1284 | 4 |
| `rain_lights` | `int32` | 1288 | 4 |
| `flashing_lights` | `int32` | 1292 | 4 |
| `lights_stage` | `int32` | 1296 | 4 |
| `exhaust_temperature` | `float32` | 1300 | 4 |
| `wiper_level` | `int32` | 1304 | 4 |
| `driver_stint_total_time_left` | `int32` | 1308 | 4 |
| `driver_stint_time_left` | `int32` | 1312 | 4 |
| `rain_tyres` | `int32` | 1316 | 4 |
| `session_index` | `int32` | 1320 | 4 |
| `used_fuel` | `float32` | 1324 | 4 |
| `delta_lap_time` | `uint16[15]` | 1328 | 30 |
| `i_delta_lap_time` | `int32` | 1360 | 4 |
| `estimated_lap_time` | `uint16[15]` | 1364 | 30 |
| `i_estimated_lap_time` | `int32` | 1396 | 4 |
| `is_delta_positive` | `int32` | 1400 | 4 |
| `i_split` | `int32` | 1404 | 4 |
| `is_valid_lap` | `int32` | 1408 | 4 |
| `fuel_estimated_laps` | `float32` | 1412 | 4 |
| `track_status` | `uint16[33]` | 1416 | 66 |
| `missing_mandatory_pits` | `int32` | 1484 | 4 |
| `clock` | `float32` | 1488 | 4 |
| `direction_lights_left` | `int32` | 1492 | 4 |
| `direction_lights_right` | `int32` | 1496 | 4 |
| `global_yellow` | `int32` | 1500 | 4 |
| `global_yellow_1` | `int32` | 1504 | 4 |
| `global_yellow_2` | `int32` | 1508 | 4 |
| `global_yellow_3` | `int32` | 1512 | 4 |
| `global_white` | `int32` | 1516 | 4 |
| `global_green` | `int32` | 1520 | 4 |
| `global_chequered` | `int32` | 1524 | 4 |
| `global_red` | `int32` | 1528 | 4 |
| `mfd_tyre_set` | `int32` | 1532 | 4 |
| `mfd_fuel_to_add` | `float32` | 1536 | 4 |
| `mfd_tyre_pressure_lf` | `float32` | 1540 | 4 |
| `mfd_tyre_pressure_rf` | `float32` | 1544 | 4 |
| `mfd_tyre_pressure_lr` | `float32` | 1548 | 4 |
| `mfd_tyre_pressure_rr` | `float32` | 1552 | 4 |
| `track_grip_status` | `int32` | 1556 | 4 |
| `rain_intensity` | `int32` | 1560 | 4 |
| `rain_intensity_10min` | `int32` | 1564 | 4 |
| `rain_intensity_30min` | `int32` | 1568 | 4 |
| `current_tyre_set` | `int32` | 1572 | 4 |
| `strategy_tyre_set` | `int32` | 1576 | 4 |
| `gap_ahead` | `int32` | 1580 | 4 |
| `gap_behind` | `int32` | 1584 | 4 |

**Candidate field count:** 87  
**Candidate structure size:** 1588 bytes

## Acquisition design boundary

- Mapping name: `Local\\acpmf_graphics`.
- Dedicated Graphics acquisition source and acquisition loop; do not read Graphics from the Physics acquisition thread.
- Copy the complete validated Graphics structure/page bytes; no field filtering in acquisition.
- Assign independent capture sequence and monotonic read timestamps; retain Graphics packet ID before/after the copy as a best-effort consistency observation.
- Dedicated bounded acquisition ring buffer and a separate recorder handoff. No shared destructive queue between consumers.
- Recorder uses the existing raw-first integrity model, but the on-disk format must identify page type and payload size so Physics and Graphics cannot be confused.
- No decoding, lap classification, state-machine logic, UI, JSON/DB writes or disk I/O in the acquisition hot path.
- Offline inspector will inventory every candidate field and preserve unknown/reserved bytes.

## First live mapping probe

A read-only diagnostic script has been added:

```powershell
python scripts/probe_acc_graphics.py --duration-seconds 5 --sample-interval-ms 10
```

It opens `Local\\acpmf_graphics` with read/query access only, samples the leading packet ID, queries the section allocation size, and saves one complete copy of the mapped section to a `.graphics-page.bin` file plus a JSON report under `user_data/raw_recordings`.

The mapping allocation size is intentionally reported separately from the 1,588-byte candidate structure size. A page-rounded allocation (for example 4,096 bytes) is not evidence that all bytes belong to the logical Graphics structure. The raw file lets us inspect the complete mapped region without committing to field offsets. This is a one-shot diagnostic probe, not the production acquisition/recorder.

## ABI verification gates before production layout lock

1. Read the live `Local\\acpmf_graphics` mapping read-only while ACC 1.10.4 is running.
2. Query the mapping section allocation size, but do not mistake page-rounded allocation size (for example 4096 bytes) for the logical C structure size.
3. Capture raw Graphics bytes and packet IDs without semantic decoding.
4. Compare the candidate 1,588-byte structure against observed packet progression and byte ranges; inspect trailing bytes separately.
5. Cross-check Shared Memory 1.9 field-order/type changes against all available independent references.
6. Only then lock the exact target layout and add offset/size regression tests.
7. Validate all fields with controlled game states and document each as validated, observed, reference-only, unused, conditional or unresolved.

## State semantics — important distinction

- `status == PAUSE` is the documented direct pause signal.
- `is_in_pit` and `is_in_pit_lane` are separate direct fields and must not be collapsed.
- The documented Graphics structure has no explicit `out_lap`, `in_lap`, `flying_lap`, `on_track`, `in_garage` or `pit_box` boolean. Those classifications must be derived only after controlled validation of the direct fields and timing transitions.
- A zero Physics speed alone is not sufficient to infer garage, pit box or on-track state.
- Preserve replay as a distinct state; do not treat replay as live driving.

## Out of scope for Stage 5.1

No production Graphics structure, acquisition thread, recorder or semantic decoder is added by this investigation document. Those follow only after the live Shared Memory 1.9 ABI check. Physics code and its existing 784-byte adapter remain untouched.


## RaceIQ and Pro Engineer cross-check — 9 November 2026

The requested reference implementations have now been inspected directly, at pinned commits:

- **RaceIQ:** [ACC structure definitions](https://github.com/SpeedHQ/RaceIQ/blob/64a34783f706722cf342e18ecb7fc06d29f30f8e/packages/capture-formats/src/acc/structs.ts), [ACC adapter notes](https://github.com/SpeedHQ/RaceIQ/blob/64a34783f706722cf342e18ecb7fc06d29f30f8e/docs/reference/adapters/acc.md), and [shared-memory reader](https://github.com/SpeedHQ/RaceIQ/blob/64a34783f706722cf342e18ecb7fc06d29f30f8e/packages/game-acc/src/shared-memory.ts).
- **Pro Engineer:** [complete ACC structures](https://github.com/Rgosh/ac-pro-engineer/blob/b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26/core/src/games/assetto_corsa_competizione/structs.rs) and [ACC implementation plan/live-capture notes](https://github.com/Rgosh/ac-pro-engineer/blob/b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26/docs/plan-acc.md).

### Direct comparison results

1. Both use `Local\\acpmf_graphics` and declare a **1,588-byte** ACC Graphics structure.
2. RaceIQ's current `GRAPHICS` offset map contains 44 explicit offset descriptors. Every descriptor aligns to the corresponding Pro Engineer member offset; naming differs mainly by camelCase versus snake_case, and RaceIQ represents the large car arrays by base offset/stride.
3. RaceIQ's offset map ends at `clock` (offset 1488) and does not explicitly enumerate the final 96 bytes. Its parser also accepts a 1,320-byte legacy minimum for old recordings. That compatibility path is not the complete current page and will not be used as the new raw-recording size.
4. Pro Engineer declares the complete 87-member `AccGraphics` structure, including direction indicators, global flags, MFD requests, track-grip/rain fields, tyre-set indices and gaps through `gap_behind` at offset 1584. It has compile-time assertions for total size 1588 and selected field offsets.
5. Pro Engineer's implementation notes describe a 337-second / 8,376-sample live ACC session capture and distinguish fields whose offsets were supported by observed values from fields that remained zero and were only retained for layout. This is useful empirical corroboration, not an official Kunos header.

### Decision

Use the **complete 87-field Pro Engineer sequence** as the full candidate field inventory, with RaceIQ as an independent offset cross-check for the 44 descriptors it exposes. Keep the existing target-PC raw capture of the **entire 4,096-byte mapping allocation**; treat the first 1,588 bytes as the candidate logical Graphics structure and the remaining 2,508 bytes as opaque mapping tail unless new evidence proves otherwise. Do not truncate new raw captures to 1,320 bytes or to the subset of fields currently consumed by the application.

This materially strengthens the 1,588-byte candidate but does **not** turn the v1.8.12-derived third-party layout into official Shared Memory 1.9 confirmation. The existing live target capture and trailing-zero observation remain separate evidence. No production Graphics structure or reader is authorized by this cross-check alone.
