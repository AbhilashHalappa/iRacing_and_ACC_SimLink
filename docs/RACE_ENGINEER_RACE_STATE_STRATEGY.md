# ACC Race Engineer — Race-State Strategy

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Target branch:** feature/race-engineer-page  
**Document status:** Strategy specification; design drafted 2026-11-13  
**Implementation status:** Documentation only. No Race-State Strategy engine, race-control event mapping, radio integration or UI is implemented by this specification.

## 1. Purpose

Race-State Strategy monitors the state of the ACC session and communicates race-control information that materially changes what the driver needs to know. It covers session phase, flags, penalties, safety-car or other neutralisation states where exposed, and important race transitions.

The strategy must distinguish:
- What ACC directly reports.
- What the application calculates from validated transitions.
- What can only be inferred and therefore must not be presented as a confirmed race-control instruction.

Race-State Strategy is not a substitute for ACC's own HUD, MFD, penalty notices or official in-game instructions. The driver must always follow the game and applicable server/race rules.

All behaviour is strictly read-only. Race Engineer must never control the car, acknowledge penalties, change setup, operate the MFD, trigger pit actions or send game-control inputs.

## 2. Scope and responsibilities

### 2.1 Session and race phase

- Identify the current session type and state only after the corresponding ACC values and transitions are validated.
- Distinguish session start, active running, paused/replay/garage states, session end and transitions between sessions where the telemetry supports them.
- Report session time remaining using the validated time source and correct session state.
- Use completed laps, race lap limit and remaining distance only when each field's meaning is validated.
- Do not infer that the race has finished merely because a timer reaches zero; timed-race completion may depend on the leader crossing the line and the final-lap procedure.
- Do not announce a green start, race restart or chequered flag from an unvalidated raw enum.

### 2.2 Flags and track status

- Communicate flag and track-status states only when the raw code-to-meaning mapping is verified for the ACC version and session context.
- Preserve the original raw value for diagnostics.
- Announce a confirmed change once, with a concise explanation.
- Distinguish a local flag, global track status and lap-validity state; they are not interchangeable.
- Do not map unknown codes to familiar motorsport meanings.
- Do not infer a yellow, green, blue, red or chequered flag from unrelated values such as lap validity, global-green candidate fields or car proximity.
- Where the ACC HUD provides the authoritative instruction, direct the driver to follow the in-game display.

### 2.3 Penalties and warnings

- Monitor only penalty and warning fields whose existence, units, enum mapping and transition behaviour are validated.
- Distinguish an observed ACC penalty from an inferred rule concern.
- Report the penalty type, amount, status or deadline only if those details are actually exposed and validated.
- Detect new, changed, served, cancelled or cleared penalty states only after transition semantics are confirmed.
- Do not invent a drive-through, stop-and-go, time penalty, warning count, track-limit sanction or serving window.
- Do not tell the driver that a penalty has been served based only on a pit entry or a changed display value without validated evidence.
- Never acknowledge, serve or otherwise interact with a penalty on the driver's behalf.

### 2.4 Safety car, full-course neutralisation and race interruptions

- Detect safety-car, virtual safety-car, full-course-yellow, red-flag or equivalent states only if ACC exposes a validated source for the current game/session mode.
- Do not assume that every real-world race-control procedure exists in ACC or is exposed through the current shared-memory interface.
- If the state is not available or the enum is unresolved, report that Race Engineer cannot verify the neutralisation state.
- Do not invent restart procedures, delta targets, speed limits, queue order, catch-up instructions or pit permissions.
- Any timing or gap interpretation during a neutralised state must be re-evaluated; normal green-flag pace assumptions may not apply.

### 2.5 Start, finish and session transitions

- Detect session start/end and race start/finish only from validated state transitions.
- Avoid duplicate announcements during brief state oscillations, reconnects or session reloads.
- Treat timer expiry and actual race completion as separate events unless ACC's behaviour for the current session type is validated.
- Do not announce the chequered flag solely because the session timer reached zero.
- Reinitialise session-scoped event history when a genuinely new session is confirmed, without confusing a reconnect with a new session.

## 3. Required inputs and evidence status

The following status reflects the current cross-strategy telemetry audit. A decoded field is not automatically safe to use as a race-control instruction.

