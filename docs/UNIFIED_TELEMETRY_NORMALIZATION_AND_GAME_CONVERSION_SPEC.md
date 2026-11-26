# Unified Telemetry Normalization and Game Conversion Specification

**Status:** Architecture specification / proposed implementation contract  
**Repository branch:** `feature/iracing-game-support`  
**Scope:** ACC, iRacing, Assetto Corsa (AC), and F1 2026  
**Baseline:** Current ACC Overview field mapping and findings  
**Application principle:** One SimLink application, one shared Overview, game-specific telemetry adapters.

---

## 1. Purpose and governing decisions

This document defines how telemetry from different racing simulators will be normalized so that one shared Overview page can consume it.

The current ACC telemetry-to-Overview mapping is the reference baseline. It documents the existing tile relationships, data flow, source fields, conversions, uncertainties, and known defects. It is a baseline for compatibility and audit—not a requirement to reproduce every legacy ACC field name or existing unit mistake in the new canonical contract.

### Decisions agreed

1. **Keep one unified application.** ACC, iRacing, AC and F1 2026 are game sources supported by the same application, not separate Overview implementations.
2. **Keep the existing Overview tiles shared.** Each game adapter supplies the same canonical telemetry contract wherever the game exposes the required information.
3. **ACC remains the baseline reference.** Use the current ACC mapping document as the reference when deciding what each Overview tile means and how it is currently populated.
4. **Normalize meaning, not just names.** Two fields may share a canonical name only when they represent the same physical quantity or semantic state.
5. **Conversions belong in game-specific adapters.** The frontend must not contain scattered ACC/iRacing/AC/F1 conversion branches.
6. **Retain native-source information.** Every conversion must be traceable to its native field, native unit, formula, and verification status.
7. **Do not fabricate channels.** If a game does not expose a value, mark it unsupported or unavailable. Do not substitute zero or infer a measurement from an unrelated channel.
8. **Keep display preferences separate.** Shared display preferences (for example km/h versus mph, PSI versus bar, °C versus °F) belong in shared settings. Native-to-canonical conversions belong in the relevant adapter.
9. **Keep game-specific exceptions explicit.** Car-specific corrections, simulator version differences, enum maps and source quirks must be recorded in versioned adapter profiles—not buried in UI code.
10. **Preserve working ACC functionality.** This specification does not authorize rewriting ACC acquisition or changing existing application code. Corrections should be isolated, tested and introduced deliberately.
11. **Normalize iRacing after the contract is agreed.** iRacing is the first non-ACC adapter to audit and bring into alignment. AC and F1 mappings must be verified against their actual telemetry interfaces before implementation.
12. **Implement incrementally.** Validate the contract and adapter mappings tile by tile. Do not attempt a broad simultaneous rewrite.

## 2. Reference baseline and relationship to the ACC mapping

The baseline document is:

- [ACC Telemetry Overview Field Mapping and Findings](ACC_Telemetry_Overview_Field_Mapping_and_Findings.md)
- Baseline revision reviewed: commit `fb897ff248329670d098f95971aec6a3e12dce9e`
- File: `docs/ACC_Telemetry_Overview_Field_Mapping_and_Findings.md`

That document traces ACC shared-memory acquisition, Physics/Graphics/Static decoding, consumers, Qt host snapshot publication, bridge delivery, frontend field reads, display formatting, and identified mismatches.

The ACC baseline remains authoritative for **what the existing Overview currently means and displays**, subject to the corrections and unresolved items listed below. This new specification defines the intended cross-game contract.

### 2.1 Existing ACC data-flow reference

The reviewed ACC path is broadly:

1. ACC exposes Physics, Graphics and Static shared-memory mappings.
2. Separate acquisition and decoder/consumer paths read those structures.
3. The Qt host assembles a telemetry snapshot and adds selected host-derived or metadata values.
4. The local HTTP/SSE bridge makes snapshots available to the frontend.
5. React Overview tiles read the snapshot, format values and derive selected presentation values.

The reviewed ACC acquisition rates differ by stream; the Qt host publishes a lower-frequency snapshot to the UI. The adapter architecture must preserve source freshness and avoid treating stale snapshots as current measurements.

### 2.2 ACC baseline issues must not become canonical behaviour

The current ACC mapping identifies, among other things:

