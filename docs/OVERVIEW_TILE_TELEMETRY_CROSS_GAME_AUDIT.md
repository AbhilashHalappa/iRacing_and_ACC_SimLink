# Unified Overview Tile Telemetry Audit — ACC Baseline and iRacing Adapter

**Repository:** `AbhilashHalappa/iRacing_and_ACC_SimLink`  
**Branch:** `feature/iracing-game-support`  
**Audited revision:** `9f0f521d17ba0d7c02f7062f8224fc2ad60fa5c4`  
**Scope:** All 24 configurable Overview tiles; frontend field consumption; ACC publisher contract; iRacing reader/publisher contract; canonical telemetry alignment.  
**Change type:** Documentation-only audit. No application source or runtime behaviour was changed.

## 1. Purpose and audit method

This document checks what the shared Overview actually renders, which snapshot fields it reads, what the two game adapters currently publish, and whether those values have compatible meanings and units.

The audit cross-checked:

- `frontend/src/App.tsx` — tile definitions, tile rendering, stream dependencies, driver trace and local lap-history capture.
- `frontend/src/timeDisplay.mjs` and `frontend/src/tileAvailability.mjs` — shared formatting and stream-health behaviour.
- `src/desktop/qt_host.py` — ACC snapshot publication.
- `src/desktop/iracing_host.py` and `src/desktop/switchable_host.py` — iRacing and switchable publication.
- `src/desktop/bridge.py` — snapshot transport.
- `src/iracing/reader.py` — current iRacing SDK field mapping and derived values.
- `docs/ACC_Telemetry_Overview_Field_Mapping_and_Findings.md` — detailed ACC source/decoder/frontend mapping.
- `docs/IRACING_OVERVIEW_FIELD_MAPPING.md` — prior iRacing field audit, cross-checked against the current reader.
- `docs/UNIFIED_TELEMETRY_NORMALIZATION_AND_GAME_CONVERSION_SPEC.md` — canonical field and unit requirements.

This is a source-code contract audit. It does not claim that every simulator field has been live-tested in the current build. ACC is treated as the established and user-tested baseline; this audit does not ask to repeat ACC validation.

## 2. Executive findings

### 2.1 Overview inventory

The frontend defines **24 configurable tiles**:

1. Driver Trace
2. Speed
3. Gear
4. Engine RPM
5. Driver Inputs / Pedals
6. Lap Times
7. Lap Time History
8. Track Weather
9. Track Map
10. Session
11. Brake Temperatures
12. Tyre Condition
13. Fuel
14. Penalties & Warnings
15. Hardware Connections
16. Delta to Best Lap
17. Sector Performance
18. Race Position & Gaps
19. Car Electronics
20. Pit Stop & Stint
21. Vehicle Damage
22. Tyre Pressure Targets
23. Race Control
24. Car Lights & Status

The tile order and visibility can be customised. The tile identifiers and source bindings are defined in the frontend, not in a separate per-game UI.

### 2.2 High-priority cross-game contract problems

The following are confirmed by the current source:

1. **Session time is formatted with an ACC-specific milliseconds assumption.** The shared helper divides `session_time_left_s` by 1000. The iRacing reader publishes `SessionTimeRemain` in seconds under `session_time_left_s`. Therefore iRacing session time is divided by 1000 a second time and displays incorrectly. ACC has a separate producer/consumer naming mismatch: its decoder emits `session_time_left_ms`, while the frontend reads `session_time_left_s`.
2. **Porsche brake-bias correction is applied in shared frontend code.** `correctedBrakeBiasPercent()` subtracts 21 percentage points whenever the car model string contains both “porsche” and “992”, without checking the active game. This ACC-specific correction can therefore affect an iRacing Porsche 992 value too. Brake-bias scaling must be handled by a game/car profile, not a shared frontend guess.
3. **The iRacing tyre-pressure field is cold setup pressure, not live hot pressure.** The adapter reads `LF/RF/LR/RRcoldPressure`, converts kPa to PSI, and publishes it as `tyre_pressure_psi`. The shared Tyre Condition and Tyre Pressure Targets tiles label it simply as pressure/actual. That presentation loses an important semantic distinction.
4. **The iRacing tyre-temperature field is an average of three zones.** The reader averages the available inner/middle/outer channels and publishes the result as `tyre_core_temp_c`. An average of three zones must not be described as a direct core sensor measurement.
5. **Lap validity and penalties are not mapped for iRacing.** The reader publishes `is_valid_lap=None`, `penalty=None`, and `penalty_time_s=None`. The shared tiles correctly have no reliable validity/penalty value to show, but the current Overview has no iRacing-specific explanation of why those fields are unavailable.
6. **Lap History remains three-sector-shaped.** The iRacing sector tile supports dynamic sector boundaries, but the separate frontend lap-history capture and history row remain hard-coded to S1/S2/S3 and only capture the first two boundaries.
7. **iRacing MFD fuel-to-add is always labelled L by the shared UI.** The current iRacing mapping notes that `PitSvFuel` may represent litres or kWh depending on vehicle. The UI must not append L when the unit is not known to be litres.
8. **Hardware Connections is not connected to hardware state.** The tile currently renders five hard-coded “Not reported” rows. It is a placeholder, not a live hardware integration.
9. **Track Map has no iRacing world position.** The reader provides lap progress/distance but publishes `player_world_position=None`. Lap progress alone is not a world-coordinate point from which the current learned circuit map can be drawn.
10. **The ACC and iRacing stream envelopes are structurally similar but not semantically identical.** The same React tile reads both, so units, unavailable states and game-specific meanings must be normalised before the frontend consumes them.

