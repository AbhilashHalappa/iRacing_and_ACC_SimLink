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


---

# 11. Source-level cross-check addendum — full field trace

**This section expands and, where necessary, supersedes earlier summary statements in this document.** It was added after cross-checking the current branch's actual decoder, consumer, Qt host, React tile code, and the repository's Physics/Graphics/Static field-coverage audits and Overview design record. The earlier sections should be read together with the corrections in §15.

## 11.1 Actual acquisition → decoder → snapshot → UI path

The current branch uses independent ACC acquisition paths; decoding is deliberately downstream from the shared-memory copy:

1. `acc_windows.py` opens the read-only ACC Physics named mapping `Local\\acpmf_physics`, reads the packet ID before and after copying the complete 800-byte page, and returns a copied raw payload. It does not decode channels in the acquisition adapter.
2. The Physics acquisition loop publishes consistent copied observations into an application-owned ring. A downstream `PhysicsDecodeConsumer` drains that ring, decodes the latest good sample, and retains capture timestamps, sequence numbers and decode-health counters.
3. Graphics has a separate acquisition/ring/decoder/consumer path. The Graphics decoder consumes a 1,588-byte v1.8.12-derived candidate structure from a 4,096-byte mapping allocation. It deliberately preserves uncertain enum values and sentinels rather than guessing.
4. Static has its own acquisition and `StaticDecodeConsumer`; its selected Variant B candidate is 820 bytes. Static is not synchronized to Physics or Graphics by packet ID; its capture time is separate.
5. `ACCDesktopWindow._publish_snapshot()` runs on a 50 ms Qt timer. It publishes Physics and Graphics consumer payloads, stream freshness, acquisition diagnostics, and a limited `vehicle` identity object. It injects host-observed out-lap state into Graphics as `lap_status`.
6. `TelemetryBridge` publishes the assembled JSON snapshot over the local HTTP/SSE bridge. React consumes this snapshot; the frontend does not open ACC shared memory.

### Snapshot shape actually published by the Qt host

| Snapshot path | Content |
|---|---|
| `game` | `"acc"` |
| `connected` | Derived from Physics stream freshness |
| `streams.physics / graphics / static` | Freshness/lifecycle status |
| `physics` | Consumer payload: stream/health/capture timestamp and `data` containing decoded Physics fields, `gear_display`, `wheel_order`, and corner-keyed `wheels` |
| `graphics` | Consumer payload: stream/health/capture timestamp and `data` containing decoded Graphics fields; host adds sibling `lap_status` |
| `vehicle` | `car_model`, `track`, `track_configuration` taken from decoded Static identity |
| `acquisition`, `capture_pipeline` | Acquisition health, ring-buffer and decoder diagnostics |

**Important publication gap:** the Static consumer is decoded and used to populate `vehicle`, but the Qt host does not publish a `static` or `static_metadata` consumer payload. Consequently the frontend path `telemetry.static_metadata.data.max_fuel` is not satisfied, even though the Static decoder has a `max_fuel` field. This is more precise than saying Static metadata is not decoded: it is decoded, but the relevant object/field is not forwarded in the snapshot.

The Physics consumer's `data` is generated from the decoder dataclass and also adds `gear_display`, `wheel_order` and `wheels`. Graphics `data` is generated from its decoder dataclass. The bridge is a publisher, not a second decoder.

## 11.2 Physics field map — exact decoded source members

ACC Physics wheel arrays use **FL, FR, RL, RR** order. Offsets below are byte offsets in the current 800-byte candidate page; decoded fields end at byte 784. The 16-byte tail is retained in the raw page and intentionally opaque.