- ACC's in-game UI displays remaining fuel in litres (L), as confirmed by the user. The reviewed Physics decoder field is named `fuel_kg`; that suffix conflicts with the game display unit but does not, by itself, prove the numeric value is kilograms. Preserve litres in the ACC Overview contract and verify the decoder value against a simultaneous HUD capture before changing source semantics or adding any conversion.
- Graphics publishes `session_time_left_ms`, while a frontend path reads `session_time_left_s`. The producer and consumer contract must be aligned.
- Static decoding obtains `max_fuel`, but the expected `static_metadata.data.max_fuel` publication shape is not present in the reviewed Qt snapshot.
- A frontend reference to `live_sector_time_ms` does not have a corresponding field in the reviewed decoded Graphics structure.
- `penalty_time_s` has a name/formatting ambiguity; its raw unit and conversion must be confirmed.
- Porsche 992 brake-bias handling contains a car-specific correction whose source scale and offset require validation. Do not assume that the existing correction is universally correct.
- Slip-angle, wind-speed, stint-time and some MFD tyre-pressure units remain unverified.
- Graphics and Static layouts described in the decoder are candidate layouts, not official ABI certification.
- ACC lap-history logic has historically assumed three sectors; the canonical contract must support dynamic sector counts.
- ACC out-lap classification is host-observed state, not a raw ACC shared-memory field.
- The learned track map is application-derived from telemetry samples, not authoritative simulator track geometry.

These are ACC adapter audit items. They must not be copied as universal assumptions for other simulators.

## 3. Target architecture

The intended data flow is:

```text
ACC source ───────┐
iRacing SDK ──────┤
AC telemetry ─────┼──> Game-specific adapters
F1 telemetry ────┘          |
                            v
                 Canonical telemetry contract
                            |
                            v
                  Shared Overview / shared UI
```

### 3.1 Responsibilities

| Layer | Responsibility | Must not do |
|---|---|---|
| Game acquisition | Read the simulator's native telemetry source safely | Apply UI formatting |
| Game-specific adapter | Map native fields, validate sentinels, convert units, normalize enums and gear, derive explicitly documented values | Invent unavailable channels |
| Conversion profile | Declare source field, source unit, canonical unit, formula, exceptions and evidence | Hide unexplained constants |
| Canonical snapshot | Publish stable game-independent field names and semantic meanings | Expose inconsistent game-specific shapes to the UI |
| Shared Overview | Render canonical values and availability; apply user display preferences | Contain per-game source mapping or conversion branches |
| Shared settings | Store display-unit and common presentation preferences | Override native-source facts |
| Game-specific settings | Store genuinely game-specific configuration | Duplicate common display settings |

### 3.2 Adapter boundary

Each simulator adapter owns all knowledge of that simulator's telemetry protocol. The frontend should not need to know whether a value originated from ACC shared memory, iRacing SDK, AC telemetry, or F1 packets.

The adapter may use native fields directly when they already match the canonical representation. In that case the conversion operation is explicitly `identity`.

## 4. Canonical telemetry contract

The following is the proposed contract for the shared Overview. The schema is semantic: field names and meanings are stable across games. Optional values may be null, but their availability state must explain why.

### 4.1 Vehicle and driver inputs

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `speed_mps` | Vehicle speed | metres per second | Never mix km/h and m/s under the same field |
| `gear` | Current gear state | Normalized gear state | Reverse, neutral and forward gears have consistent semantics |
| `gear_display` | UI-friendly gear label | String | Derived from normalized gear; e.g. R, N, 1 |
| `engine_rpm` | Engine rotational speed | RPM | Do not confuse engine RPM with wheel speed |
| `max_engine_rpm` | Applicable engine RPM limit/shift reference | RPM | Record whether source is redline, shift point or blink threshold |
| `throttle` | Driver throttle input | 0.0–1.0 | Clamp only after validating source scale |
| `brake` | Driver brake input | 0.0–1.0 | Brake pressure is a separate physical channel |
| `clutch` | Driver clutch input | 0.0–1.0 | Optional |
| `steering_angle_rad` | Physical steering wheel angle | radians | Do not map a normalized steering command into this field |
| `steering_input` | Normalized steering input, if source exposes only this | documented normalized range | Keep distinct from physical angle |
| `abs_active` | ABS intervention state | Boolean / unknown | Not the same as ABS setup level |
| `tc_active` | Traction-control intervention state | Boolean / unknown | Not the same as TC setup level |
| `tc_setting` | Configured traction-control level | Native-independent numeric/string setting where possible | Preserve source semantics and setting scale |

### 4.2 Lap and sector timing

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `lap_number` | Current lap number | Integer | Define whether it counts completed or current in-progress lap |
| `lap_distance_pct` | Progress through current lap | 0.0–1.0 | Validate source range and wrap behaviour |
| `lap_current_time_ms` | Current lap elapsed time | Milliseconds | Null when source is not valid |
| `lap_last_time_ms` | Last completed lap duration | Milliseconds | Do not treat incomplete/out lap as a valid timed lap |
| `lap_best_time_ms` | Best eligible lap duration | Milliseconds | State whether source-provided or locally derived |
| `lap_validity` | Validity of current/completed lap | `valid`, `invalid`, `unknown` | Unknown is not valid |
| `lap_status` | Additional classification | Defined enum | May include out-lap, in-lap, timed lap, incomplete, etc. |
| `sector_count` | Number of sectors for active track/session | Integer | Dynamic; never hard-code three globally |
| `current_sector_index` | Current sector | Zero- or one-based index, explicitly fixed by schema | Use one convention consistently |
| `sector_times_ms` | Sector durations | Ordered array of milliseconds or null entries | Preserve unknown partial sectors |
| `sector_best_times_ms` | Best eligible sector durations | Ordered array | Compare only compatible track/layout and valid evidence |
| `delta_to_best_ms` | Current delta to selected reference | Signed milliseconds | Sign convention must be documented and consistent |
| `estimated_lap_time_ms` | Estimated lap time | Milliseconds | Reject source sentinels and implausible values |