### 2.3 Architecture decision

Keep one shared Overview and one canonical field contract. Each game adapter is responsible for translating its native SDK/shared-memory fields into that contract, including units, provenance, and availability. The frontend should render canonical fields and user presentation settings; it should not contain game-specific conversions or car-specific telemetry corrections.

## 3. Status vocabulary

| Status | Meaning |
|---|---|
| **Mapped** | Current adapter publishes a field that is consumed by the tile with a compatible meaning and unit. |
| **Mapped — derived** | Current adapter/application computes the field from source telemetry or observed events; provenance must remain marked as derived. |
| **Partial** | Some subfields are available, but other displayed subfields are missing, uncertain, or only available for certain cars/session types. |
| **Not displayed** | Adapter publishes a useful field, but the current tile does not render it. |
| **Unavailable / no safe equivalent** | No trustworthy generic source is currently mapped. Keep it unavailable; do not substitute a different concept. |
| **Presentation mismatch** | Source value exists, but the shared frontend labels, scales, formats or interprets it incorrectly for at least one game. |
| **External** | Not simulator telemetry; belongs to the separate SimLink hardware/device subsystem. |

## 4. Shared snapshot and presentation contract

### 4.1 Snapshot shape

The shared tile component reads:

- `telemetry.physics.data` for vehicle/driver/tyre/brake values.
- `telemetry.graphics.data` for timing/session/weather/race-control values.
- `telemetry.static_metadata.data` for static vehicle metadata such as maximum fuel.
- `telemetry.vehicle` for car, track and configuration identity.
- `telemetry.lap_history` for locally retained completed-lap records.
- `telemetry.streams` and `telemetry.connected` for stream health.

The ACC Qt host publishes Physics and Graphics payloads and a `vehicle` object, but does not currently publish a `static_metadata` payload. The Static decoder is used to populate vehicle identity. The iRacing reader publishes `static_metadata.data.max_fuel` from `DriverCarFuelMaxLtr`.

The bridge is a transport only. It serves the detached snapshot supplied by the active host; it does not decode simulator telemetry.

### 4.2 Unit and conversion ownership

| Measurement | Canonical/internal contract | Display conversion |
|---|---|---|
| Speed | m/s | km/h = m/s × 3.6 |
| Gear | Normalized reverse / neutral / forward | Game-independent display label |
| RPM | rev/min | Display RPM |
| Pedals | 0–1 | percent = value × 100 |
| Steering angle | radians | degrees = radians × 180 / π |
| Lap/sector/session duration | milliseconds in canonical timing fields | Format once at UI boundary |
| Fuel | Explicit volume or mass unit per source; ACC Overview uses L | Never infer kg = L; preserve L for ACC and verify other game units |
| Temperature | °C | Display °C |
| Pressure | Pa internally where a physical pressure channel is used | PSI = Pa / 6894.757293 |
| Wind speed | m/s | km/h = m/s × 3.6 |
| Wind direction | radians | Degrees/compass at presentation boundary |
| Track progress | 0–1 | percent or map progress |

Do not use one generic numeric field for two different physical quantities. Where a simulator supplies cold setup pressure rather than live pressure, expose that semantic distinction explicitly.

## 5. Tile-by-tile source mapping

The tables below describe the current source-code mapping. “ACC source” refers to the established ACC mapping documented in the ACC baseline file. “iRacing source” refers to the current `IRacingTelemetryReader` implementation at the audited revision.

### 5.1 Driver Trace