| Offset | Raw member | Decoded field | Overview consumer / meaning | Unit or transformation |
|---:|---|---|---|---|
| 0 | `packet_id` | `packet_id` | Diagnostics / sample consistency | int32 sequence-like value; not a vehicle measurement |
| 4 | `throttle` | `throttle` | Pedals tile / driver trace | Normalized 0–1; UI multiplies by 100 for % |
| 8 | `brake` | `brake` | Pedals tile / driver trace | Normalized 0–1; UI multiplies by 100 for % |
| 12 | `fuel_kg` | `fuel_kg` | Fuel tile | Kilograms; current UI incorrectly labels as litres |
| 16 | `gear_raw` | `gear_raw`, `gear_display` | Gear tile / driver trace | ACC raw encoding: 0=R, 1=N, n≥2 means gear n−1 |
| 20 | `rpm` | `rpm` | RPM tile / driver trace | Integer RPM |
| 24 | `steering` | `steering_angle` | Steering tile / driver trace | Raw float; Overview formats as degrees/left-right indicator. Confirm calibration/scale before cross-simulator reuse |
| 28 | `speed_kph` | `speed_kph` | Speed tile / driver trace | km/h already; do not multiply by 3.6 again |
| 32 | `velocity[3]` | `velocity` | Available decoded dynamics; not the main speed tile source | Vector; axes/sign not calibrated in the audit |
| 44 | `acc_g[3]` | `acc_g` | Dynamics-capable data; not a primary current Overview tile | G vector |
| 56 | `wheel_slip[4]` | `wheel_slip` | Available wheel dynamics | Raw float array; semantics/unit not fully validated |
| 72 | `wheel_load[4]` | `wheel_load` | Available in decoder | Reference implementation returns None/marks unused for ACC; stable zero in tested captures; do not present as a valid load reading |
| 88 | `tyre_pressure_psi[4]` | `tyre_pressure_psi` | Tyre tile and target-pressure comparison | PSI already; FL/FR/RL/RR |
| 104 | `wheel_angular_speed[4]` | `wheel_angular_speed` | Available decoded dynamics | Raw angular speed; no Overview conversion currently established |
| 152 | `tyre_core_temp_c[4]` | `tyre_core_temp_c` | Tyres tile | °C; this is the temperature channel actually selected by the UI |
| 184 | `suspension_travel[4]` | `suspension_travel` | Available decoded suspension data | Raw float; not the same as suspension damage |
| 204 | `tc` | `tc_level` | Physics-side TC candidate only | Float; do not confuse with Graphics TC setup level |
| 208 / 212 / 216 | `heading`, `pitch`, `roll` | Same names | Vehicle attitude-capable data | Angular values; units/axes require validation before presentation |
| 224 | `car_damage[5]` | `car_damage` | Vehicle Damage tile: Front, Rear, Left, Right, Centre in array order | Raw values; UI intentionally does not append % because scale is unverified |
| 248 | `pit_limiter_on` | `pit_limiter_on` | Car Lights & Status tile | int32 interpreted as nonzero boolean |
| 252 | `abs` | `abs_level` | Physics-side ABS candidate | Float; not the preferred Graphics ABS setup-level source |
| 264 | `autoshifter_on` | `autoshifter_on` | Car Electronics tile | int32 interpreted as nonzero boolean |
| 276 | `turbo_boost` | `turbo_boost` | Car Electronics tile | Raw float; display unit/scale not established in the reviewed UI |
| 288 / 292 | `air_temp_c`, `road_temp_c` | Same names | Weather tile | °C |
| 296 | `local_angular_velocity[3]` | `local_angular_velocity` | Available dynamics | Vector; axes/sign need calibration |
| 348 | `brake_temp_c[4]` | `brake_temp_c` | Brakes tile | °C; FL/FR/RL/RR |
| 364 | `clutch` | `clutch` | Pedals tile | Normalized 0–1; UI multiplies by 100 for % |
| 416 | `is_ai_controlled` | `is_ai_controlled` | Car Lights & Status tile | int32 interpreted as nonzero boolean |
| 564 | `brake_bias` | `brake_bias` | Car Electronics tile | UI applies ×100 and a Porsche-992-specific −21 percentage-point correction; see unresolved issue below |
| 568 | `local_velocity[3]` | `local_velocity` | Available dynamics | Vector; axes/sign need calibration |
| 588 | `current_max_rpm` | `current_max_rpm` | RPM LED threshold | Integer RPM; frontend uses this as reported maximum RPM |
| 640 | `slip_ratio[4]` | `slip_ratio` | Tyres tile | Raw ratio; UI displays to two decimals |
| 656 | `slip_angle[4]` | `slip_angle` | Tyres tile | UI appends ° without a conversion; source unit still requires confirmation |
| 672 / 676 | `tc_in_action`, `abs_in_action` | Same names | Not currently a trusted setup-level display | Intervention indicators; stable zero in sampled capture; do not substitute them for TC/ABS setup values |
| 680 | `suspension_damage[4]` | `suspension_damage` | Vehicle Damage tile, per corner | UI multiplies raw value by 100 and labels %; scale still needs authoritative validation |
| 696 | `tyre_temp_unused[4]` | `tyre_temp_c` | Not selected by tyre tile | In the 224,956-snapshot audit capture, bytes 696–711 were byte-for-byte identical to bytes 152–167. Treat as an alias/duplicate in that evidence, not a second independent temperature channel |
| 712 | `water_temp_c` | `water_temp_c` | Car Lights & Status tile | °C; should appear only once in Overview |
| 716 | `brake_pressure[4]` | `brake_pressure` | Brakes tile | Raw values; user confirmed display is passed, but unit/scale is not established here |
| 732 / 736 | `front_brake_compound`, `rear_brake_compound` | Same names | Not currently a fully decoded user-facing compound label | Raw integer enum; mapping unverified |
| 740 / 756 | `pad_life[4]`, `disc_life[4]` | Same names | Brakes tile secondary readouts | Raw float values; units, direction and exact corner semantics need validation |
| 772 / 776 / 780 | `ignition_on`, `starter_engine_on`, `engine_running` | Same names | Car Lights & Status tile | int32 interpreted as nonzero booleans |
| 784–799 | `tail_reserved[16]` | Not decoded | None | Preserve raw; do not interpret as production telemetry |

### Physics layout and confidence

- The current raw Physics page is 800 bytes, little-endian, pack=4. Three independent reader implementations include the `mz[4]` member after `current_max_rpm`; the live read-only mapping probe confirmed access through byte 799.
- The decoder intentionally requires at least 784 bytes and stops before the opaque 16-byte tail. The raw acquirer still copies all 800 bytes.
- `tests/acquisition/test_physics_layout.py` locks the current field names, types, array sizes, offsets, and total page size. This prevents accidental transcription drift; it is not itself official Kunos ABI certification.
- The 10 November 2026 target-PC Physics capture lasted 600 seconds and passed the documented acquisition, persistence, recovery and reconciliation checks. Field semantics are tracked separately: “validated” in the audit means a plausible signal correlated with a controlled action/state, not that every unit is calibrated.
- Fields explicitly marked unused/deprecated in the reference transcription (for example tyre wear, camber, DRS, ride height, ballast, air density, several ERS/KERS/DRS fields, tyre inner/middle/outer temperature arrays and other legacy members) are not valid substitute channels. They remain raw-layout members, not available telemetry promises.

