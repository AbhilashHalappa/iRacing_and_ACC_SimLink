# ACC Telemetry → Overview Tile Field Mapping and Findings

**Repository:** `AbhilashHalappa/iRacing_and_ACC_SimLink`  
**Branch reviewed:** `feature/iracing-game-support`  
**Scope:** ACC telemetry acquisition, decoding, snapshot publication, and React Overview tile consumption  
**Document purpose:** Record the source-to-UI mapping, unit handling, known mismatches, confidence limits, and recommended validation work. This is a code-review document, not a claim that every ACC channel has been runtime-validated.

---

## 1. Executive summary

The ACC path is split across three shared-memory streams and a desktop publication layer:

- **Physics** supplies high-rate vehicle and tyre measurements.
- **Graphics** supplies session, timing, track-position, and race-control-style state.
- **Static** supplies relatively stable car/session metadata.
- The Qt host assembles/publishes telemetry snapshots for the React Overview.
- The frontend formats values and derives some presentation-level information.

The reviewed acquisition/decoder code indicates nominal polling rates of approximately **480 Hz Physics**, **100 Hz Graphics**, and **1 Hz Static**. The Qt snapshot publication path is approximately **50 ms (20 Hz)**. These are implementation settings/observations from the reviewed source, not a guarantee that every field updates at those rates.

The central engineering risk is that the Overview currently mixes raw simulator values, converted values, host-derived values, and UI-derived values without consistently exposing their units or provenance. The most important confirmed code-level concerns are the fuel mass/litre mismatch, session-time property mismatch, and static metadata not appearing in the published snapshot shape expected by the frontend.

**Do not replace unavailable channels with zero or guessed values.** Keep the tile present and display an unavailable state until a valid source or explicitly documented derivation exists.

## 2. Reviewed source paths

The review covered these files on `feature/iracing-game-support`:

- `src/race_engineer_acquisition/acc_windows.py`
- `src/race_engineer_acquisition/physics_decoder.py`
- `src/race_engineer_acquisition/graphics_decoder.py`
- `src/race_engineer_acquisition/static_decoder.py`
- `src/desktop/qt_host.py`
- `src/desktop/bridge.py`
- `frontend/src/App.tsx`
- `frontend/src/TrackMapTile.tsx`
- `frontend/src/timeDisplay.mjs`

The decoder source includes candidate layout comments for some ACC Graphics/Static structures. Those comments are useful implementation evidence, but they do not by themselves certify the layout against an authoritative Kunos ABI specification.

## 3. Data flow and update cadence

| Layer | Responsibility | Observed implementation detail |
|---|---|---|
| ACC Physics shared memory | Vehicle dynamics, controls, tyres, fuel and related physics values | Polling configured around 480 Hz |
| ACC Graphics shared memory | Timing, session state, track position, flags and related graphics values | Polling configured around 100 Hz |
| ACC Static shared memory | Stable car/session metadata | Polling configured around 1 Hz |
| Decoder layer | Reads raw shared-memory structures and maps them into Python dictionaries | Separate Physics, Graphics and Static decoders |
| Qt host | Combines acquisition state and prepares application snapshots | Snapshot publication around every 50 ms |
| Desktop bridge | Makes snapshots available to the frontend | HTTP snapshot / SSE update path |
| React Overview | Renders tiles and formats/derives display values | UI-side formatting and some derived values |

The UI publication cadence is lower than the Physics polling cadence. This is expected for a dashboard, but the application should preserve timestamps/source freshness so that stale values are not mistaken for current measurements.

## 4. One-to-one mapping by Overview area

The table below records the source family and the mapping behaviour identified in the reviewed code. Exact raw struct member names should be confirmed against the corresponding decoder implementation and the installed ACC shared-memory version before treating this as a protocol specification.

