# iRacing In-Car Settings — SDK Inventory and Dynamic Mapping

## Objective

The iRacing Car Electronics tile displays only the adjustments and persistent selections exposed by the **currently loaded car**. It does not use a fixed universal list or infer permitted settings from a car name.

The active iRacing SDK telemetry header is the runtime source of truth. The reader inspects the header on every snapshot, discovers eligible `dc*` driver-control variables, and publishes their live values and SDK metadata. This means the list can change when the driver changes cars without restarting SimLink.

## Runtime mapping

Source: active SDK variable header plus its live value.

| SDK metadata/value | Normalized field | Meaning |
|---|---|---|
| `name` | `name` | Exact SDK variable identifier |
| `desc` | `description` | SDK-provided description |
| `unit` | `unit` | SDK unit, empty if none is defined |
| live variable value | `value` | Raw number or boolean |
| value type | `value_type` | `number` or `boolean` |

Payload: `physics.data.in_car_settings[]`.

The frontend uses the SDK description as the label. Boolean values render ON/OFF. Numeric values are passed through unchanged and display a unit only if the active SDK header provides one. The app does not assume percentage, degrees, or a numbered level. For example, the SDK does not define a unit for `dcBrakeBias`, so the tile must not append `%`.

### Runtime eligibility rules

- Variable name must begin with `dc`.
- The active header description must identify an `In car ...` control.
- Persistent adjustments and selections are included.
- Momentary commands whose descriptions contain `trigger` or `momentarily` are excluded.
- A missing header entry means the active car does not expose the setting; omit it.
- If a header entry has no readable scalar live value, omit it rather than inventing zero.
- Unknown future `dc*` fields are discovered automatically when their SDK description matches the in-car setting rule.
- No per-car cache or hard-coded car allowlist is used.

## Published in-car adjustment catalogue

This is a reference union across published iRacing telemetry references and community-maintained variable catalogues. It is **not** a promise that every field is exposed by every car or every SDK version. Runtime header presence decides what the tile displays.

| SDK variable | Setting / category | Unit or scale |
|---|---|---|
| `dcABS` | ABS adjustment | Not specified |
| `dcAntiRollFront` | Front anti-roll bar | Not specified |
| `dcAntiRollRear` | Rear anti-roll bar | Not specified |
| `dcBoostLevel` | Boost level | Not specified |
| `dcBrakeBias` | Brake bias | Not specified |
| `dcBrakeBiasFine` | Fine brake bias | Not specified |
| `dcBrakeMisc` | Brake miscellaneous adjustment | Not specified |
| `dcDashPage` | Dashboard page | Not specified |
| `dcDashPage2` | Second dashboard page | Not specified |
| `dcDiffEntry` | Differential entry | Not specified |
| `dcDiffMiddle` | Differential mid-corner | Not specified |
| `dcDiffExit` | Differential exit | Not specified |
| `dcEngineBraking` | Engine braking | Not specified |
| `dcEnginePower` | Engine power | Not specified |
| `dcFuelMixture` | Fuel mixture | Not specified |
| `dcRevLimiter` | Rev limiter | Not specified |
| `dcThrottleShape` | Throttle shape | Not specified |
| `dcTractionControl` | Traction control | Not specified |
| `dcTractionControl2` | Secondary traction control | Not specified |
| `dcTractionControl3` | Third traction control (newer catalogue) | Not specified |
| `dcWeightJackerLeft` | Left weight jacker | Not specified |
| `dcWeightJackerRight` | Right weight jacker | Not specified |
| `dcWingFront` | Front wing | Not specified |
| `dcWingRear` | Rear wing | Not specified |
| `dcLowFuelAccept` | Low-fuel acceptance | Not specified |
| `dcLaunchRPM` | Launch RPM | Not specified |
| `dcPowerSteering` | Power steering | Not specified |
| `dcMGUKDeployMode` | Hybrid MGU-K deployment mode | Not specified |
| `dcMGUKRegenGain` | Hybrid MGU-K regeneration gain | Not specified |
| `dcMGUKDeployFixed` | Hybrid fixed deployment | Not specified |
| `dcFuelCutPosition` | Fuel-cut position | Not specified |

## Persistent control states

These are persistent selections/states, not numeric setup adjustments. They are displayed as ON/OFF if the active header exposes them as in-car controls.

| SDK variable | Purpose |
|---|---|
| `dcTractionControlToggle` | Traction control active state |
| `dcPitSpeedLimiterToggle` | Pit speed limiter active state |
| `dcFuelNoCutToggle` | Fuel-cut-on-straight state |
| `dcFCYToggle` | Full-course-yellow mode state |
| `dcInLapToggle` | In-lap setting state |
| `dcHeadlightFlash` | Headlight flash state |
| `dcToggleWindshieldWipers` | Wipers on/off selection |
| `dcRFBrakeAttachedToggle` | Right-front brake attached/detached state |

## Commands excluded from the settings tile

These are momentary actions, not persistent adjustments:

- `dcStarter` — starter trigger.
- `dcTriggerWindshieldWipers` — momentary wiper trigger.
- `dcTearOffVisor` — visor tear-off action.
- `dcDRSToggle` — DRS toggle command; use a separate DRS status field for active state.
- `dcPushToPass` — push-to-pass command; use a separate active/status field.
- `dcHysBoostHold` — hybrid boost hold command; classify as a setting only if a future SDK description confirms persistent state.

## Pit-service boundary

Variables beginning with `dp` represent pit-service requests or pit-stop adjustments, not the live in-car adjustment list. They remain in the Pit Stop & Stint mapping (fuel, tyres, fast repair, wing, wedge, and related requests).

## Current application behaviour

- iRacing Car Electronics renders `physics.data.in_car_settings` dynamically and retains Water Temperature as a separate engine metric.
- ACC Car Electronics rendering is unchanged.
- Existing named iRacing fields remain available for other consumers; the tile uses the dynamic array as its source of truth.
- No per-car settings allowlist, guessed units, or guessed value scales are used.

## References

- iRacing SDK telemetry variable list: https://sajax.github.io/irsdkdocs/telemetry/
- SDK variable metadata structure (name, description, unit, count): https://github.com/mherbold/IRSDKSharper
- Generated telemetry variable catalogue: https://irsdk-node.bengsfort.dev/API-Reference/irsdk-node-types/interfaces/TelemetryVarList/
- Extended driver-control examples: https://iracedeck.com/docs/features/template-variables/
- Recent multi-car variable union examples, including hybrid controls: https://github.com/mvoof/kerb/blob/main/CHANGELOG.md

These public catalogues are reference material, not the per-car allowlist. The active SDK header remains authoritative for the fields SimLink displays.