| Item | Current binding / source | ACC | iRacing |
|---|---|---|---|
| Brake | Physics `brake` | Mapped; normalized 0–1 | Mapped; SDK `Brake`, 0–1 |
| Throttle | Physics `throttle` | Mapped; normalized 0–1 | Mapped; SDK `Throttle`, 0–1 |
| Gear | Physics `gear_raw` | Mapped; ACC raw gear encoding is transformed in the frontend trace | Mapped; SDK `Gear` is normalized by the reader then transformed back to trace gear |
| Speed | Physics `speed_kph` | Mapped; already km/h | Mapped; SDK `Speed` m/s converted to km/h in reader |
| RPM | Physics `rpm` | Mapped | Mapped; SDK `RPM` |
| Distance/reset context | Graphics `distance_traveled_m`, `normalized_car_position`, `completed_laps` | Mapped | Mapped; `LapDist`, `LapDistPct`, `LapCompleted` |

**Finding:** Trace points are application-sampled, not a simulator-provided historical trace. The frontend requires valid normalized lap progress and distance. It resets on session identity/lap wrap. This tile has a viable common contract for both games.

### 5.2 Speed

- **Frontend:** `physics.data.speed_kph`, displayed directly as km/h.
- **ACC:** `speed_kph`, already km/h.
- **iRacing:** `Speed` in m/s, converted by the reader using ×3.6.
- **Status:** Mapped for both games. Do not convert again in the frontend.

### 5.3 Gear

- **Frontend:** `physics.data.gear_display`.
- **ACC:** decoder-specific raw gear convention; published display form is used.
- **iRacing:** SDK `Gear`: −1 reverse, 0 neutral, positive forward. Reader emits `gear_display` and `gear_raw=gear+1` for compatibility with the trace calculation.
- **Status:** Mapped for both. Keep native encoding out of shared UI.

### 5.4 Engine RPM

- **Frontend:** `rpm`, `current_max_rpm`; the 15-segment shift display is UI presentation logic and activates at 95% of maximum.
- **ACC:** Physics RPM and current maximum RPM.
- **iRacing:** `RPM`; maximum/shift threshold from DriverInfo `DriverCarSLShiftRPM`, falling back to player/DriverInfo blink RPM.
- **Status:** Mapped. The threshold is not a universal simulator shift-light signal; preserve the distinction between engine RPM and selected shift threshold.

### 5.5 Driver Inputs / Pedals

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Steering | `steering_angle`, converted rad→degrees in UI | Physics steering angle | `SteeringWheelAngle`, radians |
| Throttle | `throttle` ×100 | Physics normalized input | `Throttle`, 0–1 |
| Brake | `brake` ×100 | Physics normalized input | `Brake`, 0–1 |
| Clutch | `clutch` ×100 | Physics normalized input | `Clutch`, 0–1 |

**Status:** Mapped for both. iRacing handbrake is emitted separately but is not currently rendered in this tile. The displayed pedal values are simulator inputs, not the physical SimLink pedal board sensor readings.

### 5.6 Lap Times

- **Frontend:** Graphics `current_time_ms/current_time_str`, `last_time_ms/last_time_str`, `best_time_ms/best_time_str`, `completed_laps`, `is_valid_lap`, and host/adapter `lap_status`.
- **ACC:** Graphics supplies current/last/best timing and validity; the host injects out-lap status from the shared out-lap observer.
- **iRacing:** `LapCurrentLapTime`, `LapLastLapTime`, `LapBestLapTime`, `LapCompleted` are converted to milliseconds and strings. Reader currently sets `is_valid_lap=None` and `lap_status=None`.
- **Status:** Timing and lap count are mapped for both. iRacing lap legality/validity and out-lap classification are unavailable. Do not use `LapDeltaToBestLap_OK` as lap validity; it only qualifies the delta reference.
- **Impact:** iRacing can show current/last/best times, but the VALID/INVALID/OUT LAP status cannot be asserted by the current reader.

### 5.7 Lap Time History

- **Frontend:** `telemetry.lap_history`, with lap number, time, validity, delta to current best, and S1/S2/S3.
- **ACC:** App captures completed laps locally from Graphics transitions, boundary times and validity; out-laps are excluded. Existing implementation is three-sector-shaped.
- **iRacing:** Reader currently returns an empty `lap_history`; the frontend can capture from live timing, but reader `is_valid_lap` is null. The frontend capture logic is still fixed to sectors 0, 1 and 2 and stores only S1/S2/S3.
- **Status:** Partial / application-derived. Lap time capture can work, but validity remains unknown and tracks with more than three sectors are not fully retained in lap history.
- **Required:** Separate lap-history record schema from fixed S1/S2/S3 fields. Store a dynamic sector-duration array and a validity state that supports valid / invalid / unknown.