Lap history, best-lap selection and sector comparisons are application/session logic built on the canonical inputs. They must preserve validity and track/layout identity. A game adapter must not manufacture a completed lap from partial timing.

### 4.3 Fuel, stint and pit

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `fuel_remaining_l` (ACC profile) | Remaining ACC fuel | Litres (L) | ACC HUD displays litres; reconcile the decoder's `fuel_kg` field name with raw-value/HUD evidence. Do not apply an unverified density conversion |
| `fuel_capacity` | Maximum tank quantity | Quantity plus explicit unit | Unit must match or be explicitly convertible |
| `fuel_used_per_lap` | Observed fuel use per completed lap | Quantity per lap plus unit | Derived; requires stable lap boundaries |
| `fuel_laps_remaining` | Estimated remaining laps | Laps | Derived only with credible consumption estimate |
| `fuel_used_session` | Fuel consumed since session anchor | Quantity plus unit | Derived; reset behaviour documented |
| `fuel_flow` | Fuel consumption rate | Quantity per second or hour plus unit | Do not assume mass or volume |
| `stint_elapsed_ms` | Elapsed driver stint duration | Milliseconds | Only if source semantics confirmed |
| `stint_remaining_ms` | Remaining allowed stint duration | Milliseconds | Only if source actually exposes/permits derivation |
| `in_pit_lane` | Vehicle in pit lane | Boolean / unknown | Distinct from being in pit stall |
| `in_pit_stall` | Vehicle stopped in pit stall | Boolean / unknown | Optional |
| `pit_limiter_active` | Pit speed limiter state | Boolean / unknown | Distinguish setting from active state |

Fuel is not a single universal scalar. It is a physical quantity with a unit. The canonical schema must retain the explicit unit for each game's fuel channel. **ACC's game UI displays fuel in litres (L)**, so the ACC adapter and Overview must expose/display litres; the decoder field currently named `fuel_kg` must be reconciled against a simultaneous raw-value/HUD capture rather than interpreted from its suffix alone. Other simulators may expose mass (kg) or volume (L). A mass-to-volume conversion requires a documented density appropriate to the fuel and conditions; a fixed 1:1 conversion is prohibited.

### 4.4 Tyres and brakes

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `tyre_core_temp_c[corner]` | Tyre core temperature | °C | Preserve corner order |
| `tyre_surface_temp_c[corner]` | Tyre surface temperature | °C | Do not alias to core temperature without evidence |
| `tyre_pressure_pa[corner]` | Pressure | Pa | Source may be cold setup pressure or live pressure; record measurement kind |
| `tyre_pressure_kind[corner]` | Pressure measurement classification | Enum | E.g. live-hot, cold-setup, target, unknown |
| `tyre_wear[corner]` | Tyre wear/condition | Raw normalized value with documented scale | Do not assume percentage without validation |
| `slip_ratio[corner]` | Longitudinal slip ratio | Dimensionless | Optional |
| `slip_angle_rad[corner]` | Slip angle | Radians | Optional; validate source convention |
| `brake_temp_c[corner]` | Brake temperature | °C | Optional |
| `brake_pressure_pa[corner]` | Brake line pressure | Pa | Separate from pedal input |
| `brake_bias_pct` | Brake bias | Percent | Normalize source scale and document car-specific corrections |
| `abs_setting` | ABS setup level | Source-independent representation where possible | Separate from intervention |
| `tc_setting` | TC setup level | Source-independent representation where possible | Separate from intervention |
| `suspension_damage` | Damage measurement | Raw value plus verified scale | Do not append percent until scale is known |

Use stable wheel/corner identifiers: `FL`, `FR`, `RL`, `RR`. A game adapter must explicitly map its native wheel ordering to this convention.

### 4.5 Weather and track conditions

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `air_temp_c` | Ambient air temperature | °C | |
| `track_temp_c` | Track surface temperature | °C | |
| `wind_speed_mps` | Wind speed | m/s | |
| `wind_direction_rad` | Wind direction | radians | Define reference axis and clockwise/counter-clockwise convention |
| `rain_intensity` | Current rain intensity | Documented normalized/source-independent scale only if semantically comparable | Do not conflate forecast and current rain |
| `track_wetness` | Track wetness | Documented normalized/source-independent scale only if semantically comparable | |
| `track_grip_state` | Track grip state | Normalized enum only where semantics align | Preserve native value/provenance |
| `weather_description` | UI description | String/enum | Derived from verified state |

