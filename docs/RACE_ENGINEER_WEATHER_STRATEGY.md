# ACC Race Engineer — Weather Strategy

**Status:** Strategy specification  
**Branch:** `feature/race-engineer-page`  
**Date:** 2026-11-13

## 1. Purpose

Weather Strategy monitors observed ACC weather and track-condition changes, identifies meaningful transitions, and supplies reliable condition context to the other Race Engineer strategies.

Its central responsibility is to answer:
- What are the current weather and track conditions?
- How are they changing?
- Is a transition occurring or likely according to an explicitly exposed ACC forecast?
- Which other strategies should reassess their recommendations?

Weather Strategy is an evidence and coordination service. It does not independently prescribe a tyre change or pit stop.

## 2. Scope and ownership

Weather Strategy owns:
- Collection and freshness assessment of exposed weather and track-condition fields.
- Current-condition snapshots and condition history.
- Trend and transition detection from observed samples.
- Interpretation of explicitly exposed forecast fields, including their documented horizon and update behaviour.
- Communication of meaningful weather changes and their strategic implications.
- Supplying a consistent weather/track-condition context to dependent strategies.

Other strategy ownership remains separate:
- **Tyre Strategy:** tyre pressures, core temperatures, tyre behaviour, dry/wet suitability and tyre-change recommendations.
- **Pace Strategy:** pace and consistency comparisons, with weather context where relevant.
- **Setup Strategy:** evidence-based on-board setup adjustment recommendations; garage-only changes remain deferred.
- **Fuel Strategy:** fuel-consumption assessment and finish-fuel recommendations. Weather may be a context variable, but consumption changes must be observed rather than assumed.
- **Pit-Stop Strategy:** final integrated decision about whether and when to stop, including weather-related tyre decisions.
- **Race-State Strategy:** session and race-control state.

Weather Strategy must not duplicate specialist tyre, pace, setup or pit-stop recommendations.

## 3. Telemetry inputs and validation

The user has confirmed that all weather fields currently exposed by the ACC implementation match the corresponding values shown in ACC.

The current audited field groups include:
- Ambient/air temperature from Physics.
- Track/road temperature from Physics.
- Rain intensity and forecast-related values from Graphics.
- Track-grip/track-condition code from Graphics.
- Wind values from Graphics.

The implementation must preserve each decoded field's raw value, source, units/enum mapping, sample timestamp and freshness status. The user-confirmed value comparison closes the observed-value comparison for the exposed weather fields; it does not by itself establish every forecast horizon, prediction meaning, update cadence or future-condition certainty.

Before a forecast field influences a recommendation, its meaning, time horizon, units or enum mapping, update behaviour and relationship to the displayed ACC forecast must be documented. If that cannot be established, retain it as a raw/candidate display value and do not use it for forward-looking decisions.

Do not substitute an external weather forecast for ACC's in-session weather. Do not infer rain duration, future track wetness or a drying rate from a single current reading.

## 4. Observed conditions and trend assessment

Maintain a time-ordered history of fresh weather samples. Detect meaningful changes and trends only after:
- Rejecting stale, missing, non-finite or invalid samples.
- Handling session transitions and stream reconnects without carrying stale state into a new session.
- Applying field-specific noise/debounce handling supported by observed ACC behaviour.
- Retaining the source timestamp and distinguishing observation time from any forecast target time.

Potential condition states include:
- Stable / no meaningful change.
- Warming or cooling.
- Rain increasing, decreasing or stable.
- Track condition becoming wetter or drier, only if the exposed track-condition signal supports that interpretation.
- Rapid or mixed transition.
- Unknown / insufficient fresh data.

Do not assign arbitrary universal thresholds. Transition thresholds and debounce rules must be established from the actual field scale, update cadence and controlled ACC observations. Preserve raw values so thresholds can be revised without losing evidence.

## 5. Strategic interpretation

Weather Strategy communicates implications as context, not unsupported diagnoses.

| Observed or forecast change | Dependent strategy to reassess | Guardrail |
|---|---|---|
| Track temperature rises | Tyre Strategy | Reassess measured pressures and core temperatures; do not assume overheating. |
| Track temperature falls | Tyre Strategy | Reassess measured tyre behaviour; do not assume a specific pressure change. |
| Rain increases or wet conditions develop | Tyre Strategy and Pit-Stop Strategy | Combine weather evidence with actual track state and tyre observations; weather alone does not mandate a tyre change. |
| Rain decreases or conditions trend drier | Tyre Strategy and Pit-Stop Strategy | Confirm drying from reliable track-condition evidence; do not assume a dry line or exact crossover time. |
| Forecast indicates a future transition | Tyre Strategy and Pit-Stop Strategy | State the forecast horizon and uncertainty; do not present forecast as current conditions. |
| Conditions change materially during a stint | Pace Strategy and Setup Strategy | Reassess comparable pace and validated on-board controls; do not attribute performance changes to weather without evidence. |
| Weather coincides with a fuel-consumption change | Fuel Strategy | Use actual consumption history; weather is context, not a substitute for measured consumption. |

