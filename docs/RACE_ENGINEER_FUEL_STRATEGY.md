# ACC Race Engineer — Fuel Strategy

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/stage2-decoded-fanout  
**Status:** Stage 2 live fuel sufficiency integrated; three-lap safety reserve displayed; pit/refuelling recommendations pending  
**Last updated:** 2026-11-15

## 1. Purpose

The Fuel Engineer calculates whether the car can finish the race with its current fuel, whether fuel saving is sufficient, or whether a refuelling stop is required. It should recommend the **lowest practical fuel load that safely completes the race**, avoiding unnecessary fuel weight and unnecessary pit stops.

This document defines the fuel strategy only. Other Race Engineer strategies must have their own dedicated documents.

## 2. Non-negotiable operating rules

- Race Engineer is strictly read-only. It observes telemetry and gives advice; it must never operate ACC controls, the MFD, pit limiter, pit request, refuelling, setup or the car.
- The driver makes every decision and manually enters any recommended fuel amount in ACC.
- Never present an estimate as a measured value. Identify measured, calculated and inferred information distinctly.
- Never produce a fuel target from stale, invalid, contradictory or insufficient inputs.
- Do not invent race rules, tank capacity, pit windows, fuel limits or car-specific values.
- Do not recommend an amount that exceeds verified tank capacity.
- Do not recommend an extra stop solely to remove a small amount of fuel weight; compare the benefit with pit-lane loss and race constraints when those inputs are validated.

## 3. Calculation cadence and radio behaviour

### 3.1 Background calculation

- Run a fuel strategy assessment at the beginning of every lap, triggered by a reliable start/finish-line lap transition.
- Recalculate the estimate in the background as fresh fuel, consumption, race-distance, pit and session-state inputs change.
- Update the rolling consumption and lap-time averages after each newly completed valid lap.
- Reassess after a pit/refuelling transition when fresh telemetry confirms the new fuel level.
- Do not repeatedly run or announce the same assessment within a lap. A lap-start trigger must be deduplicated so one crossing produces one assessment.
- Critical fuel conditions may be assessed between lap boundaries and must not wait for the next lap.

### 3.2 Announcements — no lap-by-lap spam

The calculation happens every lap, but routine results remain silent. Do not announce “fuel OK”, “no stop required”, or unchanged calculations on every lap.

Speak only when a driver-actionable fuel event occurs, primarily:
- Refuelling becomes necessary and a pit recommendation is ready.
- A critical fuel shortfall or a rapidly worsening projection requires immediate attention.
- The recommended pit lap or required amount changes materially and the previous advice would otherwise mislead the driver.
- A previous refuelling recommendation is no longer required, if it has already been announced and leaving it uncorrected could cause an unnecessary stop.

Suppress duplicate announcements while the same condition and recommendation remain active. Announce a meaningful change or escalation, not repeated copies of an unresolved warning.

Critical fuel warnings are automatic in all communication modes. A refuelling recommendation must be delivered as an actionable strategy event according to the selected communication mode; it must not be hidden merely because the driver selected a quiet mode. Routine calculations remain silent in every mode.

## 4. Safety reserve

**Initial reserve: 3 laps.**

- The reserve is calculated using the current rolling fuel-consumption estimate.
- Reserve fuel = 3 × estimated litres per lap.
- Target finish fuel = estimated fuel needed to reach the actual race finish + three-lap reserve.
- The reserve is a safety margin, not a substitute for correct race-distance, pit-rule or fuel-capacity inputs.
- Keep the reserve configurable in a later settings phase; use 3 laps as the approved initial default.
- If consumption is not trustworthy, do not manufacture a reserve in litres from an unreliable estimate. Report that the strategy cannot be calculated reliably.

## 5. Inputs and evidence requirements

