# ACC Race Engineer — Pace Strategy

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/race-engineer-page  
**Document status:** Strategy specification; design decisions agreed 2026-11-13  
**Implementation status:** Documentation only. No Pace Strategy engine, opponent-tracking logic, radio integration or UI is implemented by this specification.

## 1. Purpose

Pace Strategy helps the driver manage race position using the driver's own pace and the timing of nearby opponents. Its primary race focus is deliberately narrow:

- The car **one position ahead** is the primary target while the driver is chasing.
- The car **one position behind** is monitored as the immediate position threat.
- The strategy does not make the whole field its primary coaching focus.
- After the driver passes the target ahead, the former target becomes the immediate car behind (subject to the updated ACC classification), and the next car ahead becomes the new target.
- If the driver loses a position, target selection is recalculated from the current reliable classification.

The purpose is to help the driver decide whether to close a gap, prepare an overtake, build or maintain a gap after passing, and defend a position when threatened. The strategy provides information and recommendations only.

## 2. Scope and responsibilities

### 2.1 Personal pace

- Compare recent valid completed laps with the driver's own best and rolling pace.
- Track lap-time and sector-time trends where the relevant timing values are available and validated.
- Identify consistency, improvement and pace loss.
- Distinguish measured lap/sector times from calculated trends.
- Consider traffic, weather, fuel and race-state context only when the relevant input is fresh and its effect can be supported.
- Do not duplicate detailed driving-technique or corner-by-corner coaching owned by Performance Coach and Corner Coach.

### 2.2 Car immediately ahead — chase and overtake preparation

- Identify the competitor one classified position ahead of the player.
- Observe the gap to that competitor and its trend.
- Compare the player's recent pace with the opponent's available lap/sector timing.
- Calculate a closing rate only from a sequence of fresh, correctly associated gap observations with validated sign and timing semantics.
- Estimate catch time only when the closing rate is sufficiently stable and positive; otherwise state that an estimate is unavailable.
- Identify where the player's measured sector performance is stronger or weaker than the opponent's only when comparable sector data is actually exposed and validated.
- Provide preparation advice based on evidence, such as maintaining pressure, avoiding unnecessary mistakes, or being ready if the gap reaches a useful range.
- Do not invent an overtaking threshold, overtaking zone, opponent weakness, or likely opponent manoeuvre.
- Do not claim that a pass is guaranteed or that the opponent will defend a particular line.

### 2.3 Car immediately behind — gap management and defence

- Identify the competitor one classified position behind the player.
- Monitor the gap and its trend when the relevant data is reliable.
- After a pass, focus on building and maintaining a gap to the car that is now immediately behind.
- Alert the driver when the gap is consistently shrinking and the position may be under pressure.
- When supported by pace and gap evidence, advise the driver to prioritise a clean, consistent lap or be prepared to defend.
- Do not infer the opponent's intentions, exact attack point or chosen line from gap data alone.
- Do not give unsafe or overly prescriptive manoeuvre instructions. The driver remains responsible for safe, rule-compliant driving.

### 2.4 One-position-at-a-time focus

The strategy may observe both adjacent competitors, but it should keep one clear primary objective:

1. **Chasing:** immediate car ahead is the primary target; immediate car behind is a secondary threat monitor.
2. **Recently passed / position secured:** the former target is now behind. Prioritise gap-building and defending against the nearest threat while identifying the next car ahead.
3. **Under pressure / defending:** the immediate car behind becomes the primary tactical concern; do not distract the driver with distant competitors.
4. **No reliable adjacent-car data:** fall back to personal pace only and explicitly state that opponent comparison is unavailable.

Do not jump to a distant car as the primary target merely because its timing is easier to obtain. Re-evaluate target identity after a confirmed position/classification transition, not from a single noisy sample.

## 3. Required inputs and evidence status

The following statuses reflect the current cross-strategy telemetry audit. A decoded field is not automatically ready for strategy use.

| Input | Current audit status | Use and restriction |
|---|---|---|
| Player completed valid lap times | Available; existing lap validity/completion evidence is validated | Personal pace baseline. Exclude invalid, incomplete and out-laps. |
| Player sector timing | Available — candidate | Use only after timing semantics and sector transitions are validated for comparisons. |
| Player best lap / last lap | Available — candidate / integrated | Preserve existing validity and time-format semantics. |
| Player race position | Available — candidate | Requires multi-car and position-transition validation before opponent selection. |
| Active car count | Available — candidate | Context only; freshness and session state required. |
| Gap ahead / gap behind | Available — candidate | Raw values are in milliseconds. Sign convention and association must be validated before calculating direction or closing rate. |
| Opponent lap / sector timing | Not yet established as a fully validated strategy input | Use only if ACC exposes a reliable opponent-specific timing source and car association. Never substitute the player's own timing. |
| Opponent identity / car association | Available — candidate through Graphics car IDs and coordinates | Multi-car population, stable ID mapping and player association need targeted live validation. |
| Traffic / nearby-car position | Available — candidate | Do not claim proximity, overlap or a passing opportunity until coordinate frame and association are validated. |
| Weather / track conditions | User validated all currently exposed weather values against ACC | Use only fresh values and preserve their actual meaning; weather does not by itself explain a pace change. |
| Fuel / fuel consumption | Current fuel in L, fuel-per-lap and estimated laps validated against ACC | Contextual factor only when fresh; do not attribute pace loss to fuel without evidence. |
| Tyre pressures / core temperatures | Four pressures and four core temperatures validated | Contextual trend inputs; no unsupported wear percentage or diagnosis. |
| Brake temperatures | Four channels validated | Context only; do not infer braking performance loss from temperature alone. |
| Session state / remaining race distance | Mixed candidate and validated fields | Do not make race-finish or strategic urgency claims from unvalidated race-distance semantics. |