### 4.1 Vehicle state and driver inputs

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Speed | Physics vehicle speed field | Decoder value is used by the Overview speed presentation | Source value + UI formatting | Confirm the decoder's source unit and keep a canonical internal unit (recommended: m/s); convert only at the display boundary |
| Gear | Physics gear field | Mapped to displayed gear state | Source value + formatting | Preserve reverse/neutral/forward semantics; do not assume all games encode gears identically |
| Engine RPM | Physics engine RPM | Displayed as RPM | Direct measurement | No unit conversion expected |
| Throttle | Physics throttle input | Normalized input displayed as percentage | Normalized 0–1 → percent | UI percentage is derived by multiplying normalized input by 100 |
| Brake | Physics brake input | Normalized input displayed as percentage | Normalized 0–1 → percent | Same normalization rule as throttle |
| Clutch | Physics clutch input | Normalized input displayed as percentage | Normalized 0–1 → percent | Same normalization rule as throttle |
| Steering | Physics steering input/angle | Displayed as steering value/angle | Source value + formatting | Confirm whether the source is normalized steering input or physical wheel angle; do not label a normalized value as degrees |
| Slip angle | Physics slip-angle channel | Frontend adds a degree symbol to the value | Unverified unit presentation | Verify whether decoder output is already degrees or radians. If radians, convert with degrees = radians × 180 / π before displaying ° |
| Brake bias | Physics brake-bias channel | Frontend multiplies by 100; Porsche 992 path subtracts 21 percentage points | Converted / car-specific correction | The Porsche correction is present in the reviewed UI path; its rationale and applicability need validation before being treated as universally correct |

### 4.2 Lap timing and lap history

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Current lap time | Graphics timing fields | Converted/formatted for display | Source timing + formatting | Keep internal timing in milliseconds; format only in the UI |
| Last lap time | Graphics completed-lap timing | Converted/formatted for display | Source timing + formatting | Validate reset/transition behaviour at session and lap boundaries |
| Best lap time | Locally tracked completed lap data / available timing state | Select minimum eligible lap time | Derived application state | Distinguish session best from personal/session history; define validity rules |
| Lap count | Graphics/session timing state and host tracking | Published as current lap count | Source/host state | Validate pit entry, out-lap and session-transition cases |
| Lap validity | ACC graphics/host-observed state | Mapped to valid/invalid state where available | Source + host classification | Do not infer validity solely from a lap time existing |
| Out-lap indicator | Host-side ACC out-lap observer | Injected observer state drives the current-lap visual treatment | Host-derived state | Not a raw ACC shared-memory field. The out-lap tile treatment is an application classification |
| Lap History | Application's locally accumulated lap records | UI displays locally retained lap records | Application-derived | It is not a direct ACC historical-laps feed. The reviewed implementation assumes three sectors; avoid applying that assumption to games with dynamic sector counts |

**Important:** A lap-time display should not silently treat an out-lap or incomplete lap as a timed valid lap. Preserve a distinct validity/status value such as `valid`, `invalid`, or `unknown`.

### 4.3 Sector performance

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Sector count | ACC track/session layout or application sector model | Current implementation presents a three-sector model in the lap-history path | Application model | Verify track-specific sector boundaries; do not assume every simulator or track uses exactly three sectors |
| Sector times | Graphics timing / locally observed timing boundaries | Time differences formatted for display | Derived timing | Validate exact boundary semantics and handling when attaching mid-sector |
| Sector bests / comparison | Locally accumulated lap/sector records | Compare eligible recorded sectors | Derived application state | Only compare sectors with compatible track/layout and valid source timing |

### 4.4 Weather and track conditions

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Air temperature | Graphics weather/session field | Displayed as °C | Direct or decoder-mapped measurement | Confirm source unit is Celsius |
| Track temperature | Graphics weather/session field | Displayed as °C | Direct or decoder-mapped measurement | Confirm source unit is Celsius |
| Wind speed | Graphics weather field | Frontend labels the value km/h | Unverified unit presentation | Verify the decoder's source unit. If m/s, convert to km/h by multiplying by 3.6 |
| Wind direction | Graphics weather field | Displayed as a direction/angle | Source value + formatting | Confirm whether source is radians, degrees, or an encoded direction |
| Rain / weather state | Graphics weather/session state | Enum or scalar mapped to UI | Enum/value mapping | Verify enum values and whether the value is intensity, forecast, or current state |
| Track grip | Graphics/session state | Enum mapped to a textual state | Enum mapping | Verify all enum values and unknown-value fallback |