| Input | Intended source / treatment | Gate |
|---|---|---|
| Current fuel remaining | Physics decoded fuel value; user confirmed ACC presents this value in litres (L). Preserve its numeric value without conversion. | Fresh Physics sample; finite and non-negative |
| Fuel per lap | Graphics `fuel_per_lap_l`; user confirmed observed values match ACC. | Fresh Graphics sample; finite and non-negative; sanity-check against completed-lap observations |
| Fuel used | Graphics `used_fuel_l`; live increase and reset on a new session were confirmed. | Observation/cross-check only until pit/refuelling reset semantics are validated |
| Last five valid lap times | Completed-lap history; exclude invalid, out-laps and incomplete laps. | Use up to five valid recent laps; expose reduced confidence when fewer than five are available |
| Consumption history | Fuel change over completed laps, where reliable; compare with Graphics fuel-per-lap. | Account for refuelling, pit transitions and session resets; do not mix across a reset |
| Remaining race time | Graphics `session_time_left_s`. | Fresh Graphics sample and validated session state |
| Race laps / lap limit | Graphics race-distance fields. | Candidate semantics must be validated before strategic use |
| Actual finish behaviour | ACC timed-race finish-line rules, including the extra lap behaviour after timer expiry where applicable. | Validate per session type; timer reaching zero alone is not the finish |
| Tank capacity | Static `max_fuel` candidate. | Verify against the current car and ACC before using as a hard constraint |
| Pit and mandatory-stop rules | Static/Graphics rule and pit-state fields. | Validate enum meanings, units, windows and applicability before using |
| Pit-lane loss | Measured or validated track/session-specific pit loss. | Do not assume a universal value |
| Weather, traffic and pace changes | Use only when supported by fresh observations and a defensible consumption relationship. | Adjust estimates only with evidence; otherwise widen uncertainty |

### Rolling lap-time average

- Use the most recent five valid completed lap times as the rolling average.
- Exclude invalid laps, out-laps and incomplete laps.
- Recalculate when a new valid lap completes.
- If fewer than five valid laps exist, use the available valid laps only if the confidence policy permits it; otherwise state that race-finish prediction is not yet reliable.
- Do not use a single anomalous lap as a permanent pace assumption.

### Consumption estimate

Use the validated Graphics fuel-per-lap value as a current reference and compare it with observed fuel consumption over completed laps when the observations are reliable. Account for refuelling and pit transitions. If sources disagree materially, lower confidence and do not issue a precise refuelling amount.

## 6. Race-finish prediction

The strategy must estimate the number of laps remaining to the **actual finish**, not simply divide remaining session time by an arbitrary lap time.

- For lap-limited races, use the validated race-lap limit and completed-lap count.
- For timed races, combine fresh remaining session time with the rolling average of the last five valid lap times, then apply the validated ACC finish-line/extra-lap behaviour for that session type.
- Include any validated formation-lap or other required fuel consumption when applicable.
- Recalculate at every lap start and when a material race-state transition occurs.
- If lap-limit semantics, timer state, finish-line behaviour or session type are not validated, do not claim an exact number of laps to finish.

Core estimate:

`Fuel to finish = expected remaining race laps × estimated litres per lap`

`Three-lap reserve = 3 × estimated litres per lap`

`Target fuel at finish = fuel to finish + three-lap reserve`

`Projected surplus/shortfall = current fuel − target fuel`

The calculations must also account for uncertainty in lap count and consumption. Where appropriate, use a conservative upper estimate rather than false precision.

## 7. Pit and refuelling decision

The strategy should first determine whether the current fuel can reach the actual finish with the three-lap reserve.

Possible internal outcomes:
- **No stop required:** current fuel safely covers the finish target. Keep silent.
- **Fuel saving may be sufficient:** calculate a realistic per-lap saving target only when a credible baseline and achievable target are available. Keep routine status silent; alert if the target becomes unrealistic or urgent.
- **Refuelling required:** identify a feasible pit lap and calculate the required addition.
- **Insufficient data:** do not give a precise target; announce only when the missing/invalid data prevents a safe actionable recommendation or creates a critical risk.

