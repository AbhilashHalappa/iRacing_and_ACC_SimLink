# ACC Race Engineer — Car Health Strategy

**Status:** Strategy specification agreed for the documentation phase  
**Scope:** ACC vehicle damage, validated mechanical warnings and evidence-based abnormal-behaviour observations  
**Implementation:** Not yet implemented as a strategy engine  
**Authority:** Advisory only; the driver remains in control of the car and all in-game actions

## 1. Purpose

Car Health Strategy monitors the condition of the vehicle during a session and gives the driver concise, evidence-backed information when the available ACC telemetry indicates damage, a validated warning, or a meaningful change in vehicle behaviour.

It must answer three questions:

1. What has measurably changed in the car's condition?
2. Is there a validated ACC warning or a sufficiently supported abnormal behaviour?
3. Does the evidence justify advising the driver to inspect the car, reduce risk, or consider a pit stop?

The strategy must not turn an uncertain signal into a definitive mechanical diagnosis. It must distinguish direct telemetry from calculated trends and inferred possibilities.

## 2. Scope and ownership

Car Health Strategy owns:
- Observing available damage channels and their changes.
- Reporting validated ACC mechanical or vehicle warnings, if their source and meaning are confirmed.
- Tracking damage changes across a session and after pit repairs.
- Identifying repeatable abnormal vehicle behaviour only when the required telemetry, baseline and confounder checks are validated.
- Giving a concise recommendation to inspect the car or consider a pit stop when the evidence supports it.
- Retaining a clear record of the signal, confidence and reason for each alert.

It does not own:
- Detailed driving-technique coaching, corner diagnosis or setup coaching; those remain with Performance Coach and Corner Coach.
- Brake pad/disc life and brake-temperature strategy; Brake Strategy owns those component observations.
- Tyre pressure, temperature, condition and degradation; Tyre Strategy owns those observations.
- Race-position tactics or physical traffic awareness; Pace and Traffic strategies own those areas.
- Integrated pit timing and stop execution; Pit-Stop Strategy will own that work and is intentionally defined last.
- Any control of the car, setup, MFD, pit menu or ACC state.

Car Health may consume validated summaries from Brake and Tyre strategies, but it must not duplicate their specialist analysis or create conflicting alerts.

## 3. Evidence and telemetry inventory

The following reflects the current project audit. Availability does not automatically mean that a field is ready for diagnosis.

| Signal / requirement | Current source or evidence | Status | Permitted use |
|---|---|---|---|
| General/body damage channels | Physics `car_damage[5]`; user-controlled pit repair returned damage to zero | **Available — validated as changing channels** | Report that damage telemetry has changed or that a non-zero damage indication is present, subject to freshness and raw-value checks. |
| Individual body/component mapping | Same five damage channels | **Not fully validated** | Do not label a channel as front bumper, rear, body panel or another specific component until mapping is established. |
| Suspension damage | Physics `suspension_damage[4]`; two channels varied in target capture | **Available — candidate** | Retain for observation/debugging only. No corner-specific diagnosis or warning until semantics and mapping are validated. |
| Collision event | No dedicated trusted collision event identified | **Unavailable as a direct event** | A damage change may be reported as a damage change, not proof that a collision occurred. |
| Engine damage | No separately trusted engine-damage field identified | **Unavailable as a direct diagnosis** | Never diagnose engine damage from temperature, RPM or generic damage channels alone. |
| Engine state/fault flags | Engine-state candidates and unresolved tail fields | **Candidate / incomplete** | Do not announce a fault until raw codes, meanings, transitions and lifecycle are validated against ACC. |
| Water / oil temperature and other engine readings | Some temperature and tail-field candidates exist; semantics and coverage are incomplete | **Candidate / incomplete** | Do not use generic thresholds or infer engine failure. Use only individually validated fields with confirmed units and car-specific limits. |
| Brake pad and disc values | Four-corner values are working in ACC; expected unit interpretation is mm but selected-car scale/direction/service limits remain gated | **Available — observed; interpretation partly open** | Leave detailed component condition and life interpretation to Brake Strategy. Car Health may consume only its validated status summary. |
| Tyre condition | Pressure and core temperatures validated; direct wear percentage unavailable; degradation is inferred | **Mixed** | Leave tyre assessment to Tyre Strategy; do not independently diagnose tyre damage or remaining life. |
| Vehicle dynamics | Physics speed, throttle, brake, steering and other channels | **Mixed: core inputs validated; some derived channels candidate** | May support future abnormal-behaviour analysis only after the relevant axes, units, timing and baseline are validated. |
| ACC fault messages | No complete trusted fault inventory identified | **Unavailable / requires targeted audit** | Report only explicitly exposed and validated ACC messages. |

