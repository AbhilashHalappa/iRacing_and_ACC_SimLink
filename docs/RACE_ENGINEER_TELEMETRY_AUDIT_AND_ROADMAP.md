# ACC Race Engineer — Telemetry Audit and Development Roadmap

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/race-engineer-page  
**Audit baseline:** branch head b180a3094f78d26fa12a9417e2f1e97e3b8a2a17  
**Document status:** Cross-strategy telemetry audit and implementation roadmap; individual strategy requirements are maintained in dedicated strategy documents  
**Implementation status:** Snapshot aggregator, initial Fuel Engineer observation slice, service integration and initial UI are committed. Fuel strategy calculations, radio/TTS integration, automated regression execution and Windows/live-ACC strategy validation remain pending.

## 1. Purpose and audit method

This document maps the agreed Race Engineer requirements to the ACC telemetry and application infrastructure that currently exists in the repository.

The audit uses:
- Current source on feature/race-engineer-page.
- Existing ACC Physics, Graphics and Static field-coverage audits.
- Existing target-PC raw recording and controlled-transition evidence documented in those audits.
- Current decoders, consumers and acquisition supervisor.
- Existing automated tests and documented validation gaps.

This is an implementation-readiness audit, not a claim that every candidate shared-memory field is officially ABI-certified or semantically validated. Existing documentation sometimes records raw field observations that are not yet safe for engineering decisions. Those distinctions are retained below.

### Status definitions

| Status | Meaning |
|---|---|
| **Available — validated** | Field is decoded and its relevant live behaviour has been correlated with a controlled action or repeatable state. |
| **Available — candidate** | A decoded value or plausible live signal exists, but units, semantics, enum mapping, sign or HUD equivalence are not fully confirmed. |
| **Calculated — feasible** | Can be calculated from available inputs, subject to validation of those inputs and the calculation. |
| **Inferred — requires evidence** | A diagnosis can potentially be inferred from multiple signals and a baseline; it is not a directly measured ACC field. |
| **Unavailable / not exposed** | No trustworthy source currently exists in the audited implementation. |
| **Live test required** | Source code exists, but the required end-to-end behaviour has not yet been confirmed in the user's running ACC session. |

## 2. Current telemetry architecture

The repository already has a useful read-only acquisition foundation:

- Independent ACC Physics, Graphics and Static acquisition streams.
- Separate bounded queues/rings and downstream consumers; decoding is kept off the high-frequency acquisition path.
- Physics raw page: 800 bytes. Its layout is strongly corroborated and target-PC acquisition/recording validation is closed for the current scope, but official Kunos Shared Memory 1.9 ABI confirmation is unavailable.
- Graphics raw mapping: 4,096 bytes copied per sample. The current candidate structure is 1,588 bytes and 86 of 87 candidate members are decoded. Its field-coverage evidence is extensive, but the candidate layout is not officially Kunos ABI-certified.
- Static candidate decoder: 820-byte Variant B, strongly favoured by target-PC evidence for the observed ACC 1.9 page. It is startup/session metadata, not a high-frequency stream of live vehicle telemetry.
- Physics and Graphics consumers retain the latest good decoded sample and expose consumer health/error information.
- The acquisition supervisor manages independent stream lifecycle and read-only mapping cleanup.
- The Qt host/bridge transports Physics and Graphics snapshots. The bridge is transport, not an analysis or decision engine.

**Important integration boundary:** Physics, Graphics and Static are independent streams. The current architecture does not provide a fully synchronized, timestamp-aligned multi-stream engineering snapshot. The Race Engineer must check freshness and packet/capture timestamps before combining values. It must not assume that the latest Physics and Graphics samples represent the exact same instant.

**Read-only rule:** Race Engineer may observe ACC shared memory and application-owned telemetry only. It must never write to ACC shared memory, send game-control inputs, alter setup, operate the MFD, trigger pit actions, change fuel/tyres, or control the car. All recommendations are advisory; the driver performs any action manually in ACC.

## 3. Requirement-by-requirement telemetry audit

### 3.1 Live race monitoring

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Current speed, throttle, brake, gear, RPM, steering | Physics decoder | **Available — validated** | Suitable for live monitoring. |
| Lap time, last lap, best lap, split/delta | Graphics decoder | **Available — candidate / integrated** | Fields are decoded and Overview consumes them. Preserve existing time-format and validity semantics; validate remaining HUD comparisons where documented. |
| Sector and sector timing | Graphics decoder | **Available — candidate** | Sector transitions correlate with recorded transitions. Some numeric timing semantics still need HUD correlation. |
| Lap validity | Graphics is_valid_lap | **Available — validated** | Existing audit records live track-limit/validity transition evidence. Do not substitute global_green or other flags. |
| Completed lap count | Graphics completed_laps | **Available — validated** | Use completed_laps, not number_of_laps, as completed laps. |
| Race lap limit / laps remaining | Graphics number_of_laps candidate | **Available — candidate** | Field exists, but semantics and live race-limit behaviour must be confirmed before calculating race laps remaining. Do not assume it is a completed-lap count. |
| Session time remaining | Graphics session_time_left_s | **Available — validated for display** | Existing Overview countdown conversion was tested by the user against ACC. Check stream freshness and session state before announcing. |
| Position and active-car count | Graphics position and active_cars | **Available — candidate** | Decoded. Multi-car and position-transition scenarios should be validated before strategic use. |
| Gap ahead / behind | Graphics gap_ahead_ms / gap_behind_ms | **Available — candidate** | Milliseconds-to-seconds presentation was implemented; sign convention remains unqualified. Preserve raw sign and do not infer closing direction until validated. |
| Traffic / nearby cars | Graphics car IDs, coordinates and normalized position | **Available — candidate** | Coordinates and player association are decoded. Multi-car ID/coordinate population and coordinate frame need a targeted live test. Do not claim proximity or overlap until validated. |
| Track limits / warnings | Graphics lap validity, flag, penalty and global flag fields | **Mixed: validated + candidate** | Lap validity is trusted. Race-control integer codes remain raw where enum meanings are unresolved. |
| Session type / state | Graphics status, session and track-status candidates | **Available — candidate** | Decode exists; confirm state transitions and raw-code mapping before deriving race phase. |
| Weather / track conditions | Graphics rain intensity, forecasts, track grip code, wind; Physics air/road temperature | **Mixed: available candidate** | Rain enum and track-grip presentation mappings are documented. Wind direction convention still needs live comparison. Physics air/road temperature isolated validation remains pending. |
| Completed-lap announcement | Lap completion transition from Graphics | **Calculated — feasible** | Announce once per newly completed lap, only after a stable transition and valid timing data. |
| Pace change / personal best | Lap times and stored session history | **Calculated — feasible** | Compare completed valid laps against best/recent baseline. Do not treat an invalid lap as pace evidence. |
| Position change / gap trend | Position and gap history | **Calculated — feasible** | Requires validated update timing and gap sign convention. |

### 3.2 Fuel strategy

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Current fuel | Physics fuel_kg (legacy internal field name) | **Available — validated unit: litres (L)** | User confirmed in ACC that fuel values are displayed in litres. Preserve the decoded numeric value exactly; interpret and display it as litres. The internal `fuel_kg` name is misleading and must not be used as the UI unit. |
| Fuel per lap | Graphics fuel_per_lap_l | **Available — validated against ACC** | User confirmed 3.66 L/lap matches ACC's in-game display. Keep freshness and finite-value checks; this confirms the observed display, not every car/condition. |
| Estimated laps remaining | Graphics fuel_estimated_laps | **Available — validated against ACC** | User confirmed 16.5 laps matches ACC's in-game display. Keep freshness and finite-value checks; recheck after refuelling and across relevant session states. |
| MFD fuel-to-add | Graphics mfd_fuel_to_add | **Available — validated (L)** | User confirmed the live ACC MFD value, including an observed example of **10.0 L**. Present as read-only information; never operate the MFD. |
| Fuel used | Graphics used_fuel_l | **Available — validated observation (L)** | User confirmed the live value is working in ACC. Expose it as an observation only; do not use it for projections until its accumulation/reset semantics are documented. |
| Maximum tank capacity | Static max_fuel | **Available — candidate** | Static Variant B decoder exposes the field; verify against car and ACC before using as a hard limit. |
| Fuel required to finish | Current fuel + validated consumption + race distance/time remaining | **Calculated — feasible** | Depends on validated current-fuel units, per-lap consumption and race-distance estimate. |
| Fuel shortfall / surplus | Required fuel minus current fuel and reserve | **Calculated — feasible** | Use uncertainty bounds and show the assumptions. |
| Fuel-saving target | Shortfall divided by remaining laps, constrained by a realistic per-lap target | **Calculated — feasible** | Advisory only. Recalculate as consumption changes and announce when saving is no longer required. |
| Estimated savings from fuel saving | Target saving per lap multiplied by remaining laps | **Calculated — feasible** | Label as an estimate, not guaranteed savings. |
| Pit-stop refuelling recommendation | Fuel shortfall, MFD fuel-to-add and pit strategy | **Calculated — feasible** | Recommendation only. Never write to the MFD or initiate a stop. |
| Safety fuel reserve | User requirement selected; reserve amount not yet decided | **Decision required** | Do not invent a reserve value. Make it configurable after the baseline fuel model is validated. |

**Fuel release gate:** current fuel is confirmed in litres (L), and the user has now confirmed that Graphics fuel-per-lap (3.66 L/lap) and estimated laps remaining (16.5 laps) match ACC's in-game values. The fuel-observation builder now treats both Graphics semantics as validated by default while still requiring fresh, finite, non-negative samples. Finish-fuel, shortfall/surplus and saving projections remain gated until a safety reserve is configured and the remaining-race-distance inputs are validated.