| Input | Current audit status | Use and restriction |
|---|---|---|
| Session time remaining | Available — validated for display | User-tested against ACC. Announcements still require freshness and correct session-state gating. |
| Session type / session state | Available — candidate | Raw status/session fields are decoded; enum mapping and transition behaviour require controlled validation. |
| Current position / active cars | Available — candidate | Context only until multi-car and transition behaviour are validated. |
| Completed lap count | Available — validated | Use the validated completed-lap field; do not substitute the race lap-limit field. |
| Race lap limit / laps remaining | Available — candidate | Meaning and race-limit behaviour require confirmation before race-distance calculations. |
| Lap validity | Available — validated | This is lap validity, not a flag or race-control state. |
| Local flag / global track status | Mixed candidate | Raw fields exist; integer codes and their meanings require validation. Unknown codes must remain unknown. |
| Penalty fields | Available — candidate / incomplete | Raw penalty, warning and related fields need enum, unit and lifecycle validation before announcements. |
| Safety-car / neutralisation state | Not established as validated | Do not claim availability until an explicit, reliable source is identified and tested. |
| Session start/end transitions | Calculated — feasible after state mapping | Requires validated state codes, stable transition detection and reconnect handling. |
| Chequered/race completion | Not established as validated | Timer expiry alone is insufficient. Validate actual ACC finish behaviour for each session type. |
| Weather and track conditions | User validated currently exposed weather values against ACC | These are conditions, not race-control instructions. |

### Data availability rule

Inspect the existing Graphics decoder and consumer APIs for the exact raw fields, enum values, units, timestamps and lifecycle semantics. Reuse the existing acquisition pipeline; do not create another shared-memory reader.

Until a raw code is mapped and validated, preserve it as an unknown code and do not announce a semantic label. A field name or plausible numeric value is not enough evidence to tell the driver that a flag, penalty or neutralisation is active.

## 4. Event model and calculations

All event handling must be freshness-aware, session-scoped and resistant to duplicate or transient transitions.

### 4.1 State transitions

- Maintain the last accepted state and its source timestamp.
- Require a stable transition according to the validated update cadence before emitting an event.
- Distinguish a real session transition from a temporary stale sample, acquisition restart, reconnect or replay/garage change.
- Emit each confirmed transition once.
- Clear or supersede stale event state when a new session is confirmed.
- If the source becomes stale, mark the state unknown rather than continuing to present the last state as current.

### 4.2 Flag and penalty event lifecycle

For each validated event, retain:
- Raw source value and mapped meaning.
- First-observed and last-confirmed timestamps.
- Current status (active, cleared, changed or unknown) only where lifecycle semantics are validated.
- Session identity and event deduplication key.
- Evidence/freshness state.

Do not infer an event's end from silence unless ACC's lifecycle semantics establish that behaviour. If a field is momentary or event-based, its capture and clearing behaviour must be tested.

### 4.3 Race progress and finish calculation

- Use completed laps for completed-lap reporting.
- Use a separately validated lap limit for race distance.
- For timed races, use session time remaining plus validated ACC finish-line behaviour.
- Do not calculate laps remaining from a timer or candidate field without a validated model.
- If finish behaviour is unknown, communicate the observed timer/lap state without predicting the exact final lap.
- Any race-completion announcement must be tied to a confirmed finish transition, not a forecast.

### 4.4 Neutralisation effects

If a neutralisation state becomes validated:
- Mark ordinary pace/gap interpretations as potentially non-comparable during the state.
- Suspend or qualify strategy calculations that assume normal racing conditions.
- Do not calculate or announce restart instructions unless the relevant ACC procedure and telemetry are explicitly supported.
- Restore normal calculations only after a confirmed return to the applicable racing state.

## 5. Recommendation and message logic

Messages should prioritise confirmed, actionable race-state information and avoid translating uncertain codes into authoritative instructions.

Illustrative message intent (not hard-coded triggers):

- **Session state:** “Session is now active.”
- **Confirmed flag:** “Yellow flag reported by ACC. Follow the in-game instructions.”
- **Confirmed penalty:** “ACC reports a penalty. Check the in-game penalty display for its serving requirements.”
- **Unknown code:** “Race-control state is unavailable; check the ACC HUD.”
- **Timer expiry without finish confirmation:** “Session timer has expired. Race completion is not yet confirmed.”
- **Confirmed finish:** “Race finished.”
- **Stale source:** “Race-state telemetry is stale. Follow the ACC HUD.”

The strategy must not:
- Invent flag meanings, penalty types or serving instructions.
- Tell the driver to pit, stop, slow down, overtake or restart based on unvalidated data.
- Treat lap invalidity as a flag or penalty.
- Treat a timer reaching zero as proof the race is finished.
- Claim a safety car, VSC, FCY or red flag without a validated source.
- Override or contradict the ACC HUD or server instructions.

## 6. Communication and priority

Race-State Strategy uses the agreed Race Engineer communication modes:

- **Driver-initiated:** quiet except confirmed critical warnings. Race-state details are available on request.
- **Balanced (default):** announce meaningful, confirmed changes such as a validated penalty, flag/track-state transition or session transition. Suppress routine unchanged status.
- **Active race engineer:** provide more proactive updates for confirmed race-state changes, without repeating the same state on every telemetry sample.

