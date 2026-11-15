# Fuel Strategy Implementation Audit

**Repository:** AbhilashHalappa/Race-Engineer-ACC-New  
**Audit branch:** `feature/fuel-strategy`  
**Audited baseline:** branch created from `feature/stage2-decoded-fanout` at the current branch tip  
**Date:** 2026-11-15  
**Scope:** Stage 2 decoded-data consumers, Race Engineer service, ACC decoders, Qt host and Race Engineer UI. Stage 1 and the existing Overview implementation are explicitly out of scope and must remain unchanged.

## Executive result

**Status: PARTIALLY IMPLEMENTED — NOT RELEASE-COMPLETE.**

The current integrated feature is a useful live fuel-sufficiency display for timed races. It reads ACC fuel observations, estimates remaining race laps from five valid completed laps, compares ACC fuel endurance against that estimate, applies a three-lap reserve, and displays an advisory fuel-add estimate. The user has validated the main values and one refuel/counter-reset sequence in ACC.

It is not yet a complete race fuel strategy. There is no qualified pit-window decision, no mandatory-stop strategy, no tank-capacity enforcement, and no spoken/controlled radio announcement system. Lap-based race finish distance is not currently calculated. Some older strategy modules exist but are not wired into the live service.

## What is integrated today

| Area | Current implementation | Audit result |
|---|---|---|
| Current fuel | Physics decoded field `fuel_kg` exposed as litres | Live-tested by user; internal field name/unit contract needs cleanup |
| ACC fuel/lap | Graphics `fuel_per_lap_l` | Read directly; no local recalculation |
| ACC fuel endurance | Graphics `fuel_estimated_laps` | Read directly; no local division estimate |
| ACC MFD fuel addition | Graphics `mfd_fuel_to_add` | Exposed as a separate ACC value |
| ACC stint fuel used | Graphics `used_fuel_l` | Exposed as current-stint counter |
| Cumulative fuel used | In-memory `SessionFuelUsedAccumulator` | One pit/refuel reset validated; process-local only |
| Timed-race progress | Graphics countdown plus five latest valid classified non-out laps | User validated live race output |
| Finish fuel | Remaining laps × ACC fuel/lap | Implemented for timed-race estimate only |
| Raw margin | ACC fuel laps minus estimated race laps; current fuel minus estimated required litres | Implemented |
| Safety reserve | Fixed three-lap reserve | Implemented |
| Next-pit fuel addition | `max(0, required fuel + reserve fuel - current fuel)` | Implemented as a conditional estimate, not a pit-window strategy |
| Radio | Text preview only | No TTS, trigger policy, cooldown or spoken messages |
| UI | Race Engineer page | Displays fuel and race-progress fields; user screenshots validate the display |

## Findings and required work

### P0 — Release blockers

1. **No pit-window / pit-now decision.** The current result estimates an amount to add at a hypothetical next stop. It does not decide whether to pit now, which lap to pit on, or whether the car can safely reach the pit entry. No pit-lane travel or pit-arrival fuel requirement is modelled.
2. **No tank-capacity enforcement.** Static decoding already exposes `max_fuel`, but the integrated fuel assessment does not consume it. The recommendation can therefore exceed the car's usable tank capacity or fail to identify an impossible target.
3. **No mandatory-pit strategy.** Graphics decoding exposes candidate fields `mandatory_pit_done` and `missing_mandatory_pits`, as well as pit-state fields. The live strategy does not use them. These fields need semantic/live qualification before they can affect recommendations.
4. **No spoken radio strategy.** `fuel_radio_preview` is explicitly `observation_only`, `speech_enabled=false`, and `strategy_recommendations_enabled=false`. There are no recommendation triggers, repeat suppression, cooldowns, pit confirmation or refuel-complete announcements.
5. **Lap-based race finish distance unavailable.** `RaceProgressAssessment` does not calculate remaining laps from a qualified lap limit. It intentionally leaves `number_of_laps` unqualified. Fuel-to-finish and pit-add estimates are consequently unavailable for lap-based races.