### Fuel to add when pitting

For a recommendation to pit at the end of the current lap:

1. Estimate fuel consumption from now until pit arrival.
2. Calculate projected fuel on pit arrival.
3. Calculate the fuel required for the remaining race from that point.
4. Add the three-lap reserve to the required finish fuel.
5. Subtract projected fuel on pit arrival.
6. Clamp the requested addition at zero.
7. Check the result against verified tank capacity and any validated refuelling constraints.

`Fuel to add = max(0, target fuel for remaining race + reserve − projected fuel on pit arrival)`

The displayed amount must be rounded to a practical ACC MFD increment only after the MFD increment is validated. Do not invent precision or an unsupported increment.

### Pit timing and avoiding overweight

- Recommend “pit at the end of this lap” only when the driver has enough time to enter the pit lane and the recommendation is based on fresh data.
- Otherwise recommend a later feasible lap or state that the pit window cannot be determined.
- Compare a one-stop or multi-stop plan only when tank capacity, pit loss, refuelling limits and mandatory-stop rules are validated.
- Do not suggest carrying unnecessary excess fuel, but do not trade away the three-lap reserve to save weight.
- Never recommend an infeasible stint or fuel addition beyond capacity. If a multi-stop plan is needed, explain that constraint and give only a validated feasible plan.

## 8. Reassessment and recommendation lifecycle

- Recalculate at each lap start, after material fuel-consumption changes, after refuelling, and after meaningful race-distance/session-state changes.
- A pit recommendation remains active until the driver pits, the fuel projection changes, the race state changes, or the recommendation is otherwise resolved.
- After refuelling, use the newly observed current fuel; do not assume the requested amount was added.
- Do not infer successful refuelling from the recommendation or from an MFD request value.
- If the driver does not pit as recommended, recalculate from the new telemetry and revise the advice only when needed.
- If a recommendation becomes obsolete, correct it once; do not keep repeating the correction.

## 9. Radio message format

Messages should be concise and actionable. Include the lap and units where useful.

Examples:
- “Fuel warning: recommend pitting at the end of this lap. Add 24 litres.”
- “Fuel critical: current projection is below the three-lap reserve. Pit as soon as safely possible.”
- “Fuel estimate is unreliable: race distance or consumption data is unavailable. No safe refuelling amount can be calculated.”
- “Fuel update: the previous stop recommendation is no longer required.”

Do not speak routine no-stop confirmations or repeat an unchanged recommendation every lap.

## 10. UI and data presentation

- Current fuel and refuelling amounts use litres (L), consistent with ACC.
- Distinguish ACC-provided values from Race Engineer calculations.
- Show the rolling five-valid-lap average and the number of valid laps currently included.
- Show the three-lap reserve assumption in the strategy details.
- When a pit recommendation exists, show recommended pit lap, projected fuel on arrival, target fuel, litres to add, and confidence/blockers.
- Keep the live status freshness-gated. Stale values may remain available for diagnostics but must not drive a current recommendation.
- Fuel Used remains an observation/cross-check only until its behaviour across in-session refuelling/pit transitions is validated.

## 11. Validation plan and release gates

### Data semantics
- Confirm current fuel and Graphics consumption values remain aligned with ACC across multiple cars and session states.
- Validate lap-time history filtering for valid laps, invalid laps, out-laps and incomplete laps.
- Validate race-lap limit and timed-race finish-line behaviour, including timer expiry.
- Validate Static maximum fuel against multiple cars and ACC.
- Validate fuel-used behaviour through pit entry, refuelling, driver swap and other in-session transitions.
- Validate mandatory-stop, pit-window and refuelling rules before enabling them in calculations.

