# ACC Overview Page — Design & Implementation Record

**Repository:** `AbhilashHalappa/Race-Engineer-ACC-New`  
**Branch:** `feature/overview-physics-consumer`  
**Document status:** Living design and implementation record  
**Scope:** ACC Overview page only. This document records agreed design, confirmed work, current limitations, and remaining work. It does not authorize changes to telemetry acquisition or proven race-engineering logic.

---

## 1. Purpose

The Overview page is the live driving dashboard for Assetto Corsa Competizione (ACC). It presents useful driving, vehicle, session, and track information in configurable tiles while keeping the display readable during driving.

The page must use real ACC telemetry wherever available. It must not fabricate values, silently substitute unrelated fields, or present unvalidated interpretations as facts.

## 2. Overall page design

### 2.1 Layout and navigation

- Desktop application with a React + TypeScript + Vite frontend hosted by the existing Python/Qt application.
- Compact, permanent, icon-only left navigation with tooltips; labels may expand when the navigation is expanded.
- Sticky top bar.
- Overview tiles use a 12-column configurable grid.
- Users can configure tile placement/layout rather than being locked to one fixed dashboard arrangement.
- Keep the interface compact and readable for live sim-racing use.
- Light and dark themes are supported, with a working theme switch.
- Use the established typography, elevated-card and button treatment, and spacing/shape system from the UI design decisions.
- Avoid browser-only assumptions: this is a standalone desktop application.

### 2.2 Tile behaviour

- Tiles are independently arranged within the configurable grid.
- Live values should update from the telemetry payload without unnecessary full-page redraws.
- Missing or unsupported values must be shown as unavailable/neutral, not as plausible-looking fabricated values.
- Temperature and status glows must communicate state without obscuring the numeric value.
- Keep high-detail historical analysis out of the live Overview where it belongs in Performance Hub.

## 3. Overview content and telemetry

The following records work that has been discussed or implemented. A listed tile or field is not a claim that every sub-field is fully validated; see the status notes.

### 3.1 Driving inputs and vehicle dynamics

- Speed.
- Gear.
- RPM and maximum RPM.
- Throttle and brake input.
- Steering angle in degrees.
- Steering-angle progress indicator: zero is centred; negative steering fills toward the left and positive steering fills toward the right.
- Pedal values are sourced from ACC telemetry, not inferred from the physical pedal hardware.
- Handbrake value is sourced from ACC telemetry where exposed.

### 3.2 RPM and shift indication

- RPM display uses a colour gradient.
- Shift indication includes a glow effect.
- RPM LED tile is retained; the previous Motor Temperature tile was removed.
- RPM LED hardware integration is separate from the live vehicle telemetry display.

### 3.3 Lap and session status

- Current lap information and lap timing.
- Lap-time tile status treatment:
  - Valid lap: green.
  - Invalid lap: red.
  - Out lap: orange.
- Out-lap tile shows the out-lap state without displaying a lap time as if it were a timed lap.
- Out-lap classification has been tested for initial out-lap detection, transition to a timed lap, pit entry/exit within a timed lap, and lap counting.
- Out-lap records are retained for debugging but are not to appear in Lap History or Session Summary.
- A direct menu jump from the middle of a lap to the garage/pits and rejoin is a known non-goal for the current implementation; this edge case is not currently classified as an out lap.

### 3.4 Track, weather, fuel and session context

- Track map tile.
- Weather information.
- Fuel information.
- Session/lap history-related overview information where supported.
- Keep the live map lightweight. Do not rewrite or rebuild the map on every lap unnecessarily.
- Detailed historical/replay analysis remains in Performance Hub rather than being duplicated in Overview.

### 3.5 Tyres and brakes

- Individual tyre and brake corner boxes are arranged FL/FR on the top row and RL/RR on the bottom row.
- Temperature colour progression: blue → green → yellow → orange → red.
- Glow intensity is configurable.
- Tyre pressure is read from ACC Physics and shown per wheel in PSI.
- Brake pressure is read from ACC Physics and has been confirmed by the user.
- Tyre temperature and brake temperature must be shown in the correct locations and not duplicated in unrelated tiles.

### 3.6 Target tyre pressure tile

**Current implementation:** The tile displays actual live tyre pressure from ACC Physics for FL, FR, RL and RR.

**Not implemented yet:** User-configurable target PSI values and target comparison.

Agreed design for the next implementation:

