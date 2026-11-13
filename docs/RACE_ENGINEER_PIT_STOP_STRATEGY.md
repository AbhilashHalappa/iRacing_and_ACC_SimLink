# ACC Race Engineer — Pit-Stop Strategy

**Document status:** Agreed strategy specification  
**Date:** 2026-11-13  
**Scope:** Integrated pit decision-making, stop timing, service aggregation, session pit history and evidence-led weight calibration

## 1. Purpose and ownership

Pit-Stop Strategy is the **single owner of pit-stop decisions and pit recommendations**. Fuel, Tyre, Brake, Car Health, Weather, Race-State, Pace and Traffic strategies provide observations, assessments and constraints. They must not issue separate, competing routine instructions to pit.

Pit-Stop Strategy consumes those outputs, combines them with race context and produces one aggregated recommendation:
- Stay out / no stop currently justified.
- Plan a stop and identify the preferred window.
- Pit now / urgent stop, only when supported by a validated hard constraint or sufficiently strong combined evidence.

A single issue may be sufficient to justify a stop, but the final recommendation still comes from this integrated decision layer. Individual strategies may continue to issue their own critical informational warnings; they must not independently tell the driver to pit.

All decisions are advisory. Race Engineer is strictly read-only: it must never operate the pit limiter, MFD, pit menu, fuel/tyre selection, setup controls or any other in-game control. The driver performs every action manually.

## 2. Strategy inputs

The decision layer should consume timestamped, freshness-aware summaries from the existing strategy services.

| Input strategy / context | Contribution to pit decision |
|---|---|
| Fuel | Fuel-to-finish feasibility, projected arrival fuel, refuelling need, reserve and tank/refuelling constraints |
| Tyres | Validated pressure/temperature/condition trends, evidence-based degradation, compound suitability and tyre-change assessment |
| Car Health | Damage observations, persistence, validated warnings, corroborating abnormal behaviour, repair/inspection need |
| Brakes | Four-corner temperature and validated pad/disc condition; service need only when semantics and limits are established |
| Weather | Current conditions, validated trends and usable forecast progression; context for tyre/service timing |
| Race-State | Session type/progress, remaining time/laps when validated, mandatory stop rules/windows, penalties/restrictions and finish state |
| Pace | Personal pace trend and immediate classified opponent context; likely strategic cost/benefit of stopping now versus later |
| Traffic | Physical traffic context and validated nearby-car information; safe/advantageous timing context where supported |
| Vehicle/session metadata | Car, track/layout, session identity, tank capacity, pit-lane loss and service constraints when validated |

The strategy must preserve each input's source, timestamp, freshness, validation status and confidence/limitations. It must not combine stale or temporally incompatible stream samples as if they were simultaneous. Existing decoded consumers and shared snapshots must be reused; do not add another ACC shared-memory reader.

## 3. One aggregated decision, not independent pit calls

Each specialist strategy reports its own evidence and recommended service requirement to Pit-Stop Strategy. It does not independently announce a routine pit instruction.

The integrated output should include:
- **Decision:** stay out, plan a stop, or pit now.
- **Urgency:** informational, planned, urgent, or required by a validated rule/constraint.
- **Timing:** preferred window or reason immediate action is needed, only when inputs support it.
- **Combined work:** refuel, tyre change, damage inspection/repair, or other validated service items.
- **Reasoning:** the strongest contributing evidence and relevant trade-offs.
- **Uncertainty:** missing, stale, candidate or unvalidated inputs that limit the recommendation.
- **Reassessment trigger:** what change (lap, fuel projection, weather transition, damage evidence, rule/window) should cause recalculation.

Example: fuel projection indicates a stop will be needed soon, tyre evidence supports changing tyres, and a validated weather forecast indicates worsening conditions. The single recommendation should combine the necessary refuelling and tyre service into one planned stop if timing and constraints support it. It must not produce separate fuel, tyre and weather pit calls.

If no stop is justified, routine "no stop" calculations remain silent according to the global communication mode. Do not create a pit recommendation merely because a strategy has an observation or a non-critical concern.

## 4. Decision model: hard constraints and weighted assessment

The decision model has two layers. A weighted score must never dilute or conceal a validated hard requirement.

### 4.1 Hard constraints

Evaluate validated hard constraints before the weighted assessment. Examples include:
- A confirmed mandatory pit-stop rule or required window, once its ACC/session semantics are validated.
- Fuel feasibility showing the car cannot complete the race without refuelling, once race finish behaviour, consumption and remaining distance are reliable.
- A validated critical vehicle condition or ACC warning whose meaning and lifecycle justify stopping.
- A validated rule, restriction or penalty requiring a specific pit action.