### P1 — Correctness and robustness

6. **Fuel-per-lap zero is accepted by the integrated sufficiency assessment.** The helper validates non-negative values, not strictly positive fuel/lap. A fresh zero can produce a zero target and a false sufficient result. Require a positive, plausible value before any fuel target or pit-add calculation.
7. **Physics fuel field naming is misleading.** The decoder calls the ACC Physics fuel float `fuel_kg`, while the consumer and UI treat it as litres. The user has live-tested the displayed values, but the code should use a unit-correct name and document the ACC ABI field semantics consistently before expanding calculations.
8. **Fuel recommendation assumes a stop at the end of the current lap.** The algebraic estimate is valid only under the stated constant-consumption assumption. It does not include current-lap progress, pit-entry distance, formation/slow-down effects, safety margin for the trip to pit entry, or a changing fuel-per-lap forecast.
9. **Timed-race remaining-lap estimate needs finish-rule qualification.** Current logic uses floor(remaining timer / mean lap time). The relationship between timer expiry, the player's next line crossing, ACC's extra-lap rule and the actual finish needs validation across race configurations before being treated as a guaranteed fuel requirement.
10. **Fuel/lap freshness and plausibility need stronger gates.** Freshness is checked, but no upper/lower plausibility envelope, change-rate handling, or outlier handling is applied to the raw Graphics value.
11. **Cumulative fuel-used is process-local.** It starts at the first observed value, is not persisted, and resets when Race Engineer restarts. The UI correctly scopes it as “since Race Engineer connected”; it must not be presented as guaranteed full-session fuel.
12. **Counter-reset detection is simplistic.** Any decrease in ACC stint fuel-used is treated as a reset and the new value is added. This handles the tested refuel reset, but needs tests/guards for duplicate samples, small regressions, session transitions, missing samples and unusual ACC counter behaviour.
13. **Strategy readiness flags are inconsistent.** `FuelEngineerSnapshot.strategy_calculations_enabled` currently requires current fuel and ACC fuel-laps data, but does not require valid fuel/lap or a valid race-distance estimate. Its name can imply more readiness than it guarantees.
14. **Blocker reporting and sub-estimate availability need a clear contract.** The overall assessment can be unavailable because ACC fuel-laps data is missing while the pit-add sub-estimate can still be available from current fuel, fuel/lap and race laps. This may be mathematically intentional, but the UI and API must clearly distinguish independent calculation readiness.

### P2 — Integration / maintenance

15. **Legacy strategy modules are not integrated.** `fuel_strategy.py` and `fuel_consumption_strategy.py` are exported from the package but are not called by `RaceEngineerService.snapshot()`. The former also expects an `estimated_laps_fresh` property that is not present on the current `FuelEngineerSnapshot`. Decide whether to retire these modules or deliberately integrate one strategy path; avoid two competing fuel calculations.
16. **Measured consumption strategy is not wired.** `fuel_consumption_strategy.py` can derive lap-to-lap consumption from compact lap records, but the service currently uses ACC's direct fuel/lap value only. The measured estimate should be retained as an independent cross-check/trend, not silently substituted for ACC's direct value.
17. **No explicit per-lap strategy event/update contract.** The Qt host polls the service snapshot at 50 ms and therefore recalculates frequently, but there is no explicit “new completed lap” assessment event or persisted recommendation state. Radio triggers must be event/state-transition based, not spoken on every UI poll.
18. **Test coverage is narrow.** Existing tests cover basic ACC field extraction, basic accumulator increases/resets, the three-lap reserve, one pit-add example, and timed-race average calculation. Missing cases are listed below.
19. **Decoder ABI confidence is documented as candidate, not official Kunos certification.** Graphics and Static decoder headers explicitly describe candidate layouts. User live tests validate selected values, but every strategy-driving field must be qualified against actual ACC observations and not assumed correct solely because a candidate offset decodes.