## 11.3 Graphics field map — exact candidate offsets and tile use

The decoder uses a **1,588-byte, 87-member, v1.8.12-derived candidate** within a 4,096-byte mapping allocation. It has been cross-checked against independent implementations and prior application use, but is **not officially certified as the Kunos Shared Memory 1.9 ABI**. The table lists the candidate byte offsets used by the decoder.

| Offset | Raw candidate member | Decoded field | Overview use / notes |
|---:|---|---|---|
| 0x000 | `packet_id` | `packet_id` | Decoder/acquisition consistency diagnostics |
| 0x004 | `status` | `status` | Session tile; raw status enum, UI maps known states |
| 0x008 | `session` | `session` | Session tile; raw session enum |
| 0x00C | `current_time[15]` | `current_time_str` | Session/current timing display |
| 0x02A | `last_time[15]` | `last_time_str` | Last-lap timing string |
| 0x048 | `best_time[15]` | `best_time_str` | Best-lap timing string |
| 0x066 | `split[15]` | `split_time_str` | Split display; do not equate blindly with a completed sector duration |
| 0x084 | `completed_laps` | `completed_laps` | Lap tile, Lap History transition, track-map lap capture |
| 0x088 | `position` | `position` | Position tile and session information |
| 0x08C / 0x090 / 0x094 | `i_current_time`, `i_last_time`, `i_best_time` | `current_time_ms`, `last_time_ms`, `best_time_ms` | Numeric millisecond timing fields |
| 0x098 | `session_time_left` | `session_time_left_ms` | Session remaining time; frontend currently reads a different property name |
| 0x09C | `distance_traveled` | `distance_traveled_m` | Distance used by driver trace/lap-relative trace reset |
| 0x0A0 | `is_in_pit` | `is_in_pit` | Pit/stint tile; distinct from pit-lane state |
| 0x0A4 | `current_sector_index` | `sector` | Sector tile and local Lap History boundary observer; candidate values observed as 0/1/2 |
| 0x0A8 | `last_sector_time` | `last_sector_time_ms` | Cumulative elapsed time at the last sector boundary in the current app logic, not the duration of the just-finished sector |
| 0x0AC | `number_of_laps` | `number_of_laps` | Session/lap-limit context |
| 0x0B0 | `tyre_compound[33]` | `tyre_compound` | Session and pit/stint display |
| 0x0F8 | `normalized_car_position` | `normalized_car_position` | Track-map progress, normalized 0–1 |
| 0x0FC | `active_cars` | `active_cars` | Bounds the car coordinate and ID arrays |
| 0x100 | `car_coordinates[60][3]` | `car_coordinates`, `player_world_position` | World XYZ coordinates; player association is resolved by player ID when present |
| 0x3D0 | `car_id[60]` | `car_ids` | Player-coordinate association; single-car capture did not validate populated IDs |
| 0x4C0 | `player_car_id` | `player_car_id` | Used to locate player's coordinate triple |
| 0x4C4 | `penalty_time` | `penalty_time_s` | Warnings tile; helper divides by 1000 despite the `_s` suffix—unit/name must be reconciled |
| 0x4C8 / 0x4CC | `flag`, `penalty` | `flag`, `penalty` | Race Control and Warnings; raw enum values, not all labels verified |
| 0x4D0 | `ideal_line_on` | `ideal_line_on` | Candidate boolean; not a primary Overview tile value |
| 0x4D4 | `is_in_pit_lane` | `is_in_pit_lane` | Pit/stint tile; distinct from `is_in_pit` |
| 0x4D8 | `surface_grip` | `surface_grip` | Weather/track conditions; raw float |
| 0x4DC | `mandatory_pit_done` | `mandatory_pit_done` | Warnings and Pit/Stint tiles |
| 0x4E0 / 0x4E4 | `wind_speed`, `wind_direction` | Same names | Weather tile; UI labels wind speed km/h; source unit and direction convention remain unverified |
| 0x4E8 | `is_setup_menu_visible` | `setup_menu_visible` | Setup/session context |
| 0x4EC / 0x4F0 | `main_display_index`, `secondary_display_index` | Same names | MFD context; enum meanings not decoded to labels |
| 0x4F4 / 0x4F8 / 0x4FC / 0x500 | `tc`, `tc_cut`, `engine_map`, `abs` | `tc_level`, `tc_cut`, `engine_map`, `abs_level` | Car Electronics; raw setup levels, no correction; user confirmed TC and ABS displayed levels in ACC |
| 0x504 | `fuel_x_lap` | `fuel_per_lap_l` | Fuel tile; Graphics-supplied litres per lap, not a local Physics-derived calculation |
| 0x508 / 0x50C | `rain_lights`, `flashing_lights` | Same names | Car Lights & Status; candidate booleans |
| 0x510 | `lights_stage` | `lights_stage` | Car Lights & Status; raw stage value pending interpretation |
| 0x514 | `exhaust_temperature` | `exhaust_temp_c` | Car Lights & Status; candidate °C field, needs live unit confirmation |
| 0x518 | `wiper_level` | `wiper_level` | Car Lights & Status; raw level, not a boolean |
| 0x51C / 0x520 | `driver_stint_total_time_left`, `driver_stint_time_left` | `driver_stint_total_ms`, `driver_stint_left_ms` | Pit/Stint tile; UI labels both as time-left fields; validate units and exact semantics |
| 0x524 | `rain_tyres` | `rain_tyres` | Pit/Stint / tyre context; candidate boolean |
| 0x528 | `session_index` | `session_index` | Session identity and Lap History session key |
| 0x52C | `used_fuel` | `used_fuel_l` | Pit/Stint tile; displayed as litres; source semantics/units still require controlled confirmation |
| 0x530 | `delta_lap_time[15]` | `delta_lap_time_str` | Delta tile primary displayed delta string |
| 0x550 | `i_delta_lap_time` | `delta_lap_time_ms` | Numeric delta in milliseconds; retained as numeric source |
| 0x554 | `estimated_lap_time[15]` | `estimated_lap_time_str` | Delta tile estimated lap string |
| 0x574 | `i_estimated_lap_time` | `estimated_lap_time_ms` | Numeric estimate; observed unavailable sentinel includes 2147483647—must not format as a real time |
| 0x578 | `is_delta_positive` | `delta_positive` | Delta sign label/colour; candidate semantics not independently event-confirmed |
| 0x57C | `i_split` | `split_ms` | Split timing; distinct from `last_sector_time_ms` |
| 0x580 | `is_valid_lap` | `is_valid_lap` | Lap and Warnings tiles; live-correlated track-limit invalidation; preserve sticky invalidity through lap completion |
| 0x584 | `fuel_estimated_laps` | `fuel_estimated_laps` | Fuel tile; Graphics-supplied estimated laps remaining |
| 0x588 | `track_status[33]` | `track_status` | Race Control/session status text; string mapping needs runtime verification |
| 0x5CC | `missing_mandatory_pits` | Same name | Warnings and Pit/Stint; raw count/status until enum semantics verified |
| 0x5D0 | `clock` | `clock_s` | Session time-of-day context |
| 0x5D4 / 0x5D8 | `direction_lights_left`, `direction_lights_right` | `direction_left`, `direction_right` | Car Lights & Status; candidate boolean indicators |
| 0x5DC / 0x5E0 / 0x5E4 / 0x5E8 | `global_yellow`, `global_yellow_1/2/3` | Same names | Race Control; global and sector yellow states |
| 0x5EC / 0x5F0 / 0x5F4 / 0x5F8 | `global_white`, `global_green`, `global_chequered`, `global_red` | Same names | Race Control; flag booleans; global green is not lap validity |
| 0x5FC | `mfd_tyre_set` | `mfd_tyre_set` | Pit/Stint tile; MFD tyre-set request |
| 0x600 | `mfd_fuel_to_add` | Same name | Pit/Stint tile; MFD fuel-add request |
| 0x604 / 0x608 / 0x60C / 0x610 | `mfd_tyre_pressure_lf/rf/lr/rr` | `mfd_tyre_pressures[4]` | Pit/Stint tile; UI labels PSI, but raw unit/semantics need validation as requested MFD pressure |
| 0x614 | `track_grip_status` | Same name | Weather tile; raw enum, UI mapping must be verified |
| 0x618 / 0x61C / 0x620 | `rain_intensity`, `rain_intensity_10min`, `rain_intensity_30min` | `rain_intensity`, `rain_10min`, `rain_30min` | Weather tile; NOW/+10/+30 display; enum/intensity mapping needs verification |
| 0x624 / 0x628 | `current_tyre_set`, `strategy_tyre_set` | Same names | Pit/Stint tile; tyre-change inference compares MFD selected set with current set |
| 0x62C / 0x630 | `gap_ahead`, `gap_behind` | `gap_ahead_ms`, `gap_behind_ms` | Position tile; milliseconds formatted for display; verify sentinels and timing reference |