### 3.3 Tyre monitoring

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Four tyre pressures | Physics tyre_pressure_psi[FL, FR, RL, RR] | **Available — validated** | Four live channels validated. Confirm cold/hot timing and units during setup/drive tests before pressure advice. |
| Four tyre core temperatures | Physics tyre_core_temp_c[FL, FR, RL, RR] | **Available — validated** | Four live channels validated. |
| Inner / middle / outer temperatures | Legacy Physics arrays are unused/zero; offset 696 is a duplicate alias of core temperatures | **Unavailable as independent channels** | Do not display or infer I/M/O gradients from these arrays. |
| Tyre wear | Legacy tyre_wear field is marked unused/deprecated | **Unavailable** | No trustworthy direct wear channel in current decoder. |
| Tyre degradation | Lap pace, pressure, temperature and stint history | **Inferred — requires evidence** | Can be estimated over a stint, but must be labelled inferred and separated from direct wear measurement. |
| Pressure change over stint | Four pressure samples over time | **Calculated — feasible** | Track per-corner trends with freshness checks and pit/service reset handling. |
| Front/rear and left/right comparisons | Four validated pressure and core-temperature channels | **Calculated — feasible** | Comparisons are supported; avoid diagnosing setup cause from one reading. |
| In-stint tyre advice | Pressure/temp trend plus pace and driver context | **Inferred — requires evidence** | Begin with conservative trend alerts, not setup prescriptions. |
| Next-stint cold pressure recommendation | Stint pressure history and target operating window | **Needs target model / decision** | No universal target should be hard-coded. Target windows must be car/tyre/condition-aware and evidence-backed. |
| Current tyre set / compound | Graphics tyre compound and tyre-set identifiers | **Available — candidate** | Raw IDs are decoded; do not invent labels for unresolved codes. |
| MFD target pressures | Graphics mfd_tyre_pressures | **Available — candidate** | These are MFD pressure requests, not measured tyre pressures. Label distinctly. |

### 3.4 Brake monitoring

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Four brake temperatures | Physics brake_temp_c[FL, FR, RL, RR] | **Available — validated** | Four live channels validated. Observed ranges are not calibrated operating limits. |
| Brake temperature comparison | Four brake-temperature channels | **Calculated — feasible** | Left/right and front/rear comparisons are possible. |
| Brake overheating warning | Brake temperature plus validated car-specific operating limits | **Needs thresholds** | Do not use generic thresholds. Establish car/compound-specific evidence first. |
| Pad life | Physics pad_life[4] | **Available — candidate / unreliable** | Recent capture showed implausible rear values; units, direction and corner mapping are unresolved. Do not show as percentage or use for warnings. |
| Disc life | Physics disc_life[4] | **Available — candidate / unreliable** | Numeric variation observed, but units, direction and service semantics are unresolved. |
| Brake pressure | Physics brake_pressure[4] | **Untrusted candidate** | Recent capture showed suspicious overlap with tyre-temperature statistics. Keep out of diagnosis until raw-offset/type issue is resolved. |
| Brake compound | Physics front/rear brake compound | **Untrusted candidate** | Implausible values in a recent capture; do not map to compound labels yet. |
| Braking performance degradation | Brake temperatures, deceleration, speed, pedal input and lap baseline | **Inferred — requires evidence** | Requires repeated evidence and track/corner context. Distinguish measured temperature from inferred performance loss. |

### 3.5 Car condition and damage

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Collision detection | No dedicated trusted collision event currently identified | **Inferred — requires evidence** | A sudden damage change or acceleration discontinuity may be a clue, not proof of collision. |
| Body / general car damage | Physics car_damage[5] | **Available — validated as changing damage channels** | A controlled pit repair returned damage to zero. Individual component meanings/scales are not yet fully mapped; do not label a specific panel/component without evidence. |
| Suspension damage | Physics suspension_damage[4] candidate | **Available — candidate** | Two components varied in target capture, but semantics and corner mapping remain unvalidated. |
| Steering-related faults | Steering angle, yaw/heading, velocity and damage context | **Inferred — requires evidence** | No direct steering-fault flag identified. |
| Engine damage | No separately trusted engine-damage field identified | **Unavailable as a direct diagnosis** | Do not claim engine damage from water temperature, RPM or generic damage channels. |
| Engine condition / faults | Engine state flags and temperature candidates | **Available — candidate / incomplete** | Engine flags need full transition validation; water temperature and several tail fields are unresolved. |
| Other ACC vehicle faults | No complete trusted fault inventory identified | **Unavailable / needs targeted audit** | Only report faults explicitly exposed and validated by ACC telemetry. |
| Handling / pace effect | Damage plus vehicle dynamics and lap baseline | **Inferred — requires evidence** | Recommend inspection only when multiple signals support a meaningful concern. |

### 3.6 Vehicle performance diagnosis

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Throttle / brake / steering / speed | Physics | **Available — validated** | Core inputs for diagnosis. |
| Acceleration G and velocity | Physics | **Available — observed / candidate** | Live variation documented; axis/sign conventions should be verified for each calculation. |
| Wheel slip / slip ratio / slip angle | Physics arrays | **Available — candidate** | Values vary, but controlled wheel-slip and cornering correlations remain incomplete. |
| Suspension travel | Physics | **Available — validated as varying channels** | Units and per-corner mapping should be checked before thresholds. |
| Understeer / oversteer | Steering, yaw/heading, lateral acceleration, speed and corner context | **Inferred — requires evidence** | No direct understeer/oversteer flag. Require repeatable evidence and baseline comparison. |
| Traction loss / wheelspin | Wheel speed, slip ratio, throttle, speed and gear | **Calculated / inferred — feasible** | Validate thresholds and distinguish wheelspin from kerbs, bumps and low-speed manoeuvres. |
| Lock-up | Wheel speed/slip, brake input and vehicle speed | **Calculated / inferred — feasible** | Validate wheel-speed model and avoid false positives during low-speed/kerb events. |
| Poor acceleration | Speed, throttle, gear, RPM and lap/corner baseline | **Inferred — requires evidence** | Account for gear, traction, gradient, traffic and setup differences. |
| Unusual braking | Brake input, deceleration, speed and corner baseline | **Inferred — requires evidence** | Require repeated comparable events. |
| Balance change during stint | Dynamics and lap history | **Inferred — requires evidence** | Compare like-for-like corners and conditions; do not attribute cause prematurely. |
| Cause attribution | Multiple validated channels and evidence history | **Not approved without evidence** | Say what changed and what may explain it; do not assert driver or car fault from one signal. |

**Separation rule:** Race Engineer provides concise race-level observations and actionable alerts. Detailed driving-technique coaching remains with Performance Coach and Corner Coach; do not duplicate their corner-by-corner coaching.
### 3.7 Race strategy

| Requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Fuel strategy | Fuel inputs and calculations above | **Calculated — feasible after fuel gate** | Implement after fuel units and projections are validated. |
| Pit timing | Fuel, tyre state, race time, gaps and mandatory-stop state | **Calculated — feasible with constraints** | Must account for race rules and uncertainty; no unverified mandatory-stop assumptions. |
| Tyre-change recommendation | Tyre trend, weather, stint and race context | **Inferred — requires evidence** | Advisory only; tyre wear is not directly available. |
| Mandatory pit monitoring | Graphics mandatory_pit_done and missing_mandatory_pits candidates; Static pit-window candidates | **Available — candidate** | Validate event semantics and pit-window units before issuing rule-critical warnings. |
| Penalty monitoring | Graphics penalty code/time | **Mixed: time presentation validated, code mapping candidate** | User has validated displayed penalty time conversion. Raw penalty code meanings remain conservative. |
| Safety-car strategy | Race-control flags/session state | **Needs validation** | Do not claim safety-car status unless a specific ACC field/state is validated. |
| Weather strategy | Rain and forecast fields | **Available — candidate** | Forecast values can inform advice after enum/state checks; never predict beyond ACC's exposed forecast. |
| Push / conserve advice | Pace, fuel, gaps, tyre state and race phase | **Calculated / inferred — feasible** | Explain the reason and confidence. |
| Position / gap strategy | Position and gap fields | **Needs sign and timing validation** | Preserve raw sign; avoid overtake/defend recommendations until gap direction and update cadence are confirmed. |
| Race rules | Static/session metadata and live race-control state | **Incomplete** | No rule is assumed mandatory unless ACC explicitly exposes validated evidence. |

### 3.8 Setup recommendations

| Setting / requirement | Current source / evidence | Status | Audit decision |
|---|---|---|---|
| Brake bias | Physics brake_bias candidate | **Available — candidate / known mismatch** | Existing brake-bias mismatch remains open. Do not base recommendations on it until source/display correlation is resolved. |
| Tyre pressures | Physics measured pressures and Graphics MFD requested pressures | **Available — mixed** | Measured values are available; target-pressure recommendation model remains to be defined. |
| TC | Graphics tc_level | **Available — candidate / integrated** | Live changes observed; raw level is displayed. Recommendation logic still needs car/condition evidence. |
| ABS | Graphics abs_level | **Available — candidate / integrated** | Live changes observed; raw level is displayed. Recommendation logic still needs car/condition evidence. |
| TC cut / engine map | Graphics raw setting fields | **Available — candidate** | Decoded; preserve raw values where mapping is unresolved. |
| Aero balance | No trustworthy live setup field identified in current decoded set | **Unavailable** | Do not generate numeric aero recommendations. |
| Suspension setup | No complete trusted live setup field set identified | **Unavailable** | Suspension travel/damage are not setup values. Do not confuse telemetry with adjustable setup. |
| Before/after comparison | Setup snapshots plus lap/dynamics history | **Calculated — feasible after setup capture exists** | No automatic setup changes. Compare only manually recorded or otherwise verified setup states. |
| Automatic application of settings | Explicitly prohibited | **Not permitted** | Engineer may explain and recommend; driver changes every setting manually in ACC. |

### 3.9 Radio, interaction and data reliability