A hard constraint may make a stop required regardless of the weighted score. The reason and source must be stated. Candidate telemetry, raw damage movement, stale data, inferred faults without corroboration or an unvalidated rule must not be promoted to hard constraints.

### 4.2 Fixed initial strategy weights

The following weights are the agreed starting configuration for the weighted pit-necessity assessment:

| Strategy | Initial weight |
|---|---:|
| Fuel | 25% |
| Tyres | 25% |
| Car Health | 20% |
| Brakes | 15% |
| Weather | 10% |
| Race-State strategic context | 5% |
| **Total** | **100%** |

These weights are **fixed initially**. They must not adapt automatically during early implementation or be changed based on a small number of races. Changes may be considered later only when enough recorded race evidence supports a defensible adjustment.

Pace and Traffic are contextual timing inputs, not independent pit-necessity weight contributors in this initial model. They can influence the preferred stop window, expected position loss/gain and whether it is strategically sensible to wait, but must not manufacture a service requirement.

The weights represent initial decision priority, not calibrated probabilities or physical measurements. Do not describe the resulting score as a probability of needing to pit.

### 4.3 Score handling and missing evidence

Each strategy contribution must be derived from its documented, validated evidence and a transparent severity/need mapping. That mapping and its thresholds require strategy-specific validation; do not invent numeric severity thresholds simply to make the weighted model operational.

- Missing, stale, ambiguous or unvalidated inputs are **unknown**, not zero need and not evidence that the car is healthy.
- Unknown contributions must be marked unavailable and excluded from claims about certainty. The system must expose which weighted inputs were actually assessed.
- Do not silently redistribute an unavailable strategy's weight across the remaining strategies in the initial implementation.
- A score must not be produced as authoritative when evidence coverage is insufficient. Report that the aggregate assessment is limited and rely only on validated hard constraints and available evidence.
- Keep the raw per-strategy findings alongside the aggregate result so the driver can understand why it was produced.
- Do not let a high aggregate score override contradictory evidence or an unvalidated assumption; explain conflicts and request reassessment when appropriate.

The exact score scale, thresholds for "plan a stop" versus "pit now", minimum evidence coverage and hysteresis/deduplication rules remain implementation and validation items. They must be defined transparently before enabling score-driven radio recommendations.

## 5. Stop timing and service aggregation

Once a stop is required or recommended, determine the best supported timing using:
- Remaining race time/laps and actual finish-line behaviour.
- Fuel projection at pit arrival and amount needed for the remainder.
- Tyre condition and compound suitability at the likely next stint.
- Damage urgency, repair availability and estimated repair duration when known.
- Brake condition and service availability only when validated.
- Current and forecast weather, with forecast horizon and freshness preserved.
- Pit-lane time loss and service constraints when measured/validated.
- Current position, gaps, immediate opponents, traffic and likely rejoin context when reliable.
- Mandatory stop windows, restrictions and whether required services can be combined.

The strategy should prefer combining compatible work into one stop when that is supported by evidence and does not create a greater strategic cost. It must not recommend an additional stop merely to optimise a small amount of fuel or a marginal service benefit without considering pit-lane loss and race context.

Do not invent pit-lane loss, repair duration, service availability, refuelling rate, tyre-change time, mandatory rules or safe rejoin gaps. If these are unknown, present the limitation and avoid false precision.

## 6. Pit-stop history

Maintain a persistent, chronological pit-stop history for every session. Each stop should have a stable session/stop identity and record the following where available:

### 6.1 Stop event and timing
- Pit entry and pit exit observations, with timestamps and source.
- Pit-lane duration and stationary/service duration only when reliably measurable.
- Session time, completed lap and race position at entry and exit.
- Track and car identity, session type and conditions.

### 6.2 Fuel service
- Fuel level before and after the stop.
- Fuel added, calculated only when before/after values are comparable and trustworthy.
- MFD fuel-to-add observation where available, clearly distinguished from actual fuel added.
- Source and confidence for each value.

### 6.3 Tyre service
- Tyre pressures and temperatures before and after where fresh samples exist.
- Compound/set identity before and after only when decoded semantics are validated.
- Whether tyres were changed, based on validated telemetry or explicit driver confirmation.
- Do not infer a tyre change from a pit visit alone.

### 6.4 Damage, brake and other service
- Damage and brake observations before and after the stop.
- Repair/service performed only when directly observed through validated telemetry or confirmed by the driver.
- Distinguish a measured reset/change from confirmation of a particular repair.
- Record unknown service details as unknown; never assume that damage was repaired or components were replaced.