### Calculation scenarios
- Enough fuel to finish with reserve: no announcement and no stop recommendation.
- Small shortfall: determine whether a realistic saving target is sufficient.
- Refuelling required: correct pit lap and litres to add.
- Pit arrival fuel projection and post-refuelling recalculation.
- Consumption increase/decrease, weather/pace changes and anomalous laps.
- Fewer than five valid laps and stale/missing/contradictory streams.
- Tank capacity reached; verify feasible multi-stop handling.
- Timed and lap-limited races with actual finish-line behaviour.
- Recommendation change, resolution and duplicate suppression.

### Release conditions
- No routine lap-by-lap radio spam.
- One background assessment per lap boundary, with deduplicated event handling.
- Actionable refuelling and critical fuel warnings are delivered once per meaningful state change.
- Three-lap reserve is applied and visible in the calculation.
- No impossible fuel amount, unvalidated pit-rule assumption or stale-data recommendation.
- No ACC/MFD/game-control writes.
- Automated tests, frontend build and Windows live-ACC validation are completed before claiming release readiness.

## 12. Current confirmed facts and outstanding gates

### Confirmed by user in ACC
- Fuel values are displayed in litres (L); preserve the raw numeric value.
- Graphics fuel per lap matched ACC in the observed test (3.66 L/lap).
- Graphics estimated laps remaining matched ACC in the observed test (16.5 laps; a later new-session observation showed 16.9).
- MFD fuel-to-add matched ACC in the observed test.
- Graphics Fuel Used increased during a session and reset to zero on a new session.
- Race Engineer must only provide information and recommendations; it must not change anything in the game.

### Still to validate
- Fuel Used reset/accumulation across pit stops and refuelling.
- Actual race-distance and timed-race finish-line semantics for supported session types.
- Tank capacity per car and MFD refuelling increment/constraints.
- Three-lap reserve calculation against real race outcomes.
- Reliable consumption estimator across changing pace, weather and pit/refuelling transitions.
- Mandatory stops, pit windows and pit-lane loss.
- End-to-end radio announcement and suppression behaviour in all three communication modes.

## 13. Relationship to other Race Engineer documents

This is the dedicated Fuel Strategy specification. The telemetry audit/roadmap remains the cross-strategy implementation and validation tracker. Each additional strategy (for example tyre, brake, race/pit, vehicle condition or setup) should receive its own focused specification document, with shared telemetry facts referenced rather than duplicated.

## 14. Initial implementation slice (2026-11-14)

The first pure Fuel Strategy calculation module is implemented in
`src/race_engineer_acquisition/fuel_strategy.py`.

### Implemented

- Applies the approved initial three-lap reserve.
- Calculates reserve fuel in litres from fresh, positive Graphics fuel-per-lap data.
- Exposes ACC estimated laps available and the number of laps remaining after the reserve.
- Calculates target fuel and projected finish margin only when fresh current fuel,
  fresh fuel-per-lap data, and an explicitly validated number of laps to the
  actual race finish are supplied.
- Fails closed when any required input is stale, invalid, or unvalidated.
- Reports a fuel shortfall as an assessment only. It does not independently
  issue a pit recommendation or fuel-to-add amount.
- Has no ACC write/control path and does not call TTS.

### Still pending

- A reliable, identified and gap-detectable completed-lap event channel and
  reconciliation behaviour.
- A validated race-progress provider for actual remaining laps, including
  timed-race finish-line behaviour.
- Rolling five-valid-lap history and consumption cross-checks.
- Fuel-saving feasibility, pit-arrival projection, tank-capacity and refuelling
  constraint handling.
- Strategy output lifecycle, actionable-change deduplication and central
  Pit-Stop decision integration.
- Background runtime scheduling, UI presentation, radio integration,
  automated test execution and live ACC validation.

This is a calculation foundation, not a release-ready Fuel Strategy. Do not
enable pit or radio recommendations from this slice alone.


## 15. Stage 2 completed-lap event input — implementation increment

The Stage 2 broker now publishes `lap.completed` events from fresh decoded Graphics state and emits `lap.completion_gap` when the authoritative completed-lap counter advances by more than one between observations.