### Graphics field interpretation and evidence

- The full-lap recording on 9 November 2026 contained 18,000 samples over 180 seconds. Candidate offsets `0x004` (status), `0x084` (completed laps), `0x0A4` (sector), and `0x580` (lap validity) correlated with observed game events.
- `normalized_car_position` at `0x0F8` progressed through 0–1 and wrapped near the completed-lap boundary. The first three coordinate floats at `0x100` changed while the sole active car was moving; player-ID association still needs multi-car validation.
- The pit probe showed `is_in_pit=0` while `is_in_pit_lane=1`; these are distinct states and must not be collapsed.
- `is_valid_lap` transitioned 1→0 after the user-confirmed track-limit violation. Keep invalidity sticky for the lap rather than letting a later true sample erase the violation.
- Candidate bytes `0x634`–`0xFFF` were all zero in that capture. This supports, but does not prove, the 1,588-byte candidate logical-size boundary.
- The 60 car-ID slots were zero and unchanged in the single-car recording; this does not validate or disprove their multi-car semantics.
- The candidate `is_delta_positive` changed in the recording without a user-confirmed delta-sign event; retain as candidate/observation-only.
- Candidate `estimated_lap_time_ms` includes an apparent int32 unavailable sentinel. The UI must reject sentinel values rather than show a huge lap time.

