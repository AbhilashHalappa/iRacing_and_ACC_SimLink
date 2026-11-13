# ACC Race Engineer — Setup Strategy

**Status:** Strategy specification agreed for the documentation phase  
**Scope:** In-session/on-board adjustable settings first; garage-only setup optimisation is deferred  
**Implementation:** Not yet implemented as a complete strategy engine  
**Authority:** Advisory and read-only; the driver manually changes and confirms every setting

## 1. Purpose

Setup Strategy helps the driver make evidence-based adjustments to settings that can be changed from the car while remaining in an ACC session. It then evaluates the observed effect of those changes and builds a persistent, track- and car-specific setup history.

The long-term goal is to identify useful baseline settings and condition-specific variations from repeatable evidence, not to prescribe generic values or assume that a recommended change was applied.

The initial scope prioritises on-board adjustments. Garage-only setup work is explicitly deferred to a later phase.

## 2. Scope and ownership

### 2.1 Initial scope: on-board adjustments

Potential settings include, only where the selected car and ACC session actually expose them as adjustable on-board controls:

- Brake bias.
- Traction control settings and stages.
- ABS settings and stages.
- Engine map or engine-related selectable modes.
- Other verified driver-adjustable controls available in that car.

This list is not a claim that every setting exists, is adjustable while driving, or has the same meaning/range in every car. The available controls, labels, ranges, increments and direction of effect must be identified per car and validated before recommendations are enabled.

Setup Strategy may recommend an adjustment and explain its expected benefit and trade-off. It must never send inputs, operate the car controls, write to ACC, change a setting or assume the driver followed the recommendation.

### 2.2 Deferred scope: garage setup

Settings that require garage access or a setup-screen visit are deferred. Examples may include springs, dampers, ride height, aero, alignment and other garage-only parameters, subject to the selected car's actual setup options.

Do not mix garage-only recommendations into the initial on-board workflow. The future garage phase should reuse the same setup-history and comparison foundation.

### 2.3 Ownership boundaries

- Setup Strategy owns recommendations about adjustable vehicle settings and evaluation of their observed effects.
- Brake Strategy owns brake temperature and pad/disc condition analysis. Setup Strategy may consume its validated summary when relevant, but must not duplicate its component-health alerts.
- Tyre Strategy owns tyre pressure, temperature, condition and degradation assessment. Setup Strategy may consume validated tyre summaries as context.
- Pace Strategy owns race-position tactics and immediate-opponent focus.
- Traffic Strategy owns physical traffic context.
- Performance Coach and Corner Coach retain detailed driving-technique and corner-by-corner coaching.
- Pit-Stop Strategy owns integrated stop timing.
- The driver retains control of all setup changes.

## 3. Data sources and evidence classes

Setup Strategy must distinguish three kinds of information.

### 3.1 Automatically captured telemetry

Capture relevant telemetry and session context through the existing application telemetry pipeline, subject to freshness and validation. Useful context includes:

- Track identity and layout, where reliably identified.
- Car identity/model and relevant session configuration.
- Session identity and timestamps.
- Weather and track conditions, using the exposed fields whose values the user has validated against ACC.
- Lap and sector times, validity and lap history.
- Speed, throttle, brake, steering and other validated vehicle-dynamics channels.
- Tyre and brake summaries from their owning strategies, where validated.
- Fuel load and race/session context where validated.
- Traffic context only where association and timing are reliable.

Automatic telemetry capture records what the car did; it does not by itself prove which setup setting was active.

### 3.2 Driver-confirmed setting changes

Because ACC may not expose every current setup/control value as telemetry, the system must support explicit driver confirmation of a change.

A confirmed adjustment record should include, where available:

- Setting name and car-specific control identity.
- Previous value and new value.
- Units, scale and increment, only if known.
- Time/session/lap at which the driver says the change was applied.
- Whether the change was recommended by Race Engineer or made independently.
- Optional driver feedback about the symptom and perceived result.

A recommendation is not a change record. A proposed value must remain marked **recommended / not confirmed** until the driver confirms the actual setting. If the driver reports a different value, record the reported value rather than the recommendation.

### 3.3 Setup-file import

Setup-file import is a supporting source for setup baselines and garage configurations, not a substitute for confirmation of an in-session adjustment.