### 4.5 Fuel and stint

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Fuel remaining | Physics fuel quantity (`fuel_kg` in the reviewed decoder path) | Frontend consumes it as `fuelLitres` and labels it L | **Confirmed unit mismatch** | Kilograms are not litres. Expose kg explicitly or use a verified litre-valued source. Do not assume 1 kg = 1 L |
| Fuel capacity / maximum fuel | Static decoder reads `max_fuel` | Frontend expects `telemetry.static_metadata.data.max_fuel` | **Confirmed publication-shape mismatch** | The reviewed Qt host snapshot does not publish the expected `static_metadata.data` structure, so the tile cannot reliably obtain capacity from this path |
| Fuel used per lap | Difference between observed fuel values across completed laps | Calculated from fuel samples | Derived | Needs stable lap boundaries and non-negative/credible delta handling |
| Estimated laps remaining | Fuel remaining divided by observed fuel-per-lap | Calculated estimate | Derived | Only show when sufficient valid consumption samples exist; show unavailable before that |
| Driver stint total | Graphics/session driver stint field | Frontend label describes time remaining | **Semantics need verification** | Confirm whether source is elapsed stint duration, total stint allowance, or remaining time before presenting it as “time left” |
| Pit / stint state | Graphics/session state | Enum/state mapping | Source/enum mapping | Validate pit entry/exit and driver swap transitions |

### 4.6 Tyres and brakes

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Tyre core temperature | Physics decoder `tyre_core_temp_c` | Displayed as °C | Direct measurement | The frontend uses this field for the tyre temperature tile |
| Alternate tyre temperature | Physics decoder also exposes `tyre_temp_c` | Not the selected field in the reviewed tile path | Direct measurement, field selection unresolved | Document why core temperature is preferred and confirm the exact meaning of both channels |
| Tyre pressure | Physics tyre pressure field, where exposed | UI formatting to PSI/bar as applicable | Direct measurement + unit conversion | Confirm raw unit before conversion; canonical internal unit recommended: Pa |
| Brake temperature | Physics brake-temperature channel | Displayed as °C | Direct measurement | Confirm each wheel index maps to the intended corner and source unit is Celsius |
| Tyre wear / condition | Physics tyre condition fields where available | UI mapping | Source value / derived condition | Preserve raw values and document any thresholds used for colour/state |
| Tyre set | Static/Graphics tyre-set metadata where available | Enum/index mapping | Enum mapping | Verify index semantics and session changes |

### 4.7 Track map and position

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| World position | Physics/Graphics position channels used by the host | Samples are accumulated into a track outline | Source coordinates | Verify coordinate axes, scale and orientation for each car/track context |
| Track progress | Position/lap progression state | Normalized progress used for UI placement | Derived | Keep normalized progress in 0–1 and avoid mixing it with distance units |
| Track map geometry | Locally learned world-coordinate samples | Cached locally; reviewed implementation requires at least 80 points | Application-derived / cached | Map is learned from telemetry, not a preloaded authoritative track map |
| Corner markers | Derived from learned map / track-position information | UI annotations | Derived | Validate marker placement against real track landmarks |
| Map persistence | Local application storage | Reuses cached map samples | Application storage | Treat cache as game/track/layout-specific; do not overwrite a good map with sparse or invalid samples |

### 4.8 Session, race control and car state

