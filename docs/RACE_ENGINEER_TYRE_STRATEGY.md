# ACC Race Engineer — Tyre Strategy

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/race-engineer-page  
**Status:** Strategy requirements agreed; implementation and live strategy validation pending  
**Last updated:** 2026-11-13

## 1. Purpose

The Tyre Strategy monitors tyre pressure, temperature, condition and stint performance, and advises the driver about tyre use, tyre changes and the appropriate available tyre type for current and expected track/weather conditions.

The strategy follows a full evidence-based race-engineer approach, but is strictly limited to data ACC actually exposes and the project has validated. It must never fabricate tyre wear, remaining life, target pressures, temperature thresholds, weather forecasts, compound availability or a diagnosis.

This document defines Tyre Strategy only. Other Race Engineer strategies have separate specifications.

## 2. Non-negotiable operating rules

- Race Engineer is strictly read-only. It observes and advises; it must never change tyre pressures, tyre type, setup, MFD, pit requests, pit actions or any other ACC/game control.
- The driver makes every decision and performs every change in ACC.
- Separate measured ACC values, calculated trends and inferred diagnoses in the UI and message model.
- Use only fresh, valid and semantically validated telemetry for live recommendations.
- Do not turn missing, stale, implausible or unreliable telemetry into a guessed value.
- Do not claim actual tread wear, remaining tyre life, graining, blistering, flat spots or physical damage unless ACC provides a trustworthy direct signal or the driver supplies a report that is clearly identified as driver feedback.
- Do not infer a definitive cause from one pressure, temperature, lap-time or handling observation.
- Use car-, tyre- and condition-specific target ranges only when sourced from validated ACC/game data or a verified reference. Never apply a generic pressure or temperature threshold to every car/track.
- Weather fields have been compared by the user with ACC and are confirmed to match. Preserve the source units and meanings; distinguish current conditions from any forecast/horizon fields.
- A validated current weather observation is not automatically a validated future forecast. Only use future conditions when an actual forecast/horizon value is exposed, fresh and validated.
- Keep detailed driving-technique coaching with Performance Coach and Corner Coach. Tyre Strategy may report tyre-related evidence and likely effects without duplicating corner-by-corner coaching.

## 3. Strategy responsibilities

### 3.1 Pressure monitoring

Monitor each tyre independently:
- Current pressure in ACC's native unit.
- Pressure relative to a validated target operating range for the selected car/tyre.
- Pressure trend over the lap and stint where sampling supports it.
- Left/right and front/rear differences.
- Pressure response to temperature, weather and pit/tyre-change transitions.

Classify pressure as below, within or above target only when a trustworthy target range is available for that car/tyre/condition. If no target is available, report the measured pressure and trend without labelling it optimal or abnormal.

Do not infer a pressure adjustment amount unless a validated target and a validated relationship between the current and desired pressure are available. Advice remains informational; the driver changes pressures manually.

### 3.2 Temperature monitoring

Use validated tyre core temperatures to:
- Track warm-up and cooling behaviour.
- Identify sustained temperature changes and meaningful differences between tyres.
- Correlate temperature with pressure, lap pace, weather and stint phase.
- Identify possible cold/hot operating conditions only when an applicable validated operating window exists.

The decoded inner/middle/outer tread temperature values are currently unreliable. They must not drive recommendations, temperature-distribution diagnoses or pressure/setup advice until separately fixed and validated.

Do not confuse core temperature with instantaneous tread-surface temperature. Do not claim a tread-width temperature pattern from core-temperature telemetry.

### 3.3 Tyre condition

Report only condition evidence that is directly available and validated. At present:
- No trustworthy direct tyre-wear percentage is available.
- No validated direct signal for remaining tread depth or tyre life is available.
- Graining, blistering, flat spotting, cuts and punctures are physical inspection findings, not diagnoses to invent from the current telemetry.
- Driver-reported symptoms may be incorporated in a future phase, but must be labelled as driver feedback and not as measured telemetry.

Until trustworthy condition data exists, the strategy must say that direct tyre condition/wear is unavailable rather than showing a fabricated health percentage.

### 3.4 Degradation and stint-performance monitoring

Tyre degradation may be estimated only as an evidence-based inference from multiple observations over a stint.

Potential supporting evidence:
- Recent valid completed-lap times and sector times.
- Tyre pressure and core-temperature trends.
- Fresh weather and track-condition changes.
- Fuel load and race phase, where validated.
- Traffic, yellow flags, driver errors and other pace confounders, where validated.
- A comparable baseline from the same session/stint or a suitably matched reference.

Rules:
- Exclude invalid laps, out-laps, incomplete laps and laps materially affected by traffic, flags, errors or other known confounders from a clean pace trend.
- Do not attribute slower laps to tyres solely because lap time increased.
- Compare like with like where possible: same track, car, tyre type, comparable fuel/load, conditions and traffic.
- Distinguish observed pace loss from inferred tyre-related pace loss.
- State confidence and relevant confounders.
- If the available evidence cannot separate tyre effects from other causes, report that the cause is uncertain.
- Do not estimate a numeric tyre-life percentage or exact laps remaining without a validated wear/degradation model.