Weather Strategy may raise a condition-change event for dependent strategies to recalculate. The specialist strategy decides whether its own recommendation changes.

## 6. Forecast handling

If ACC exposes a reliable forecast progression for the remainder of the session:
- Retain each forecast value with its target horizon/time and the time it was received.
- Distinguish forecast from observed current weather in data structures, UI and radio wording.
- Update forecasts only when fresh ACC forecast data arrives.
- Track forecast changes over time so the system can identify when ACC's prediction itself changes.
- Use the forecast to prepare the driver for possible transitions, not to assert that a transition is guaranteed.
- Reconcile forecast with observed conditions as the session progresses.
- If forecast fields are missing, stale, ambiguous or have an unknown horizon, report forecast unavailable and fall back to observed conditions.

Do not extrapolate a current rain value into a future forecast. Do not invent probabilities, rain start/end times, track-drying times or confidence percentages.

## 7. Communication behaviour

Use the global Race Engineer communication modes:
- **Driver-initiated:** remain quiet for routine weather changes; critical actionable warnings remain eligible for automatic delivery.
- **Balanced (default):** announce meaningful transitions when they affect a strategic assessment. Avoid routine repetition of unchanged values.
- **Active:** provide proactive concise updates for meaningful observed changes and relevant forecast transitions.

Across all modes:
- Deduplicate unchanged or repeated weather events.
- Announce a meaningful change once, then announce again only if its state or strategic significance changes.
- Distinguish observed conditions from forecast conditions in the wording.
- Include the relevant consequence without duplicating Tyre Strategy's detailed recommendation.
- If data becomes stale, do not continue presenting the last value as current.
- Respect global mute/resume, repeat-last-message and details-on-request behaviour.

Example phrasing:
- “Track temperature is rising; reassessing tyre pressures and temperatures.”
- “Rain intensity is increasing. Check actual track conditions before considering wet tyres.”
- “ACC forecast indicates rain later in the session; current conditions remain dry.”
- “Weather data is stale; I cannot confirm the current conditions.”

These are wording examples, not hard-coded thresholds or automatic tyre/pit commands.

## 8. History and data model requirements

Maintain compact session history containing:
- Session identity and timestamp.
- Raw observed weather fields and their source timestamps.
- Decoded display values with units or enum labels where validated.
- Freshness/validity state.
- Detected transitions and the evidence supporting each transition.
- Forecast values separately, including receive timestamp and target horizon.
- Which dependent strategies were notified and when, where useful for debugging.

History should support comparison across sessions and later analysis of weather effects. Keep the record compact and reuse existing session/history infrastructure. Do not introduce a second shared-memory reader or a high-volume duplicate telemetry store.

## 9. Validation gates

Before enabling strategic use:
- Confirm all weather fields continue to match ACC across relevant session states and selected cars/tracks.
- Verify source timestamps, update cadence, stale-data handling and session reset behaviour.
- Document units and enum meanings for every exposed field.
- Validate track-grip code transitions against ACC's displayed track conditions.
- Validate wind direction/speed interpretation before using it for directional or lap-time conclusions.
- Establish forecast target horizon, update cadence and displayed ACC equivalence before forward-looking recommendations.
- Test transitions from dry to wet, wet to dry, changing track temperature, reconnects and new sessions.
- Confirm that dependent strategies receive the same timestamped weather context without duplicating acquisition.
- Verify that weather alone never triggers a tyre change, setup change or pit-stop recommendation.

## 10. Explicit non-goals and safety boundaries

- No fabricated weather values, forecasts, probabilities, transition times or drying rates.
- No generic tyre operating thresholds or diagnosis owned by Tyre Strategy.
- No automatic tyre, setup, MFD, pit or vehicle control.
- No external forecast substituted for ACC in-session weather.
- No claim that weather caused a pace or fuel-consumption change without repeatable supporting evidence.
- No additional shared-memory reader.
- ACC HUD/server information remains authoritative; Race Engineer is supplementary and read-only.

## 11. Implementation sequence

1. Reuse existing validated weather consumers and expose a freshness-aware, timestamped weather snapshot.
2. Add compact observed-weather and forecast history, keeping the two categories distinct.
3. Implement field-specific trend/transition detection after cadence and semantics are documented.
4. Publish condition-change events to Tyre, Pace, Setup, Fuel and Pit-Stop strategies through shared interfaces.
5. Add mode-aware radio messages with deduplication and stale-data handling.
6. Validate controlled weather transitions in ACC before enabling forecast-driven strategic prompts.

No application code is changed by this specification.