### 5.8 Track Weather

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Road/track temperature | Physics `road_temp_c` | Physics road temperature | `TrackTempCrew`, °C |
| Air temperature | Physics `air_temp_c` | Physics air temperature | `AirTemp`, °C |
| Track grip | Graphics `track_grip_status` | ACC grip enum; source mapping documented, unknown values remain neutral | No direct equivalent; null |
| Rain now / forecast | Graphics `rain_intensity`, `rain_10min`, `rain_30min` | ACC Graphics values; enum semantics must follow ACC mapping | Not mapped; `TrackWetness` is not rain intensity or a forecast |
| Wind speed | Graphics `wind_speed`, displayed km/h | UI labels km/h; source unit requires preserving the established ACC mapping | `WindVel` m/s converted to km/h |
| Wind direction | Graphics `wind_direction`, rad→compass | ACC source semantics need to follow ACC decoder evidence | `WindDir`, radians |

**Status:** Partial for iRacing. Track/air temperature and wind are mapped; ACC-style grip and rain forecast are unavailable. Do not substitute wetness for rain intensity.

### 5.9 Track Map

- **Frontend:** `TrackMapTile` consumes vehicle track/configuration plus Graphics progress, position and lap context.
- **ACC:** Track identity comes from Static-derived `vehicle`; Graphics provides normalized progress and player world coordinates. The map is learned from valid captured world-coordinate samples and cached locally.
- **iRacing:** Track/configuration and `LapDistPct`/`LapDist` are mapped, but reader publishes `player_world_position=None`. Lap progress is not a world X/Y coordinate.
- **Status:** Partial for iRacing. Track identity/progress exist; the current learned-map geometry/vehicle-position capture does not have the world-coordinate pair it needs.
- **Required:** Keep the map unavailable or show only a clearly identified progress indicator until a trustworthy coordinate/geometry source is implemented. Do not invent world coordinates from lap percentage.

### 5.10 Session

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Track | `vehicle.track` | Static-derived identity | `WeekendInfo.TrackName` |
| Session type | Graphics `session` | ACC enum mapping | `SessionInfo.Sessions[SessionNum].SessionType` mapped to shared known values |
| Session status | Graphics `status` | ACC status enum | Derived from `IsReplayPlaying` / `IsOnTrack` |
| Time left | Graphics `session_time_left_s` passed to `sessionTimeDisplay` | Decoder emits `session_time_left_ms`; host does not rename it to the frontend key | `SessionTimeRemain` in seconds is published as `session_time_left_s` |
| Lap count | Graphics `completed_laps` | Mapped | `LapCompleted` |
| Position / active cars | Graphics `position`, `active_cars` | Mapped | `PlayerCarPosition`, DriverInfo Drivers |
| Tyre compound | Graphics `tyre_compound` | ACC Graphics source | `PlayerTireCompound` |

<badge color="danger">Confirmed iRacing formatting bug</badge> The shared `sessionTimeDisplay()` helper divides the input by 1000 because it was written for the ACC millisecond payload. iRacing already publishes seconds. This causes the iRacing time-left display to be approximately 1000 times too small. The correct fix is a canonical `session_time_remaining_ms` (or explicit unit-tagged seconds) contract, not a game conditional inside the formatter.

### 5.11 Brake Temperatures

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Disc temperature per corner | `wheels[corner].brake_temp_c` | Physics brake temperature | No general live brake-temperature channel mapped; null |
| Brake pressure | `wheels[corner].brake_pressure` | Physics brake pressure; unit/scale documented as needing confirmation | `LF/RF/LR/RRbrakeLinePress`, reader mapping documents bar |
| Pad life | `pad_life` | Physics candidate life channel | No general live pad-life field; null |
| Disc life | `disc_life` | Physics candidate life channel | No general live disc-life field; null |

**Status:** Partial for iRacing. Brake temperature and pad/disc life are unavailable. Brake line pressure is mapped, but the UI currently displays it without a unit suffix. Do not convert a missing temperature into zero.

### 5.12 Tyre Condition

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Tyre temperature | `tyre_core_temp_c` | ACC selected core-temperature field | Average of available `tempCL`, `tempCM`, `tempCR` zones |
| Pressure | `tyre_pressure_psi` | ACC Physics pressure already PSI | `coldPressure` in kPa converted to PSI; this is cold setup pressure, not live hot pressure |
| Slip ratio | `slip_ratio` | ACC Physics channel | Null |
| Slip angle | `slip_angle` | ACC Physics channel | Null |
| Tread remaining | `tyre_wear_pct` | Not currently displayed by the tile | Reader emits average of available `wearL/M/R`; not displayed by the current tile |

**Status:** Partial for iRacing. The current tile presents a temperature and pressure number, but their semantics differ from the ACC fields. The iRacing temperature is a three-zone average, and pressure is cold setup pressure. Slip values are unavailable. Tread remaining is already in the payload but not rendered.