- Editable target PSI for Front Left.
- Editable target PSI for Front Right.
- Editable target PSI for Rear Left.
- Editable target PSI for Rear Right.
- Display actual PSI, configured target PSI, and actual-minus-target difference for each wheel.
- Save the configured values persistently across application restarts.
- Provide a clear way to edit the values from the Overview tile or its settings.
- Label these as **configured target pressures**. Do not call them ACC MFD values unless a verified ACC data source actually provides the MFD setting.
- Do not invent a target value or display a false comparison when no target has been configured.

### 3.7 Vehicle damage

- Vehicle damage array is displayed as five separately labelled values:
  - Front
  - Rear
  - Left
  - Right
  - Centre
- Suspension damage remains displayed separately by wheel: FL, FR, RL and RR.
- The five-value car-damage array is shown in ACC's array order. Values are raw telemetry values; do not append a percentage sign or imply a percentage scale unless the scale is verified.
- Water temperature must not be duplicated in Vehicle Damage.

### 3.8 Car lights and status

The Car Lights & Status area should include:

- Rain light.
- Wiper.
- Left indicator.
- Right indicator.
- Other supported light/status indicators already present in the tile.

Remove from this tile:

- Air temperature.
- Road temperature.

Water temperature should appear only once in the Overview, not as a duplicate in Vehicle Damage and Car Lights & Status.

**Expected status-colour behaviour:**

| State | Expected colour |
|---|---|
| ON | Green |
| OFF | Yellow |
| Unknown / unavailable | Neutral |

**Known issue:** The user reports that this ON/OFF/unknown colour behaviour is not working. Do not treat it as complete. Inspect the actual ACC payload values and frontend status interpretation for each indicator before changing the colour logic. Handle booleans, numeric values, enums/bit fields, null and missing fields explicitly. Do not assume every ACC status is represented by a simple boolean.

### 3.9 Electronics and race-control status

- Electronics status changes were designed to produce a green pulse for one second.
- Race-control status glow should follow the relevant flag colour.
- Only apply these effects when the underlying status is valid and understood.

## 4. Configurable settings

The following configuration options have been agreed for the Overview experience.

### 4.1 Temperature thresholds

Provide editable threshold values for the colour transitions.

| Setting | Agreed starting values |
|---|---|
| Tyre temperature thresholds | 70 / 90 / 100 / 110 °C |
| Brake temperature thresholds | 250 / 400 / 500 / 600 °C |

These are starting/configuration values, not verified Porsche factory limits or universal ACC car limits. Thresholds should be configurable for the selected car/profile.

### 4.2 Damage thresholds

- Provide editable damage severity thresholds.
- Agreed starting values: 20 / 40 / 70.
- The telemetry damage scale and units must be verified before displaying these as percentages or assigning absolute physical meaning.
- Do not assume the five car-damage values are percentages.

### 4.3 Glow intensity

- Configurable glow intensity.
- Agreed initial test/default value: 65%.
- The setting should affect the relevant temperature/status glow presentation consistently.

### 4.4 Target tyre pressure

Four independent values, one for each wheel:

| Setting | Unit |
|---|---|
| Front-left target pressure | PSI |
| Front-right target pressure | PSI |
| Rear-left target pressure | PSI |
| Rear-right target pressure | PSI |

These are user-entered target values, not automatically sourced MFD values unless proven otherwise.

### 4.5 Car-specific configuration

- Porsche 992 GT3 R is the initial car/profile used for configuration and testing.
- Temperature and damage thresholds should be configurable rather than hardcoded as universal values.
- A complete multi-car profile-management system has not yet been finalised. Do not claim it is implemented.
- Do not apply Porsche-specific corrections or thresholds to other cars without evidence.

### 4.6 Lap status colours

The agreed default presentation is valid = green, invalid = red, out lap = orange. These are agreed display behaviours. Treat them as configurable only if/when an explicit colour-setting control is implemented; do not claim such controls exist merely because the colours are agreed.

### 4.7 Persistence and reset

- Configuration should persist across application restarts.
- Provide a reset-to-defaults action if the settings UI supports it.
- Verify persistence and reset behaviour in the application before marking them complete.

## 5. ACC data and implementation constraints