| Overview field / tile value | ACC source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Session type / phase | Graphics session fields | Enum mapped to UI text | Enum mapping | Verify all supported session values and unknown fallback |
| Session time remaining | Graphics decoder publishes `session_time_left_ms`; frontend reads `session_time_left_s` and the helper divides by 1000 | **Confirmed producer/consumer property mismatch** | Unit/property mismatch | Align the contract on an explicit `session_time_left_ms` value and convert to seconds exactly once |
| Position | Graphics position field | Displayed as ordinal position | Direct/enum-like value | Verify grid/race session behaviour |
| Gap / interval | Graphics timing fields, if populated | Formatted for display | Source timing + formatting | Do not show fabricated values when no reference car or timing is available |
| Flags / penalties | Graphics race-control fields | Enum mapped to text/colour | Enum mapping | Verify flag and penalty enum values; unknown values must remain unknown |
| Warnings | Graphics/session state | UI warning mapping | Enum/state mapping | Confirm warning lifetime and reset semantics |
| Lights / car status | Graphics/static state where decoded | Enum/bit mapping | Enum/bit mapping | Validate bit positions and state names against runtime evidence |
| Damage | ACC source channel if decoded | UI mapping | Source value if present | Do not infer damage from unrelated telemetry; keep unavailable if not supplied |
| Electronics (ABS / TC / map) | Physics/static channels as decoded | Direct value or enum mapping | Source/enum mapping | Validate whether each value is current setting, active intervention, or configured map |
| Race-control state | Graphics/session fields | Enum mapping | Source/enum mapping | Confirm all enum/index meanings before assigning user-facing labels |

### 4.9 Hardware tile

| Overview field / tile value | Source | Mapping / conversion | Classification | Review notes |
|---|---|---|---|---|
| Pedal / controller connection | Existing hardware subsystem and bridge state | Hardware status is rendered in the Overview | Hardware-derived | This is not an ACC telemetry channel |
| RPM LED connection | Existing hardware subsystem | Connection/status display | Hardware-derived | Keep separate from simulator adapter telemetry |
| Hardware sensor values | Hardware subsystem, where applicable | Hardware-specific mapping | Hardware-derived | Do not overwrite hardware readings with simulator values |

## 5. Confirmed code-level mismatches

These are the highest-priority findings from the reviewed source paths.

### 5.1 Fuel mass is consumed as litres

- Decoder/source path exposes fuel as `fuel_kg`.
- Frontend consumes the value through a `fuelLitres`-style property and labels it in litres.
- Kilograms and litres are different physical quantities. Fuel density varies by fuel and temperature; a fixed 1:1 conversion is not valid.

**Recommended correction:** Keep the source value named and typed as kilograms (for example, `fuel_remaining_kg`) unless a verified ACC litre field is available. If the UI wants litres, convert using a documented, justified density or a simulator-provided litre value. Do not silently relabel kg as L.

### 5.2 Session remaining-time property mismatch

- Graphics decoder publishes `session_time_left_ms`.
- Frontend reads `session_time_left_s`.
- The reviewed formatting helper divides the supplied value by 1000.

**Recommended correction:** Define one canonical producer/consumer field, preferably `session_time_left_ms`, and convert milliseconds to seconds only in the presentation layer. Add a contract test to prevent future property-name drift.

### 5.3 Static metadata is not present in the expected snapshot shape

- Static decoder reads `max_fuel`.
- Frontend expects `telemetry.static_metadata.data.max_fuel`.
- The reviewed Qt host snapshot does not publish that expected nested structure.

**Recommended correction:** Either publish the static metadata object through the bridge with an explicit schema, or update the consumer to the actual published shape. Add an integration-level snapshot test; decoder-only tests will not catch a publication omission.

## 6. Items requiring verification (not confirmed defects)

| Item | Current code observation | Verification required |
|---|---|---|
| Porsche 992 brake-bias correction | UI multiplies raw brake bias by 100 and subtracts 21 percentage points for Porsche 992 | Confirm raw scale, why the offset is required, and whether it applies to every relevant Porsche 992 configuration |
| Slip-angle unit | UI adds a degree symbol | Confirm decoder/source unit; convert radians to degrees if needed |
| Wind-speed unit | UI labels the value km/h | Confirm source unit; convert m/s to km/h if applicable |
| Driver stint time semantics | UI wording indicates time remaining | Confirm whether source means elapsed, allowed, or remaining stint duration |
| Tyre temperature channel choice | Decoder exposes both `tyre_core_temp_c` and `tyre_temp_c`; tile uses core temperature | Confirm definitions and intended tile metric |
| Graphics/Static shared-memory layouts | Decoder comments describe candidate layouts | Validate against authoritative Kunos documentation and observed runtime data |
| Enum/index mappings | Session, status, grip, rain, penalties, flags, lights, gear, engine map and tyre set use mapped values | Verify all values, unknown values, and version compatibility |