### 4.6 Track map and position

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `world_position_m` | Vehicle world position | Coordinate vector in metres, with coordinate frame metadata | Do not assume axes/orientation are shared |
| `track_position` | Position on track | Normalized 0.0–1.0 progress where available | Separate from world coordinates |
| `track_name` | Track identity | String | |
| `track_configuration` | Layout/configuration identity | String or null | Must participate in cache identity |
| `track_map_samples` | Learned/available map geometry | Coordinates plus provenance | Distinguish learned map from official map |
| `corner_markers` | Track corner annotations | Derived geometry/metadata | Optional; do not fabricate |

Track map geometry is not interchangeable across games unless the coordinate system, track identity and layout are reconciled. A learned map must be keyed by game/source, track, layout and any other required coordinate-frame metadata.

### 4.7 Session, race control, vehicle and warnings

| Canonical field | Meaning | Canonical representation | Notes |
|---|---|---|---|
| `session_type` | Practice, qualifying, race, etc. | Normalized enum plus native value | Preserve unknown |
| `session_time_remaining_ms` | Session time remaining | Milliseconds | Convert to seconds only for presentation |
| `position` | Overall position | Integer | |
| `class_position` | Class position | Integer | |
| `car_count` | Active participant count | Integer | Define whether includes pace/spectator vehicles |
| `gap_ahead_ms` | Time gap to car ahead | Signed/defined milliseconds | Only if source supports reliable association |
| `gap_behind_ms` | Time gap to car behind | Signed/defined milliseconds | |
| `flag_state` | Race-control flag | Normalized enum plus native value | Unknown values remain unknown |
| `penalty_state` | Penalty state | Structured/normalized enum | Penalty duration unit explicit |
| `incident_count` | Incident count | Integer | Preserve driver/team/session distinction |
| `engine_warnings` | Engine warning state | Bitset/enum with decoded meanings | |
| `vehicle_damage` | Damage channels | Raw named measurements with verified scales | Do not fabricate percentages |
| `lights_state` | Car light state | Boolean/enum per light | Validate bit mapping |
| `vehicle_identity` | Car make/model/class | Metadata | Not a telemetry measurement |
| `driver_identity` | Active driver | Metadata | Respect team-driver/session changes |

### 4.8 Hardware values remain separate

Pedal-board connection, hardware sensor selection, load-cell tare, handbrake input, RPM LED connection and other controller information belong to the hardware subsystem. They must not be overwritten by simulator telemetry.

The shared Overview may show both simulator telemetry and hardware status, but the canonical simulator adapter must not claim ownership of hardware-originated values.

## 5. Canonical units and display conversions

Use the following canonical units internally. Display-unit preferences are applied after the adapter has published canonical values.

| Quantity | Canonical unit | Display conversion |
|---|---|---|
| Speed | m/s | km/h = m/s × 3.6; mph = m/s × 2.2369362921 |
| Pedal inputs | 0.0–1.0 | percent = value × 100 |
| Physical steering angle | radians | degrees = radians × 180 / π |
| RPM | RPM | Identity |
| Temperature | °C | °F = °C × 9/5 + 32 |
| Pressure | Pa | PSI = Pa / 6894.757293; bar = Pa / 100000 |
| Time | ms | seconds = ms / 1000; format at UI boundary |
| Wind speed | m/s | km/h = m/s × 3.6; mph = m/s × 2.2369362921 |
| Angular direction | radians | degrees = radians × 180 / π |
| Track progress | 0.0–1.0 | percent = value × 100 |
| Fuel | Explicit quantity + unit; ACC profile uses L | ACC Overview displays litres; verify native decoder semantics and do not apply an unverified conversion |
| Fuel flow | Explicit quantity/time + unit | Convert only with dimensionally valid formula |

### 5.1 Conversion rules

- Convert exactly once at the adapter boundary to canonical units.
- Do not convert a canonical value again in another adapter or in the frontend.
- Do not use field suffixes that contradict the stored unit.
- Keep integer time values in milliseconds until display formatting.
- Keep normalized inputs in 0.0–1.0 internally; display percentages in the UI.
- A conversion formula must include the source unit and target unit.
- For offsets, sign changes, scale factors or car-specific corrections, record the reason and evidence.
- Validate finite numeric values; reject NaN and infinity.
- Reject documented source sentinels and implausible values before publishing a channel.
- Do not silently clamp an invalid value into a plausible value. If clamping is required for a documented source range, record it as part of the conversion profile.

## 6. Per-game conversion profiles

Every game adapter must have a conversion profile. Profiles should be explicit, reviewable and versioned. A profile entry should contain:

- Canonical field.
- Native source field and source structure/API.
- Native unit and canonical unit.
- Conversion operation/formula.
- Native scale/range and semantic meaning.
- Enum/gear mapping, if applicable.
- Sentinel and invalid-value rules.
- Car-specific or game-version-specific exception, if applicable.
- Evidence/reference and verification status.

### 6.1 ACC profile

ACC is the baseline adapter and must be mapped using the existing ACC field mapping document. Its profile must account for the separate Physics, Graphics and Static streams and the Qt host publication boundary.

The profile must explicitly identify:
- Raw shared-memory field and decoder output field.
- Consumer/host snapshot field.
- Frontend tile field.
- Source unit and canonical unit.
- Any host-derived or application-derived value.
- Current verification status.

ACC conversion and contract audit priorities are:

1. ACC fuel is displayed in litres (L). Correlate the Physics decoder field named `fuel_kg` with the in-game HUD; preserve L in the ACC Overview and only change decoder naming/conversion after evidence establishes the native numeric semantics.
2. Align session remaining time on `session_time_remaining_ms` (or another single agreed canonical name) end to end.
3. Publish Static metadata through an explicit schema if required, rather than relying on an unpublished nested object.
4. Identify or derive the live sector time explicitly; do not reference a nonexistent decoded field.
5. Resolve penalty duration units and field naming.
6. Verify brake-bias scale and Porsche 992 correction with controlled evidence before retaining or changing the offset.
7. Verify slip-angle, wind-speed, wind-direction, stint, brake-pressure/life, suspension-damage, exhaust-temperature, MFD tyre-pressure and fuel-used semantics.
8. Validate enums, sentinels and unknown-value behaviour.
9. Preserve lap-validity stickiness and out-lap exclusion.
10. Validate multi-car coordinate association and race gaps.
11. Use dynamic sector count and sector boundaries rather than a global three-sector assumption.
12. Keep acquisition loops free of heavy decoding, serialization, UI callbacks and disk I/O.

No correction in this list should be interpreted as already implemented by this specification.

### 6.2 iRacing profile

iRacing is the first non-ACC adapter to align with the canonical contract. The existing iRacing reader already publishes a snapshot intended for the Overview; audit it field by field against this specification.

The reader must document:
- SDK variable name and declared unit.
- SDK session/static YAML source where used.
- Native field type, sentinel and valid range.
- Conversion to canonical unit.
- Derived values and their session/lap anchors.
- Availability and stale behaviour.
- Whether the source is live measurement, setup value, configuration, session metadata or locally derived.

Known mapping observations from the current reader that must be explicitly reviewed:

| Area | Existing reader observation | Required treatment |
|---|---|---|
| Speed | Reads SDK `Speed` in m/s and publishes km/h in a field named `speed_kph` | Canonical adapter output should be m/s; display conversion later |
| Pedals | Reads `Throttle`, `Brake`, `Clutch` | Verify SDK range and publish normalized 0–1 |
| Gear | Reads SDK `Gear`; SDK convention differs from display labels | Normalize reverse/neutral/forward explicitly |
| RPM | Reads `RPM` and shift/blink thresholds | Publish engine RPM and separately classify the threshold meaning |
| Fuel | Reads `FuelLevel` and `FuelLevelPct` | Preserve actual SDK quantity unit and percentage separately; do not assume litres without confirming SDK declaration |
| Tyre temperature | Reads `LF/RF/LR/RRtempCL/CM/CR` and averages available channels | Confirm channel semantics; do not label an average as core temperature unless justified |
| Tyre pressure | Reads `*coldPressure`, documented in the current reader comment as kPa, then converts to PSI | Canonical pressure should be Pa; preserve cold-setup classification, not live hot pressure |
| Brake pressure | Reads `*brakeLinePress` | Verify native unit and mapping to canonical brake line pressure |
| Wind | Reads `WindVel` and `WindDir` | Confirm SDK units/conventions and normalize to m/s/radians |
| Temperature | Reads water/oil/air/track temperature channels | Verify native units and retain distinct temperature meanings |
| Sector timing | Uses session `SplitTimeInfo.Sectors` and derives boundaries | Preserve dynamic sector count and unknown partial sectors |
| Fuel use per lap | Derived from observed fuel at lap boundaries | Mark as derived and require stable completed-lap observations |
| Estimated laps | Fuel remaining / observed fuel per lap | Do not publish until sufficient credible consumption data exists |
| Race gaps | Uses `CarIdxF2Time` and `CarIdxPosition` association | Validate sign, ordering, class/race context and missing opponents |
| ABS | Reads `BrakeABSactive` | Treat as intervention state, not setup level |
| Track map | Uses world position/progress where available | Record coordinate frame and track/layout identity |

This table records code observations and audit requirements. Where SDK documentation or controlled runtime evidence is not yet available, the source-unit or semantic claim remains unverified. Do not infer a definitive unit solely from a variable name or an existing comment.