**Required:** Use explicit field semantics such as `tyre_temperature_zone_average_c` and `cold_setup_pressure_psi` until a true core/hot-pressure source is available. The shared tile must not label cold pressure as live actual pressure.

### 5.13 Fuel

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Remaining fuel | Frontend currently reads `physics.data.fuel_kg`, displays L | ACC game UI displays L; preserve the established ACC display contract | `FuelLevel` is L; reader emits `fuel_l` and a legacy `fuel_kg` alias whose comment explicitly says the value is litres |
| Fuel per lap | Graphics `fuel_per_lap_l` | ACC Graphics `fuel_x_lap` mapped to L/lap | Derived from `FuelLevel` at completed-lap transitions |
| Estimated laps | Graphics `fuel_estimated_laps` | ACC Graphics estimated-laps field | Derived from remaining fuel / smoothed fuel per lap |
| Tank capacity | `static_metadata.data.max_fuel` | Static decoder reads `max_fuel`, but ACC Qt snapshot does not currently publish `static_metadata` | `DriverCarFuelMaxLtr`, published in `static_metadata.data.max_fuel` |
| Fuel bar | Current fuel / highest value observed since app start | Session-observed high-water reference | Same frontend logic |

**Status:** Remaining fuel and consumption estimates are mapped for iRacing. ACC fuel is already established as litres by the user; no repeat ACC fuel validation is part of this audit. The iRacing adapter currently retains a legacy `fuel_kg` alias solely because the shared frontend reads it; the canonical contract should replace that alias with an explicitly unit-bearing `fuel_remaining_l`.

### 5.14 Penalties & Warnings

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Lap validity | Graphics `is_valid_lap` | ACC validity source | Null; no safe equivalent currently mapped |
| Penalty type | Graphics `penalty` | ACC penalty enum | Null; SessionFlags are not ACC penalty codes |
| Penalty time | Graphics `penalty_time_s` | ACC field name/unit requires preserving the documented ms semantics | Null |
| Missing mandatory pits | `missing_mandatory_pits` | ACC Graphics source | Null |
| Mandatory pit complete | `mandatory_pit_done` | ACC Graphics source | Null |
| Incidents | Not currently rendered | N/A | Reader emits player/team/driver incident counts, but this tile does not display them |

**Status:** iRacing unavailable for the ACC-specific penalty/validity fields. Incident counts are available in the iRacing payload and are not currently displayed. Do not map SessionFlags to ACC penalty enums.

### 5.15 Hardware Connections

- **Frontend:** Five hard-coded rows: Wheel USB link, Wheel device, Pedals device, Handbrake device, RPM LED Controller.
- **Current behaviour:** Each row always renders “Not reported”.
- **ACC/iRacing:** Neither simulator adapter supplies these values. They belong to the SimLink hardware/device subsystem.
- **Status:** External placeholder; not connected to live hardware state in this Overview implementation.
- **Required:** Integrate the existing hardware bridge/state source separately. Do not infer USB/device state from simulator telemetry.

### 5.16 Delta to Best Lap

- **Frontend:** Graphics `delta_lap_time_str`, `delta_positive`, `estimated_lap_time_ms/str`, `best_time_ms/str`.
- **ACC:** Graphics delta and estimated lap fields; sign semantics remain a source-validation item in the ACC baseline.
- **iRacing:** `LapDeltaToBestLap` seconds converted to milliseconds/string; direction from sign; estimated lap computed as best lap + delta.
- **Status:** Mapped for iRacing. Delta sign and reference validity must remain explicit. Do not confuse delta-reference validity with lap validity.

### 5.17 Sector Performance

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Current sector | Graphics `sector` | ACC sector field | Derived from `SplitTimeInfo.Sectors[].SectorStartPct` and `LapDistPct` |
| Dynamic sector count/boundaries | `sector_boundaries_pct` | ACC currently has a fixed three-sector assumption in parts of Overview/lap history | Reader derives dynamic boundary array from active track session metadata |
| Live sector time | `live_sector_time_ms` | Current ACC decoder contract does not directly expose the frontend's expected field | Derived from `LapCurrentLapTime` minus the observed boundary time |
| Completed sector times | `sector_times_ms` | ACC lap-history boundary observations | Derived from observed dynamic sector crossings |
| Best sector history | Frontend history | Current Overview best-sector calculation is fixed to three sectors | Not available from reader history; current reader returns empty `lap_history` |

**Status:** iRacing current-sector tile supports dynamic sector count. If the application attaches mid-sector, the active partial sector remains unavailable until a boundary is observed; this is intentional and must not be fabricated.

**Important limitation:** The dynamic sector tile and the lap-history tile are separate paths. The dynamic sector tile can show the active iRacing track's sector count, but frontend lap-history capture still records only S1/S2/S3. Best-sector history is also not dynamic. This is a known frontend limitation, not a missing iRacing SDK feature.