## 11.4 Static field map and publication status

The current decoder selects **Variant B**, an 820-byte Static candidate with 33 UTF-16 code units for `TrackConfiguration`. Target-PC evidence favours this over the competing 784-byte Variant A because Variant B places coherent CarSkin and dry/wet tyre-name strings at the observed offsets. This is a leading candidate, not official Kunos ABI certification.

| Offset | Static candidate field | Decoded field | Current application use / disposition |
|---:|---|---|---|
| 0 | SMVersion UTF-16[15] | `sm_version` | Diagnostic/version context |
| 30 | ACVersion UTF-16[15] | `ac_version` | Diagnostic/version context |
| 64 | NumCars int32 | `num_cars` | Decoded metadata; not a primary Overview value |
| 68 | CarModel UTF-16[33] | `car_model` | Published under `vehicle.car_model` |
| 134 | Track UTF-16[33] | `track` | Published under `vehicle.track` |
| 200 / 266 / 332 | PlayerName / PlayerSurname / PlayerNick | Same names | Decoded but not currently published to Overview snapshot |
| 400 | SectorCount int32 | `sector_count` | Decoded metadata; UI lap-history logic currently assumes three sectors rather than consuming this field |
| 412 | MaxRPM int32 | `max_rpm` | Decoded; current RPM threshold uses Physics `current_max_rpm` |
| 416 | MaxFuel float32 | `max_fuel` | Decoded, but not forwarded as `static_metadata.data.max_fuel`; fuel-capacity tile therefore shows unavailable |
| 464 | PenaltiesEnabled int32 | `penalties_enabled` | Decoded session metadata |
| 468 / 472 / 476 | AidFuelRate / AidTireRate / AidMechanicalDamage | Same names | Decoded settings; not a live Overview measurement |
| 484 | AidStability | `aid_stability` | Decoded settings |
| 488 / 492 | AidAutoClutch / AidAutoBlip | `auto_clutch`, `auto_blip` | Decoded settings; distinguish from Physics auto-shifter |
| 524 | TrackConfiguration UTF-16[33] | `track_configuration` | Published under `vehicle.track_configuration`; used in track-map identity and session history key |
| 592 / 596 / 600 | ERSMaxJ / IsTimedRace / HasExtraLap | Same names | Candidate metadata; not assumed to be valid live telemetry |
| 604 | CarSkin UTF-16[33] | `car_skin` | Decoded, not currently published to Overview |
| 672 / 684 | ReversedGridPositions / IsOnline | Same names | Decoded candidate session metadata |
| 688 / 754 | DryTyresName / WetTyresName | Same names | Decoded candidate tyre metadata; not current live tyre temperature/pressure source |

Static layout notes:

- Common-prefix offsets through `TrackConfiguration` are shared between the competing candidates. Variant B tail offsets are favoured by the target-PC strings; the 4,096-byte mapping allocation does not itself establish logical structure size.
- `MaxTorque`, `MaxPower`, suspension travel and tyre radius metadata are described as unused/not shown in references and should remain raw-only unless demonstrated.
- `AidAllowTyreBlankets` has a type conflict in references; preserve raw until resolved.
- Pit-window values have unresolved units/semantics and should remain raw.
- Static has no documented packet ID/source timestamp; do not pretend it is synchronized to Physics or Graphics.

## 11.5 React Overview tile-by-tile wiring

This table describes the actual tile consumers in the current `App.tsx`, not merely the conceptual data available in the decoders.