| Requirement | Current state | Status | Audit decision |
|---|---|---|---|
| Three communication modes | Design agreed; no Race Engineer mode engine yet | **Not implemented** | Driver-initiated, Balanced and Active modes must all be supported and switchable during a session. |
| Critical warnings in every mode | Design agreed | **Not implemented** | Safety-critical warnings bypass routine mode suppression, subject to validation and anti-repeat rules. |
| Active mode every completed lap | Design agreed | **Not implemented** | One short announcement per completed lap, including lap number and time when valid. |
| Balanced meaningful changes only | Design agreed | **Not implemented** | Avoid routine every-lap chatter. |
| Driver-initiated quiet mode | Design agreed | **Not implemented** | Keyboard hold-to-talk trigger selected. |
| Hold-to-talk request capture | Key interaction selected; speech recognition not selected for this phase | **Decision incomplete** | A key can trigger a request, but the actual request input is not yet defined. Do not silently assume microphone recognition or invent a menu of fixed requests. Resolve before implementing conversational queries. |
| Existing TTS | Windows TTS backend already exists in the app | **Available infrastructure — integration required** | Reuse existing TTS; do not introduce a second speech stack without reason. |
| Short messages / detailed explanations on request | Design agreed | **Not implemented** | Keep radio queue concise; detailed status is on demand. |
| Repeat last message / mute non-critical radio | Design agreed | **Not implemented** | Mute must not suppress critical safety warnings. |
| Avoid repeated unresolved warnings | Design agreed | **Not implemented** | Track active issue identity, severity, last announcement and resolution state. |
| Measured vs calculated vs inferred labels | Design agreed | **Not implemented** | Every engineering statement must carry an evidence class internally and expose uncertainty clearly. |
| Data freshness / stream health | Acquisition and consumer health exist | **Available infrastructure** | Race Engineer must gate analysis on lifecycle state, sample age, decode errors and stream mismatch. |
| No F1 assumptions | Non-negotiable project requirement | **Design rule** | ACC-only fields, rules, units and session semantics. |

## 4. Key audit findings and implementation blockers

1. **The telemetry foundation is substantial.** Physics and Graphics are acquired independently, with downstream decoders and latest-good-sample consumers. The Race Engineer does not need a new shared-memory reader.
2. **Graphics is the primary race/session source.** It supplies lap/session timing, validity, position, gaps, weather/race-control candidates, pit state, fuel estimates and MFD values.
3. **Physics is the primary vehicle-state source.** It supplies pedal inputs, speed, steering, RPM, gear, tyre pressures/core temperatures, brake temperatures, damage channels and vehicle-dynamics candidates.
4. **Static is metadata, not a live strategy feed.** Car, track, max fuel/RPM and selected session/aid metadata may be useful, but unresolved pit-window fields must remain raw-only.
5. **The two live streams are not a synchronized snapshot.** Build a freshness-aware aggregation layer; never assume latest Physics and Graphics samples are simultaneous.
6. **Tyre I/M/O temperatures and direct tyre wear are not available as trusted channels.** Do not promise those features.
7. **Brake temperatures are usable; pad/disc life, brake pressure, brake compounds and several engine-tail fields are not yet trustworthy.**
8. **Damage channels are real, but component labels/scales are incomplete.** Avoid claiming body, suspension or engine-specific damage without mapping evidence.
9. **Race-control enums and gap sign convention need care.** Preserve raw values and do not guess meaning.
10. **Fuel strategy remains gated, but current-fuel units are confirmed.** Current fuel is retained exactly as ACC provides it and interpreted/displayed in litres (L). Fuel per lap and estimated laps remain candidate Graphics values until compared with ACC; no finish-fuel or saving target is enabled yet.
11. **Setup recommendation scope must be restricted to supported settings.** Aero and suspension setup recommendations are not currently supported by the audited telemetry.
12. **The driver-initiated interaction is not fully specified.** Hold-to-talk key is agreed, but the mechanism for entering the request remains open.
13. **No game control is ever permitted.** This applies to every stage, including setup, MFD, pits and strategy.

## 5. Development roadmap

The stages below are ordered by dependency and risk. A stage is not complete merely because code exists; its acceptance gate must pass.

### Stage 0 — Audit and requirements closure

**Status:** Foundation-readiness audit documented. User confirmed current-fuel units as litres (L); remaining fuel telemetry semantics and reserve policy remain visible and gated.

Tasks:
- Maintain this field-to-feature matrix as the source of truth.
- Preserve current fuel as the raw ACC-provided value; defer unit/HUD confirmation until the user performs a later controlled check. Keep unit-dependent fuel calculations disabled.
- Confirm Graphics fuel estimates against ACC before enabling fuel strategy.
- Confirm gap sign and update behaviour.
- Validate multi-car coordinate/ID mapping before traffic advice.
- Resolve the brake-bias source/display mismatch.
- Keep uncertain tyre/brake/damage fields excluded from trusted decisions.
- Decide safety-fuel reserve configuration.
- Resolve how a hold-to-talk key supplies the actual request.
- Define the supported first-version advisory thresholds and evidence/confidence policy.

Acceptance gate:
- Every Stage 1/2 feature has a named trusted source or an explicitly approved calculation.
- All unresolved items remain visible as blockers, not silently treated as available.

### Stage 1 — Race Engineer foundation

Tasks:
- Create a Race Engineer domain/service layer separate from telemetry acquisition and UI.
- Add a freshness-aware Physics/Graphics/Static snapshot aggregator.
- Track source timestamp, packet ID, stream health, decode errors and unavailable fields.
- Define typed engineering observations: measured, calculated, inferred, warning, recommendation.
- Implement the three mode states: Driver-initiated, Balanced and Active.
- Implement warning priority, deduplication, severity escalation, resolution and cooldown.
- Implement a single radio-message queue using the existing TTS backend.
- Add mute/resume for non-critical messages and repeat-last-message.
- Add keyboard hold-to-talk plumbing only after request-input semantics are agreed.
- Ensure mode changes do not restart the app or clear session state.

Acceptance gate:
- Unit tests prove mode switching, priority, deduplication, escalation, recovery, mute behaviour and stale-data suppression.
- No Race Engineer code writes to ACC or emits driving/game-control inputs.
- A simulated session can generate and queue messages without a live ACC dependency.

### Stage 2 — Live Race Engineer

Tasks:
- Monitor lap completion, lap time, validity, sector transitions, PB and pace trend.
- Monitor position, gaps, session time, race-lap candidate, flags, penalties and pit state.
- Add weather/track-condition summaries using only supported Graphics mappings.
- Implement mode-specific announcements:
  - Driver-initiated: quiet except critical warnings.
  - Balanced: important events and meaningful changes only.
  - Active: every completed lap and lap time, plus important events.
- Add on-demand full status and individual category reports when request input is resolved.

Acceptance gate:
- Live ACC test covers valid/invalid laps, sector transitions, pit entry/exit, session countdown, position/gap changes, weather/flags and stream interruptions.
- No duplicate lap announcements or repeated unresolved warnings.
- Active mode reports every completed lap exactly once; Balanced does not announce every routine lap.

### Stage 3 — Fuel Engineer

Tasks:
- Validate current-fuel units and Graphics fuel-per-lap / estimated-laps against ACC.
- Build a robust per-lap consumption estimator using completed laps and refuelling/pit boundaries.
- Calculate fuel required to finish, reserve, surplus/shortfall and confidence range.
- Generate a realistic per-lap saving target and estimated total saving.
- Recalculate as consumption, race distance or conditions change.
- Detect when saving is no longer required.
- Generate refuelling advice using MFD request values only as read-only context.

Acceptance gate:
- Compare predictions against controlled ACC runs with known fuel loads and multiple completed laps.
- Verify behaviour after pit refuelling and changing consumption.
- Do not announce a saving target when inputs are stale, invalid or contradictory.
- Engineer never changes fuel or MFD values.

### Stage 4 — Tyre and Brake Engineer

Tasks:
- Build four-corner pressure and core-temperature trend models.
- Track stint age and pit/service resets.
- Compare front/rear and left/right behaviour.
- Add conservative brake-temperature monitoring after car-specific limits are established.
- Add tyre degradation estimates only as inferred trends.- Keep I/M/O temperatures, direct tyre wear, pad/disc life, brake pressure and brake compound out of trusted logic until their field issues are resolved.
- Define next-stint pressure advice only after a supported target-window model exists.Acceptance gate:- Validate cold-to-hot pressure changes, pit resets, tyre changes, wet/dry transitions and brake-temperature trends.
- Confirm no false warnings from initial zero/unpopulated samples.
- Clearly distinguish measured pressure/temperature from inferred degradation.

### Stage 5 — Vehicle Condition and Dynamics Engineer

Tasks:
- Add validated wheel-slip/traction and lock-up indicators.
- Establish repeatable corner/context baselines for understeer/oversteer and balance changes.
- Add damage-change monitoring without inventing component names.
- Correlate suspected faults with multiple independent signals.
- Recommend pit inspection only when evidence and severity justify it.
- Keep detailed driving-technique coaching with Performance Coach and Corner Coach.

Acceptance gate:
- Controlled tests cover wheelspin, braking/lock-up, damage/repair and repeatable balance changes.
- Each diagnosis includes supporting observations and confidence.
- No single noisy sample can trigger a definitive fault claim.

### Stage 6 — Race Strategy Engineer

Tasks:
- Combine validated fuel, tyre, brake, weather, position and race-state observations.
- Add pit-window/mandatory-stop advice only after Static/Graphics rule fields are semantically validated.
- Add push/conserve and position-based advice using validated gap sign and timing.
- Add safety-car strategy only if ACC exposes a verified state.
- Maintain explicit uncertainty and never infer a mandatory rule from an unknown enum.

Acceptance gate:
- Scenario tests cover short fuel, fuel surplus, tyre trend, changing weather, penalties, pit obligations and race-state transitions.
- Every recommendation explains the reason and assumptions.
- All actions remain manual.

### Stage 7 — Setup Engineer

Tasks:
- Start only with supported settings: TC, ABS, TC cut/engine map where mappings are understood, tyre pressures and brake bias after mismatch resolution.
- Add setup-state snapshots and before/after comparison.
- Build evidence-based expected-effect descriptions.
- Keep aero and suspension recommendations disabled until trustworthy setup telemetry or another verified source exists.
- Never apply settings automatically.

Acceptance gate:
- Controlled setup changes are correlated with displayed ACC settings.
- Advice is limited to the settings with verified current values and supported effects.
- No code path can write a setting to ACC.

### Stage 8 — UI, full-session validation and release hardening