When supported and safely parsed, an imported setup file may provide:
- Car and setup identity.
- Garage setup values present in the file.
- A named baseline/version and import timestamp.

The importer must preserve source provenance and handle unsupported, missing or car-incompatible fields as unknown. Do not assume a setup file reflects the current live car state unless the driver explicitly associates it with that session. File import must never write a setup into ACC.

## 4. Setup history and persistence

Maintain a persistent, append-oriented history so the system can compare settings and outcomes over time.

The history should be keyed and filterable by:

- Car identity/model.
- Track and layout.
- Session and setup version.
- Weather and track conditions.
- Setting name and before/after values.
- Adjustment timestamp and lap boundary.
- Driver confirmation status and source provenance.

Each adjustment should create an event rather than silently overwriting the previous value. Preserve the sequence of settings and the telemetry observations associated with each period.

Store enough session context to make comparisons meaningful, but avoid retaining unnecessary high-frequency raw telemetry indefinitely. Prefer compact lap/sector summaries and bounded evidence windows around each adjustment, with a retention policy that can be configured later.

A history record must make it possible to answer:
1. What setting was changed?
2. What was the value before and after?
3. Who/what confirmed the change and when?
4. What conditions applied before and after?
5. What measurable results changed?
6. How strong is the evidence that the setting contributed to the result?

## 5. Before/after evaluation

Evaluate an adjustment only after the driver confirms it and the system can identify a reasonable pre-change and post-change observation window.

Compare, where data is valid and comparable:

- Valid lap and sector pace.
- Lap-to-lap consistency and variability.
- Repeatable sector or corner-related performance indicators, without duplicating detailed coaching.
- Relevant vehicle-response indicators supported by validated telemetry.
- Tyre and brake context from their owning strategies.
- Driver feedback, if provided.

Use multiple laps where practical. Exclude invalid, incomplete and out-laps from pace comparisons unless a separate, explicitly justified analysis requires them.

### 5.1 Control for confounding factors

A faster lap after an adjustment does not prove that the adjustment caused the improvement. Account for:

- Traffic and clear-air differences.
- Fuel-load changes.
- Tyre age, pressure and temperature.
- Brake condition and temperature.
- Weather and track evolution.
- Different compounds or tyre changes.
- Driver input and consistency.
- Session phase, flags and interruptions.
- Track limits, invalid laps and incomplete sectors.

If the conditions differ materially, mark the comparison as limited or inconclusive instead of presenting a false result.

### 5.2 Learning and confidence

Classify findings in plain language, for example:

- **Insufficient evidence:** too few or incomparable observations.
- **Promising:** observed improvement, but not yet repeatable or sufficiently controlled.
- **Repeatable improvement:** improvement reproduced across comparable runs.
- **Mixed trade-off:** one area improved while another worsened.
- **No clear benefit:** evidence does not show a meaningful improvement.
- **Negative result:** repeatable deterioration under comparable conditions.

Do not invent statistical confidence, causal certainty or universal best values. Any numeric confidence score or threshold requires a documented method and validation.

A setting should be called a preferred or proven value only after repeatable, comparable evidence supports it. Otherwise describe it as a candidate or previously tested value.

## 6. Recommendation behaviour

A recommendation should state:

1. The setting to consider changing.
2. The proposed direction/value only when the car-specific range and increment are validated.
3. The telemetry or driver feedback supporting the recommendation.
4. The expected benefit.
5. The likely trade-off or risk, where known.
6. The evidence level and relevant uncertainty.

Do not recommend a numeric value if the current value, valid range, increment or setting semantics are unknown. In that case, describe the observed issue and request/require the missing setting information rather than guessing.

Avoid repeated recommendations while the setting and evidence have not materially changed. If a prior recommendation becomes obsolete, explain why.

The strategy must not recommend changing several interacting settings at once unless there is a validated reason. Prefer controlled, traceable adjustments so the effect can be evaluated.

## 7. Communication and interaction

Setup Strategy follows the global Race Engineer communication modes and radio controls.