| Overview tile | Actual source paths / fields consumed | UI transformations / derived logic | Findings / limits |
|---|---|---|---|
| Driver Trace | Physics `brake`, `throttle`, `gear_raw`, `speed_kph`, `rpm`; Graphics `distance_traveled_m`, `completed_laps`, `normalized_car_position` for trace reset context | Brake/throttle ×100; gear raw 0→−1, otherwise raw−1; retains a rolling recent trace | UI-derived trace, not simulator history; local time stamps and a bounded recent sample window |
| Speed | Physics `speed_kph` | Display directly as km/h | Already km/h; no conversion needed |
| Gear | Physics `gear_display` / `gear_raw` | 0=R, 1=N, otherwise raw−1 | ACC-specific encoding |
| RPM | Physics `rpm`, `current_max_rpm` | Segment gradient; shift flash at 95% of current maximum RPM | Threshold is presentation logic, not a simulator shift-light channel |
| Pedals | Physics `throttle`, `brake`, `clutch` | Normalized values ×100 and clamped to 0–100% | Pedal hardware is not the source of these values |
| Laps | Graphics `current_time_ms`, `last_time_ms`, `best_time_ms`, `completed_laps`, `is_valid_lap`; host-injected `lap_status` | Milliseconds formatted; valid/invalid/out-lap styling; out-lap suppresses timed-lap presentation | `lap_status="out"` is injected by the host out-lap observer, not raw Graphics |
| Lap History | Graphics `completed_laps`, `sector`, `last_sector_time_ms`, `last_time_ms`, `is_valid_lap`, `session_index`, `session`; Static-derived vehicle identity | Captures sector boundary observations; S1=t1, S2=t2−t1, S3=lapTime−t2; stores a bounded local history in localStorage | Local application history, not an ACC history feed. Assumes 3 sectors. Only records a lap if both boundary observations are available and ordered; out-laps are excluded |
| Weather | Physics `air_temp_c`, `road_temp_c`; Graphics `track_grip_status`, `rain_intensity`, `rain_10min`, `rain_30min`, `wind_speed`, `wind_direction` | Temperature displayed °C; wind speed labelled km/h; rain NOW/+10/+30 and grip rendered from raw values | Wind units/direction and rain/grip enum labels require validation |
| Track Map | Static `vehicle.track`, `vehicle.track_configuration`; Graphics `normalized_car_position`, `player_world_position`, `completed_laps`, `is_valid_lap`, `last_time_ms` | Learns world-coordinate X/Z polyline; rotates projection 90° clockwise; stores version-2 cache in localStorage keyed by normalized track + configuration | Requires at least 80 valid points; commits a learned layout only after capture rules accept it. It is not an official circuit map. Do not rebuild/rewrite on every lap |
| Session | Static vehicle identity; Graphics `session`, `status`, `session_time_left_s` (frontend key), `completed_laps`, `position`, `tyre_compound` | Raw enums formatted through helper functions; time helper divides by 1000 | Decoder actually emits `session_time_left_ms`, so current UI key does not match; session time can remain unavailable |
| Brakes | Physics wheel `brake_temp_c`, `brake_pressure`, `pad_life`, `disc_life` | Four-corner FL/FR/RL/RR layout; temperature thresholds and glow; raw pressure/pad/disc secondary values | Brake temperature °C; brake pressure and life units/semantics need further qualification |
| Tyres | Physics wheel `tyre_core_temp_c`, `tyre_pressure_psi`, `slip_ratio`, `slip_angle` | Four-corner layout; temperature bands/glow; pressure shown PSI; slip and angle formatted | Core temperature is selected; angle gets ° suffix without conversion; tyre_temp_c is not an independent validated alternate |
| Fuel | Physics `fuel_kg`; Graphics `fuel_per_lap_l`, `fuel_estimated_laps` | Remaining fuel variable is named `fuelLitres` and displayed with L; bar fraction = current value / highest value observed since app start; fuel/lap and laps remaining displayed directly | Confirmed kg→L labelling bug; bar is not tank-capacity percentage. Fuel/lap and estimated laps come from Graphics, not a locally calculated Physics estimator; direct HUD/refuel/session-reset validation remains open |
| Warnings | Graphics `is_valid_lap`, `penalty`, `penalty_time_s`, `missing_mandatory_pits`, `mandatory_pit_done` | Validity/penalty helpers and time formatting | Penalty enum values and penalty-time unit/suffix need verification; helper divides penalty time by 1000 |
| Delta | Graphics `delta_lap_time_str`, `delta_positive`, `estimated_lap_time_str`, numeric estimate fields | Displays delta string, positive/negative label and estimated lap | `delta_positive` semantics only observation-level; reject numeric sentinel values |
| Sectors | Graphics `sector`, `last_sector_time_ms`, `split_ms`, plus current-time values | Live and last-completed sector presentation | Frontend references `live_sector_time_ms`, but this field is not present in the current `DecodedGraphics` dataclass; confirm whether it is injected/derived elsewhere. Do not claim it is a direct decoder field. |
| Position | Graphics `position`, `gap_ahead_ms`, `gap_behind_ms` | Millisecond gaps formatted for display | Validate gap sign/sentinel and timing reference; single-car recording cannot validate race gaps |
| Car Electronics | Graphics `tc_level`, `tc_cut`, `engine_map`, `abs_level`; Physics `brake_bias`, `autoshifter_on`, `turbo_boost` | Raw TC/ABS setup levels; brake-bias correction helper; ON/OFF auto-shifter; turbo boost | TC and ABS Graphics setup levels were user-confirmed displayed correctly. Brake-bias correction is not trusted; turbo units unverified. Do not substitute Physics TC/ABS intervention flags |
| Pit / Stint | Graphics `is_in_pit`, `is_in_pit_lane`, `mandatory_pit_done`, `driver_stint_total_ms`, `driver_stint_left_ms`, `used_fuel_l`, `mfd_tyre_set`, `mfd_fuel_to_add`, `mfd_tyre_pressures`, `current_tyre_set`, `strategy_tyre_set`, `rain_tyres`, `tyre_compound` | Stint values formatted as time; tyre-change indication compares MFD set vs current set; MFD pressure requests shown by corner | Pit vs pit-lane are distinct. Stint semantics and MFD pressure units need verification |
| Vehicle Damage | Physics `car_damage[5]`, wheel `suspension_damage[4]` | Car damage shown Front/Rear/Left/Right/Centre raw; suspension damage ×100 and threshold colours | Do not label five car-damage raw values as percentages. Suspension damage percent scale still needs validation |
| Race Control | Graphics `flag`, `penalty`, `track_status`, `global_yellow`, `global_yellow_1/2/3`, `global_white`, `global_green`, `global_chequered`, `global_red` | Raw enum/boolean list with flag-colour effects where understood | Candidate flag/penalty enum mappings are not all verified; unknown values must stay neutral |
| Car Lights & Status | Physics `pit_limiter_on`, `engine_running`, `ignition_on`, `starter_engine_on`, `is_ai_controlled`, `water_temp_c`; Graphics `rain_lights`, `flashing_lights`, `lights_stage`, `wiper_level`, `direction_left`, `direction_right`, `exhaust_temp_c`, `rain_tyres` | Boolean-like values converted to ON/OFF; integer levels kept as raw status | User reported ON/OFF colour behaviour not working; inspect payload type/value per field. Wiper/lights-stage are levels, not booleans |
| Tyre Pressure Targets | Physics actual `tyre_pressure_psi`; user settings `acc-target-pressures` in localStorage | Per-corner actual PSI vs manually configured target PSI and difference | Target is user-entered, not ACC MFD. Blank by default; no comparison when target is unset |
| Hardware | Existing hardware subsystem/bridge | Connection state | Not sourced from ACC telemetry; RPM LED and pedal hardware remain separate |