Tasks:
- Complete Race Engineer page layout: communication mode, radio status, current priority, message history, active issues and request controls.
- Show source/evidence state for key recommendations without cluttering radio messages.
- Test switching modes during a live session and retaining session state.
- Test disconnect/reconnect, stale streams, decoder errors, TTS failure and application shutdown.
- Verify keyboard focus and key conflicts with ACC controls.
- Run automated tests, frontend production build and Windows ACC validation.
- Update project documentation and completion status.

Acceptance gate:
- No unhandled failures during a complete practice/race session.
- Critical warnings work in all modes; routine messages respect the selected mode.
- All recommendations are advisory and the game remains untouched by the application.
- No known unavailable field is presented as measured telemetry.

## 6. Suggested first implementation slice

After Stage 0 blockers are closed, implement the smallest end-to-end vertical slice:

1. Inspect and document the existing Physics/Graphics/Static consumer contracts and freshness metadata; add a Race Engineer snapshot aggregator without changing acquisition workers or stealing recorder queues.
2. Race Engineer mode manager and warning/message priority queue.
3. One completed-lap event with exact-once handling.
4. Existing TTS output.
5. Mode-specific behaviour for all three modes.
6. UI controls and message history after the message contract is stable.

This proves the core event-to-radio architecture before adding complex fuel, tyre or vehicle diagnosis.

## 7. Decisions already confirmed

- Three selectable modes: Driver-initiated, Balanced and Active race engineer.
- Balanced is the recommended/default mode.
- Critical warnings are automatic in every mode.
- Active mode announces every completed lap and lap time.
- Balanced mode announces meaningful changes, not every lap.
- Driver-initiated mode remains quiet except critical warnings.
- Keyboard hold-to-talk is the selected trigger interaction for the current phase.
- Microphone/voice recognition is not selected for this phase.
- Existing TTS infrastructure should be reused.
- Messages should be short; detailed explanations are available on request.
- Repeated unresolved warnings must be suppressed; meaningful severity changes may be announced.
- Race Engineer is strictly read-only and advisory. It must never change ACC, the car, setup, MFD, fuel, tyres, pit actions or driving controls.
- No F1-specific assumptions or leftovers.
- Do not duplicate Performance Coach or Corner Coach detailed driving-technique coaching.

## 8. Open decisions / validation register

| Item | Why it matters | Required next action |
|---|---|---|
| Fuel unit and HUD equivalence | Controls every fuel projection and saving recommendation | Deferred by user; preserve raw ACC value and confirm in a later controlled ACC session |
| Fuel reserve amount | Changes finish-fuel target | Decide configurable reserve policy |
| Graphics estimated laps / per-lap equivalence | Cross-checks fuel model | Compare against ACC display over a known stint |
| Gap sign convention | Needed for position strategy | Compare values with known car ahead/behind |
| Multi-car coordinate mapping | Needed for traffic and proximity | Test with multiple active cars |
| Brake-bias mismatch | Prevents trustworthy brake-bias advice | Resolve source and displayed setting |
| Pad/disc life, brake pressure, compounds | Current tail interpretation is unreliable | Targeted raw-offset/type investigation only if needed |
| Tyre wear / I-M/O temperatures | Not currently available as trusted telemetry | Keep unsupported; do not fabricate |
| Damage component mapping | Prevents false component-specific diagnosis | Correlate controlled damage and repair |
| Mandatory pit / pit-window semantics | Rule-critical strategy | Validate relevant Static/Graphics fields and units |
| Safety-car state | Required for safety-car strategy | Identify and validate an explicit ACC signal |
| Hold-to-talk request input | Key trigger alone does not define the request content | Decide whether current phase uses fixed commands, text entry or defers free-form speech |
| Warning thresholds | Prevents false alerts | Define per-car/per-condition evidence-based thresholds |

## 9. Existing source documents used

- docs/ACC_PHYSICS_FIELD_COVERAGE_AUDIT.md
- docs/ACC_GRAPHICS_FIELD_COVERAGE_AUDIT.md
- docs/ACC_STATIC_FIELD_LAYOUT_AUDIT.md
- docs/ACC_ACQUISITION_SUPERVISOR.md
- docs/ACC_DOWNSTREAM_FANOUT.md
- docs/ACC_RECORDING_FORMAT.md
- docs/ACC_RECORDING_MANIFEST.md

These source documents remain authoritative for their respective acquisition, ABI, recording and field-evidence details. This Race Engineer document maps that evidence to feature readiness; it does not replace or rewrite the underlying audits.


## 10. Current progression decision (2026-11-13)

- User confirmed by checking the ACC game UI that fuel values are in litres (L). This resolves the current-fuel unit uncertainty; the Physics decoder's internal `fuel_kg` field name is misleading and must not determine presentation.
- Preserve the existing decoded numeric value without conversion. Overview and Race Engineer displays must label current fuel in litres (L), consistent with ACC.
- Fuel projections remain gated only on validation of the Graphics fuel-per-lap / estimated-laps semantics and selection of a safety reserve; the current-fuel unit itself is no longer a blocker.
- Stage 0 is therefore sufficiently closed to begin Stage 1 foundation work, with all unresolved semantic checks retained as explicit feature gates.
- Stage 1 first task: inspect the existing decoded consumer APIs, timestamps/packet identifiers, and health/lifecycle surfaces. Design the aggregator around those existing contracts; do not add a second shared-memory reader, modify acquisition hot paths, or add Graphics/Static fan-out merely for the Race Engineer.


## 11. Stage 1 implementation progress (2026-11-13)

### Completed: first snapshot-aggregation slice

Added `src/race_engineer_acquisition/engineering_snapshot.py` and exported its public types from the acquisition package.

The aggregator:
- Reads the existing `PhysicsDecodeConsumer.snapshot` and `GraphicsDecodeConsumer.snapshot` properties; it never drains or takes ownership of their queues.
- Reads existing Physics, Graphics and Static acquisition health snapshots.
- Preserves each decoded stream's capture timestamp, capture sequence and ACC packet ID.
- Calculates sample age using the same process-local monotonic clock domain as acquisition timestamps.
- Applies independent configurable freshness limits (defaults: Physics 500 ms, Graphics 1,000 ms, Static read-health 3,000 ms).
- Requires both acquisition and decoder consumer lifecycle states to be running before a decoded stream is marked fresh.
- Keeps the last good decoded value visible for diagnostics when stale, while exposing `is_fresh` so decision logic can fail closed.
- Exposes Static as raw acquisition/read health only. It does not decode Static bytes or claim that a successful unchanged-page read is a new metadata snapshot.
- Explicitly does not claim Physics and Graphics samples are synchronized. Combined freshness means both independently pass their freshness gates, not that they were captured at the same instant.

Added `tests/test_engineering_snapshot.py` for independent freshness, stale-stream isolation, stopped consumers, missing samples, future timestamps, Static's raw-only status, and invalid thresholds.

**Validation status:** implementation and test source committed; tests have not yet been executed in a Windows project environment. No live ACC validation has been performed. This slice does not modify acquisition workers, ring buffers, recorders, decoders, UI, TTS or ACC/game state.

### Remaining Stage 1 work

1. Run the new unit tests and the existing acquisition/consumer regression suites in the project's supported environment.
2. Integrate the aggregator into the Race Engineer domain/service lifecycle without changing acquisition ownership.
3. Add typed engineering observations (measured, calculated, inferred, warning, recommendation).
4. Implement communication-mode state and warning/message priority, deduplication, escalation, resolution and cooldown.
5. Add the single radio queue using existing TTS, then test it with a simulated session before UI integration.

The current implementation is a standalone, testable aggregation boundary; it is not yet connected to the Race Engineer page or radio/TTS.


## 12. Initial Fuel Engineer implementation slice (2026-11-13)

Added `src/race_engineer_acquisition/fuel_engineer.py` with a pure, read-only builder that consumes the existing freshness-aware aggregate snapshot.

- Exposes Physics current fuel as litres (L), preserving the decoded numeric value without conversion. The legacy decoder member remains named `fuel_kg`; this slice does not rename the shared decoder API.
- Exposes Graphics fuel-per-lap, estimated-laps and MFD fuel-to-add as candidate observations only, each gated by Graphics freshness and finite/non-negative value checks.
- Never combines stale Physics or Graphics values into a current fuel view.
- Keeps finish-fuel, shortfall/surplus, fuel-saving, and refuelling recommendations disabled by default.
- Strategy calculations can only be enabled when both Graphics semantics are explicitly marked validated and a non-negative safety reserve is supplied. This is a guard, not a claim that those validations or reserve have already been selected.
- Added `tests/test_race_engineer_fuel.py` covering unit-preserving current fuel, candidate-only status, validation/reserve gating, stale-stream suppression, and invalid values.

**Validation status:** source and test files are committed to the branch. Tests have not been run in the user's Windows environment; no ACC live-session comparison has been performed. No UI, TTS, MFD, fuel setting, or game-control behaviour was changed.

**Next fuel step:** wire this observation snapshot into the Race Engineer service/page after confirming the page/service integration point, then run a controlled ACC stint to compare the Graphics fuel-per-lap and estimated-laps values with ACC's own display. Keep safety reserve selection separate.


### Fuel telemetry validation update (2026-11-13)

The user compared the live Race Engineer/Overview fuel values with ACC and confirmed the following:
- Estimated laps remaining: **16.5 laps**
- Fuel per lap: **3.66 L/lap**

The fuel-observation builder defaults fuel-per-lap and estimated-laps semantics to validated, while continuing to reject stale, non-finite and negative samples. MFD fuel-to-add is also confirmed against ACC in litres. Fuel used is confirmed to be live/working, but its exact accumulation and reset semantics remain open; do not use it for strategy calculations. This is a validation of the observed ACC display values; future checks after refuelling and across session states remain useful. Finish-fuel and shortfall recommendations remain disabled until a safety reserve is configured and remaining-race-distance inputs are validated.


### Fuel telemetry validation update (2026-11-13)

The user confirmed the following fuel observations against the live ACC session:
- Fuel per lap: **3.66 L/lap**.
- Estimated laps remaining: **16.5 laps**.
- MFD fuel to add: **10.0 L** in the observed example.
- Fuel used: live value confirmed working; its accumulation/reset semantics remain undocumented, so it is observation-only for now.