Rules:
- Confirmed high-priority race-control information may be announced in every mode, subject to the global critical-warning policy.
- Candidate or unknown codes must never be promoted to critical warnings.
- Deduplicate events and announce meaningful severity/status changes.
- If an event is cleared, announce clearance only when the source semantics confirm it.
- When telemetry is stale or ambiguous, explicitly defer to the ACC HUD.
- Reuse the existing Windows TTS and shared radio/message queue when integrated. This document does not implement TTS.
- Race-State messages take precedence over routine pace/traffic commentary when a confirmed race-control event materially affects the driver.

## 7. UI requirements

The Race-State view should show only information supported by validated sources:

- Current session type/state and source freshness.
- Session time remaining.
- Completed laps and race lap limit as separate values, with candidate status shown where applicable.
- Confirmed current flag/track status, including source and freshness.
- Confirmed active penalties and their details only where semantics are validated.
- Safety-car/neutralisation state only if a validated source exists.
- Recent confirmed race-state events with timestamps.
- Clear unknown/unavailable/stale indicators instead of guessed labels.
- A reminder that ACC HUD/server instructions remain authoritative.

Do not render unknown integer codes as familiar flag or penalty labels. Do not show a green/ yellow/red state merely as decoration when the source is unknown.

## 8. Shared data and service boundaries

Race-State Strategy should consume existing freshness-aware decoded snapshots and shared event infrastructure.

Likely shared dependencies:
- Graphics session/status, flag, penalty and race-progress fields.
- Session identity and transition lifecycle.
- Completed-lap and session-time observations.
- Shared timestamp/freshness checks and event deduplication.
- Shared radio priority and message queue.
- Pace/Fuel strategy race-progress context, but only through validated common state.

Common session-state normalization and event lifecycle should be reusable across strategies. Race-control interpretation and message priority remain owned by Race-State Strategy / Race Engineer domain services.

## 9. Validation plan and release gates

### Gate A — field semantics and enum mapping

1. Inventory the exact decoded session, status, flag, penalty and race-control fields.
2. Record raw values and compare each controlled ACC state with the in-game HUD.
3. Establish enum mappings only for values directly observed and repeatably correlated.
4. Validate units, timing, momentary versus persistent behaviour and clear/reset semantics.
5. Determine whether safety-car, VSC, FCY, red-flag and chequered states are actually exposed in the supported ACC modes.
6. Validate stale/disconnected behaviour and unknown-code handling.

### Gate B — lifecycle and calculations

1. Test session start, active running, pause/replay/garage, session end and next-session transitions.
2. Test reconnect and acquisition restart without creating false new-session events.
3. Test each exposed flag transition and its clearing behaviour.
4. Test each exposed penalty/warning transition and lifecycle.
5. Validate completed-lap count separately from lap limit.
6. Test timer expiry and actual finish-line completion in timed races.
7. Confirm that unknown or stale values never create semantic race-control announcements.

### Gate C — race scenarios

- Practice, qualifying and race sessions.
- Session timer running, expiring and transitioning to actual finish.
- Valid and invalid laps.
- Each race-control flag state that ACC actually exposes.
- Penalty issued, changed, served and cleared, where exposed.
- Safety-car or neutralisation states only if supported.
- Session restart, reconnect, replay/garage transition and new session.
- Telemetry becoming stale during an active event.

### Gate D — integration and acceptance

- Reuse existing telemetry acquisition; no second shared-memory reader.
- Do not duplicate Pace Strategy or Traffic Strategy responsibilities.
- Correct priority, deduplication and clearing behaviour across all three communication modes.
- UI and radio distinguish observed, calculated and unknown states.
- ACC HUD and server instructions remain authoritative.
- Race Engineer remains read-only and never operates controls or performs race actions.
- Automated tests, production build and live Windows ACC validation are completed before claiming release readiness.

## 10. Explicit non-goals

- Controlling the car or performing pit/penalty actions.
- Replacing the ACC HUD, server rules or official race-control instructions.
- Guessing flag/penalty enum mappings.
- Claiming unsupported safety-car, VSC, FCY, red-flag or chequered states.
- Predicting the exact final lap from timer expiry without validated finish behaviour.
- Making strategy calculations from stale or unvalidated race-state inputs.
- Inventing penalty serving procedures or restart instructions.

## 11. Current implementation status

This document records the Race-State Strategy design only. It does not claim that flag/penalty interpretation, neutralisation detection, session lifecycle, finish detection, UI or radio integration have been implemented or validated.

The current telemetry audit identifies session type/state and race-control integer codes as candidates requiring controlled transition and HUD correlation. Session time remaining and completed lap count have separate user validation, but race lap-limit and timed-race finish semantics remain gated. The next engineering task is to inspect the existing decoded APIs and validate exact state/enum semantics before enabling race-control announcements. No new shared-memory reader should be introduced.