### 3.5 Tyre-type / compound recommendation

Recommend only tyre types or compounds actually available for the selected ACC car and session. Do not assume that every car has the same options or that ACC provides multiple dry slick compounds.

For the current ACC GT3 scope, treat the practical selection primarily as dry tyre versus wet tyre, subject to the actual choices exposed by the selected car/session. Do not invent soft/medium/hard choices or real-world compound families that are not selectable in ACC.

Use the validated weather and track-condition observations that are relevant and available, including:
- Track wetness / wetness state.
- Rain intensity or rain level.
- Ambient temperature.
- Track temperature.
- Other decoded weather state or forecast/horizon fields only according to their validated semantics.

Decision principles:
- Recommend the dry option when observed track conditions support dry running.
- Recommend the wet option when observed track conditions support wet running.
- Treat changing rain and track wetness as a transition, not an instant binary switch.
- Consider the direction and rate of change only when multiple fresh samples or validated forecast/horizon data support it.
- For an approaching weather change, distinguish “prepare for a change” from “change now”.
- Consider expected conditions after a planned pit stop only when the available weather horizon actually covers that period.
- Do not recommend a tyre change from ambient or track temperature alone.
- Do not recommend a change solely because rain is forecast if track conditions do not yet support it.
- If current track state, available tyre choices or relevant weather inputs are missing/stale/ambiguous, return “insufficient information” rather than guessing.
- A tyre-type recommendation is advisory; the driver decides whether and when to change tyres.

### 3.6 Pit-stop tyre advice

Combine current tyre observations, stint trends, expected remaining race distance and available weather information to advise whether a tyre change should be considered at a stop.

Do not claim that a tyre change is mandatory or faster unless the applicable race rules and performance evidence are validated. Do not calculate a tyre-life-to-finish estimate until a validated degradation model exists.

## 4. Inputs and current evidence status

| Input | Current project evidence | Strategy treatment |
|---|---|---|
| Four tyre pressures | Available and validated against ACC | May be used as measured, freshness-gated values |
| Tyre core temperatures | Available and validated | May be used as measured, freshness-gated values |
| Inner/middle/outer tread temperatures | Existing decoded values are unreliable | Exclude from decision logic |
| Direct tyre wear percentage | Not available as trusted telemetry | Do not display or infer a numeric wear percentage |
| Degradation | Not directly measured; may be inferred | Use multi-signal stint evidence only; clearly label inference |
| Ambient temperature | User confirmed weather fields match ACC | Use validated source value and native unit |
| Track temperature | User confirmed weather fields match ACC | Use validated source value and native unit |
| Rain/weather fields | User confirmed all weather fields match ACC | Use decoded weather fields according to their actual semantics and freshness |
| Track wetness | Use only if the existing decoded field is among the user-validated weather fields | Gate on freshness and validated field semantics |
| Tyre type currently selected | Must be confirmed from the existing source/decoder before use | Do not infer selected type from conditions |
| Tyre choices available for selected car | Requires verified source or confirmed ACC selection/options | Do not invent unavailable choices |
| Lap and sector history | Existing Race Engineer/ACC lap history; classification and validity rules apply | Use valid completed laps only |
| Fuel load | Fuel observation exists; strategy semantics remain subject to fuel gates | Use as a pace confounder only when fresh and validated |
| Traffic/flags | Some fields remain candidate or require validation | Use only after their relevant semantics are validated |
| Driver feedback | Not integrated in current phase | Do not assume or fabricate driver feedback |

### Weather validation note

The user has explicitly confirmed that all weather fields currently exposed by the ACC implementation match the values shown in ACC. This closes the user's weather-value comparison for those fields. It does not by itself validate an undocumented interpretation, unit conversion, future forecast horizon or a derived prediction. Preserve the decoded values and use each field only according to its source semantics.

## 5. Analysis cadence and radio behaviour

- Maintain tyre observations continuously from fresh Physics/Graphics/weather snapshots, using the existing acquisition consumers and snapshot aggregation.
- Update stint-level assessments after each newly completed valid lap.
- Reassess immediately when a meaningful weather/track-state transition, pit/tyre-change transition or tyre warning occurs.
- Deduplicate lap-boundary and state-change events; do not create repeated assessments or announcements from the same event.
- Do not announce routine “tyres OK” messages or repeat unchanged pressure/temperature readings.
- Announce meaningful actionable changes: a validated pressure/temperature warning, a significant sustained trend, a credible tyre-related pace concern, or a supported dry/wet change recommendation.
- Critical tyre-related warnings are automatic in all communication modes. Non-critical updates follow the selected Driver-initiated, Balanced or Active mode.
- Suppress repeated unchanged warnings; announce meaningful escalation, resolution or a changed recommendation once.
- Keep routine analysis silent in the background.

## 6. Output and message requirements

Every tyre-related output must identify whether it is:
- **Measured:** directly read from a fresh, validated ACC field.
- **Calculated:** derived from measured inputs using a documented calculation.
- **Inferred:** a possible diagnosis or trend supported by multiple observations.

