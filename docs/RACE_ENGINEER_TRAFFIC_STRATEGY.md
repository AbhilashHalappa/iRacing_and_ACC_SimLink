# ACC Race Engineer — Traffic Strategy

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/race-engineer-page  
**Document status:** Strategy specification; design drafted 2026-11-13  
**Implementation status:** Documentation only. No Traffic Strategy engine, proximity/overlap detection, radio integration or UI is implemented by this specification.

## 1. Purpose

Traffic Strategy helps the driver understand nearby traffic and manage interactions with cars that are not necessarily the immediate classified opponent. It is particularly relevant in mixed-class racing, lapping, being lapped, catching slower cars, and being approached by faster cars.

Traffic Strategy complements, but does not replace, Pace Strategy:

- **Pace Strategy** focuses on the immediate classified car one position ahead and one position behind, race-position gaps, chasing, passing that target and defending the position.
- **Traffic Strategy** focuses on physical traffic context: nearby cars, relative movement, closing situations, overlap/proximity when reliably measurable, and traffic that may affect the player's progress.
- Do not duplicate the same gap narration or position coaching in both strategies. A situation should have one primary message owner.

All advice is informational. The driver remains responsible for safe, predictable and rule-compliant driving. Race Engineer must never control the car or send game inputs.

## 2. Scope and responsibilities

### 2.1 Traffic awareness

- Identify other cars around the player only when their identity and position can be associated reliably.
- Distinguish cars ahead, alongside and behind only when the available coordinate/relative-position model has been validated.
- Track whether a nearby car is approaching, receding or maintaining relative position using a sequence of fresh observations.
- Detect a potential traffic interaction only when proximity and relative movement evidence support it.
- Do not equate a small timing gap with physical proximity or overlap.
- Do not infer a car's racing line, intention, awareness or likely manoeuvre from position data alone.

### 2.2 Catching slower traffic

- Identify a car ahead that is physically relevant to the player's path only when relative-position data is trustworthy.
- Estimate closing behaviour from repeated, fresh relative observations; do not infer it from a single sample.
- Where validated speed/relative-position data supports it, report that the player is closing and that traffic may affect the next part of the lap.
- Help the driver anticipate the need for patience and a clean, predictable approach.
- Do not prescribe a passing side, braking point, corner entry or exact passing manoeuvre without validated track-relative context.
- Do not assume a car is slower solely because it is a different class or because its position is lower/higher.

### 2.3 Being approached or lapped

- Identify a faster-approaching car only when the relative movement is supported by fresh data.
- Distinguish a physical closing situation from a car that is merely ahead/behind in classification.
- Where the applicable ACC race-control information is validated and relevant, communicate a blue-flag or lapping context as an observed race-control state.
- Do not invent blue-flag status, lapping rules, class priority or right-of-way.
- Do not tell the driver to make an abrupt move or leave the racing line. Any advice must favour predictable, rule-compliant behaviour and remain general unless the situation is directly observable.

### 2.4 Overlap and proximity

- Detect side-by-side overlap only if the coordinate frame, car dimensions/reference points, player association and overlap calculation have been validated.
- If the data only supports approximate nearby-car awareness, report it as such; do not label it as overlap.
- Do not infer contact or collision from proximity alone.
- Do not issue precise spatial warnings from stale, sparse or ambiguous coordinates.

### 2.5 Traffic effect on pace

- Mark lap/sector observations as potentially traffic-affected only when there is supporting traffic evidence at the relevant time.
- Keep traffic context separate from measured lap/sector time.
- Do not automatically discard a valid lap because traffic was nearby.
- Avoid attributing a pace loss to traffic unless timing and traffic observations align sufficiently.
- Detailed driver technique and corner-by-corner coaching remain with Performance Coach and Corner Coach.

## 3. Required inputs and evidence status

The following statuses reflect the current cross-strategy telemetry audit. A decoded value is not automatically safe for traffic decisions.

| Input | Current audit status | Use and restriction |
|---|---|---|
| Graphics car IDs | Available — candidate | Requires stable mapping to active cars and the player. |
| Graphics car coordinates | Available — candidate | Coordinate frame, units, update cadence and player association require controlled validation. |
| Player identity / car association | Available — candidate | Must be stable across session start, pit transitions and car-list changes. |
| Player and opponent position | Available — candidate | Useful for context only after multi-car validation; classification is not physical proximity. |
| Gap ahead / gap behind | Available — candidate | Raw values are in milliseconds; sign, reference car and semantics require validation. Timing gaps do not prove physical overlap. |
| Opponent speed / relative speed | Not yet established as a validated traffic input | Use only if an existing decoded source can be reliably associated with each opponent. Do not derive from unrelated player-only speed. |
| Player speed | Available — validated | Context only; does not establish opponent closing rate by itself. |
| Track position / normalized spline position | Available — candidate | Requires direction, wrap-around and coordinate semantics validation before relative-distance calculations. |
| Session / race-control flags | Mixed candidate and validated | Use only explicitly validated meanings; do not invent blue-flag or lapping states from raw codes. |
| Lap and sector timing | Available — candidate / integrated | Context for traffic-affected pace only after timing semantics and event alignment are validated. |
| Weather / track conditions | User validated currently exposed weather values against ACC | Context only; do not attribute traffic behaviour or pace effects to weather without evidence. |