## Existing architecture compliance

- The integrated service consumes Stage 2 decoded snapshots and compact lap history.
- The broker's role is downstream of existing decoders.
- No reason was found in the inspected fuel path to modify Stage 1.
- No reason was found to modify the existing Overview implementation.
- Keep all future fuel work in Stage 2 consumers/service and the Race Engineer page. Do not introduce another acquisition reader, decoder, raw-page consumer or high-resolution recorder.

## Required test matrix before release

### Input and freshness
- Physics stale / Graphics stale independently.
- Missing, NaN, infinity, negative, boolean and zero fuel values.
- Zero, implausibly low and implausibly high fuel/lap.
- ACC fuel-laps missing or stale while other values remain fresh.
- Graphics and Physics samples with different capture ages.

### Race distance
- Timed race with fewer than five valid laps.
- Five valid laps, invalid laps and out-laps interspersed.
- Lap-time outlier and abrupt pace changes.
- Timer expiry and actual checkered finish, including `has_extra_lap` true/false.
- Lap-based race with qualified lap limit and extra-lap semantics.
- Practice / qualifying / unknown session types.
- Session reset, pause/resume and reconnect.

### Fuel calculation
- Positive/negative raw margin and safety-adjusted margin.
- ACC endurance estimate compared directly, without recomputing it from current fuel.
- Changing ACC fuel/lap values.
- No-stop-needed and shortfall cases.
- Pit-add estimate with unavailable inputs.
- Tank capacity, current fuel near maximum, and target exceeding capacity.
- Pit-entry arrival fuel and remaining fuel-to-finish.
- Mandatory stop count / completion / fuel requirement.

### Fuel-used accumulator
- Increasing values.
- Duplicate values (must not double count).
- Refuel reset to zero and non-zero reset.
- Missing/invalid values.
- Small backward sample / out-of-order sample.
- Session identity change.
- App restart limitation documented and tested.

### Radio and pit lifecycle
- One warning when shortfall first appears.
- Escalation when margin crosses reserve/critical thresholds.
- No repeated announcement every 50 ms.
- Recovery / cancellation after refuel.
- Pit entry, pit exit and refuel-complete transition.
- No speech from stale or unqualified inputs.
- Manual mute / text-only mode and TTS unavailable.

## Recommended implementation order

1. Fix input validation and readiness contracts (especially strictly positive fuel/lap).
2. Qualify remaining-race-lap logic for timed and lap-based races, including ACC finish rules.
3. Add tank-capacity-aware target and pit-add calculations.
4. Qualify mandatory-pit and pit-state semantics, then implement pit-window / pit-now logic.
5. Add persistent strategy state and per-lap/state-transition assessment events.
6. Implement radio recommendation policy, repeat suppression and TTS routing.
7. Integrate measured consumption as a cross-check and remove or consolidate obsolete strategy modules.
8. Complete automated tests and run a controlled ACC validation matrix.

## User-validated live evidence recorded before this audit

The user supplied two chronological readings from the same race (Screenshot 2 first, Screenshot 1 second):

- First: 11.8 L current fuel; 2.72 L/lap; 4.3 ACC fuel laps; 15 estimated race laps; 40.8 L estimated finish fuel; 37.2 L estimated next-pit addition including reserve; 17.2 L ACC current-stint fuel used; 35.5 L cumulative since connection; 43.0 L ACC MFD fuel-to-add.
- Second, after refuelling: 57.8 L current fuel; 2.72 L/lap; 21.2 ACC fuel laps; 15 estimated race laps; 40.8 L estimated finish fuel; 0.0 L estimated next-pit addition; 0.0 L ACC current-stint fuel used; 35.6 L cumulative since connection; 0.0 L ACC MFD fuel-to-add.

This validates the observed refuel transition and the separation between ACC's stint counter, Race Engineer's in-memory cumulative counter, and ACC's MFD amount. It does not validate pit-window timing, tank capacity, mandatory stops or radio behaviour.