The current iRacing reader has also had a test expectation around sector availability: a test expected no sector where the reader derived sector index 2. That behaviour must be resolved through the contract and source evidence, not by forcing a fabricated sector value or weakening the test without justification.

### 6.3 Assetto Corsa (AC) profile

AC mapping must be based on the actual telemetry interface used by this application and the exact fields available from that interface/version.

For every canonical field:
1. Identify the actual AC source/API field.
2. Confirm its native unit and scale from reliable documentation or controlled capture.
3. Record whether it is live, static, derived, or unavailable.
4. Implement a conversion only after the source semantics are verified.
5. Add adapter tests using captured or controlled source values.

Do not assume AC uses ACC's shared-memory layout or that similarly named fields have identical units. Do not assume Content Manager, CSP, Pure or third-party plugins expose a field unless the application's selected telemetry source actually supplies it.

### 6.4 F1 2026 profile

F1 2026 mapping must be based on the exact packet specification/version and the telemetry source implemented in this repository.

For every canonical field:
1. Identify packet ID, field name, data type, scale and unit.
2. Confirm packet version compatibility and player-car indexing.
3. Record packet timing/frequency and stale handling.
4. Normalize gear, flags, session types and car-state enums explicitly.
5. Validate packet sentinel values and missing/invalid packet behaviour.
6. Keep derived race-engineer values distinct from raw packet values.

Do not assume F1 packet fields match ACC or iRacing semantics merely because the Overview labels are shared.

## 7. Availability, validity, freshness and provenance

A numeric value alone is insufficient to describe telemetry quality. Every optional canonical channel must have an explicit availability state and source provenance.

### 7.1 Availability states

Use these semantic states consistently:

| State | Meaning | UI behaviour |
|---|---|---|
| `available` | A current, validated source value exists | Display value |
| `unsupported` | This simulator/source does not expose the channel | Display unavailable marker or omit the tile value |
| `unavailable` | Channel is expected/known but no valid reading is currently supplied | Display unavailable marker |
| `stale` | Last valid sample exceeds its channel freshness threshold | Do not present it as current; optionally show stale indicator |
| `invalid` | Source value failed validation or is a known sentinel | Do not display as a valid measurement |
| `not_applicable` | Channel does not apply in the current vehicle/session context | Hide or explain as appropriate |

A missing value must never be silently converted to zero. Zero is a valid measurement for many channels (for example speed, throttle, brake, fuel flow, or damage) and must not mean “not available.”

### 7.2 Provenance

Where practical, canonical channel metadata should retain:

- Game/source identifier.
- Native field name.
- Native structure/API/packet.
- Native unit and type.
- Canonical unit.
- Conversion operation/profile version.
- Source timestamp or sample age.
- Verification status and evidence reference.
- Derived/raw classification.

Example conceptual payload:

```python
{
    "speed_mps": 55.2,
    "availability": "available",
    "source": {
        "game": "iracing",
        "field": "Speed",
        "interface": "iRacing SDK",
        "native_unit": "m/s"
    },
    "conversion": {
        "operation": "identity",
        "profile_version": 1,
        "status": "verified"
    }
}
```

Example for a channel not exposed by a source:

```python
{
    "brake_temp_c": None,
    "availability": "unsupported",
    "source": None,
    "conversion": None
}
```

These examples illustrate the contract. The final runtime representation may use a compact shared metadata block rather than repeating the same metadata object for every channel, provided each channel remains traceable.

### 7.3 Derived-value classification

Every value should be classifiable as one of:

1. **Raw/source measurement** — directly read from the simulator.
2. **Decoder-normalized measurement** — same physical quantity, converted into the canonical unit or representation.
3. **Host-derived state** — classified by application-side observation (for example out-lap state).
4. **Application-derived value** — computed from multiple samples or session records (for example fuel per lap, estimated laps remaining, learned map).
5. **Presentation value** — formatting, rounding, display-unit conversion, labels, colour thresholds.

A tile must not present a derived value as though the simulator directly supplied it.

## 8. Gear, enum and semantic normalization

### 8.1 Gear

Each adapter must map its native gear encoding into one canonical representation. Reverse, neutral and forward gear numbers must have consistent meanings. The display string is generated from that normalized representation.

Do not assume that all games use the same integer offset or reserve the same value for reverse/neutral.

### 8.2 Enums and flags

For session type, flags, track grip, rain, penalties, pit state, lights, engine warnings and tyre sets:

- Keep native value available for diagnostics.
- Map only values whose meanings are verified.
- Preserve unknown/unmapped values as unknown.
- Do not map an unfamiliar value to a convenient default such as green flag, dry track, or no penalty.
- Version enum mappings where protocol versions change.

### 8.3 Measurement versus configuration versus intervention