## 11.6 Additional producer/consumer contract gaps found in the cross-check

| Frontend expectation / use | Decoder or publisher reality | Consequence |
|---|---|---|
| `graphics.session_time_left_s` | `DecodedGraphics` emits `session_time_left_ms` | Session time property mismatch; frontend formatter also divides by 1000 |
| `graphics.live_sector_time_ms` | Not a member of the current `DecodedGraphics` dataclass | Live sector timer may remain unavailable unless another layer derives/injects it |
| `static_metadata.data.max_fuel` | Static decoder has `max_fuel`, but Qt snapshot only publishes Static-derived vehicle identity | Tank capacity is unavailable to the tile |
| Fuel variable named `fuelLitres` | Physics emits `fuel_kg` | Incorrect unit label |
| `penalty_time_s` | Decoder field is named `penalty_time_s`; formatter comment says source is milliseconds and divides by 1000 | Field suffix is misleading; confirm raw semantics and rename the contract explicitly |
| `last_sector_time_ms` treated as a sector duration | App's own lap-history logic treats it as cumulative elapsed time at the sector boundary | Consumers must subtract boundary timestamps to derive S2/S3; do not display it as an isolated sector duration |
| Static `sector_count` | Decoded but not forwarded to frontend | Lap History currently assumes exactly 3 sectors rather than using Static sector count |
| Graphics candidate `estimated_lap_time_ms` | Can contain int32 sentinel 2147483647 | Filter sentinel before formatting or arithmetic |
| Graphics `delta_positive` | Observed change but no user-confirmed positive/negative event | Keep as candidate until a controlled comparison confirms sign meaning |
| Graphics `mfd_tyre_pressures` | UI appends PSI; source unit not independently established | Label as request only and validate unit before treating as physical PSI |
| Physics `tyre_temp_c` at offset 696 | Byte-for-byte alias of `tyre_core_temp_c` at offset 152 in the long capture | Do not present as an independent sensor/channel |

## 12. ACC-specific configuration and tile behaviour retained from the Overview design record

These are UI requirements/implementation notes, not additional raw telemetry channels:

- Corner order is FL/FR on the top row and RL/RR on the bottom row.
- Temperature colour progression is blue → green → yellow → orange → red. Starting configurable thresholds recorded in the design: tyre 70/90/100/110 °C and brake 250/400/500/600 °C. These are configurable starting values, not universal car limits.
- Damage threshold starting values are 20/40/70, but the raw five-value car-damage scale must not be described as percent until verified.
- Glow intensity has a configurable starting value of 65%.
- Target PSI has four independent FL/FR/RL/RR values; unset values remain blank and suppress comparison.
- Porsche 992 GT3 R was the initial configuration/test car. Do not apply Porsche-specific corrections to other cars without evidence.
- Lap tile colours: valid green, invalid red, out-lap orange. The out-lap label suppresses a lap time. Out-lap records are retained for debugging but excluded from Lap History/Session Summary.
- The direct menu jump from mid-lap to garage/pit and rejoin remains a known out-lap observer edge case; it was explicitly a non-goal for the tested implementation.
- Fuel bar scaling is based on the highest fuel value observed since app start, not verified tank capacity.
- Vehicle damage is five raw car-damage values plus four per-wheel suspension-damage values; water temperature appears only in Car Lights & Status.
- Vehicle lights/status colour behaviour was reported not working; do not mark it complete from the presence of fields alone.
- ACC Graphics fuel-per-lap and estimated-laps fields are decoded at offsets 0x504 and 0x584. They are integrated in the Overview, but direct comparison with the in-game HUD including refuelling/session reset remains pending.
- Target pressure settings and glow settings are saved in browser localStorage; desktop restart persistence requires runtime validation.
- Overview layout saves only when the user clicks Save in dashboard edit mode; the Qt host uses a stable loopback origin and named persistent WebEngine profile.

## 13. Evidence status and confidence — keep these categories separate