Do not convert these verification items into “confirmed” facts until source documentation or controlled runtime evidence supports them.

## 7. Derived values and provenance

The Overview should distinguish at least these categories:

1. **Raw/source measurement** — read from ACC shared memory.
2. **Decoder-normalized measurement** — same physical quantity, with a known unit/representation conversion.
3. **Host-derived state** — for example, out-lap classification observed by the application.
4. **Application-derived value** — for example, fuel per lap, estimated laps remaining, or a learned track map.
5. **UI presentation** — formatting, rounding, labels, colour thresholds and display-unit conversion.

A tile should not present a derived value as though ACC directly supplied it. Where practical, the telemetry contract should retain source name, unit, timestamp/freshness and derivation status.

## 8. Recommended canonical cross-simulator telemetry contract

The shared Overview should consume a game-independent contract. Each simulator adapter owns its raw field mapping and conversion. The UI should not contain simulator-specific corrections.

| Canonical field | Recommended internal representation | UI conversion |
|---|---|---|
| Speed | m/s | km/h = m/s × 3.6; mph = m/s × 2.236936 |
| Gear | Normalized reverse / neutral / forward gear state | Game-appropriate gear label |
| Engine speed | RPM | Display RPM |
| Throttle / brake / clutch | Normalized 0–1 | Percent = value × 100 |
| Steering angle | Radians, if it is a physical angle | Degrees = radians × 180 / π |
| Fuel remaining | Explicit quantity plus unit (kg or L) | Display the matching unit; never relabel |
| Tyre pressure | Pa | PSI = Pa ÷ 6894.757; bar = Pa ÷ 100000 |
| Temperatures | °C | Display °C or convert explicitly |
| Lap and sector times | Milliseconds | Format as time string |
| Lap validity | `valid` / `invalid` / `unknown` | UI state |
| Sector data | Dynamic count and per-sector timing | Render the number of sectors supplied |
| Session remaining | Milliseconds | Seconds = ms ÷ 1000 |
| Track progress | Normalized 0–1 | Position marker / percentage |
| Wind speed | m/s | km/h = m/s × 3.6 |
| Wind direction | Radians, if source is angular | Convert explicitly for display |
| Availability | Explicit available / unavailable / stale state | Blank or “—” with suitable explanation |
| Provenance | Raw / normalized / derived / UI-derived | Optional diagnostic detail |

The contract should allow a field to be unavailable without substituting zero. It should also carry enough source freshness information to prevent stale telemetry from looking live.

## 9. Recommended validation order

1. **Fix the contract mismatches first:** fuel unit/name, session-time property, and Static metadata publication.
2. **Add decoder-to-snapshot tests:** verify each decoded value survives host aggregation and bridge serialization under the expected property name.
3. **Add unit tests:** explicit tests for ms↔s, m/s↔km/h, radians↔degrees, Pa↔PSI/bar, and normalized input↔percent.
4. **Validate enum mappings:** include unknown/unrecognized values and ensure they do not crash or become misleading labels.
5. **Validate timing transitions:** session start/end, lap transition, invalid lap, out-lap, pit entry/exit and reconnect.
6. **Validate track map:** sample threshold, track identity, cache reuse and sparse/invalid samples.
7. **Run controlled ACC sessions:** compare dashboard values against ACC HUD/telemetry tools at idle, on track, in pits and across session transitions.

## 10. Review conclusion

The ACC adapter provides a useful basis for the shared Overview, but the source-to-UI contract needs tightening before it should be treated as a reference implementation for other simulators. In particular:

- Make units explicit end-to-end.
- Keep raw source values distinct from normalized and derived values.
- Correct the three confirmed data-contract mismatches.
- Verify candidate shared-memory layouts and enum mappings against authoritative/runtime evidence.
- Keep unavailable channels unavailable rather than inventing values.
- Keep game-specific mapping and conversion logic inside the ACC adapter, not in shared React tile components.

This document records findings from source inspection. It does **not** state that the recommended corrections have been implemented or that all channels have passed live ACC validation.