Keep these separate:
- ABS/TC setup level versus ABS/TC intervention.
- Brake pedal input versus brake line pressure.
- Cold setup tyre pressure versus live hot tyre pressure.
- Engine redline versus shift point versus shift-light blink threshold.
- Stint elapsed time versus stint allowance versus stint time remaining.
- Current rain versus rain forecast.
- Raw damage value versus a derived percentage.

## 9. Conversion profile format

A conversion profile should be machine-readable or represented in a structured adapter definition, with human-readable documentation generated or maintained alongside it.

Conceptual example:

```python
SPEED_PROFILE = {
    "canonical_field": "speed_mps",
    "source_field": "Speed",
    "source_interface": "iRacing SDK",
    "source_unit": "m/s",
    "canonical_unit": "m/s",
    "operation": "identity",
    "validity": {
        "finite": True,
        "minimum": 0.0
    },
    "verification": {
        "status": "verify_against_sdk_reference",
        "evidence": None
    }
}
```

Example of a source reporting km/h:

```python
SPEED_PROFILE = {
    "canonical_field": "speed_mps",
    "source_field": "speed_kph",
    "source_unit": "km/h",
    "canonical_unit": "m/s",
    "operation": "value / 3.6",
    "verification": {
        "status": "must_be_verified_for_actual_source",
        "evidence": None
    }
}
```

These are schema examples only. They do not assert that the current AC or F1 adapters expose those exact fields.

### 9.1 Verification status vocabulary

Use explicit statuses such as:

- `verified_documentation` — authoritative interface documentation confirms the field/unit/meaning.
- `verified_capture` — controlled runtime capture confirms expected behaviour.
- `verified_code_path` — source-to-UI path has been traced, but native ABI semantics may remain uncertain.
- `candidate` — plausible mapping awaiting sufficient evidence.
- `unverified` — not yet confirmed.
- `unsupported` — source does not expose the channel.
- `deprecated` — no longer used; retained for migration/audit context.

A code comment or a variable suffix alone is not authoritative unit evidence.

## 10. Shared Overview and settings responsibilities

### 10.1 Overview

The Overview consumes canonical fields only. It may:
- Format time.
- Apply display-unit preferences.
- Round values for readability.
- Render unavailable/stale/invalid states.
- Render game-independent labels and visualizations.
- Render optional fields when available.

It must not:
- Read raw simulator SDK/packet/shared-memory fields.
- Contain simulator-specific conversion constants.
- Guess units based on game or car names.
- Convert unsupported channels into zeros.
- Treat configuration as live intervention.
- Infer a value from an unrelated channel without a documented derivation.

### 10.2 Settings

Shared settings should own:
- Speed display unit (km/h or mph).
- Temperature display unit (°C or °F).
- Pressure display unit (PSI or bar).
- Other common display and accessibility preferences.

Game-specific settings should be grouped under the application's central Settings page, but only contain genuinely game-specific options. Adapter conversion profiles are engineering configuration, not end-user display settings.

### 10.3 Hardware

Hardware configuration and telemetry remain a separate subsystem. Pedal sensor selection, load-cell tare, load-cell configuration, handbrake calibration, board communication and RPM LED hardware status must continue to be managed by the hardware layer and delivered to the shared UI independently of simulator adapters.

## 11. Validation and testing requirements

### 11.1 Unit tests per conversion

For each profile conversion, test:
- Known normal input.
- Boundary values.
- Zero where zero is physically valid.
- Negative values where physically possible or invalid as appropriate.
- Missing/null value.
- NaN and infinity.
- Source sentinel.
- Out-of-range input.
- Correct canonical unit and numeric precision.
- Exactly-once conversion.

### 11.2 Contract tests

Every adapter must pass the same canonical contract tests:
- Required top-level schema is present.
- Optional fields are null/available with a valid state, never silently omitted in an ambiguous way.
- Units and semantic definitions match the contract.
- Gear states normalize consistently.
- Time fields use milliseconds.
- Inputs use the agreed normalized scale.
- Wheel order is FL/FR/RL/RR.
- Dynamic sector count is preserved.
- Unknown enum values remain unknown.
- Unsupported channels are not populated with fabricated values.
- Source timestamps/freshness are retained.
- Derived values are labelled as derived.

### 11.3 Snapshot and integration tests

Test the entire path from native reader to adapter to canonical snapshot to bridge to Overview consumer. Decoder-only tests are insufficient where the host may fail to publish decoded metadata or may rename a field.

### 11.4 Runtime validation

For each simulator:
1. Capture a controlled session.
2. Compare source values with the canonical snapshot.
3. Verify conversion math independently.
4. Verify UI display against canonical snapshot.
5. Exercise session start/end, reconnect, pit entry/exit, lap transition and invalid-lap cases.
6. Record source version and capture evidence.
7. Mark each field's verification status.

## 12. Implementation sequence

Proceed in controlled phases.