### Data availability rule

Before opponent-aware Pace Strategy is enabled, audit the existing decoder and consumers for the exact opponent timing and gap fields, their timestamps, units, sign convention, car association and update cadence. Reuse existing acquisition and decoded consumer APIs. Do not add a second shared-memory reader or assume that independently sampled Physics and Graphics data are synchronized.

If only aggregate gap-ahead/behind values are available, the strategy may use them only after controlled tests establish which competitor they refer to and the sign/direction convention. If opponent-specific lap or sector times are unavailable, do not fabricate pace comparisons; use validated gap trends and the player's own lap history instead.

## 4. Calculations

All calculations are read-only and must carry source freshness and confidence/evidence state.

### 4.1 Personal pace

- Maintain a rolling comparison of recent valid completed laps.
- Compare the latest valid lap with the player's best and recent baseline.
- Calculate consistency/spread only from a sufficient set of comparable valid laps.
- Compare sectors only when sector boundaries and timing values are valid and comparable.
- Exclude invalid laps, out-laps, incomplete laps and obvious timing-transition artefacts.
- Label calculated trends as calculated; do not present them as direct ACC measurements.

### 4.2 Pace difference to the target ahead

When opponent timing is available and validated:

- Compare like-for-like completed laps and sectors.
- Calculate the player's pace advantage/disadvantage against the immediate target.
- Use multiple observations where possible; a single lap may be affected by traffic, errors, pit entry/exit or changing conditions.
- Do not compare non-equivalent laps or sectors without disclosing the limitation.

When opponent timing is not available:

- Do not estimate opponent pace from invented values.
- Use a validated gap trend as the available evidence.
- State that the opponent's lap/sector pace is unavailable.

### 4.3 Gap trend and closing rate

- Preserve the raw ACC gap value and unit.
- Convert milliseconds to seconds only for presentation/calculation where the source unit is confirmed.
- Establish the sign convention and car association before assigning ahead/behind direction.
- Calculate gap change over elapsed time from fresh observations.
- Calculate closing rate only after filtering noisy updates and confirming the target car has not changed.
- A catch-time estimate may be produced only when the closing rate is consistently favourable and the estimate is meaningful; otherwise report no reliable estimate.
- Recalculate/reset the trend when position, target identity, session state or timing source changes.

No fixed “attack now” gap, threat threshold or closing-rate threshold is approved until car-, track- and data-specific evidence supports it.

### 4.4 Position transition

- Confirm a pass or position change using stable ACC position/classification evidence, not a single transient sample.
- Update adjacent-car identities after the classification transition.
- Prevent duplicate or oscillating radio messages during position swaps or timing noise.
- A completed pass does not itself prove the gap is safe; continue monitoring the new immediate car behind.

## 5. Recommendation logic

Recommendations should be concise, conditional and tied to the observed evidence.

Examples of acceptable message intent (illustrative wording, not hard-coded triggers):

- **Chase:** “You're closing on the car ahead. Keep the pressure on.”
- **Pace advantage:** “Your recent pace is stronger; the gap is coming down.”
- **No closing trend:** “The gap is stable. No reliable catch estimate.”
- **Overtake preparation:** “You're within range; focus on a clean exit and be ready for an opportunity.”
- **After a pass:** “You're ahead. Build a consistent gap.”
- **Defence:** “The car behind is closing. Prioritise a clean, consistent lap and be prepared to defend.”
- **Gap stable:** “The gap behind is stable. Maintain your rhythm.”
- **Insufficient evidence:** “Opponent timing is unavailable; monitoring your own pace.”

The strategy must not:
- Guarantee an overtake or predict an opponent's intent.
- Recommend an unsafe move or tell the driver to force a pass.
- Invent track-specific passing zones or opponent weaknesses.
- Recommend pushing harder without evidence that it is appropriate.
- Claim a gap is safe based on one sample.
- Treat a small gap alone as proof that the opponent is attacking.
- Give detailed corner technique that belongs to Performance Coach or Corner Coach.

## 6. Communication and priority

Pace Strategy uses the Race Engineer's agreed communication modes:

- **Driver-initiated:** quiet except critical warnings. Pace details are available on request.
- **Balanced (default):** announce meaningful pace/position changes, a material closing trend, a significant threat from behind, or a useful post-pass gap update. Suppress routine unchanged status.
- **Active race engineer:** provide more proactive chase/defence updates, while avoiding repetitive gap narration. The existing Active-mode completed-lap announcement remains a separate Race Engineer-wide behaviour.

Rules:
- Critical warnings remain automatic in every mode, but Pace Strategy must not invent a critical warning category from ordinary opponent proximity.
- Deduplicate unchanged messages.
- Announce material changes in trend or severity, and resolve/withdraw outdated messages when target identity changes.
- Do not announce every noisy gap fluctuation.
- Keep radio messages short; detailed evidence and explanation are available on request.
- Use existing Windows TTS and the shared radio/message queue when integrated; this document does not implement TTS.

## 7. UI requirements

The Pace Strategy view should make the immediate race context understandable at a glance:

- Player's current position.
- Immediate car ahead, its gap and trend.
- Immediate car behind, its gap and trend.
- Current primary focus: chasing, defending, gap-building or personal pace.
- Player's recent valid pace and personal reference.
- Opponent pace comparison only when the source is available and validated.
- Catch-time estimate only when the closing-rate calculation passes its evidence gate.
- Source freshness / unavailable-state indication for important opponent data.
- Short current recommendation and a concise reason.

Do not fill the page with the full field or unsupported opponent metrics. The immediate ahead/behind pair should remain the focus.

## 8. Shared data and service boundaries

Pace Strategy should consume shared observations rather than create independent telemetry readers or duplicate calculations.

Likely shared dependencies:
- Freshness-aware Physics/Graphics engineering snapshots.
- Completed-lap and lap-validity events.
- Session/lap history and sector timing.
- Position, adjacent gaps and opponent association.
- Weather and track conditions.
- Fuel, tyre and brake observations where relevant.
- Race/session state.

Common calculations such as valid-lap filtering, rolling pace, gap trend, event deduplication and freshness evaluation should be reusable by other strategies where appropriate. Strategy-specific interpretation and message priority remain owned by Pace Strategy / Race Engineer domain services.

## 9. Validation plan and release gates

### Gate A — opponent telemetry semantics

1. Verify position and active-car count against ACC in a multi-car session.
2. Compare gap-ahead and gap-behind values with known cars and visible ACC timing.
3. Establish units, sign convention, update cadence and whether each gap is relative to the immediate classified neighbour.
4. Validate stable opponent identity across position changes, pit entry/exit and session transitions.
5. Determine whether opponent-specific lap and sector timing is actually exposed by the current ACC implementation.
6. Validate stale/disconnected behaviour and ensure the last good value is not treated as current.

### Gate B — calculations

1. Compare personal pace calculations against valid completed laps.
2. Test invalid laps, out-laps, incomplete laps and session resets.
3. Test gap trend with a known faster car approaching and a known gap increasing.
4. Confirm closing-rate and catch-time calculations against recorded observations.
5. Confirm target changes after an overtake and after losing a position.
6. Verify no catch estimate or opponent pace comparison appears when its required inputs are missing or stale.

### Gate C — race scenarios

- Chasing one car with a stable gap.
- Closing on the car ahead over several laps.
- Gap increasing / no longer closing.
- Passing the target and switching to gap-building.
- Immediate car behind closing and creating a defensive concern.
- Position swap / classification fluctuation.
- Target car pitting or leaving the session.
- Traffic, invalid lap, weather change and fuel change as pace confounders.
- Opponent data loss while personal pace remains available.

### Gate D — integration and acceptance

- No second shared-memory reader or acquisition hot-path changes.
- No duplicate Performance Coach / Corner Coach coaching.
- Correct behaviour in all three communication modes.
- Radio deduplication and target-transition handling work.
- UI distinguishes measured, calculated and inferred values.
- All advice remains informational and advisory; no ACC controls, setup, MFD, pit actions or driving inputs are operated.
- Automated tests, production build and live Windows ACC validation are completed before claiming release readiness.

## 10. Explicit non-goals

- Full-field race analytics as the primary coaching experience.
- Predicting opponent intent, skill, mistakes or chosen racing line.
- Automated overtaking, steering, braking, throttle or defensive control.
- Prescribing a guaranteed overtaking point or fixed gap threshold without evidence.
- Replacing Performance Coach or Corner Coach.
- Fabricating opponent lap/sector times when ACC does not expose a reliable source.
- Treating candidate gap/position fields as validated before controlled ACC checks.

## 11. Current implementation status

This document records the agreed strategy design only. It does not claim that opponent tracking, pace calculations, recommendations, UI or radio integration have been implemented or validated. The current cross-strategy telemetry audit remains authoritative for field readiness. The next engineering task is to inspect the existing decoded APIs and validate position/gap/opponent associations before implementing opponent-aware calculations.
