# ACC Race Engineer — Brake Strategy

**Status:** Design specification  
**Branch:** `feature/race-engineer-page`  
**Last updated:** 2026-11-13

## 1. Purpose

Brake Strategy monitors brake temperatures, brake pad condition, brake disc condition and braking behaviour during an ACC session. It provides concise, evidence-based observations, warnings and recommendations to help the driver maintain consistent braking performance and identify potential component concerns.

The strategy is advisory and strictly read-only. It must never change ACC setup, brake ducts, brake bias, brake compounds, controls or pit/MFD settings. The driver makes every decision and performs every action in ACC.

## 2. Core principles

- Use only telemetry actually exposed by ACC and validated by the project.
- Preserve raw values and their source metadata. Do not fabricate units, thresholds, component life, wear rates or diagnoses.
- Distinguish measured values, calculated trends and inferred concerns.
- Apply independent stream freshness checks before combining Physics, Graphics or Static observations.
- Do not diagnose mechanical failure from temperature or wear values alone.
- Use car-specific evidence and validated limits. Do not apply generic brake-temperature or minimum-thickness thresholds to every car.
- Suppress duplicate unchanged warnings; announce meaningful changes, escalation or resolution.
- Keep detailed driving-technique coaching with Performance Coach and Corner Coach. Brake Strategy provides race-level brake-system observations and actionable warnings.

## 3. Telemetry inputs and current readiness

All per-corner arrays use the ACC/project wheel order **FL, FR, RL, RR**, subject to retaining the decoder's documented mapping.

| Input | Source | Current status | Permitted use |
|---|---|---|---|
| Four brake temperatures | Physics `brake_temp_c[4]` | Available — user validated | Display, per-corner comparisons and trend tracking |
| Four brake pad-life values | Physics `pad_life[4]` | Available — user confirmed working; unit/scale interpretation based on ACC-specific reference | Preserve/display raw values; provisional mm interpretation; validate per car before life predictions |
| Four brake disc-life values | Physics `disc_life[4]` | Available — user confirmed working; unit/scale interpretation based on ACC-specific reference | Preserve/display raw values; provisional mm interpretation; validate per car before life predictions |
| Brake pedal input | Physics brake input | Available — validated | Context for braking-event analysis |
| Vehicle speed / deceleration | Physics speed and acceleration channels | Available; derived semantics require validation | Candidate braking-performance analysis |
| Wheel speeds / slip | Physics wheel-speed and slip channels | Candidate; controlled lock-up validation required | Do not issue lock-up diagnosis until validated |
| ABS intervention | Physics candidate fields | Requires validation | No ABS-specific warning until semantics are verified |
| Brake pressure | Physics `brake_pressure[4]` | Untrusted candidate in prior audit | Exclude from decisions until source offset/type concern is resolved |
| Brake compound | Physics front/rear compound fields | Untrusted candidate in prior audit | Do not map raw values to compound labels until validated |
| Dedicated brake fault / damage event | No trusted dedicated event identified | Unavailable | Do not claim a specific brake-system failure |

### 3.1 Pad and disc life units

ACC-specific shared-memory references describe the pad-life and disc-life arrays as remaining thickness in **millimetres (mm)**, with reference new-component values reported as approximately **29 mm for pads** and **32 mm for discs**. These are reference observations, not universal limits or guaranteed values for every car, component or configuration.

The user confirms that the values are working and displayed separately for all four wheels, but currently sees numeric values without an in-game unit label. Therefore:

- Retain the raw decoded numeric values unchanged.
- The specification may document **mm as the expected/reference unit**, but the implementation must retain an explicit unit-confidence/validation gate until the values are checked against a known car and controlled ACC state.
- Do not label the UI as mm with unconditional certainty until that check is complete. If shown before then, label as a provisional/reference interpretation or display the raw number without a unit.
- Do not assume 29 mm and 32 mm are universal new-component baselines.
- Do not infer remaining percentage, distance-to-replacement or safe minimum thickness from these reference values.

## 4. Functional responsibilities

### 4.1 Brake temperature monitoring

- Monitor all four brake temperatures independently.
- Show the latest fresh value and its timestamp/age.
- Track per-corner trends across representative laps and braking events.
- Compare left/right and front/rear temperatures.
- Identify sustained unusual temperature behaviour only against validated car-specific operating limits or a reliable per-session baseline.
- Distinguish a brief peak during heavy braking from a sustained thermal concern.

Do not classify a brake as too cold, optimal or overheating using generic universal thresholds. If a validated car-specific operating window is unavailable, report the measured temperature and trend without assigning an unsupported health category.

### 4.2 Pad condition monitoring

- Track all four pad-life raw values independently.
- Preserve corner identity and stream freshness.
- Once mm semantics are validated, compare remaining thickness across corners and across time.
- Detect meaningful changes and unusual per-corner differences.
- Calculate wear rate only after confirming value direction, scale, sampling behaviour and reset/replacement semantics.
- Do not estimate remaining laps, distance or race life until a validated wear-rate model and car-specific minimum service thickness are available.

### 4.3 Disc condition monitoring

- Track all four disc-life raw values independently.
- Preserve corner identity and stream freshness.
- Once mm semantics are validated, compare remaining thickness across corners and over time.
- Detect meaningful changes and unusual per-corner differences.
- Calculate wear rate only after confirming value direction, scale, sampling behaviour and reset/replacement semantics.
- Do not estimate remaining laps, distance or race life until a validated wear-rate model and car-specific minimum service thickness are available.

### 4.4 Braking behaviour analysis

Potential future analysis may correlate brake input, speed reduction/deceleration, wheel-speed behaviour and comparable corner/lap history to identify changes in braking behaviour.