### Data availability rule

Before enabling Traffic Strategy, inspect and reuse existing decoded Graphics/Physics consumer APIs. Validate car identity, player association, coordinate frame, units, update cadence, track-position wrap-around, and stale-data behaviour. Do not add a second shared-memory reader or assume Physics and Graphics samples are timestamp-aligned.

If opponent coordinates are incomplete or ambiguous, disable spatial warnings and retain only the traffic facts that can be established. If opponent-specific speed is unavailable, do not manufacture relative speed. A classification gap must not be presented as a physical distance or overlap measurement.

## 4. Calculations and event detection

All calculations must preserve source freshness and distinguish observed, calculated and inferred information.

### 4.1 Nearby-car tracking

- Associate each observed car with a stable identity for the current session.
- Track player-relative position only after the coordinate model is validated.
- Handle track wrap-around and cars crossing the start/finish line.
- Reset or re-associate tracks when cars enter/leave the session, pit, disconnect or the player identity changes.
- Reject stale, implausible or discontinuous coordinate samples.
- Do not use a single noisy frame to trigger a radio warning.

### 4.2 Closing and receding trends

- Calculate relative movement from multiple fresh observations of the same car.
- Confirm direction and units before describing a car as approaching or pulling away.
- Smooth noisy updates and apply event persistence/hysteresis based on validated sampling behaviour.
- Do not define universal proximity or closing-rate thresholds before controlled ACC evidence exists.
- Do not estimate time-to-contact unless relative distance and relative speed are both validated and the estimate is demonstrably stable. In the absence of those inputs, report only the observed trend.

### 4.3 Traffic interaction classification

Potential categories, enabled only when their evidence gates pass:

- Car ahead in the player's vicinity.
- Car approaching from behind.
- Car alongside / overlap detected.
- Player closing on traffic.
- Player being caught or approached.
- Traffic interaction ended / car no longer nearby.

A category must not be emitted when the data only supports a weaker statement. For example, “nearby car detected” must not be upgraded to “alongside” without validated overlap geometry.

### 4.4 Traffic-affected pace

- Align traffic observations with the relevant lap/sector interval only when timestamps and timing boundaries support it.
- Label traffic influence as possible or likely only according to the strength of evidence.
- Do not adjust the player's pace baseline automatically without an explicit, validated policy.
- Keep the measured lap time intact and annotate the context separately.

## 5. Recommendation logic

Traffic messages should be brief, factual and conservative. Illustrative intent (not hard-coded triggers):

- **Traffic ahead:** “Traffic ahead. Be patient and plan a clean approach.”
- **Closing on traffic:** “You're closing on the car ahead; traffic may affect your next sector.”
- **Car approaching from behind:** “A car is closing from behind. Stay predictable and remain aware.”
- **Validated overlap:** “Car alongside. Leave racing room.” This message is permitted only if overlap detection is validated.
- **Traffic cleared:** “Traffic clear. Return focus to your pace.”
- **Possible traffic effect:** “This lap may be traffic-affected; the timing is unchanged.”
- **Insufficient evidence:** “Nearby-car data is unavailable; traffic guidance is limited.”

The strategy must not:
- Tell the driver to force a pass, block, weave, brake-check or make an abrupt move.
- Prescribe a passing side, racing line or exact manoeuvre from unvalidated coordinates.
- Claim overlap, contact, proximity or closing speed from a classification gap alone.
- Assume a different class automatically has priority or is slower.
- Invent blue flags, lapping status, track rules or opponent intentions.
- Produce repeated warnings for every coordinate update.
- Duplicate Pace Strategy's immediate-position gap commentary.

## 6. Communication and priority

Traffic Strategy uses the Race Engineer's agreed communication modes:

- **Driver-initiated:** quiet except critical warnings. Traffic details are available on request.
- **Balanced (default):** announce meaningful, evidence-backed traffic interactions that may affect the driver's immediate awareness; suppress routine proximity updates.
- **Active race engineer:** provide more proactive traffic awareness, but do not narrate every nearby car or repeat unchanged warnings.

Rules:

- Safety-relevant, validated overlap warnings may be prioritised in every mode once overlap detection is proven reliable. Until then, do not create a critical warning category from candidate coordinates.
- Deduplicate messages by car identity and interaction state.
- Announce meaningful state changes (approaching, alongside, cleared) only when the transition is stable.
- Withdraw outdated warnings when the car identity changes or the data becomes stale.
- Do not let Traffic Strategy and Pace Strategy speak over one another about the same immediate opponent. Pace Strategy owns classified one-position chase/defence; Traffic Strategy owns physical traffic awareness.
- Keep messages concise; detailed status is available on request.
- Reuse existing Windows TTS and shared radio/message queue when integrated. This document does not implement TTS.

## 7. UI requirements

The Traffic Strategy view should present only trustworthy, useful traffic context:

- Nearby cars with stable identity where available.
- Relative location category only when validated (ahead, behind, alongside).
- Closing / receding / stable trend only when calculated from fresh observations.
- Traffic interaction state and age/freshness.
- Traffic-affected lap/sector annotation only when supported.
- Clear unavailable/ambiguous state when car association or coordinates cannot be trusted.
- Short recommendation with the evidence category (observed, calculated or inferred).

Do not present a fabricated radar, exact distance, overlap indicator, relative speed or time-to-contact. A visual proximity map/radar is not approved until the coordinate model and car association are validated.

## 8. Shared data and service boundaries

Traffic Strategy should consume shared observations rather than create independent telemetry readers.

Likely shared dependencies:
- Freshness-aware Graphics/Physics engineering snapshots.
- Stable car identity and player association.
- Car coordinates and normalized track position.
- Player speed and any validated opponent-specific speed.
- Session/race-control state and validated flag meanings.
- Lap/sector timing and history for traffic context.
- Shared event deduplication, freshness and radio priority services.

Common car tracking, coordinate normalization, relative-motion calculations and event lifecycle should be reusable by Pace Strategy if appropriate. Traffic-specific interpretation and message ownership remain within Traffic Strategy.

## 9. Validation plan and release gates

### Gate A — source semantics

1. Inspect existing decoded car IDs, coordinates, normalized positions and consumer APIs.
2. Establish coordinate units, axes, origin, direction and player association.
3. Validate stable car identity across multiple cars, pit entry/exit, disconnects and session transitions.
4. Establish update cadence, timestamp quality and stale-data behaviour.
5. Determine whether opponent-specific speed or relative speed is exposed.
6. Validate track wrap-around and coordinate discontinuity handling.
7. Determine whether the current data can support overlap detection; if not, explicitly keep overlap unavailable.

### Gate B — event calculations

1. Validate a car approaching from ahead and from behind.
2. Validate closing, receding and stable relative-motion trends.
3. Confirm that classification gaps are not mistaken for physical distance.
4. Test noisy, stale, missing and discontinuous samples.
5. Test car identity changes and cars entering/leaving the session.
6. Verify that traffic-affected lap/sector annotations align with the correct timing interval.
7. Confirm no spatial warning is generated when the evidence gate fails.

### Gate C — race scenarios

- Catching a slower car.
- Being approached by a faster car.
- Mixed-class traffic, if supported by the selected session.
- Two cars running close together.
- A car alongside, only if overlap geometry is validated.
- Traffic clearing and the player returning to clean air.
- Pit entry/exit and start/finish-line wrap-around.
- A car joining, disconnecting or being removed from the session.
- Candidate data becoming stale during an interaction.
- Pace changes with and without corroborating traffic observations.

### Gate D — integration and acceptance

- Reuse existing telemetry acquisition; no second shared-memory reader.
- Do not duplicate Pace Strategy's immediate classified-position coaching.
- Correct priority and deduplication across the three communication modes.
- Clear distinction between measured, calculated and inferred traffic information.
- No fabricated radar, distance, overlap, relative speed, blue-flag status or time-to-contact.
- All recommendations remain informational and advisory; no ACC controls or driving inputs are operated.
- Automated tests, production build and live Windows ACC validation are completed before claiming release readiness.

## 10. Explicit non-goals

- Automated steering, braking, throttle, overtaking or defensive control.
- Predicting opponent intent, awareness, racing line or manoeuvres.
- Unsafe or prescriptive passing instructions.
- Treating classification position/gaps as physical proximity.
- Displaying a radar or spatial distances before coordinate validation.
- Claiming overlap or contact from ambiguous coordinate samples.
- Inventing opponent speed, relative speed, blue flags or class priority.
- Replacing Pace Strategy, Performance Coach or Corner Coach.

## 11. Current implementation status

This document records the Traffic Strategy design only. It does not claim that car tracking, proximity/overlap detection, relative-motion calculations, traffic recommendations, UI or radio integration have been implemented or validated.

The current cross-strategy telemetry audit identifies car IDs, coordinates and normalized position as candidates. The next engineering task is to inspect existing decoded APIs and run controlled multi-car ACC validation before enabling traffic-aware calculations. No new shared-memory reader should be introduced.