The fuel-observation snapshot exposes MFD fuel-to-add and fuel-used values only when the Graphics stream is fresh and the values are finite and non-negative. These observations do not enable finish-fuel or fuel-saving calculations; the safety reserve and remaining-race-distance gates remain in force. All values are advisory/read-only, and the application must not operate the ACC MFD.


## 13. Race Engineer fuel observation integration (2026-11-13)

- Added a Race Engineer service boundary that consumes the existing Physics/Graphics consumers through the freshness-aware snapshot aggregator; no second shared-memory reader or acquisition queue was introduced.
- The Qt host now publishes the fuel observation snapshot and a concise text radio preview with each bridge snapshot.
- Added an initial Fuel Engineer workspace showing current fuel, fuel used, fuel per lap, estimated laps and MFD fuel-to-add. The UI labels the preview as text-only; no TTS or communication-mode routing is claimed as integrated.
- Corrected the fuel-used observation to read the decoded Graphics member `used_fuel_l` (not the nonexistent `used_fuel` attribute).
- The service is observation-only. It does not write to ACC or operate the MFD. Fuel-used accumulation/reset semantics remain open; fuel-to-finish and saving calculations remain disabled until reserve and remaining-race-distance inputs are validated.

**Validation status:** changes are committed to the feature branch but have not been built or run in the user's Windows environment. A live ACC check is still required to confirm the Fuel Engineer page updates and the values remain consistent through session transitions.

### Fuel-used accumulation and new-session reset validation (2026-11-13)

The user completed a controlled live ACC check of the Race Engineer fuel observations:

- During the session, **Fuel Used increased to 1.1 L** while **Fuel Remaining was 60.9 L**. This confirms that the decoded Graphics `used_fuel_l` value changes as fuel is consumed.
- After starting a **new session**, **Fuel Used reset to 0.0 L** and **Fuel Remaining reset to 62.0 L**.\n- In the new session, Fuel per Lap displayed **3.66 L/lap**, Estimated Laps Remaining displayed **16.9 laps**, and MFD Fuel to Add displayed **0.0 L**.
- The observed fuel-used behaviour is therefore validated for live accumulation during a session and reset on a new session.
**Scope limitation:** this test does not establish whether Fuel Used resets or accumulates across pit stops, refuelling events, driver swaps, or other in-session transitions. Keep Fuel Used observation-only until those semantics are separately tested. The display remains freshness-gated and read-only.
**Strategy gate unchanged:** no finish-fuel, shortfall/surplus, or fuel-saving recommendation is enabled. A configurable safety reserve and validated remaining-race-distance inputs are still required. No ACC controls or MFD values are written by Race Engineer.


## 14. Dedicated strategy specifications and fuel strategy decision (2026-11-13)

Strategy requirements are maintained in separate documents so each strategy can be developed, reviewed and validated independently. This audit/roadmap remains the shared telemetry and implementation tracker; it is not the detailed specification for every strategy.

### Fuel Strategy specification

The dedicated Fuel Strategy specification is now available:

- [Race Engineer Fuel Strategy](RACE_ENGINEER_FUEL_STRATEGY.md)

The Fuel Strategy document is authoritative for fuel decision logic, reserve, calculation cadence, pit/refuelling recommendations, radio suppression, UI presentation and validation scenarios.

### Newly confirmed fuel strategy behaviour

- Assess fuel strategy in the background at the beginning of every lap, with exactly-once lap-boundary handling.
- Recalculate using current fuel, a rolling average of the last five valid completed lap times, validated fuel consumption, remaining race distance/time and actual finish-line behaviour.
- Use an initial safety reserve of **three laps** of estimated fuel consumption.
- Do not announce routine “fuel OK” or unchanged no-stop results. Background calculations must not create lap-by-lap radio spam.
- Announce actionable refuelling recommendations and critical fuel warnings. Suppress duplicate unchanged messages; correct a previously announced recommendation only when it materially changes or becomes obsolete.
- Calculate fuel expected to remain on pit arrival, then recommend the amount to add for the remaining race plus the three-lap reserve.
- The driver manually enters fuel in ACC and decides whether to pit. Race Engineer remains strictly read-only and must never operate the MFD or initiate pit actions.

These decisions supersede the earlier open-reserve wording in this roadmap. The three-lap reserve is selected as the initial default; car-specific tank capacity, remaining-race-distance semantics, timed-race finish behaviour, pit rules and other calculation inputs remain subject to validation before strategy calculations are enabled.


## 15. Dedicated Tyre Strategy specification and weather validation update (2026-11-13)

The dedicated Tyre Strategy specification has been created:

- [Race Engineer Tyre Strategy](RACE_ENGINEER_TYRE_STRATEGY.md)

This document is authoritative for tyre pressure and temperature monitoring, condition/degradation evidence, dry/wet tyre-type recommendations, pit-stop tyre advice, radio behaviour, UI requirements and validation scenarios.

### User-confirmed tyre strategy decisions

- Use the full adaptive, evidence-based approach: correlate pressure, temperature, stint trends, weather and driver feedback if/when that input is integrated.
- Strictly limit recommendations to data that ACC exposes and the project has validated. Never fabricate a value, threshold, wear percentage, diagnosis, compound option or remaining tyre life.
- Recommend the tyre type/compound based on track and weather conditions, but only from choices actually available for the selected ACC car/session. Do not assume unsupported dry compound choices.
- The Race Engineer remains strictly read-only; the driver makes all tyre and setup changes in ACC.
- Keep direct measurements, calculations and inferences clearly distinguished.

### Weather telemetry validation update (2026-11-13)

The user has now explicitly confirmed that **all weather fields currently exposed by the ACC implementation match the values shown in ACC**. This closes the user's value-comparison validation for those exposed weather fields.

Use the validated weather observations in Tyre Strategy, subject to each field's actual semantics, freshness and units. A field matching ACC does not automatically validate an undocumented interpretation or a future forecast horizon; current conditions and forecast/horizon data must remain distinguished. Future-looking tyre recommendations may only use a genuinely available and validated forecast/horizon.

### Tyre telemetry readiness and limits

- Four tyre pressures: available and validated.
- Tyre core temperatures: available and validated.
- Inner/middle/outer tread temperatures: currently unreliable; exclude from trusted decision logic.
- Direct tyre wear percentage / remaining tread life: unavailable as trusted telemetry; do not fabricate a health percentage or exact remaining life.
- Tyre degradation: inference only, requiring multiple signals, valid lap history and confounder checks.
- Pressure target ranges and temperature operating windows: require validated car-/tyre-specific references before classifying readings as optimal or abnormal.
- Selected tyre type and available choices: verify per car/session before making a recommendation.
- For the current ACC GT3 scope, treat the practical selection primarily as dry versus wet tyre, subject to the actual options exposed by the selected car/session. Do not invent soft/medium/hard choices.

This section supersedes any earlier roadmap wording that implies weather fields are still unvalidated. It also clarifies that weather validation does not close the separate tyre target-range, wear, temperature-distribution or compound-availability gates. No application code was changed as part of this documentation update.


## 16. Dedicated Brake Strategy specification and pad/disc telemetry update (2026-11-13)

The dedicated Brake Strategy specification has been created:

- [Race Engineer Brake Strategy](RACE_ENGINEER_BRAKE_STRATEGY.md)

This document is authoritative for four-corner brake-temperature monitoring, pad/disc condition observations, braking-behaviour analysis, evidence requirements, radio behaviour, UI requirements and validation gates.

### User-confirmed brake telemetry

- Four brake-temperature channels are available and user-validated.
- Brake pad-life values are working and appear separately for FL, FR, RL and RR.
- Brake disc-life values are working and appear separately for FL, FR, RL and RR.
- The user sees numeric pad/disc values without a unit label.

### Pad/disc unit interpretation

ACC-specific shared-memory references describe pad-life and disc-life values as remaining thickness in millimetres (mm), with commonly documented new-component reference values around 29 mm for pads and 32 mm for discs. These are reference values, not universal car-independent limits.

Until the user's selected car and a controlled ACC state confirm the interpretation:
- Preserve raw values and corner mapping.
- Treat mm as the expected/reference unit, not as an unconditional validated runtime label.
- Do not calculate wear rate, remaining laps/distance, replacement timing or percentage health.
- Do not apply universal new-component or minimum-thickness thresholds.

### Supersession of earlier brake audit wording

This update supersedes the earlier §3.4 statements that pad-life and disc-life are simply unreliable/unusable. The user has confirmed the four-corner values are working. The remaining uncertainty concerns unit/scale semantics, value direction, car-specific baselines, service limits and wear/reset behaviour. The existing brake-pressure and brake-compound candidate warnings remain unchanged; they are still excluded from diagnosis until separately validated.

### Brake Strategy design decisions

- Monitor all four brake temperatures, pad values and disc values independently.
- Compare per-corner values and trends only when samples are fresh and their semantics are understood.
- Use car-specific, evidence-backed temperature limits; never hard-code generic universal thresholds.
- Keep braking-performance, ABS and lock-up diagnosis gated on validation of their respective telemetry.
- Do not claim mechanical failure or component remaining life without sufficient validated evidence.
- Race Engineer remains read-only; all setup, component and pit decisions remain with the driver.

No application code was changed as part of this documentation update.


## 17. Dedicated Pace Strategy specification and opponent-focus decision (2026-11-13)

The dedicated Pace Strategy specification has been created:

- [Race Engineer Pace Strategy](RACE_ENGINEER_PACE_STRATEGY.md)

This document is authoritative for personal pace analysis, immediate-opponent focus, chase/overtake preparation, post-pass gap management, defensive awareness, communication, UI requirements and validation gates.

### User-confirmed Pace Strategy design