- **Driver-initiated:** remain quiet for routine setup observations; provide details when requested. Validated critical warnings from the owning strategy remain governed by the global critical-alert rule.
- **Balanced:** announce a meaningful, evidence-backed on-board adjustment opportunity without repeatedly restating it.
- **Active race engineer:** provide proactive but concise setup observations when a useful change is supported; avoid chatter after every telemetry fluctuation.
- Allow the driver to confirm whether a recommended adjustment was applied and enter the actual value if ACC does not expose it.
- Allow the driver to record an independently made change.
- Allow the driver to provide optional feedback about whether the car improved, worsened or felt different.
- Keep recommendation, confirmation and measured outcome as separate states.

The input mechanism for confirming changes must be selected during implementation in a way that fits the existing Race Engineer interaction design. Do not assume voice recognition or free-form speech is available.

## 8. UI and history presentation

The Setup Strategy UI should provide:

- Current session and car/track context.
- On-board settings that are actually supported for the selected car.
- Current value and source, when known.
- Recommended adjustment, reason, expected effect and evidence level.
- Clear **recommended**, **driver-confirmed**, **observed** and **unknown** states.
- A chronological adjustment history.
- Before/after comparison for each confirmed change.
- Filters for car, track, conditions and setting.
- A track/car setup summary showing repeatable values separately from untested candidates.
- Explicit warnings when a comparison is inconclusive or context differs.

Do not display a recommended value as the live current value. Do not show a setup file as the active setup unless its association with the session is confirmed.

## 9. Shared data and architecture

- Consume existing decoded telemetry consumers and freshness-aware snapshots.
- Reuse existing lap/session history and track/car identity sources where available.
- Consume Tyre and Brake summaries through defined interfaces; preserve their ownership.
- Store setup change events and compact comparison summaries in application-owned persistence.
- Keep analysis and recommendation logic in the service/strategy layer, not in React components or high-frequency acquisition callbacks.
- Do not add another ACC shared-memory reader or acquisition pipeline.
- Do not write to ACC shared memory, send control inputs or automate setup changes.
- Preserve provenance for telemetry-derived values, driver-confirmed values and imported setup-file values.

## 10. Validation plan and release gates

1. **Car/control inventory:** identify the actual on-board adjustable settings for each supported car and session.
2. **Setting semantics:** validate names, current values, units, ranges, increments and direction of effect against ACC.
3. **Source coverage:** establish which settings are exposed by telemetry, which require driver confirmation and which may be read from setup files.
4. **Manual confirmation:** test that a recommendation remains unconfirmed until the driver records the actual applied value.
5. **Setup-file import:** validate file parsing, car association, missing/unknown fields and provenance. Import must be read-only.
6. **Adjustment event history:** verify chronological records survive session changes and application restarts without overwriting prior events.
7. **Before/after windows:** confirm lap/sector observations are assigned to the correct pre-change and post-change periods.
8. **Confounder handling:** test traffic, fuel, tyre, brake, weather, track evolution and driver variation.
9. **Repeatability:** compare repeated changes/runs before labelling a value preferred or proven.
10. **No-change and negative tests:** verify inconclusive or worse results are reported honestly and do not become false recommendations.
11. **Read-only guarantee:** confirm no game control, setup write, MFD action or automatic adjustment occurs.
12. **Regression:** ensure existing Race Engineer, Performance Coach, Corner Coach and other strategy behaviour remains unchanged.

A setting remains recommendation-ineligible until its car-specific semantics and available range are understood. A setup-file value or driver-reported value must retain its provenance and must not be presented as telemetry-measured unless it truly came from a validated telemetry source.

## 11. Phasing and implementation decision

### Phase A — in-session setup learning

- Inventory and validate supported on-board settings.
- Capture telemetry and compact lap/session context automatically.
- Add driver confirmation for actual setting changes not exposed by telemetry.
- Create persistent adjustment history.
- Implement evidence-gated before/after comparison and cautious recommendations.
- Support setup-file import as a read-only supporting source where practical.

### Phase B — garage setup strategy (deferred)

- Extend the same history model to garage-only setup parameters.
- Compare imported/current garage setup versions.
- Build track-, car- and condition-specific baseline recommendations from repeatable evidence.
- Keep all changes manual and driver-controlled.

This document defines the agreed strategy only. It does not claim that setup capture, setup-file import, history, recommendations or UI have been implemented. No garage setup recommendations are in the initial phase.