## Second-pass source verification (2026-11-15)

This section records a deeper source-level pass over the live service, fuel modules, Graphics/Physics decoders, race-progress logic, and focused fuel tests. It supersedes any broad interpretation above where it adds precision.

### Confirmed details and corrections

- **The live path is exactly identifiable:** `RaceEngineerService.snapshot()` calls `build_fuel_engineer_snapshot()`, then `assess_race_progress()`, then `assess_fuel_sufficiency()`. It does not call `assess_fuel_strategy()` or `assess_measured_fuel()`. The Race Engineer UI reads the `fuel_sufficiency_strategy` payload.
- **A second fuel strategy module already exists, but is deliberately conservative and currently disconnected.** `fuel_strategy.py` requires an explicitly validated actual-finish lap count and positive fuel/lap, and deliberately returns no pit recommendation. It cannot currently be dropped into the live service: it asks the fuel snapshot for `estimated_laps_fresh`, while the integrated snapshot exposes `fuel_laps_fresh`. This is an integration/API mismatch, not proof that its calculation is production-ready.
- **A measured-consumption estimator also already exists with focused tests.** `fuel_consumption_strategy.py` estimates consumption from consecutive classified valid timed-lap fuel-boundary records, rejects lap gaps/refuel increases, and requires at least two intervals by default. It is not called by the live service and its estimate is not shown in the UI. It should be a cross-check, not a silent replacement for ACC's direct fuel/lap field, consistent with the user's chosen source-of-truth rule.
- **The radio preview is definitively observation-only.** The service builds a static text summary; payload flags are `speech_enabled=false` and `strategy_recommendations_enabled=false`. There is no TTS dispatch, threshold trigger, cooldown, duplicate suppression or state-transition policy in this fuel service.
- **Tank capacity is available in decoded Static metadata as `max_fuel`.** The live fuel assessment does not receive Static metadata, so no capacity check is currently performed.
- **Pit/mandatory fields are present in the Graphics candidate decoder:** `is_in_pit`, `is_in_pit_lane`, `mandatory_pit_done`, `missing_mandatory_pits`, `driver_stint_left_ms`, `driver_stint_total_ms`, and MFD fuel-to-add. Their presence in a candidate decoder does not qualify their semantics or establish a working pit strategy. They are not consumed by the current fuel service.
- **The fuel-used accumulator handles duplicate samples naturally** (zero delta), but every downward movement is treated as a stint reset and the new value is added. There is no threshold or monotonic packet/capture guard inside the accumulator. Existing tests cover a normal increase, one reset, new session ID and missing observations; they do not cover out-of-order samples, small regressions, duplicate packet delivery, or restart persistence.
- **Zero fuel/lap is a real validation gap in the integrated path.** Both `fuel_engineer.py` and `fuel_sufficiency_strategy.py` accept finite non-negative fuel/lap. The separate disconnected `fuel_strategy.py` correctly requires fuel/lap > 0, but that guard does not protect the live UI calculation.
- **The live timed-race estimate is floor(timer / mean of five latest valid laps).** It is not yet qualified against the actual ACC finish-line rule, the static `has_extra_lap` value, or observed chequered transitions. The implementation deliberately leaves Graphics `number_of_laps` and `global_chequered` unqualified and does not calculate lap-based remaining distance.
- **Current-fuel field naming needs a careful ABI check, not an assumption.** The Physics decoder reads the float at byte offset 12 into a property named `fuel_kg`, while the UI treats it as litres and the user's ACC readings look plausible. This audit has not independently established a kg-to-litre conversion or a mismatch. Do not add a conversion. The proper pending task is to verify the field's documented ACC unit and rename the decoded property if the value is indeed litres.

### Exact focused-test coverage found