| Phase | Work | Exit condition |
|---|---|---|
| 1 | Agree and freeze canonical telemetry schema | Field names, semantics, units and availability states reviewed |
| 2 | Define per-game conversion profiles | ACC, iRacing, AC and F1 profiles have explicit source mappings or documented gaps |
| 3 | Audit current adapters | Every current field mapped to canonical contract or marked unsupported/unverified |
| 4 | Align iRacing adapter | iRacing passes common contract and conversion tests |
| 5 | Verify AC and F1 source mappings | Native fields, units, versions and semantics supported by evidence |
| 6 | Integrate shared Overview contract | UI reads canonical fields without per-game mapping logic |
| 7 | Expand automated validation | Regression tests cover adapters, conversions and snapshot publication |

### 12.1 Incremental tile validation

When implementation begins, work tile by tile. For each tile:
1. Identify the exact canonical fields it consumes.
2. Verify ACC baseline behaviour and document any necessary correction.
3. Map iRacing source fields and conversions.
4. Validate with actual iRacing telemetry.
5. Repeat for AC and F1 only after their sources are verified.
6. Confirm unsupported/unavailable display behaviour.
7. Add tests before moving to the next tile.

Do not change multiple unrelated tiles in one implementation step. Preserve known-working ACC functionality throughout.

## 13. Prioritized audit checklist

### Contract and architecture
- [ ] Freeze canonical field names and meanings.
- [ ] Confirm canonical units and wheel ordering.
- [ ] Confirm availability and provenance representation.
- [ ] Define normalized gear and enum conventions.
- [ ] Define source freshness thresholds and timestamps.
- [ ] Define how profile versions are recorded.

### ACC
- [ ] Confirm ACC's litre-valued fuel display against the Physics decoder value; resolve the misleading `fuel_kg` field name without an unverified conversion.
- [ ] Align session remaining-time field name and unit.
- [ ] Publish Static metadata through a documented snapshot schema.
- [ ] Resolve live sector-time source/derivation.
- [ ] Resolve penalty-time unit and naming.
- [ ] Verify brake bias and Porsche 992 correction.
- [ ] Verify slip angle, wind and stint semantics.
- [ ] Verify tyre pressure, fuel, damage and brake-related channels.
- [ ] Validate enums and sentinels.
- [ ] Preserve out-lap and lap-validity behaviour.
- [ ] Replace fixed three-sector assumptions with dynamic sector count where appropriate.
- [ ] Validate gaps and multi-car coordinate association.

### iRacing
- [ ] Audit every current reader field against canonical units.
- [ ] Confirm SDK field units from authoritative SDK reference.
- [ ] Distinguish cold setup tyre pressure from live pressure.
- [ ] Verify tyre temperature channel semantics and averaging.
- [ ] Verify fuel quantity unit and capacity unit.
- [ ] Verify brake line pressure unit.
- [ ] Verify wind direction convention and speed unit.
- [ ] Verify session type and enum mappings.
- [ ] Verify F2 gap calculation sign and opponent association.
- [ ] Resolve sector availability test disagreement with source evidence.
- [ ] Ensure fuel-per-lap and estimated laps are marked derived.

### Assetto Corsa
- [ ] Identify the actual telemetry interface used.
- [ ] Inventory source fields for every Overview tile.
- [ ] Verify units, ranges, enums and update cadence.
- [ ] Mark unsupported fields explicitly.
- [ ] Capture and test real telemetry.

### F1 2026
- [ ] Identify the exact packet specification and version.
- [ ] Inventory source fields for every Overview tile.
- [ ] Verify units, scales, player-car indexing and packet cadence.
- [ ] Verify sentinels and enum mappings.
- [ ] Mark unsupported fields explicitly.
- [ ] Capture and test real telemetry.

## 14. Non-goals and safeguards

This specification does not:
- Authorize an immediate rewrite of the ACC acquisition pipeline.
- Certify any unverified ACC Graphics/Static ABI layout.
- Assert that AC or F1 exposes every ACC Overview channel.
- Require fake fallback values to keep every tile populated.
- Move hardware configuration into simulator adapters.
- Move game-specific telemetry conversion into React.
- Define the final implementation language or exact runtime serialization for every provenance field.
- Replace the ACC baseline mapping document.

Any proposed conversion that cannot be supported by a documented source unit or controlled runtime evidence must remain marked unverified. It must not be promoted to a production conversion merely to make the UI look complete.

## 15. Final architectural rule

**Each simulator speaks its own native telemetry protocol; each adapter translates that protocol into one stable, evidence-backed canonical contract; the shared Overview renders that contract without knowing which simulator produced it.**

ACC remains the baseline reference for the existing Overview. iRacing is the first non-ACC adapter to align. AC and F1 follow only after their source fields and conversions have been verified. All conversions, exceptions, derivations and unavailable channels remain explicit and testable.