The event preserves ACC's completed-lap time and validity observation, source capture sequence and source timestamp. ACC-invalid laps remain invalid. Session changes/counter resets re-seed the observer. The initial live observation seeds state without generating a historical lap.

After a gap, `DecodedTelemetryBroker.reconcile_lap_progress()` can restore the current session/lap cursor from the latest fresh Graphics state. It does not replay missing lap history; consumers must treat the affected history window as incomplete.

**Fuel integration remains gated:** the Fuel consumer has not yet been connected to this event subscription, and the rolling five-valid-lap average must not be calculated from incomplete history. The producer and reconciliation tests have been added but have not yet been executed locally or validated in a live ACC session. No pit or radio recommendation is enabled.


## 16. Current implementation status — 2026-11-15

This section supersedes the earlier pending-status statements in Sections 14 and 15 where they conflict with the current Stage 2 implementation.

### Implemented in the active runtime

- Stage 2 publishes completed-lap events and completion-gap events; strategy history consumes the event stream and stores compact per-lap records.
- Completed valid timed laps are filtered into the current ACC run's lap history. Out-laps and invalid laps are excluded from the five-lap pace sample.
- Timed-race remaining laps are estimated from fresh ACC Graphics remaining time and the latest five valid completed lap times. The live 20-minute race test confirmed the displayed format, countdown, average and remaining-lap estimate.
- ACC fuel-per-lap and ACC fuel-laps-remaining values are consumed directly when fresh. Race Engineer does not derive ACC fuel endurance by dividing current fuel by consumption.
- The active sufficiency assessment compares ACC fuel laps with estimated remaining race laps and exposes the raw ACC-derived margin in laps and litres.
- A separate three-lap safety reserve is now applied without changing the raw ACC margin:
  - reserve fuel = 3 × fresh ACC fuel per lap;
  - safety-adjusted margin in laps = ACC fuel laps remaining − estimated race laps remaining − 3;
  - safety-adjusted target fuel = estimated fuel to finish + reserve fuel;
  - safety-adjusted fuel margin = current fuel − safety-adjusted target fuel.
- The Race Engineer page displays both the raw ACC margin and the safety-adjusted margin/target. If fuel-per-lap or current fuel is not fresh, the corresponding litre calculation remains unavailable.
- Current-stint ACC Fuel Used and a separate in-memory cumulative observed fuel-used counter are exposed. The cumulative value starts when Race Engineer observes the session; it is not a guaranteed full-session total if the app connects late, and it resets when the application process restarts.
- Fuel calculations remain read-only. No ACC controls, MFD values or vehicle settings are written.

### Still pending

- Validate cumulative Fuel Used across multiple real pit/refuelling cycles and clarify its behaviour on driver swaps; the current accumulator is in-memory and connection-scoped.
- Validate the three-lap reserve against more live race scenarios and multiple cars.
- Consumption-history cross-check against ACC fuel-per-lap, including changing pace/weather and pit transitions.
- Fuel-saving feasibility and achievable per-lap saving targets.
- Pit-arrival fuel projection, pit timing, litres-to-add recommendation and recommendation lifecycle.
- Verified tank-capacity enforcement, MFD increment, mandatory-stop rules, pit windows and pit-lane loss.
- Actionable radio/TTS events, communication-mode routing and duplicate suppression.
- Lap-based race finish estimation and timed-race finish-line/extra-lap confirmation across supported session types.
- Automated tests, frontend build and Windows live-ACC validation must be run on the user's working copy before treating this increment as validated.

### Interpretation of the two margins

Do not replace the ACC margin with the reserve-adjusted margin. They answer different questions:

- **ACC fuel margin** answers whether ACC's estimated fuel endurance covers the estimated race distance.
- **Safety-adjusted margin** answers whether that same estimate also retains the approved three-lap reserve.

A positive ACC margin can therefore coexist with a negative safety-adjusted margin. This is intentional and must be shown clearly rather than hiding the raw ACC comparison.