- `tests/test_race_engineer_fuel.py`: direct field extraction, stale streams, invalid/negative values, accumulator normal increase/reset/new session/missing observation. No zero fuel/lap assertion, duplicate/out-of-order samples, or persistence test.
- `tests/test_fuel_sufficiency_strategy.py`: direct ACC fuel-lap comparison, unavailable source, three-lap reserve, reserve shortfall and basic next-pit addition. No zero fuel/lap, tank capacity, mandatory pit, pit arrival, race-finish edge cases or recommendation/radio lifecycle tests.
- `tests/test_fuel_consumption_strategy.py`: measured consumption, invalid/out laps, classification, lap gaps, refuelling increase, stale current fuel and configuration validation. These tests validate the standalone estimator only; they do not prove integration into the live service.
- No `tests/test_fuel_strategy.py` exists at the inspected path, despite the module being exported from the package.

### Revised pending-work list (verified)

1. Fix the live-path positive fuel/lap validation and strengthen plausible-range/freshness checks.
2. Qualify timed-race finish-lap semantics and implement a separate validated lap-based finish-distance provider; keep unknown cases unavailable.
3. Add tank-capacity constraints using fresh Static `max_fuel`.
4. Qualify pit entry/lane/mandatory-stop field semantics from ACC live captures before implementing pit window, pit-now, mandatory stop and refuel-completion logic.
5. Model fuel required to reach pit entry and distinguish it from fuel required to finish; label the current pit-add figure as a simplified end-of-current-lap estimate until then.
6. Define one canonical strategy API. Either integrate the conservative `fuel_strategy.py` after resolving the `estimated_laps_fresh`/ `fuel_laps_fresh` mismatch and validated finish-distance contract, or remove it. Do not maintain parallel competing calculations.
7. Integrate measured fuel consumption as a displayed/diagnostic cross-check only, with explicit disagreement handling against ACC fuel/lap.
8. Implement radio policy and TTS only after calculation confidence, trigger thresholds, cooldown, repeat suppression, mute and recovery transitions are specified.
9. Expand accumulator tests and decide whether cumulative fuel should persist across app restarts; current UI scope text is correct for its process-local implementation.
10. Add service-level integration tests proving the actual `RaceEngineerService.snapshot()` output and UI payload are wired to the intended calculation path.

### Scope limitation

This is a source-level audit of the fuel-related modules and their direct service/UI/decoder dependencies, not a claim that every repository file or every historical product requirement has been exhaustively reviewed. Any requirement not traceable to a written specification or inspected implementation is intentionally not labelled complete.



## Issue #27 implementation update (2026-11-15)

The Stage 2 race-progress consumer now publishes one canonical distance estimate:
- `estimated_race_laps_remaining`
- `estimated_race_laps_source`
- `estimated_race_laps_qualified`
- Existing `laps_remaining` remains as a compatibility alias.

Timed races retain the existing calculation: floor(remaining ACC session timer / mean of the latest five valid, classified, non-out completed laps). The source is explicit and the estimate is marked unqualified for guaranteed finish distance until ACC timer-expiry, final-crossing and extra-lap behaviour is validated in live sessions. `has_extra_lap` remains observational; no unverified +1 lap is added.

Lap-based arithmetic is implemented behind an explicit `lap_limit_qualified=True` gate: qualified ACC lap limit minus valid completed-lap count. It returns zero at the lap limit and fails closed if the completed count is missing or exceeds the limit. The live service does not enable this gate yet because issue #22 has not completed its ACC field qualification. Until then, lap-based remaining distance remains unavailable rather than using the unqualified Graphics candidate.

The live service now passes the canonical estimate to Fuel Sufficiency. Existing `laps_remaining` remains in the Race Progress payload for compatibility. Stage 1 and Overview are unchanged.

Automated tests added for qualified lap-based arithmetic, unqualified/missing/contradictory values, timed estimate source/qualification, and timer expiry. Live ACC finish-rule validation and issue #22 qualification remain outstanding; this issue is not release-complete.