This remains evidence-gated:
- Validate channel semantics, units, signs and wheel mapping first.
- Compare like-for-like braking zones and account for speed, gear, track conditions, traffic, fuel load and driver input.
- Treat lock-up and ABS activity as separate phenomena.
- Do not claim brake fade, mechanical failure or driver error from a single event or one telemetry channel.
- Do not duplicate corner-by-corner coaching from Performance Coach or Corner Coach.

### 4.5 Brake cooling observations

If sustained temperature trends and validated operating windows support it, the engineer may recommend that the driver/team review brake cooling. It must not claim a blocked duct or prescribe a specific duct setting without supporting evidence. The application must never change brake ducts or setup.

### 4.6 Pit-stop and race-finish assessment

Once pad/disc units, wear direction, wear rate and car-specific service limits are validated, the strategy may estimate whether a component is likely to remain within its validated service limit through the expected remaining race distance.

Until then, it may report observed values and trends only. It must not recommend replacement based on an invented remaining-life calculation.

## 5. Calculation and evidence rules

- Use only fresh, finite and semantically validated samples.
- Preserve raw values even when a derived interpretation is blocked.
- Compare each corner with its own history and appropriate axle/opposite-corner context.
- Use robust windows of representative valid laps/events; reject stale, incomplete or clearly non-comparable samples.
- Do not calculate a wear rate from a single pair of readings until resolution, update cadence and rounding behaviour are understood.
- Keep temperature peaks, sustained temperature and stint trends as distinct observations.
- A warning requires either a validated hard limit or repeatable evidence against a validated baseline.
- State uncertainty and missing inputs explicitly.

## 6. Radio and communication behaviour

Brake Strategy follows the Race Engineer's three global communication modes:

- **Driver-initiated:** remain quiet except critical validated warnings and explicit driver requests.
- **Balanced:** announce meaningful brake-temperature or component-condition changes and critical warnings; do not narrate routine stable readings.
- **Active race engineer:** provide more proactive race-level updates, while still suppressing repetitive unchanged messages.

Critical warnings are automatic in all modes, but only when a validated threshold or sufficiently strong evidence supports them. Deduplicate unresolved warnings; announce meaningful escalation, resolution or a materially changed recommendation once. Detailed values and per-corner reports are available on request when request handling is implemented.

Example messages below are illustrative only, not validated thresholds:
- "Front-left brake temperature is above its validated operating range. Monitor the next braking zones."
- "Rear-right pad thickness is reducing faster than the other corners. Trend is being monitored."
- "Brake temperatures are stable across all four corners."

## 7. UI requirements

The Brake Strategy view should:
- Present four-corner brake temperatures.
- Present four-corner pad and disc values separately.
- Show units only when validated; otherwise show raw values without a fabricated unit.
- Show source freshness/staleness and data-quality state.
- Distinguish measured values, calculated trends and inferred concerns.
- Show per-corner trends and comparisons only when sufficient history exists.
- Explain why an alert was raised and identify the supporting channels.
- Never display invented percentages, component health scores or remaining-life estimates.

## 8. Validation plan and release gates

### Gate A — raw values and mapping
1. Capture pad-life and disc-life values for FL, FR, RL and RR on a known car.
2. Confirm the decoder's wheel order against the ACC wheel/corner ordering.
3. Compare values with an authoritative ACC-specific definition or a controlled known-thickness/service state.
4. Confirm expected units, value direction and whether values represent remaining thickness.
5. Confirm whether new-component reference values vary by car or brake configuration.

### Gate B — lifecycle and wear behaviour
1. Record values over multiple representative laps.
2. Determine whether values change continuously, in steps or only at specific update intervals.
3. Check whether values decrease with wear and how rounding/resolution behaves.
4. Check behaviour after a pit stop and after any component replacement/service action available in ACC.
5. Establish car-specific minimum service limits from reliable documentation before any replacement warning.

### Gate C — temperatures
1. Compare all four brake-temperature channels with ACC displays under controlled braking.
2. Establish car-specific operating windows from reliable references.
3. Test cold, representative and sustained-heavy-braking conditions.
4. Verify that warnings distinguish short peaks from sustained conditions.

### Gate D — braking behaviour
1. Validate wheel-speed and slip semantics under controlled lock-up conditions.
2. Validate ABS intervention separately.
3. Compare repeatable braking zones across valid laps.
4. Check false positives from kerbs, bumps, low-speed manoeuvres, traffic and changing grip.

### Release criteria
- No stale or untrusted value can trigger a critical recommendation.
- Pad/disc units, mapping, value direction and service limits are verified before wear-rate or remaining-life predictions are enabled.
- Temperature thresholds are car-specific and evidence-backed.
- Every inference is clearly distinguished from direct measurement.
- No ACC/game control, setup, MFD or pit action is written or triggered by Race Engineer.
- Automated tests and Windows/live-ACC validation are completed before claiming implementation readiness.

## 9. Confirmed decisions and outstanding gates

### Confirmed
- Brake Strategy includes four-corner temperature monitoring.
- Brake pad life and brake disc life values are working and separately available for all four wheels, per user confirmation.
- The strategy will use the full evidence-based approach, but only within actual validated ACC telemetry.
- Pad/disc values are expected to represent thickness in mm according to ACC-specific shared-memory references; preserve raw values and retain a validation gate before derived calculations.
- The strategy remains strictly read-only and advisory.

### Outstanding
- Confirm pad/disc mm semantics and value direction in a controlled ACC test for the selected car.
- Confirm new-component baseline values and car-to-car variation.
- Establish minimum service thickness from reliable car-specific references.
- Validate wear-rate and replacement/reset behaviour.
- Establish car-specific brake-temperature operating ranges.
- Validate ABS, lock-up and brake-pressure channels before using them diagnostically.
- Validate braking-performance inference and false-positive controls.