### 5.18 Race Position & Gaps

- **Frontend:** Graphics `position`, `active_cars`, `gap_ahead_ms`, `gap_behind_ms`.
- **ACC:** Graphics position/gap fields; sign/reference requires multi-car validation.
- **iRacing:** `PlayerCarPosition`, DriverInfo Drivers count, and Race-session `CarIdxPosition` + `CarIdxF2Time` association. Gaps are emitted only when a Race session and valid opponents are available.
- **Status:** Mapped for iRacing in Race sessions; no gap should be displayed outside the supported context. Class position is emitted but not currently rendered.

### 5.19 Car Electronics

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| TC level | Graphics `tc_level` | ACC setup level | `dcTractionControl`, vehicle-dependent |
| ABS level | Graphics `abs_level` | ACC setup level | `dcABS`, vehicle-dependent |
| Brake bias | Physics `brake_bias` through shared `correctedBrakeBiasPercent()` | ACC Porsche correction is already known to be car-specific and unresolved in the baseline | `dcBrakeBias`; scale is car-specific and must not receive ACC correction |
| TC cut | Graphics `tc_cut` | ACC field | Null |
| Engine map | Graphics `engine_map` | ACC field | Null |
| Auto shifter | Physics `autoshifter_on` | ACC field | Null |
| Turbo boost | Physics `turbo_boost` | ACC field; unit requires validation | Null; `ManifoldPress` is manifold pressure, not turbo boost |

<badge color="danger">Cross-game correction leak</badge> The shared brake-bias helper checks only car model and applies the Porsche 992 −21 percentage-point offset. It does not check `telemetry.game`. Move this correction/scale interpretation into the ACC adapter or a verified ACC car profile. iRacing `dcBrakeBias` must pass through its own verified scale unchanged.

### 5.20 Pit Stop & Stint

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Pit box / stall | Graphics `is_in_pit` | ACC pit-stall state | `PlayerCarInPitStall` |
| Pit lane | Graphics `is_in_pit_lane` | ACC pit-lane state | `OnPitRoad` |
| Mandatory stop complete | `mandatory_pit_done` | ACC source | No safe universal equivalent; null |
| Stint total/time left | `driver_stint_total_ms`, `driver_stint_left_ms` | ACC fields; semantics need confirmation | No universal direct equivalent currently mapped |
| Fuel used | `used_fuel_l` | ACC Graphics field; unit semantics documented for confirmation | Session-start FuelLevel minus current FuelLevel |
| MFD fuel to add | `mfd_fuel_to_add`, frontend currently appends L | ACC Graphics MFD request | `PitSvFuel`; may be L or kWh depending on vehicle |
| MFD/current/strategy tyre set | `mfd_tyre_set`, `current_tyre_set`, `strategy_tyre_set` | ACC sources | No universal current tyre-set index; null |
| Tyre change request | Derived from MFD vs current set | ACC comparison | Not mapped |
| MFD pressure requests | `mfd_tyre_pressures[i]`, UI appends PSI | ACC Graphics request fields; source units require validation | `PitSvLFP/RFP/LRP/RRP`, kPa→PSI |
| Tyre compound | `tyre_compound` | ACC Graphics source | `PlayerTireCompound` |

**Status:** Partial for iRacing. Pit box/lane, fuel used, tyre compound and pressure requests are available. Mandatory stop, stint limit/time, and tyre-set comparison are not. The MFD fuel unit must be carried with the value; a hard-coded L suffix is not valid for all iRacing vehicles.

### 5.21 Vehicle Damage

- **Frontend:** `car_damage[5]` and `wheels[corner].suspension_damage`.
- **ACC:** Five raw car-damage channels and per-wheel suspension damage; scales are not universally established.
- **iRacing:** Reader sets `car_damage=None` and `suspension_damage=None`. Shock deflection/velocity are not damage and must not be substituted.
- **Status:** No safe generic iRacing equivalent currently mapped. Keep unavailable.

### 5.22 Tyre Pressure Targets

- **Frontend:** Per-corner `tyre_pressure_psi` compared with manually configured FL/FR/RL/RR target PSI from local storage.
- **ACC:** Live Physics pressure already PSI; target is a user-entered setting, not ACC MFD.
- **iRacing:** Reader uses cold setup pressure in kPa converted to PSI. Target remains user-entered.
- **Status:** Presentation mismatch for iRacing. The calculation is mathematically possible, but “Actual” is misleading because the source is cold setup pressure. Until live hot pressure exists, label both the source and comparison as cold setup pressure versus configured target, or mark the comparison unavailable.
- **Required:** Keep user target settings game-aware if the user expects different target values for different cars/games; do not silently reuse an ACC target profile.