### 6.5 Recommendation and outcome
- Aggregated recommendation at the time, including contributing strategy evidence, fixed weights/configuration version, hard constraints, selected timing and proposed combined services.
- Whether the driver followed, delayed, changed or declined the recommendation, if known.
- Subsequent valid lap/sector pace, consistency, position and gap trends over a comparable post-stop window.
- Weather, traffic, fuel load, tyre state and other confounders needed to interpret the outcome.
- Outcome assessment labelled measured, calculated, inferred or inconclusive. Do not attribute a pace change to the stop or a service without comparable evidence.

### 6.6 Data provenance and gaps
For every field, retain whether it was automatically observed, calculated from validated observations, imported, or driver-confirmed. Preserve timestamps and source references. If ACC does not expose a service detail, leave it unknown until the driver confirms it. Do not fabricate or backfill missing values.

Use compact per-session records consistent with the project's storage goals. Do not create unnecessary high-frequency recordings solely for pit history; reuse existing telemetry/session history and store pit events plus relevant before/after summaries.

## 7. Learning and future weight calibration

Pit history is intended to support evidence-based review of pit decisions across sessions, cars, tracks/layouts and conditions.

Initially, weights remain fixed at the values in §4.2. No automatic self-adjustment is permitted.

A future review may consider changing weights only after a sufficiently large and representative body of recorded race evidence exists. Before any change:
- Define the sample-size and evidence-quality requirements.
- Compare similar car, track/layout, session format, weather, race phase and service scenarios.
- Account for driver pace, traffic, fuel load, tyre state, damage, track evolution, pit-lane loss and other confounders.
- Compare the predicted benefit and actual outcome, including cases where a stop was delayed, declined or unnecessary.
- Check that a proposed change improves decisions across multiple comparable cases rather than overfitting one race.
- Preserve old weight versions and the rationale/evidence for each approved change.
- Require an explicit, reviewed configuration change; do not silently learn or modify weights in the background.

The system may analyse and propose a future weight adjustment, but the baseline weights remain unchanged until the evidence is sufficient and the change is deliberately approved.

## 8. Communication behaviour

Use the global Driver-initiated, Balanced and Active Race Engineer modes. The integrated pit decision is the only source of routine pit recommendations.

- Driver-initiated mode remains quiet except critical warnings; an actionable fuel/vehicle hard constraint must not be hidden.
- Balanced mode announces meaningful changes to the aggregate decision, upcoming stop windows and urgent requirements.
- Active mode may provide proactive timing updates, but should not repeat unchanged recommendations every lap.
- Announce changes in urgency or service plan, not every unchanged input update.
- Explain the combined work in one concise message. Specialist strategies may provide separate critical informational warnings without issuing a separate pit instruction.
- Provide full reasoning/history details on request; support repeat-last-message and mute/resume rules from the global communication specification.

## 9. Safety, integrity and non-goals

- Read-only operation is mandatory. Never issue ACC control inputs or operate pit functions.
- Never claim a stop is mandatory unless the rule is validated for the active session.
- Never claim a service was performed based only on a pit visit or recommendation.
- Never treat stale/missing data as healthy or as a zero contribution.
- Never fabricate a pit window, pit-lane loss, repair time, service constraint, tyre change, refuel amount or position outcome.
- Do not confuse pit entry/exit with lap completion or session finish.
- Pit-Stop Strategy owns the final integrated pit decision; specialist strategies own their underlying evidence and domain assessments.
- This specification does not authorise application-code changes or claim that the strategy has been implemented or live-validated.

## 10. Implementation and validation gates

Before enabling live pit recommendations:
1. Audit available strategy output APIs and define a shared, timestamped decision snapshot with freshness/validation metadata.
2. Validate race distance/finish behaviour, tank capacity, fuel projection and refuelling semantics.
3. Establish which tyre, brake and damage inputs can support service urgency and what remains candidate-only.
4. Identify mandatory-stop and penalty rules only from validated ACC/session sources.
5. Validate pit entry/exit detection and event boundaries; distinguish pit lane from stationary service time.
6. Establish which service outcomes are automatically observable and define driver confirmation for the rest.
7. Define and test score scale, severity mappings, minimum evidence coverage, hard-constraint precedence, decision thresholds, hysteresis and duplicate suppression.
8. Validate stop timing with pit-lane loss, service durations and rejoin context only where measured.
9. Test dry/wet transitions, traffic, changing fuel projections, damage/repair, reconnects, new sessions, missing streams and stale inputs.
10. Validate session pit-history persistence, provenance, recovery and before/after outcome comparisons.
11. Keep the agreed starting weights fixed; any later adjustment requires a documented evidence review and explicit approval.

No application code was changed as part of this strategy-definition work.
