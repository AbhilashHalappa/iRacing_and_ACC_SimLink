# Strategy Live Data and Compact Lap History

**Status:** Approved implementation contract  
**Scope:** Race Engineer ACC New, Stage 2 decoded-data consumers and strategy inputs

## 1. Decision

Every strategy uses two complementary inputs:

1. **Live decoded state** for current conditions and immediate decisions.
2. **Compact completed-lap history** for trends, averages, comparisons and predictions.

High-resolution lap telemetry is not a dependency of the Strategy Engine. It remains available for a future dedicated driving-analysis feature if a demonstrated requirement justifies its memory and storage cost.

Live state is authoritative for what is happening now. History must never override a fresh live measurement. A strategy that needs a live value must not silently substitute a historical value when that live value is stale or unavailable.

## 2. Architecture

```text
ACC Shared Memory
       |
Existing Stage 1 raw-data fan-out (unchanged)
       |
Existing Physics / Graphics decoders (unchanged)
       |
Stage 2 decoded-data fan-out
       |
       +---- Existing Overview consumer (unchanged)
       |
       +---- Strategy live-state consumers
       |
       +---- Shared Strategy Lap History consumer
                    |
                    +---- Fuel strategy
                    +---- Tyre strategy
                    +---- Pit strategy
                    +---- Pace strategy
                    +---- Race strategy
                    +---- Future strategy consumers
```

The Strategy Engine consumes decoded state and domain events only. It must not read ACC shared memory, raw acquisition pages, raw rings, or decoder internals. Each downstream consumer has independent bounded delivery; a slow strategy must not block acquisition, decoding, Overview, or another strategy.

## 3. Lap boundary and classification authority

- Completed-lap boundaries come from the existing Stage 2 decoded Graphics lap-completion event.
- Lap validity comes directly from ACC Graphics `is_valid_lap`. Do not independently calculate or reinterpret validity.
- Out-lap classification must reuse the existing Overview/desktop out-lap observer result. Do not introduce a second out-lap detector or infer out-lap status from lap validity.
- The orange Overview glow is presentation. Strategy history must receive the observer's underlying classification state, not inspect UI styling. The existing `ACCOutLapObserver` is owned by the Stage 2 decoded broker and supplies both the unchanged Overview `lap_status` field and the completed-lap classification; there is one observer instance, not a duplicate strategy detector.
- Classification must be associated with the lap that was active before the start/finish transition. Do not accidentally apply the newly started lap's state to the lap that just completed.
- Unknown or unavailable classification remains unknown. It must not be promoted to false.
- The existing out-lap observer currently detects the initial garage-to-track out-lap. Its known scope must not be silently expanded to mid-race pit exits.

## 4. Compact per-lap record

Store one record per observed completed lap. Do not store high-frequency Physics or Graphics samples.

A record may contain only values available and sufficiently fresh at the lap boundary:

| Group | Fields |
|---|---|
| Identity | Session identity, lap number |
| Classification | ACC valid/invalid/unknown, existing out-lap true/false/unknown |
| Timing | ACC last lap time |
| Fuel | Fuel remaining, Graphics fuel-per-lap and used-fuel observations |
| Tyres | Compound, four tyre pressures, four core temperatures and other validated per-wheel measurements |
| Race / pit context | Position, gaps ahead/behind, penalties, mandatory-pit state and driver-stint time remaining |
| Conditions | Rain intensity, track-grip status, air and road temperatures |
| Vehicle condition | Validated brake temperature, damage and relevant condition measurements |
| Provenance | Graphics and Physics capture sequence/timestamp for the sampled values; freshness/availability state |

Physics and Graphics are independent streams and are not guaranteed to be synchronized. The Stage 2 lap event carries this compact boundary sample alongside ACC lap timing and classification, avoiding correlation against a later coalesced snapshot. Every captured field must retain its own source timestamp/sequence. A missing or stale measurement stays null/unavailable; it is never filled with a value from an unrelated lap.

Session-level identity such as track and car should be stored once per session, not duplicated in every lap record. Keep storage bounded to the current session and a configured recent-lap limit. Persist compact lap records only; do not persist high-frequency telemetry for strategy.

## 5. Strategy input rules

| Decision | Input |
|---|---|
| Current fuel warning | Live Physics fuel |
| Fuel consumption trend / finish projection | Compact lap history plus fresh live fuel |
| Current tyre-temperature warning | Live Physics tyre temperatures |
| Tyre degradation trend | Compact lap history plus live tyre state |
| Pit now / continue | Live race and pit state plus historical consumption/degradation trends |
| Immediate damage warning | Live Physics damage |
| Pace consistency | ACC-valid, non-out-lap history |
| Race progress | Live Graphics state; history may support trend estimates |

A strategy must check source freshness, validity, session identity and history completeness before calculating. If a required input is unavailable, stale, contradictory or incomplete, it must expose that limitation and withhold an unreliable recommendation.

## 6. Eligibility and gaps

Keep invalid and out-laps in the history as records for auditability. Strategy-specific calculations select eligible records:

- ACC-invalid laps are excluded from representative pace calculations.
- Out-laps are excluded from representative timed-lap calculations.
- Unknown validity or out-lap classification is not treated as valid/false.
- A completed-lap counter jump, event queue gap, session reset or unreconciled sequence discontinuity marks history incomplete.
- Never fabricate missing lap records from the latest ACC lap counter or latest-lap fields.
- Cursor reconciliation restores current progress only; it does not reconstruct missing historical laps.

History completeness and per-strategy eligibility are separate. A known invalid lap does not make the history incomplete; it is simply ineligible for calculations that require a valid timed lap.

## 7. Storage and performance

- No raw recorder dependency.
- No second ACC reader.
- No high-frequency telemetry persistence.
- One compact record per completed lap.
- Bounded in-memory history and bounded persistent session history (SQLite, one current session, up to 256 recent lap records).
- Persistence is performed only at session/lap-history changes, never at the Physics/Graphics sample rate. A dedicated bounded background writer handles SQLite I/O away from Overview publication, acquisition and decoder threads.
- On recovery, verify session identity and lap continuity. If identity or continuity cannot be established, retain diagnostic records if useful but mark the history incomplete and disable calculations that depend on completeness.

## 8. Non-goals and preservation constraints

- Do not modify Stage 1.
- Do not change existing Overview behaviour, UI payload shape, rendering or update cadence.
- Do not create a second lap-validity or out-lap classifier.
- Do not make Fuel the owner of shared lap history.
- Do not make high-resolution telemetry a prerequisite for any race-strategy consumer.
- Do not let strategy consumers issue ACC controls. The Race Engineer remains read-only; the driver makes all decisions and actions.