### 3.1 Current damage interpretation

The five `car_damage` channels have been observed changing, and a controlled pit repair returned the values to zero. This supports using them as general damage observations.

It does not yet establish:
- The exact physical component represented by each array element.
- A universal scale or unit for the values.
- A car-independent threshold for minor, moderate or severe damage.
- Whether each channel has identical semantics across every car.
- A reliable relationship between a damage value and lap-time loss, handling risk or mechanical failure.

Therefore, the initial implementation should preserve raw values and report only what is directly supported. Do not convert them to a percentage, severity category or component name without additional evidence.

### 3.2 Suspension and engine limitations

Suspension damage channels remain candidates. The observed variation is not sufficient to assign a wheel/corner or determine what a value means. Keep them out of driver-facing diagnosis until a controlled test establishes channel mapping, value direction, units and repair/reset behaviour.

No separately trusted engine-damage field or complete fault inventory is currently established. Engine temperature, RPM, power or generic engine-state values must not be used as substitutes for a direct engine-damage measurement. Any future engine warning needs its own source and validation record.

## 4. Decision and alert rules

### 4.1 Direct observations first

The strategy may state:
- A validated damage channel has changed.
- A validated damage indication is currently present.
- A previously observed damage indication has returned to its verified repaired/baseline state.
- A validated ACC mechanical warning is active, cleared or has changed severity.

It must not state a cause unless the source explicitly provides one or multiple independent validated signals support a carefully qualified inference.

### 4.2 Change detection and baselines

- Keep a session baseline only after the relevant stream is fresh and stable.
- Detect changes using raw values and a validated noise/deadband model; do not invent a threshold.
- Distinguish a new damage change from an already-known persistent value.
- Handle stream reconnects, session changes and car changes by invalidating or re-establishing baselines.
- Do not interpret a missing, stale, non-finite or implausible sample as damage or as proof that the car is healthy.
- Treat a pit repair as confirmed only when the relevant observed values return to the validated repaired state. A pit entry alone is not proof that repairs occurred.
- Keep before/after values and timestamps so a driver can understand why an alert was raised.

### 4.3 Abnormal vehicle behaviour

Abnormal behaviour is an inference, not a direct damage measurement. It may be considered only when:
- The input channels and their units/sign conventions are validated.
- Samples are fresh and sufficiently time-aligned.
- A meaningful baseline exists for the same car and comparable conditions.
- The pattern repeats or is corroborated by independent evidence.
- Traffic, tyre state, brake state, weather, kerbs, track surface, driver inputs, fuel load and session transitions are considered as possible confounders.
- The strategy can describe the observed change without claiming an unsupported cause.

If these conditions are not met, report the measured change or say that there is insufficient evidence. Do not diagnose suspension, steering, engine or drivetrain failure from one unusual lap or one sensor.

### 4.4 Severity

No universal damage thresholds or generic severity bands are approved at this stage.

Severity may be used only when:
- ACC provides a validated severity/status field, or
- A car-specific threshold has been established through controlled testing and documented evidence.

Until then, use neutral wording such as “damage reading changed” or “damage indication present.” Do not use “critical,” “unsafe,” “engine failure,” or similar language based only on an uncalibrated numeric value.

## 5. Recommendations

Recommendations must be proportional to the evidence.

Allowed when supported:
- “Damage reading has changed; monitor the car.”
- “ACC reports [validated warning text].”
- “The same abnormal behaviour has repeated; consider inspecting the car at a suitable stop.”
- “Damage values returned to the previously validated repaired state.”

Not allowed without additional evidence:
- “You have front suspension damage.”
- “The engine is failing.”
- “The car is unsafe to drive.”
- “You lost X seconds because of damage.”
- “Pit now” based solely on an uncalibrated damage value.

A recommendation to inspect or pit is advisory. The driver decides whether and when to act. Pit timing, mandatory-stop rules, tyre/fuel service and integrated stop planning belong to Pit-Stop Strategy.

## 6. Communication behaviour

Car Health follows the Race Engineer's global communication mode and alert controls.