- Pace Strategy may compare the player's pace with other cars, but its primary focus is **one classified position ahead at a time**.
- The goal while chasing is to understand how to close on and prepare to overtake the immediate car ahead.
- The immediate car behind is also monitored so the driver can maintain a gap and defend a position when necessary.
- After a confirmed pass, the former target becomes the immediate car behind (subject to updated classification), and the next car ahead becomes the new target.
- Both adjacent cars may be observed, but only one is the primary tactical focus at a time: chase, defend, gap-building or personal pace.
- Personal valid-lap and sector pace remains part of the strategy.
- Opponent-specific pace comparisons and catch-time estimates are permitted only when the corresponding ACC timing/gap source, car association, units, sign convention and freshness are validated.
- Do not invent opponent timing, passing thresholds, opponent intent, passing zones or likely manoeuvres.
- If opponent telemetry is unavailable or unreliable, fall back to personal pace and explicitly report the limitation.
- Keep detailed corner-by-corner driving coaching with Performance Coach and Corner Coach.
- All recommendations remain advisory; Race Engineer never controls the car or changes ACC state.

### Current telemetry validation gates

- Graphics position and active-car count remain candidate inputs for opponent strategy.
- Gap-ahead and gap-behind are decoded in milliseconds, but sign convention and immediate-neighbour association must be confirmed.
- Multi-car identity/coordinate mapping remains candidate and requires controlled live validation.
- Opponent-specific lap/sector timing availability has not yet been established as a validated input.
- The next engineering step is to inspect existing decoded consumer APIs and validate these semantics before enabling opponent-aware calculations. Do not add another shared-memory reader.

No application code was changed as part of this documentation update.


## 18. Dedicated Traffic Strategy specification (2026-11-13)

The dedicated Traffic Strategy specification has been created:

- [Race Engineer Traffic Strategy](RACE_ENGINEER_TRAFFIC_STRATEGY.md)

This document is authoritative for nearby-car awareness, catching slower traffic, being approached/lapped, proximity and overlap gating, traffic-affected pace context, communication, UI requirements and validation gates.

### Agreed Traffic Strategy boundaries

- Traffic Strategy focuses on physical traffic context and nearby-car interactions, not simply classified position.
- Pace Strategy retains ownership of the immediate classified car one position ahead/behind, race-position chasing, passing that target, gap-building and defending.
- Traffic Strategy may identify cars ahead, behind or alongside only when the existing car association and coordinate model support those statements.
- Catching, being approached, relative movement and overlap must be based on fresh, correctly associated observations; a timing gap alone is not physical proximity.
- Traffic-affected lap/sector context must be aligned with the relevant timing interval and must not overwrite measured lap times or automatically discard valid laps.
- No fabricated distance, relative speed, time-to-contact, overlap, contact, blue-flag status, class priority, racing line or opponent intent.
- Reuse existing decoded consumer APIs and telemetry acquisition. Do not add another shared-memory reader.
- All recommendations remain informational and advisory; Race Engineer never controls the car or changes ACC state.

### Current telemetry validation gates

- Graphics car IDs, coordinates and normalized track position remain candidate inputs.
- Player/opponent association, coordinate frame, units, update cadence, track wrap-around and stale-data behaviour require controlled multi-car ACC validation.
- Opponent-specific speed or relative speed has not been established as a validated traffic input.
- Overlap detection is not approved until car dimensions/reference points and coordinate geometry can support it reliably.
- Race-control/blue-flag semantics must remain gated on explicit validation.
- Until these gates pass, Traffic Strategy must use only the facts the available telemetry can reliably establish and clearly report unavailable information.

No application code was changed as part of this documentation update.


## 19. Dedicated Race-State Strategy specification (2026-11-13)

The dedicated Race-State Strategy specification has been created:

- [Race Engineer Race-State Strategy](RACE_ENGINEER_RACE_STATE_STRATEGY.md)

This document is authoritative for session-state awareness, flag and track-status interpretation, penalty/warning lifecycle, safety-car/neutralisation availability gates, session transitions, race-finish handling, communication, UI requirements and validation.

### Race-State Strategy boundaries

- Report only race-control states whose raw values, enum meanings, units and lifecycle have been validated against ACC.
- Preserve unknown raw codes as unknown; never guess a flag, penalty or neutralisation meaning.
- Keep lap validity separate from flags and penalties.
- Use completed-lap count separately from the candidate race lap limit.
- Treat session timer expiry and actual race completion as distinct until timed-race finish-line behaviour is validated.
- Do not claim safety car, VSC, FCY, red flag or chequered states unless a reliable source is explicitly identified and tested.
- ACC HUD and server instructions remain authoritative; Race Engineer provides supplementary information only.
- Reuse existing decoded consumers and event infrastructure; do not add another shared-memory reader.
- All behaviour remains strictly read-only. No penalty acknowledgement, MFD operation, pit action or game control is permitted.

### Current telemetry validation gates

- Session time remaining is validated for display, and completed-lap count is validated.
- Session type/state and race-control integer codes remain candidates requiring controlled transition and HUD correlation.
- Race lap limit / laps remaining semantics remain unvalidated.
- Penalty and warning fields require enum, unit and lifecycle validation before announcement.
- Safety-car/neutralisation and chequered/finish sources have not been established as validated inputs.
- Timer expiry alone must never trigger a confirmed race-finished announcement.

No application code was changed as part of this documentation update.


## 20. Dedicated Car Health Strategy specification (2026-11-13)

The dedicated Car Health Strategy specification has been created:

- [Race Engineer Car Health Strategy](RACE_ENGINEER_CAR_HEALTH_STRATEGY.md)

This document is authoritative for damage observations, validated mechanical warnings, evidence-based abnormal-behaviour assessment, alert behaviour, UI presentation and validation gates.

### Car Health Strategy boundaries

- Monitor only damage channels and mechanical warnings whose source, semantics and freshness are understood.
- The five Physics `car_damage` channels have been observed changing, and a controlled pit repair returned the values to zero. This validates them as changing general-damage observations, but not their individual component mapping, units, scale or severity thresholds.
- Do not assign body-panel/component names, percentages, severity bands or safety conclusions to uncalibrated damage values.
- Physics `suspension_damage[4]` remains candidate telemetry; channel meaning, corner mapping, units, value direction and repair behaviour require controlled validation before driver-facing diagnosis.
- No separately trusted engine-damage field or complete mechanical-fault inventory is currently established. Do not infer engine damage from temperature, RPM, power or generic engine-state values.
- Collision detection is not directly available as a trusted event. A damage change is evidence of a damage-reading change, not proof of a collision.
- Abnormal vehicle behaviour is an inference and requires validated channels, a comparable baseline, repeatable/corroborating evidence and confounder checks.
- Brake component condition remains owned by Brake Strategy; tyre condition remains owned by Tyre Strategy. Car Health may consume validated summaries but must not duplicate their specialist alerts.
- Detailed driving-technique coaching remains with Performance Coach and Corner Coach.
- Reuse existing decoded consumers and freshness-aware snapshots. Do not add another shared-memory reader or acquisition path.
- All reports and recommendations remain advisory. The driver decides whether to inspect or pit; Race Engineer never controls the car, setup, MFD or pit actions.

### Current validation gates

- General damage-channel movement and return to zero after a controlled pit repair have been observed; component mapping and severity interpretation remain open.
- Suspension damage channels remain candidate-only.
- Engine fault/damage sources and warning lifecycle require targeted source identification and ACC HUD correlation.
- Vehicle-dynamics diagnosis requires validated units, axes, signs, timestamp alignment and repeatable baselines.
- Stale or missing telemetry must be reported as unavailable, never as evidence that the car is healthy.
- No universal damage threshold or generic severity classification is approved.
- Damage assessment and final pit timing are separate: Car Health tracks raw damage changes, persistence, corroborating evidence and observed repair transitions; Pit-Stop Strategy owns the final integrated stop-timing decision.
- A changed raw damage value alone must not trigger a pit recommendation. Persistent damage plus repeatable, independently supported abnormal behaviour may justify advising inspection at a suitable stop, with correlation phrased cautiously.
- A validated ACC warning/confirmed critical condition may justify an urgent warning only according to its validated meaning and lifecycle. No uncalibrated `car_damage[5]` threshold, component diagnosis, severity score, safety claim or quantified lap-time loss is permitted.
- Pit-Stop Strategy must integrate validated damage urgency with race distance/position, pit-lane loss, repair duration/availability and opportunities to combine repair with an already-planned fuel/tyre stop. All actions remain manual and driver-controlled.
- No application code was changed as part of this documentation update.

## 21. Dedicated Setup Strategy specification (2026-11-13)

The dedicated Setup Strategy specification has been created:

- [Race Engineer Setup Strategy](RACE_ENGINEER_SETUP_STRATEGY.md)

This document is authoritative for in-session/on-board setting recommendations, driver-confirmed adjustments, setup history, before/after evaluation, setup-file provenance, communication, UI requirements and validation gates.

### User-confirmed Setup Strategy decisions

- Prioritise **on-board adjustments that can be made during an ACC session**. Garage-only setup changes are deferred to a later phase.
- Potential on-board controls include brake bias, TC, ABS, engine map and other car-specific adjustable controls, but only where the selected car/session actually exposes them. Do not assume a universal control inventory or common ranges across cars.
- Setup Strategy recommends changes and explains the evidence, expected benefit and trade-off. The driver manually applies every change; Race Engineer must never send control inputs or modify ACC.
- Automatically capture telemetry and compact lap/session context so pre-change and post-change behaviour can be compared.
- Maintain persistent setup adjustment history, organised by car, track/layout and conditions, with chronological setting versions and source provenance.
- Require driver confirmation of the actual applied setting whenever ACC telemetry does not expose it. A recommendation is not proof that a change was made.
- Support setup-file import as a read-only supporting source for baseline/configuration values, while distinguishing imported values from live telemetry and driver-confirmed changes.
- Evaluate changes using valid lap/sector pace, consistency, relevant vehicle response and optional driver feedback. Account for traffic, fuel, tyres, brakes, weather, track evolution and driver variation before attributing an outcome to a setting.
- Build preferred track/car/condition-specific values only from repeatable comparable evidence. Label limited evidence as candidate or inconclusive; never declare a universal best setup from one faster lap.
- Garage-only settings such as suspension, dampers, springs, ride height, aero and alignment remain outside the initial implementation scope and will be considered later.
- Reuse existing telemetry consumers and history infrastructure; do not add another shared-memory reader. All setup actions remain manual and driver-controlled.