### 5.23 Race Control

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Main flag | Graphics `flag` | ACC enum | `SessionFlags` bitfield translated to known shared display values |
| Global flags | Graphics global booleans | ACC global flag fields | Partial known SessionFlags bits |
| Track status | Graphics `track_status` | ACC session/track status | Derived from OnPitRoad / IsOnTrack / IsInGarage; vehicle state, not full track condition |
| Sector yellow | `global_yellow_1/2/3` | ACC sector/global yellow fields | Only global yellow mapped; sectors 2/3 null |
| Global green/checkered/red | Graphics booleans | ACC global flag fields | Known SessionFlags bits |
| Race-control message | Hard-coded explanatory text in UI | No text field in current ACC snapshot | No text field in current iRacing mapping |

**Status:** Partial for iRacing. Known flags are mapped; per-sector yellow and race-control text are unavailable. Unknown bit patterns must not be translated to a guessed flag.

### 5.24 Car Lights & Status

| Item | Frontend binding | ACC | iRacing |
|---|---|---|---|
| Pit limiter | Physics `pit_limiter_on` | Mapped | `dcPitSpeedLimiterToggle` |
| Engine running | Physics `engine_running` | Mapped | Derived from RPM > 0 |
| Ignition / starter / AI control | Physics boolean fields | ACC fields | Null / not mapped |
| Water temperature | Physics `water_temp_c` | Mapped | `WaterTemp` |
| Rain/flashing lights, light stage, wiper, indicators | Graphics fields | ACC Graphics fields | No general equivalents currently mapped |
| Exhaust temperature | Graphics `exhaust_temp_c` | ACC field | No general equivalent mapped |
| Rain tyres | Graphics `rain_tyres` | ACC field | Do not infer from compound text alone |

**Status:** Partial for iRacing. Pit limiter, derived engine-running state and water temperature are mapped. Most lighting controls are unavailable. The reader currently uses boolean defaults for some optional controls; a missing SDK variable must not be presented as a confirmed OFF state.

## 6. Cross-cutting implementation findings

### 6.1 Shared formatting is not unit-neutral

`frontend/src/timeDisplay.mjs` documents that its session helper is for ACC milliseconds and divides by 1000. The iRacing reader publishes `session_time_left_s` from `SessionTimeRemain` in seconds. This is a concrete iRacing bug. Canonical timing should be milliseconds or a value+unit schema, with one conversion at the UI boundary.

The penalty formatter also divides by 1000. That is appropriate only for the ACC millisecond-valued source currently expected by the shared UI. iRacing penalty time is null, so do not populate it with an unrelated incident count.

### 6.2 Shared frontend contains game/car-specific telemetry logic

The Porsche 992 brake-bias correction is applied in `App.tsx` based on car model only. The active game is not checked. This violates the adapter boundary and can corrupt an iRacing value. No further correction should be made in the frontend; first move the existing ACC-specific interpretation behind the ACC adapter and define a separate iRacing field/scale.

### 6.3 Availability and null semantics

The UI displays `—` for many null numeric values, but optional iRacing booleans read with `bool(_read(..., False))` can collapse a missing SDK variable into `False`. A missing channel must remain unavailable, not become OFF.

The current tile dependency map uses Physics/Graphics/Static stream freshness. The iRacing reader currently marks all three stream entries fresh together from the same SDK snapshot. This is a reader-level freshness model, not evidence of three independent iRacing acquisition streams. The UI should treat the values as one SDK snapshot with per-field availability.

### 6.4 Lap history and dynamic sectors are separate contracts

The iRacing reader has a dynamic sector-boundary implementation, but the frontend lap-history capture and table remain three-sector-specific. A dynamic current-sector display does not imply dynamic historical sector retention. A future shared lap record should contain a list of sector durations and validity status rather than fixed `s1Ms/s2Ms/s3Ms` properties.

### 6.5 Hardware remains a separate subsystem

The Hardware Connections tile is currently placeholder content. It must eventually consume actual device/bridge state from SimLink hardware integration. Neither ACC nor iRacing telemetry is a valid source for wheel/pedal/handbrake/RPM-LED USB status.

## 7. Prioritized remediation plan

No code changes are included in this audit. Recommended implementation order:

| Priority | Area | Required work | Reason |
|---|---|---|---|
| P0 | Canonical timing | Normalize session remaining time to one explicit unit; remove ACC-only divide-by-1000 assumption from shared helper | Confirmed iRacing display bug and ACC producer/consumer mismatch |
| P0 | Brake bias | Remove game/car correction from shared frontend; define adapter-owned scale and ACC-only profile behaviour | Prevents ACC correction leaking into iRacing |
| P1 | Tyre pressure semantics | Separate cold setup pressure from live hot pressure; correct labels and target comparison | Current iRacing data is cold pressure |
| P1 | MFD fuel-to-add | Carry quantity unit (L/kWh/unknown) and display correct unit | Current UI hardcodes L |
| P1 | Lap history | Replace fixed S1/S2/S3 record with dynamic sector array; preserve validity as valid/invalid/unknown | Required for tracks with variable sector count |
| P1 | Lap validity | Investigate an iRacing-supported legality source; until found, retain unknown | Avoid false valid/invalid claims |
| P1 | Tyre temperature | Rename or qualify iRacing three-zone average; preserve individual zones if useful | Prevents false core-temperature semantics |
| P2 | Hardware tile | Connect to hardware bridge/device state | Current tile is hard-coded placeholder |
| P2 | Track map | Identify a trustworthy iRacing world-coordinate/track-geometry source | Lap percentage is not a world coordinate |
| P2 | Warnings | Add iRacing incident counts as their own semantic fields, not ACC penalty enums | Useful mapped data is currently not displayed |
| P2 | Brake tile | Label brake line pressure unit; keep unavailable brake temperature/pad/disc life neutral | Avoids unlabeled pressure and fabricated channels |
| P2 | Race control | Add per-sector yellow only if source evidence exists; expose unknown state clearly | Current iRacing mapping has only global yellow |
| P3 | Additional useful fields | Consider tyre wear, ABS active, handbrake, engine warnings, repair time, push-to-pass and class position in appropriate tiles | Fields already emitted but not displayed |

## 8. Tile-level implementation acceptance rules

For each future tile change:

1. Identify the exact frontend binding and the canonical field.
2. Trace the game-native SDK/shared-memory source.
3. Record source unit, canonical unit, conversion formula and whether the value is direct or derived.
4. Record availability for ACC and iRacing separately.
5. Keep missing, stale, invalid, unsupported and not-applicable distinct.
6. Never map a nearby but semantically different channel (for example, cold pressure as hot pressure, wetness as rain intensity, shock deflection as damage, manifold pressure as turbo boost, or delta validity as lap validity).
7. Add focused adapter tests and frontend contract tests.
8. Verify one tile at a time in the target simulator before moving to the next.
9. Do not change ACC's established behaviour while implementing iRacing support.
10. Record actual test results and unresolved items; do not mark a field live-validated based only on a fake SDK test.

## 9. Recommended first implementation tile

Start with **Lap Times**, but keep its scope limited:

- Keep iRacing current, last and best lap timing as currently sourced.
- Correct the shared time-unit contract before using session time or any other time fields.
- Preserve lap validity as unknown until a supported iRacing legality source is identified.
- Do not infer validity from `LapDeltaToBestLap_OK`.
- Keep ACC's existing validity/out-lap behaviour unchanged.
- Add tests for milliseconds/seconds conversion and null validity.

Lap History and dynamic sector persistence should follow as a separate tile-sized change, not be bundled into the first Lap Times implementation.

## 10. Source revision references

| Source | Revision / SHA at audit |
|---|---|
| Repository branch head | `9f0f521d17ba0d7c02f7062f8224fc2ad60fa5c4` |
| `frontend/src/App.tsx` | `48b28bb241825daadb6594e2e14172e1b78ebfcb` |
| `frontend/src/timeDisplay.mjs` | `888bf48d55784d0aa577dfa8906451d90d92bc1a` |
| `frontend/src/tileAvailability.mjs` | `a6186be3b6a81c26550f7359ee878485e2ac2b68` |
| `src/desktop/qt_host.py` | `b9f25b6b46aa3d153ca5101f61fdfa73e9da61bb` |
| `src/desktop/bridge.py` | `d11634e85857bcdddbc3be79e543e8bad96531ba` |
| `src/desktop/iracing_host.py` | `1ac82369a5799698a2ff0a87fff17237f294c2cb` |
| `src/desktop/switchable_host.py` | `6776a3964b8918b3c973f0f9f6eb3aceeb767592` |
| `src/iracing/reader.py` | `8751647ac54b4de1d4ff1fb5d442ab4e60c09e4f` |
| ACC field mapping baseline | `docs/ACC_Telemetry_Overview_Field_Mapping_and_Findings.md` |
| Prior iRacing mapping | `docs/IRACING_OVERVIEW_FIELD_MAPPING.md` |
| Unified normalization spec | `docs/UNIFIED_TELEMETRY_NORMALIZATION_AND_GAME_CONVERSION_SPEC.md` |

---

**Maintenance rule:** Update this audit when a tile's source binding, canonical meaning, unit, adapter availability or validation status changes. Keep source mapping, derived logic, UI formatting and hardware state as separate responsibilities.