- **Driver-initiated:** remain quiet for routine observations; validated critical ACC warnings remain automatic.
- **Balanced:** announce new meaningful damage changes and validated warnings; suppress routine unchanged readings.
- **Active race engineer:** provide concise updates when a meaningful condition changes, but do not repeatedly narrate stable damage values.
- Critical warnings are automatic in every mode only when their source and severity are validated.
- Do not repeat the same unresolved warning on every update or lap.
- Announce a meaningful severity change, a newly validated warning, or a confirmed clear/repair transition.
- If a warning clears, say so only when the source's clear lifecycle is validated.
- Mute/resume applies to non-critical radio only; critical warnings remain available.
- Details on request should include the observed signal, value/unit if validated, change from baseline, timestamp/freshness and why the strategy is concerned.
- Never present an inferred possibility as a confirmed ACC fault.

## 7. UI and data presentation

The Car Health view should distinguish:
- **Direct observations:** raw damage or validated ACC warning.
- **Calculated changes:** difference from a known baseline or trend.
- **Inferences:** qualified abnormal-behaviour assessment, with evidence and confidence.
- **Unavailable information:** explicit indication when a component or diagnosis is not supported.

For each displayed item, include the component only if its mapping is validated, the current value only if its unit/scale is understood, and a status only if its threshold or source meaning is validated.

Avoid decorative health percentages, invented red/amber/green states, universal component-life estimates or a false “all healthy” result when data is missing. A stale or unavailable signal must be shown as unavailable, not normal.

## 8. Shared data and architecture

- Consume the existing Physics and Graphics consumers through the existing freshness-aware snapshot/service boundary.
- Do not add another ACC shared-memory reader, mapping, acquisition queue or competing telemetry pipeline.
- Preserve stream-specific timestamps and freshness. Do not combine Physics and Graphics samples as though they were simultaneous unless timestamp alignment supports it.
- Reuse session identity, car identity, lap history and pit/repair event context where available.
- Keep damage observation and alert state in the Race Engineer service layer, not in the high-frequency acquisition callback or React UI.
- Do not alter existing Race Engineer, Performance Coach, Corner Coach, fuel, tyre or brake calculations to implement Car Health.
- Any cross-strategy summary must have one owner and a clear source; Car Health must not duplicate Brake or Tyre alerts.

## 9. Validation plan and release gates

Before enabling driver-facing diagnosis, validate each source independently.

1. **Damage channel transition:** record all five `car_damage` values before and after a controlled, repeatable damage event. Confirm which channels change, value direction, scale, repeatability and car dependence.
2. **Repair transition:** record values before pit entry, during/after repair and after rejoining. Confirm whether each channel resets, decreases or remains unchanged. Do not assume pit entry means repair.
3. **Component mapping:** vary one damage source at a time where safely/repeatably possible. Map a channel to a named component only with repeatable evidence.
4. **Suspension channels:** establish all four channel meanings, corner order, units, value direction and repair behaviour before use.
5. **Engine/fault inventory:** correlate every candidate flag/message with ACC HUD or an explicit ACC state transition. Record raw code, decoded meaning, activation, clearing and reconnect behaviour.
6. **Dynamics baseline:** validate units, axes, signs, timestamps and repeatability before using vehicle-dynamics changes for abnormal-behaviour inference.
7. **False-positive tests:** include kerbs, traffic, tyre/brake changes, weather changes, fuel changes, driver input variation and normal session transitions.
8. **Freshness/reconnect tests:** verify stale data, stream failure, reconnect, new session and car changes do not create false alerts.
9. **Radio tests:** verify mode behaviour, duplicate suppression, severity changes, clear events, mute/resume and critical-warning handling.
10. **Regression:** confirm existing Overview, Fuel, Tyre, Brake, Pace, Traffic, Race-State, Performance Coach and Corner Coach behaviour is unchanged.

A signal remains excluded until its own gate passes. Validation of general damage-channel movement does not validate component mapping, severity thresholds or causal diagnosis.

## 10. Acceptance criteria

Car Health Strategy is ready for implementation only when:
- Every driver-facing direct observation has a documented source, meaning, unit/scale, freshness rule and validation evidence.
- Component labels and severity categories are used only where validated.
- Candidate suspension/engine/fault signals remain hidden from diagnosis until their individual gates pass.
- Inferences require a comparable baseline, repeatable evidence and confounder checks.
- Stale or missing telemetry never becomes a “healthy” status.
- Alerts are deduplicated and follow the global communication mode.
- No false collision, engine, suspension or safety diagnosis is made.
- No new shared-memory reader or acquisition path is introduced.
- All recommendations remain read-only and the driver retains control of every action.

## 11. Current implementation decision

This document defines the strategy; it does not authorize or imply that the Car Health engine, UI, alerts or live diagnosis have been implemented. The current phase is strategy definition and shared telemetry auditing. Implementation should begin only after the remaining strategy specifications and the combined telemetry/data-ownership plan are complete.