### Setup Strategy readiness

- The available on-board control inventory, per-car labels/ranges/increments and telemetry exposure must be audited before numeric recommendations are enabled.
- Setup-file format coverage and association with the active car/session require validation before import can be treated as reliable.
- Persistent event history, confirmation workflow, before/after windows and confounder handling require implementation and tests.
- No application code was changed as part of this documentation update.


## 22. Dedicated Weather Strategy specification (2026-11-13)

The dedicated Weather Strategy specification has been created:

- [Race Engineer Weather Strategy](RACE_ENGINEER_WEATHER_STRATEGY.md)

### User-confirmed Weather Strategy decisions

- Weather Strategy monitors changing ACC weather and track conditions and supplies timestamped context to dependent strategies.
- The user has confirmed that all weather fields currently exposed by the ACC implementation match the values shown in ACC.
- Weather Strategy must also monitor ACC's predicted weather progression for the remainder of the session when reliable forecast fields are exposed.
- Forecast values must remain separate from observed current conditions and retain their target horizon/time and receive timestamp.
- Forecast meaning, horizon, update cadence and semantics must be documented before forecast-driven strategic recommendations are enabled.
- Missing, stale or ambiguous forecast data must be reported as unavailable; do not extrapolate current rain into a forecast or invent probabilities, rain duration, transition times or drying rates.
- Weather Strategy owns weather observations, trend/transition detection and condition history. Tyre Strategy owns tyre-condition assessment and tyre-change recommendations; Pit-Stop Strategy owns the final integrated stop decision.
- Weather alone must never trigger a tyre change, setup change or pit-stop recommendation. Dependent strategies must combine weather context with their own validated evidence.
- Reuse existing decoded consumers and freshness-aware snapshots; do not add another shared-memory reader.
- Maintain compact session history for observed conditions, forecast progression, detected transitions and dependent-strategy notifications.
- All recommendations remain advisory and read-only. The driver performs every in-game action manually.

### Weather Strategy readiness

- The user-confirmed value comparison covers all weather fields currently exposed by the implementation. Units, enum interpretation, freshness, timestamp alignment and update cadence still need to be preserved and tested per field.
- Forecast target horizon, update cadence and relationship to ACC's displayed forecast require explicit validation before future-looking recommendations.
- Track-grip transitions and wind interpretation must remain gated by their documented semantics.
- Controlled dry-to-wet, wet-to-dry, temperature-change, reconnect and new-session tests are required.
- No application code was changed as part of this documentation update.


## 23. Dedicated Pit-Stop Strategy specification (2026-11-13)

The dedicated Pit-Stop Strategy specification has been created:

- [Race Engineer Pit-Stop Strategy](RACE_ENGINEER_PIT_STOP_STRATEGY.md)

### User-confirmed integrated pit-decision design

- Pit-Stop Strategy is the **single decision-making and recommendation layer** for pit stops. Fuel, Tyre, Brake, Car Health, Weather, Race-State, Pace and Traffic provide evidence/context; they must not issue separate competing routine pit instructions.
- The integrated strategy combines all relevant evidence and produces one recommendation: stay out, plan a stop, or pit now/urgently, with the supported timing and combined service list.
- A single issue may justify a stop, but the final pit recommendation still comes from the integrated decision layer. Specialist strategies may issue their own critical informational warnings without issuing separate pit instructions.
- Use a two-layer model: validated hard constraints first, then a weighted assessment. A validated mandatory rule, fuel infeasibility or confirmed critical condition can require a stop regardless of the weighted score. Candidate or stale telemetry must not become a hard constraint.
- The agreed initial weighted assessment is fixed at Fuel 25%, Tyres 25%, Car Health 20%, Brakes 15%, Weather 10% and Race-State strategic context 5% (100% total).
- Pace and Traffic are contextual timing inputs in the initial model, not independent pit-necessity weight contributors.
- These weights are fixed initially. They must not adapt automatically. Changes may be considered only after sufficient representative race history has been recorded and reviewed, with documented evidence and explicit approval.
- The weighted score is not a probability. Missing, stale, ambiguous or unvalidated inputs remain unknown; do not treat them as zero need or silently redistribute their weight. Score scale, evidence-coverage rules and decision thresholds require explicit definition and validation before live use.
- Combine compatible fuel, tyre, damage/repair and other validated services into one stop where timing and constraints support it. Consider race distance, pit-lane loss, service duration, weather, position, gaps and traffic without inventing unavailable values.
- Maintain persistent chronological pit-stop history per session: observed pit entry/exit, fuel before/after/added, tyre state and changes, damage/brake state and confirmed services, conditions, position/gaps, recommendation, driver action and subsequent pace/consistency outcomes.
- Every history value must retain provenance: automatically observed, calculated from validated observations, imported or driver-confirmed. Unexposed service details remain unknown until confirmed; a pit visit alone does not prove refuelling, tyre change or repair.
- Use compact event and before/after summaries, reusing existing telemetry/session history. Do not add another shared-memory reader or unnecessary high-frequency recording.
- All recommendations remain advisory and read-only. Race Engineer never operates pit controls, MFD or any in-game function.

### Pit-Stop Strategy readiness

- Strategy-output aggregation and timestamp/freshness alignment are not yet implemented or live-validated.
- Mandatory-stop rules, finish behaviour, fuel feasibility, service constraints, pit-lane loss, repair duration and pit entry/exit/service detection require source-specific validation.
- The score scale, per-strategy severity mappings, minimum evidence coverage, hard-constraint precedence, decision thresholds and hysteresis/deduplication must be defined and tested before score-driven recommendations.
- Pit-history persistence, provenance, driver-confirmation workflow and post-stop outcome analysis require implementation and tests.
- Initial weights remain fixed as specified; future adjustment requires sufficient comparable evidence and explicit approval.
- No application code was changed as part of this documentation update.


## 24. Shared Telemetry Requirements Matrix (2026-11-13)

The cross-strategy shared telemetry requirements matrix has been created:

- [Race Engineer Shared Telemetry Requirements Matrix](RACE_ENGINEER_SHARED_TELEMETRY_REQUIREMENTS_MATRIX.md)

The matrix consolidates the ten strategy specifications and identifies:
- Shared Physics, Graphics, Static, application-history, derived and driver-confirmed inputs.
- Which strategies consume each data family.
- Current validation state and restrictions on candidate/inferred/unavailable data.
- Existing snapshot aggregator and Fuel observation API contracts.
- Shared services needed for lap/sector history, race progress, fuel, tyres, brakes, damage, weather, opponents/traffic, setup, pit decisions/history and radio.
- Cross-stream freshness/timestamp rules, ownership boundaries and anti-double-counting rules.
- Prioritised validation gaps and an implementation sequence based on shared dependencies.

### Source/API findings verified in this pass

- `src/race_engineer_acquisition/engineering_snapshot.py` implements `RaceEngineerSnapshotAggregator` and reads the existing Physics and Graphics consumer snapshots plus acquisition health. It does not read shared memory or drain queues.
- Physics and Graphics have separate capture timestamps and independent freshness limits (default 500 ms and 1,000 ms respectively). The aggregate snapshot explicitly does not claim that their samples are synchronized.
- Static currently appears in this aggregate as raw read-health information only; it does not expose decoded Static metadata through `RaceEngineerTelemetrySnapshot.static`.
- `src/race_engineer_acquisition/fuel_engineer.py` implements a conservative observation builder for current fuel, fuel-per-lap, estimated laps remaining, MFD fuel-to-add and fuel-used. It does not yet calculate finish fuel, shortfall, saving or refuelling amount; a configured reserve is still required to enable its calculation gate.
- Focused tests for the snapshot aggregator and Fuel observation builder were inspected but not executed.

### Remaining source-audit limitation

The low-level Physics/Graphics decoder implementations, complete consumer API surface, Static metadata consumer and existing session-history/pit-event storage APIs were not fully verified in this pass. The matrix explicitly marks this as a P0 source/API audit task; decoder field names taken from existing audit documents must be reconciled against the actual decoder source before implementation.

No application code was changed as part of this documentation update.

## 25. Fan-out telemetry distribution architecture (2026-11-13)

The shared telemetry matrix defines the required fan-out architecture in Section 9:

- [Shared Telemetry Requirements Matrix — Fan-out architecture](RACE_ENGINEER_SHARED_TELEMETRY_REQUIREMENTS_MATRIX.md#9-required-fan-out-data-distribution-architecture)

### Required architecture

ACC shared memory is acquired and decoded once per source stream. Existing consumer snapshots are published as immutable latest-value state, while meaningful transitions are published as identified events. Independent strategy consumers receive the same data without destructive queue reads or shared mutable state.

The target fan-out consumers are Fuel, Tyre, Brake, Car Health, Weather, Race-State, Pace, Traffic, Setup and Pit-Stop. Shared domain calculations (such as lap/sector normalisation, fuel observations, stint boundaries and weather context) must have one owner and be reused by strategies.

Strategy outputs are submitted to one central coordinator for priority, communication-mode handling, critical-warning bypass, deduplication and TTS serialization. Pit-Stop Strategy remains the sole owner of routine pit recommendations. The architecture remains strictly read-only with respect to ACC.

### Audit and implementation gates

1. Inspect the actual acquisition workers and decoded consumer APIs to verify one reader per source and establish whether current consumers already receive independent fan-out or merely read a latest-value cache.
2. Inspect queue ownership, callback/subscriber registration and thread boundaries. Confirm no consumer destructively drains data needed by another.
3. Inspect event production and persistence for completed laps, pit entry/exit, session transitions and damage/weather changes. Add stable event identity, gap detection and deduplication where absent.
4. Define latest-value delivery for live state and reliable/gap-detectable delivery for history-critical events. A failed or slow strategy must not block acquisition or other consumers.
5. Define per-calculation freshness and cross-stream timestamp-skew gates.
6. Inspect strategy output and TTS call sites; route findings through one coordinator rather than allowing independent strategy speech.
7. Add acceptance tests for multi-consumer fan-out, subscriber failure isolation, event gaps/replay/deduplication, stale/misaligned data and centralized radio arbitration.

### Current implementation status

- **Verified:** the existing `RaceEngineerSnapshotAggregator` reads existing Physics/Graphics consumer snapshots and acquisition health without opening another shared-memory reader or draining their queues.
- **Not yet verified:** whether the underlying acquisition/consumer layer already provides full independent fan-out to multiple strategy subscribers; the snapshot aggregator alone does not prove this.
- **Not yet implemented/verified:** complete strategy subscriber lifecycle, reliable event fan-out, failure isolation, event-gap reconciliation and centralized strategy-output/radio arbitration.
- **Required next source-audit focus:** trace acquisition worker → decoder → consumer publication → every consumer/subscriber → strategy output/TTS call site. Record the real ownership and delivery semantics before changing implementation.

No application code was changed as part of this architecture documentation update.


## 26. Strategy consumer architecture decision (2026-11-13)

The dedicated strategy-consumer architecture has been documented:

- [Race Engineer Strategy Consumer Architecture](RACE_ENGINEER_STRATEGY_CONSUMER_ARCHITECTURE.md)
- [Shared Telemetry Requirements Matrix — fan-out architecture](RACE_ENGINEER_SHARED_TELEMETRY_REQUIREMENTS_MATRIX.md#9-required-fan-out-data-distribution-architecture)

### User-confirmed architecture decisions

- **Keep the Overview page and its existing publishing path untouched.** The current Qt snapshot publisher, TelemetryBridge HTTP/SSE transport and React Overview consumer remain separate from strategy distribution. Strategy processing must not be inserted into the Overview rendering/publishing path.
- Reuse the existing ACC acquisition streams, rings, decoders, decoded Physics/Graphics consumer snapshots and freshness-aware engineering snapshot. No strategy opens another ACC shared-memory reader or drains acquisition queues.
- Add a strategy-only snapshot/event publisher and connect it to the live strategy runtime. The exact safe publication hook must be established by source/API audit; do not assume a callback or add a new high-frequency poller without evidence.
- Use latest-value/coalescing delivery for replaceable live telemetry and identified, gap-detectable delivery/reconciliation for history-critical events such as completed laps, pit/session transitions, damage changes and weather transitions.
- Reuse and integrate the existing `FanOutDispatcher` in `src/race_engineer_acquisition/fanout.py` after verifying its queue, worker, fairness, ordering, coalescing and failure-isolation semantics. It exists but was not connected to the audited live runtime.
- Do not default to one high-frequency worker thread or polling loop per strategy. Prefer event-triggered evaluation and a bounded shared scheduler/worker facility, selected only after the existing dispatcher threading model is verified.
- Add shared calculation services with one owner per common calculation. Strategies consume immutable results with source sequence/timestamp, freshness, provenance and validation state.
- Add independent consumers for Fuel, Tyre, Brake, Car Health, Weather, Race-State, Pace, Traffic, Setup and Pit-Stop.
- Strategy consumers emit typed observations/recommendations; they do not speak directly. A central decision coordinator resolves outputs, while a separate communication coordinator applies the three radio modes, priorities, critical-warning bypass, deduplication and existing TTS.
- Pit-Stop Strategy remains the only routine pit-recommendation authority and retains the agreed fixed initial weights. All actions remain advisory and read-only.
- Store compact lap/session summaries and meaningful events asynchronously. Do not duplicate high-frequency raw telemetry for strategy history or block acquisition on persistence.
- Establish CPU, memory, queue, latency, acquisition-health and Overview responsiveness baselines. Set numeric budgets only after repeatable measurement; do not copy performance claims from reference products.

### Required implementation sequence

1. Complete the source/API audit for consumer publication, timestamps/sequences, dispatcher worker model, service cadence, event producers and history/storage APIs.
2. Define versioned snapshot, event, strategy-output, error and metrics contracts.
3. Add the strategy-only input publisher without changing the Overview route or adding an unnecessary polling loop.
4. Integrate or minimally extend the existing FanOutDispatcher to satisfy the delivery and isolation contract.
5. Implement shared calculation services and add strategy consumers incrementally.
6. Add compact history, event reconciliation, central decision and communication coordination.
7. Benchmark and validate with deterministic replay, automated tests, Windows build and live ACC sessions.

### Performance and acceptance gates

- No additional ACC shared-memory reader.
- No changes to the Overview publishing/rendering pipeline.
- No unbounded queues or per-strategy high-frequency polling loops.
- Slow/failed consumers cannot block acquisition, Overview or other consumers.
- Live snapshots coalesce; history-critical event gaps are detected and reconciled or surfaced.
- Shared calculations execute once and are reused.
- CPU, memory, queue depth/age, event latency and Overview responsiveness remain within measured, agreed budgets.
- No strategy or coordinator writes to ACC or performs game-control actions.

### Current status

This is an agreed design, not an implementation claim. The strategy-only publisher, dispatcher runtime integration, shared calculation services, strategy consumers, decision/communication coordinators and compact strategy history remain to be implemented or verified. No application code was changed as part of this documentation update.

## 27. Fan-out dispatcher integration audit (2026-11-13)

The detailed source audit is recorded in [Race Engineer Strategy Consumer Architecture — Section 16](RACE_ENGINEER_STRATEGY_CONSUMER_ARCHITECTURE.md#16-fan-out-dispatcher-source-audit-2026-11-13).

### Verified findings

- `src/race_engineer_acquisition/fanout.py` implements a generic bounded dispatcher that consumes one `AcquisitionRingBuffer` and offers each item to independent per-consumer queues.
- Per-consumer queue accounting includes offered, dispatched, processed, failed, rejected, queued and in-flight items, with first/last lost and failed capture sequences.
- Consumer registration is fixed before dispatcher start. The dispatcher does not own or start consumer workers.
- Current Physics and Graphics acquisition rings are consumed directly by their dedicated decoder workers. These are SPSC rings; adding the dispatcher as another reader would compete with and steal raw samples from the decoder.
- Strategy consumers require decoded, freshness-aware state and domain events. The existing raw-ring dispatcher is not directly connected to the decoded snapshots or `RaceEngineerSnapshotAggregator`.
- The live acquisition runtime does not instantiate the dispatcher or register strategy consumers.
- Existing fan-out tests cover deterministic queue isolation and accounting, but not decoded snapshot coalescing, event replay/recovery, worker scheduling, latency, CPU overhead or live ACC behaviour.

### Decision

Do not attach the existing dispatcher directly to the Physics or Graphics acquisition rings for strategy distribution. Preserve the current acquisition/decoder ownership and Overview pipeline.

Reuse its bounded-queue, acknowledgement and failure-accounting concepts. Before coding, compare a minimal generic decoded snapshot/event publisher adaptation with a separate lightweight strategy broker. The chosen design must support latest-value coalescing, typed history-critical events, per-consumer subscriptions, gap detection/reconciliation, bounded scheduling and measurable failure isolation.

### Outstanding work

1. Inspect exact decoded snapshot publication points and identify a safe low-cost notification boundary.
2. Decide whether the existing dispatcher should be generalised or whether a small decoded strategy broker is simpler and cheaper.
3. Specify collision-safe event identity across streams and sessions.
4. Specify live-state coalescing separately from history-critical event delivery.
5. Define consumer lifecycle/restart and shared worker scheduling.
6. Add deterministic tests for slow/failed consumers, coalescing, event gaps/recovery, multi-stream identity, lifecycle and bounded memory.
7. Run tests, Windows build, controlled replay and CPU/memory/latency comparisons before enabling more strategy consumers.

**Validation status:** source and test files were inspected only. Tests were not executed. No application code or Overview path was changed. No performance benchmark or live ACC validation was performed.



## 28. Strategy broker architecture decision (2026-11-13)

Following the detailed source audit of `FanOutDispatcher`, the initial strategy distribution approach is now **a lightweight decoded-state strategy broker**. The decision and detailed contract are recorded in [Race Engineer Strategy Consumer Architecture — Section 17](RACE_ENGINEER_STRATEGY_CONSUMER_ARCHITECTURE.md#17-strategy-distribution-implementation-choice--lightweight-decoded-state-broker-2026-11-13).

### Decision

- Do not attach `FanOutDispatcher` to Physics or Graphics acquisition rings. Those SPSC rings are already consumed by their decoder workers; a second reader would compete for and steal samples.
- Do not force the existing raw-ring dispatcher to become the decoded strategy bus.
- Introduce a small in-process broker at the decoded-data boundary. It distributes immutable decoded snapshots and typed domain events to independently subscribed strategy consumers.
- Keep live state and history-critical events on separate delivery paths: latest-value slots coalesce obsolete snapshots; bounded event mailboxes preserve identity/order and expose gaps for reconciliation.
- Reuse bounded-capacity, acknowledgement, failure-accounting and loss-metric concepts from `FanOutDispatcher`, without directly coupling it to raw acquisition.
- Use bounded shared scheduling, per-subscriber isolation and asynchronous compact history. No strategy-specific shared-memory readers, high-frequency polling loops or decoder-thread strategy calculations.
- The existing Overview Qt publisher, TelemetryBridge HTTP/SSE route and React consumer remain untouched and independent.

### Remaining source-audit gates

1. Identify the exact decoded Physics/Graphics publication point and engineering snapshot update cadence.
2. Trace service lifecycle and determine a constant-time, bounded, failure-isolated handoff to the broker.
3. Identify existing producers for completed laps, session changes, pit transitions, damage changes and weather transitions.
4. Define collision-safe event identity, event ordering, duplicate handling and reconciliation source.
5. Define broker subscription lifecycle, bounded shared scheduling, metrics and shutdown/restart behaviour.
6. Add deterministic tests for coalescing, event gaps/recovery, independent subscribers, slow/failing consumers and bounded memory.
7. Benchmark CPU, memory, event latency, acquisition health and Overview responsiveness before/after integration; then validate with Windows build and controlled ACC sessions.

**Status:** Architecture choice approved and documented; source-level publication-hook audit, implementation, tests, build, benchmark and live ACC validation remain pending. No application code or Overview path was changed.