Examples:
- “Front-left pressure is below the validated target range. Current reading: [measured value].”
- “Tyre core temperatures are rising across the last several laps. No validated operating-window assessment is available for this car.”
- “Pace has dropped over the stint. Tyre degradation is one possible contributor, but traffic and track conditions prevent a confident attribution.”
- “Track wetness and rain are increasing. Prepare for a possible switch to wet tyres; current conditions do not yet justify a change.”
- “Wet tyres are recommended for the current observed track conditions. Driver decision required.”
- “Tyre wear percentage is not available from validated telemetry; remaining tyre life cannot be calculated.”

Do not use these examples as fixed thresholds or claim that the values shown in brackets are available unless the corresponding field is present and fresh.

## 7. UI requirements

The Tyre Strategy UI should:
- Show four tyres separately (FL, FR, RL, RR).
- Display measured pressure and core temperature with freshness/availability state.
- Show target-range status only when a validated target exists.
- Show trends over a stint without presenting inference as measurement.
- Present tyre-type recommendation with its evidence: current track state, rain/weather trend and relevant temperature readings.
- Distinguish “recommended now”, “prepare for possible change” and “insufficient information”.
- Show the reason, confidence and blockers behind an assessment.
- Avoid a single tyre-health percentage while direct wear data is unavailable.
- Never show unreliable inner/middle/outer temperatures as trusted measurements.
- Keep unavailable values visibly unavailable rather than substituting zeros or estimates.

## 8. Validation plan and release gates

### Telemetry and semantics
- Confirm pressure and core-temperature freshness behaviour across session start, normal running, pit entry/exit and tyre changes.
- Confirm initial zero/unpopulated samples do not trigger warnings.
- Confirm the weather fields used by strategy remain aligned with ACC across dry, damp, wet, rain-intensity and changing-temperature scenarios.
- Document each weather field's exact meaning, unit, current/forecast status and horizon before using it in decisions.
- Identify and verify the selected tyre type and available tyre choices for supported cars.
- Keep inner/middle/outer temperatures excluded until corrected and validated.
- Confirm lap/sector history excludes invalid laps, out-laps and incomplete laps.

### Strategy scenarios
- Cold tyres warming up without premature warnings.
- Pressure below/within/above a validated car-specific target range.
- Pressure changes correlated with core temperature.
- Hot track versus cool track with otherwise comparable conditions.
- Dry track with rain forecast but no meaningful wetness change.
- Track becoming wet and track drying after rain.
- Weather changing during a stint and across a pit-stop horizon.
- Pace loss with tyre evidence versus pace loss caused by traffic, flags, fuel or driver error.
- Pit stop with tyre change and without tyre change.
- Stale or missing tyre/weather streams; no fabricated recommendation.
- Unsupported car/tyre choice or missing target data; report insufficient information.

### Release conditions
- No unsupported pressure target, temperature threshold, wear percentage or remaining-life estimate.
- No false compound/tyre-type options; recommendation limited to choices actually available in ACC for the selected car/session.
- No recommendation based on stale or unvalidated inputs.
- Inferences explain evidence and uncertainty; no single-signal definitive diagnosis.
- Radio announcements are actionable, event-driven and deduplicated.
- No ACC/game/MFD/setup/tyre control writes.
- Automated tests, frontend build and Windows live-ACC validation are completed before claiming release readiness.

## 9. Confirmed decisions and remaining gates

### Confirmed by user
- Tyre Strategy uses the full adaptive, evidence-based approach (option C): correlate pressure, temperature, stint trends, weather and available driver feedback, but never fabricate missing data.
- The strategy is limited to the data actually available and validated in the ACC project.
- All currently exposed weather fields have been compared by the user with ACC and confirmed to match.
- Four tyre pressures and tyre core temperatures are validated in the current telemetry audit.
- Inner/middle/outer temperatures are unreliable and must not drive decisions.
- Direct tyre wear is unavailable as trusted telemetry; degradation can only be inferred with supporting evidence.
- Tyre-type/compound recommendations must consider track and weather conditions.
- Race Engineer is strictly read-only; the driver makes all changes in ACC.

### Remaining validation / implementation gates
- Verify exact weather field semantics, units and whether each field is current state or forecast/horizon before using it in a derived decision.
- Verify how the selected tyre type and available tyre options are exposed for each supported car/session.
- Establish validated car/tyre-specific pressure target ranges and temperature operating windows; do not use generic values.
- Resolve inner/middle/outer temperature reliability if that capability is desired.
- Identify any trustworthy direct tyre-wear source; otherwise keep wear and remaining tyre life unavailable.
- Develop and validate a multi-signal degradation model before producing numeric degradation or remaining-life estimates.
- Validate dry/wet transition recommendations in controlled ACC sessions.
- Integrate driver feedback only as a separate, explicitly labelled input in a later phase.

## 10. Relationship to other Race Engineer documents

This is the dedicated Tyre Strategy specification. The telemetry audit/roadmap remains the cross-strategy implementation and validation tracker. Fuel Strategy is documented separately in `docs/RACE_ENGINEER_FUEL_STRATEGY.md`. Shared telemetry contracts and evidence should be maintained centrally and referenced here rather than duplicated.