- ACC Physics data is decoded in the acquisition/consumer pipeline and delivered to the frontend through the desktop bridge.
- The frontend must consume the published telemetry snapshot; it must not open ACC shared memory or independently decode packets.
- Preserve the existing high-frequency Physics SPSC ring single-consumer architecture. Do not add another reader to the same SPSC ring; use an intentional fan-out if another consumer is required.
- The bridge is responsible for publishing snapshots/SSE, not telemetry decoding.
- ACC wheel order is FL, FR, RL, RR.
- Live tyre pressure values are available from the Physics payload and are currently displayed by the target-pressure tile.
- Steering angle is available and has been confirmed working.
- Brake pressure has been confirmed passed.
- Do not label Physics TC/ABS slip-ratio threshold fields as driver TC/ABS setup levels.
- Do not display unsupported TC/ABS intervention flags as genuine ON/OFF states.
- Brake bias is currently unresolved; see issue #13 below.

## 6. Known issues and pending work

| Item | Status | Notes |
|---|---|---|
| Vehicle-light ON/OFF colours | Not working / investigate | Expected ON green, OFF yellow, unknown neutral. Validate source values and each indicator's mapping. |
| Target PSI inputs | Not implemented | Add four editable wheel-specific values, persistence and actual-vs-target difference. |
| Brake bias | Open issue #13 | Dashboard value does not match ACC. Remove speculative correction and verify field offset/type/units and car identity before fixing. |
| TC setup level | Not validated | Do not substitute Physics slip threshold. |
| ABS setup level | Not validated | Do not substitute Physics slip threshold. |
| TC intervention | Not validated | Find a supported source before presenting a live state. |
| ABS intervention | Not validated | Find a supported source before presenting a live state. |
| Car-specific profiles | Partial design | Porsche 992 GT3 R is the starting profile; full profile management remains future work. |
| Damage scale/units | Needs validation | Preserve raw values unless scale is verified. |
| Out-lap menu-to-garage edge case | Known limitation | Direct mid-lap menu jump/rejoin is not currently marked as an out lap. |

### Brake-bias issue reference

GitHub issue: [#13 — Investigate ACC brake-bias value mismatch](https://github.com/AbhilashHalappa/Race-Engineer-ACC-New/issues/13)

The dashboard previously showed values around 79.4% / 81.0% while ACC displayed 58.4% / 60.0%. A speculative Porsche 992 offset was attempted and did not resolve the mismatch. The issue is intentionally deferred; do not add another guessed offset.

## 7. Validation and acceptance criteria

A change to Overview is not complete merely because it compiles.

- Confirm each displayed value against ACC or a trusted source.
- Test each wheel independently (FL, FR, RL, RR).
- Verify units and wheel ordering.
- Verify valid, invalid and out-lap visual states.
- Verify missing/unavailable data uses a neutral or unavailable presentation.
- Verify vehicle-light states independently for each light.
- Verify all configurable settings can be changed and are retained after restart.
- Verify target PSI comparison uses only user-configured targets and live actual pressure.
- Verify no duplicate water-temperature display remains.
- Verify Overview remains responsive and does not cause unnecessary map redraws.
- Run the relevant frontend build and focused Python tests after implementation; record actual results rather than assuming success.

## 8. Change log

### ACC Overview — current documented state

- Configurable tile layout on a 12-column grid.
- Light/dark theme switch.
- Compact permanent icon navigation and sticky top bar.
- Live speed, gear, RPM, throttle, brake and steering data.
- Steering angle displayed in degrees with a centred left/right progress bar.
- RPM gradient and shift glow; RPM LED tile retained, Motor Temperature tile removed.
- Lap tile valid/invalid/out-lap colour behaviour.
- Track map, weather and fuel context.
- Per-corner tyre/brake display and temperature colour progression.
- Live tyre pressure from ACC Physics shown as actual PSI.
- Target-pressure tile currently lacks editable target values and comparison.
- Vehicle damage shown as Front/Rear/Left/Right/Centre, with suspension damage separately by wheel.
- Car Lights & Status includes rain light, wiper and left/right indicators; air and road temperature removed.
- Water temperature duplicate removed from Vehicle Damage and should appear only once.
- Vehicle-light colour mapping remains broken and requires investigation.
- Brake-bias mismatch recorded in issue #13.

---

**Maintenance rule:** Update this document whenever an Overview feature is implemented, changed, tested, deferred, or found to be unsupported. Keep the distinction between *agreed*, *implemented*, *user-tested*, and *pending validation* explicit.