| Evidence label | Meaning |
|---|---|
| Decoder field exists | Code has a named field at a candidate offset; this alone does not prove ABI or semantics |
| Raw observed | Values changed or were nonzero in a capture; causality/meaning may still be unknown |
| Controlled correlation | A controlled action or user-confirmed game event correlated with a field |
| User-confirmed UI behaviour | User explicitly confirmed the displayed behaviour/value |
| Reference implementation | Independent reader/application has a corresponding member or use; not official Kunos certification |
| Unverified | No controlled correlation or authoritative source has settled the meaning |
| UI-derived | Computed by frontend/application from source fields |
| Host-derived | Computed by the application host, such as out-lap observer status |

### Known evidence snapshots

- Physics: target-PC ACC 1.10.4 capture, shared-memory identifiers `smVersion=1.9`, `acVersion=1.7`; 600-second capture on 10 November 2026 passed raw acquisition/persistence/recovery/reconciliation checks. The corrected Physics page is 800 bytes; final 16 bytes remain opaque.
- Graphics: 18,000 samples over 180 seconds on 9 November 2026; status, completed laps, sector and lap validity correlate with observed events; normalized progress and coordinates show plausible motion. Graphics ABI remains candidate, not officially certified.
- Static: target-PC candidate inspection favours 820-byte Variant B over 784-byte Variant A based on coherent CarSkin and dry/wet tyre strings at B offsets. Still not official ABI certification.
- Prior ACC application evidence: the Graphics coverage audit records prior live-confirmed lap validity/history, track-limit warning, S1/S2/S3 timing, reference-lap validity, PRE-CORNER refresh, overlay update/retention and Corner Coach reference correctness. These are application-level behaviour confirmations, not raw offset proof.

## 14. Corrected validation priorities

1. Fix the fuel quantity contract: expose kg as kg, or use a verified litre-valued channel. Do not retain the `fuelLitres` alias for Physics `fuel_kg`.
2. Publish an explicit Static metadata object or intentionally map required Static fields into a documented snapshot shape. At minimum decide whether `max_fuel` and `sector_count` are to be consumed by Overview.
3. Align `session_time_left_ms` between decoder, snapshot and frontend; format once. Reconcile `penalty_time_s` naming against its actual raw unit.
4. Resolve the missing `live_sector_time_ms` expectation and make the live sector timer's producer explicit.
5. Use Static `sector_count` or another verified source instead of hardcoding three sectors if the Overview is to support arbitrary ACC tracks/layouts.
6. Remove or validate the Porsche brake-bias correction. Historical ACC issue #13 records the previous correction as speculative and unable to resolve the dashboard/HUD mismatch (dashboard around 79.4%/81.0% vs ACC 58.4%/60.0%). Do not add another guessed offset.
7. Validate wind speed/direction, slip angle, brake pressure, pad/disc life, suspension damage scale, exhaust temperature, MFD pressure request units, fuel used and stint-time semantics.
8. Validate enum and sentinel handling for session/status, flags, penalty, track grip, rain, lights, tyre sets, MFD indices and estimated lap time.
9. Preserve lap-validity stickiness and out-lap separation. Keep out-laps out of Lap History/Session Summary.
10. Validate multi-car player coordinate association and race gaps; the single-car Graphics recording cannot establish them.
11. Keep the acquisition hot path isolated: no decoding, serialization, UI callbacks or disk I/O in the high-rate shared-memory copy loop. Preserve independent rings/consumers and monitor packet consistency, ring loss and decode errors.
12. Validate all tile values against the live ACC HUD or controlled actions, with explicit recording of which items are user-confirmed, controlled-correlated, observed-only or still unknown.

## 15. Corrections to earlier sections of this document

The cross-check found several places where the initial short document was incomplete or imprecise:

- **Fuel per lap and estimated laps remaining are not calculated locally from Physics fuel deltas in the current Overview path.** They are read from Graphics fields `fuel_per_lap_l` (offset 0x504) and `fuel_estimated_laps` (offset 0x584). The earlier recommendation to build a duplicate Physics estimator should not be followed.
- **Static is decoded, but not fully published.** The host uses Static data for `vehicle.car_model`, `vehicle.track` and `vehicle.track_configuration`; it does not publish `static_metadata.data.max_fuel`. This is the exact reason the UI's tank-capacity lookup is unavailable.
- **The tyre temperature fields at offsets 152 and 696 are not established as two distinct measurements.** A long raw capture found them byte-for-byte identical in every one of 224,956 samples. The UI uses `tyre_core_temp_c`; do not claim the second field is an independent alternate sensor.
- **ACC speed is already `speed_kph`.** No m/s-to-km/h conversion is required for this tile.
- **ACC tyre pressure is already `tyre_pressure_psi`.** No Pa-to-PSI conversion is required for this source.
- **Sector boundary timing is cumulative.** `last_sector_time_ms` is treated by the frontend lap-history observer as cumulative elapsed time at a boundary; sector durations are derived by subtraction.
- **The current Qt host publishes out-lap state as a sibling Graphics `lap_status` field.** It is not a raw member in the Graphics decoder.
- **The initial document omitted many actual Overview tiles and detailed fields**, including Driver Trace, Warnings, Delta, Position, Pit/Stint, Race Control, Car Lights & Status, Tyre Pressure Targets, per-corner pad/disc/brake-pressure values, MFD requests, and the actual Static/Graphics publication boundary. The tile map in §11.5 is the source-level cross-check for these.
