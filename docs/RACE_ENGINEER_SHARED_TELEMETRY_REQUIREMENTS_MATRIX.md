# ACC Race Engineer — Shared Telemetry Requirements Matrix

**Date:** 2026-11-13  
**Branch:** `feature/race-engineer-page`  
**Status:** Cross-strategy requirements consolidation; source/API audit partially verified  
**Authority:** This matrix consolidates the dedicated strategy specifications. Those documents remain authoritative for strategy behaviour and domain-specific rules.

## 1. Purpose

This matrix identifies telemetry and supporting information that multiple Race Engineer strategies need, where each item originates, which strategies consume it, its current validation status, and the shared service or history capability needed to make it reliable.

It is intended to prevent duplicate telemetry readers, duplicate calculations, conflicting recommendations and unsupported assumptions before strategy implementation expands.

**Evidence boundary:** This pass inspected the existing `RaceEngineerSnapshotAggregator` and `build_fuel_engineer_snapshot` source modules and their focused tests, together with all current strategy specifications and the telemetry roadmap. The consumer-facing snapshot contract is therefore verified. The underlying Physics/Graphics decoder implementations and all strategy-specific consumer APIs were not fully available through the repository code-search results in this pass; decoder member names below are taken from the existing audit/specifications and must be checked against decoder source before implementation. This is not a claim that every source field has been re-audited.

## 2. Existing acquisition and consumer contract

### 2.1 Existing verified API

Source: `src/race_engineer_acquisition/engineering_snapshot.py`

The current aggregator exposes:
- `RaceEngineerSnapshotAggregator(runtime, ...)`
- `snapshot() -> RaceEngineerTelemetrySnapshot`
- `RaceEngineerTelemetrySnapshot.physics`
- `RaceEngineerTelemetrySnapshot.graphics`
- `RaceEngineerTelemetrySnapshot.static`
- Per decoded stream: `data`, `capture_timestamp_ns`, `capture_sequence`, `packet_id`, `sample_age_ns`, `max_age_ns`, acquisition/consumer lifecycle, decode errors and `is_fresh`.
- Static currently exposes `RawStreamHealthView` only: lifecycle, last successful read, read age, read failures, buffer rejections and freshness. It has no decoded `data` member in this snapshot API.

The aggregator reads the existing runtime consumers:
- `runtime.physics_consumer.snapshot`
- `runtime.graphics_consumer.snapshot`
- `runtime.acquirers["physics"].health.snapshot`
- `runtime.acquirers["graphics"].health.snapshot`
- `runtime.acquirers["static"].health.snapshot`

It does not read shared memory, drain acquisition queues or mutate acquisition state.

### 2.2 Freshness contract currently implemented

| Stream | Default maximum age | Snapshot representation | Important limitation |
|---|---:|---|---|
| Physics | 500 ms | Decoded `TelemetryStreamView` | Independent capture timestamp |
| Graphics | 1,000 ms | Decoded `TelemetryStreamView` | Independent capture timestamp |
| Static | 3,000 ms | Raw `RawStreamHealthView` | Health only in this aggregator; no decoded Static metadata exposed here |

Physics and Graphics use local monotonic capture timestamps. The aggregator reports each stream's age independently and does **not** claim that the latest samples are synchronized. Any cross-stream calculation must check each contributing stream's freshness and timestamp separation itself. The default age limits are implementation defaults, not proof that every strategy calculation is safe at those ages.

The focused snapshot tests cover independent freshness, stale Physics with fresh Graphics, stopped consumers, missing samples, future timestamps, Static health-only behaviour and invalid freshness limits. These tests were inspected but not executed in this audit.

### 2.3 Existing Fuel observation slice

Source: `src/race_engineer_acquisition/fuel_engineer.py`

Verified function:
- `build_fuel_engineer_snapshot(telemetry, fuel_per_lap_validated=True, estimated_laps_validated=True, safety_reserve_l=None)`

It consumes the aggregate Physics/Graphics snapshots and currently exposes:
- Current fuel from Physics `fuel_kg`, interpreted as litres without numeric conversion based on the user's ACC confirmation.
- Graphics `fuel_per_lap_l`, `fuel_estimated_laps`, `mfd_fuel_to_add`, `used_fuel_l`.
- Per-stream freshness and blocker state.
- Strategy calculations remain disabled when required observations are unavailable or the safety reserve is not configured.

This module does not yet calculate finish fuel, fuel shortfall, fuel saving or pit refuelling amount. The test file `tests/test_race_engineer_fuel.py` verifies conservative observation handling and reserve gating; tests were inspected, not run.

## 3. Master telemetry requirements matrix

Status vocabulary:
- **Validated:** user or controlled test has confirmed the relevant live value/behaviour for the stated scope.
- **Candidate:** decoded or observed, but one or more meanings, units, mappings, signs, lifecycle or associations remain unconfirmed.
- **Inferred:** derived diagnosis/trend, not a direct ACC measurement; requires multiple validated inputs and evidence.
- **Unavailable:** no trustworthy source established in the current audit.
- **Calculated — gated:** calculation is possible in principle, but one or more input or model release gates remain open.
- **Not yet code-audited:** requirement is in the strategy specification, but this pass did not verify a matching decoder/consumer implementation.

### 3.1 Physics stream

| Data family / fields | Strategy consumers | Current evidence / status | Shared service or rule |
|---|---|---|---|
| Speed, throttle, brake, gear, RPM, steering angle | Pace, Traffic, Car Health, Brake, Setup, Performance context | Available and validated for live monitoring | One immutable Physics snapshot; common unit/freshness validation |
| Current fuel (`fuel_kg` legacy member) | Fuel, Pit-Stop, Race-State context | User-confirmed display unit is litres (L); preserve numeric value, do not convert | One canonical `current_fuel_l` observation; retain legacy source name in provenance |
| Four tyre pressures | Tyre, Weather context, Setup, Pit-Stop | Four channels validated; pressure target model and cold/hot interpretation still need strategy-specific validation | Per-corner tyre observation and stint trend history |
| Four tyre core temperatures | Tyre, Pit-Stop, Weather context | Four channels validated | Per-corner temperature snapshot/trend; no invented thresholds |
| Inner/middle/outer tread temperatures | Tyre | Not available as independent trusted channels; legacy arrays unused/zero and one offset aliases core temperature | Exclude from calculations/UI; do not reconstruct gradients |
| Four brake temperatures | Brake, Pit-Stop, Car Health context | Four channels validated | Per-corner brake observation and trend; car-specific limits remain gated |
| Brake pad and disc values (four corners each) | Brake, Pit-Stop | User confirms values work and are displayed separately; mm is expected reference interpretation, but selected-car unit/direction/baseline/service limits still need controlled confirmation | Preserve raw values and corner identity; do not calculate remaining life or service threshold yet |
| General damage channels (`car_damage[5]`) | Car Health, Pit-Stop | Five channels change; controlled pit repair returned values to zero. Component mapping, units, scale and severity are unresolved | Session-baselined raw damage history; no component names or severity score |
| Suspension damage (`suspension_damage[4]`) | Car Health, Pit-Stop | Candidate only; mapping, units, value direction and repair behaviour unresolved | Preserve raw channels for validation only |
| Velocity/acceleration, G, wheel speed/slip, suspension travel, yaw/heading | Car Health, Brake, Traffic, Setup, Pace | Mixed: values observed/decoded; axes, signs, units and controlled-event correlations remain open | Reusable vehicle-dynamics sample/history only after per-field semantic validation |
| Brake bias candidate | Setup, Brake context | Candidate with known mismatch; do not base recommendations on it yet | Keep excluded until source/display correlation is resolved |

### 3.2 Graphics stream

| Data family / fields | Strategy consumers | Current evidence / status | Shared service or rule |
|---|---|---|---|
| Lap time, last lap, best lap, split/delta, sector transitions/timing | Pace, Tyre, Brake, Car Health, Setup, Fuel, Pit-Stop, Radio | Decoded/integrated; some numeric timing semantics remain candidate | Shared lap/sector event service; preserve raw values and validity |
| Lap validity (`is_valid_lap`) | All lap-history consumers; Pace, Tyre, Brake, Setup | Validated | One canonical validity event; exclude invalid laps from comparable pace/degradation baselines |
| Completed laps (`completed_laps`) | Race-State, Fuel, Pit-Stop, Pace, Radio | Validated | One race-progress observation; do not substitute `number_of_laps` |
| Race lap limit (`number_of_laps`) | Race-State, Fuel, Pit-Stop | Candidate; semantics not validated | Do not calculate laps remaining from this until validated |
| Session time remaining (`session_time_left_s`) | Race-State, Fuel, Pit-Stop, Pace, Radio | Validated for display | Shared session-clock observation; timer expiry is not proof of race finish |
| Position and active cars | Pace, Traffic, Pit-Stop | Candidate; multi-car transitions/association need validation | Shared classification snapshot; validate update timing and target identity |
| Gap ahead/behind (`gap_ahead_ms`, `gap_behind_ms`) | Pace, Pit-Stop | Candidate; milliseconds are decoded but sign convention and target association unresolved | Store raw signed values; no closing-time/overtake calculation until sign and cadence validated |
| Car IDs, coordinates, normalized track position | Traffic, Pace context, Pit-Stop | Candidate; player/opponent association, coordinate frame, wrap-around, units and cadence need multi-car validation | Shared opponent/traffic observation model; never create another reader |
| Fuel per lap (`fuel_per_lap_l`) | Fuel, Pit-Stop | User confirmed match to ACC in observed use | Shared fuel observation; validate finite/non-negative and Graphics freshness |
| Estimated laps remaining (`fuel_estimated_laps`) | Fuel, Pit-Stop | User confirmed match to ACC in observed use | Shared fuel observation; finish strategy still needs reserve and finish-distance gates |
| Fuel used (`used_fuel_l`) | Fuel, Pit-Stop, history | User confirmed observation works; reset/accumulation across refuel/pit not established | Observation only until reset semantics are tested |
| MFD fuel-to-add (`mfd_fuel_to_add`) | Fuel, Pit-Stop | User confirmed match to ACC; read-only | Show as ACC request/indication, not proof of fuel added |
| MFD tyre pressure requests | Tyre, Setup, Pit-Stop | Candidate; distinct from measured tyre pressure | Keep requested and measured pressures as separate properties |
| Tyre compound/set identifiers | Tyre, Pit-Stop, history | Candidate; raw IDs exist but labels/options need validation per car/session | Preserve raw identifier; map only validated choices |
| Weather rain intensity and forecast fields | Weather, Tyre, Pit-Stop | User confirmed all currently exposed weather values match ACC; forecast horizon/semantics/cadence still need validation | Timestamped observed-weather and forecast objects must remain separate |
| Track grip/condition code and wind fields | Weather, Tyre, Pit-Stop | Value comparison confirmed for exposed weather fields; enum interpretation/direction semantics still gated | Shared weather snapshot; do not infer drying rate or wind direction without semantics |
| TC, ABS, engine-map/on-board setting fields | Setup | Candidate/integrated display; per-car labels/ranges/increments and exposure need audit | Shared setup observation/history with provenance; no control writes |
| Session type/status, track status and race-control codes | Race-State, Fuel, Pit-Stop, Radio | Candidate; enum mapping and lifecycle require controlled validation | Shared race-state event service; preserve unknown raw codes |
| Penalty code/time | Race-State, Pit-Stop, Radio | Penalty-time presentation conversion validated; code mapping/lifecycle candidate | Keep raw code and display time separate; no rule-critical action before mapping |
| Mandatory pit flags/window fields | Race-State, Pit-Stop | Candidate; flag meaning, window units and lifecycle need validation | Rule/mandatory-stop service gated on explicit ACC semantics |
| Static-dependent pit/session metadata | Fuel, Race-State, Pit-Stop | Static decoder candidate metadata exists in roadmap, but current engineering snapshot exposes only Static read health | Separate decoded Static metadata adapter is required before strategies can consume it |

### 3.3 Static/session metadata

| Requirement | Intended consumers | Current state | Required action |
|---|---|---|---|
| Car identity, track/layout, session metadata | All strategies; history keys | Static candidate decoder documented; not exposed in current engineering snapshot's Static view | Inspect existing Static decoder/consumer and add a read-only metadata view only if already decoded; do not assume current aggregator provides it |
| Maximum fuel capacity | Fuel, Pit-Stop | Static `max_fuel` candidate in roadmap | Verify per car and ACC; expose with provenance before using as hard capacity |
| Pit window / session rule metadata | Race-State, Pit-Stop | Static candidates documented; semantics/units not validated | Validate raw source, mapping, units and session lifecycle before rule-critical use |

### 3.4 Application history, driver input and derived data

| Data / capability | Strategy consumers | Source type | Current status / shared requirement |
|---|---|---|---|
| Valid completed-lap history and lap/sector comparisons | Pace, Tyre, Brake, Car Health, Setup, Fuel | Application session history + Graphics events | Reuse existing lap/session history; verify API, persistence, session identity and invalid/out-lap exclusion rules |
| Stint history and pressure/temperature trends | Tyre, Weather, Pit-Stop | Derived from Physics samples + lap/pit events | Build compact per-lap/per-stint summaries; no high-frequency duplication |
| Fuel consumption trend and finish projection | Fuel, Pit-Stop | Derived from fuel and lap/race progress | Finish calculation gated by reserve, remaining distance, finish-line behaviour, tank capacity and consumption reset semantics |
| Brake thermal trend / pad-disc trend | Brake, Pit-Stop | Derived from Physics samples and lap/pit events | Keep raw per-corner values; thresholds and wear-rate calculations gated |
| Damage persistence / repair transition | Car Health, Pit-Stop | Derived from Physics damage history + pit events | Session baseline and before/after values; a reset is not proof of a specific repair unless validated |
| Weather transitions and forecast progression | Weather, Tyre, Pit-Stop | Derived from Graphics/Physics weather snapshots | Timestamp and target horizon; observed conditions separate from forecast |
| Opponent pace, closing trend and tactical target | Pace, Traffic, Pit-Stop | Derived from classification, gap and car association | Gate on validated sign, timing cadence, opponent identity and association |
| Physical traffic proximity/overlap | Traffic, Pit-Stop context | Derived from Graphics car positions/coordinates | Not enabled until coordinate frame, geometry, identity and wrap-around are validated |
| Setup versions and before/after context | Setup, Pit-Stop context | Setup-file import, driver confirmation, telemetry/lap history | Distinguish imported, live-observed and driver-confirmed values; recommendation is not proof of change |
| Pit-stop history and service outcomes | Pit-Stop, Fuel, Tyre, Brake, Car Health, Setup | Pit entry/exit telemetry, before/after observations, driver confirmation | New persistent event model required; record unknown when service not exposed; retain provenance |
| Race-state transitions and finish | Race-State, Fuel, Pit-Stop | Graphics transitions and validated ACC race-control sources | Timer expiry != confirmed finish; race lap limit and control enums remain gated |
| Driver feedback / setup or pit service confirmation | Setup, Pit-Stop, potentially Tyre | Explicit user input | Interaction mechanism not yet defined; never infer confirmation from recommendation or pit visit |

## 4. Strategy-to-shared-service dependency map

| Shared service / canonical object | Primary consumers | Responsibilities |
|---|---|---|
| Telemetry snapshot and health | All strategies | Reuse existing Physics/Graphics consumers; per-stream timestamps, freshness, lifecycle and decode errors |
| Static metadata view | Fuel, Race-State, Pit-Stop, all history keys | Read-only decoded metadata with explicit freshness/provenance; not currently present in aggregate data view |
| Lap/sector event and history service | Pace, Tyre, Brake, Car Health, Setup, Fuel, Pit-Stop, Radio | One source of completed-lap events, validity, lap/sector timing and compact history |
| Race/session progress service | Race-State, Fuel, Pit-Stop, Pace | Session type/state, clock, completed laps, validated distance/finish transitions |
| Fuel observation/calculation service | Fuel, Pit-Stop | Canonical litres, consumption observations, MFD request, reserve, finish feasibility; calculations remain gated |
| Tyre observation/stint service | Tyre, Weather, Pit-Stop, Setup context | Four-corner pressure/core temperature, compound IDs, stint boundaries, degradation evidence |
| Brake observation service | Brake, Pit-Stop, Car Health context | Four-corner temperatures, pad/disc raw values, trend and validation state |
| Vehicle health/damage history | Car Health, Pit-Stop | General/suspension raw damage, validated fault events, persistence, repair transitions |
| Weather context service | Weather, Tyre, Pit-Stop, Setup context | Timestamped current conditions, transitions and forecast horizons |
| Opponent/classification context | Pace, Traffic, Pit-Stop | Position, adjacent classified cars, gaps, physical traffic observations where validated |
| Setup state/history | Setup, Pit-Stop context | Car/track/condition key, setup versions, driver-confirmed on-board changes, before/after comparisons |
| Pit decision and history service | Pit-Stop only for final decision; specialist services supply evidence | Hard constraints, fixed weighted model, combined services, stop timing, session pit events and outcome history |
| Radio/communication service | All strategy outputs | Three modes, critical bypass, deduplication, message priority, TTS reuse and user requests |

**Ownership rule:** Specialist services own their domain measurements and assessments. Pit-Stop Strategy alone owns the final pit recommendation. Pace/Traffic provide timing context; they do not independently add pit-necessity weight in the initial model.

## 5. Cross-strategy data-sharing rules

1. **One acquisition path:** no strategy opens its own ACC shared-memory reader or drains an acquisition queue.
2. **One canonical observation per field:** normalize units and labels once, while retaining original decoder member name and source.
3. **No false synchronization:** every value retains stream timestamp and freshness; calculations across streams enforce an explicit allowed timestamp difference.
4. **Unknown is not zero:** missing, stale, invalid or unvalidated fields remain unknown and do not imply healthy/normal state.
5. **No double counting:** a shared underlying fact should not be counted as multiple independent reasons merely because several strategies consume it. Example: weather affects tyre assessment, but the same weather observation should not be counted again as a separate independent tyre and weather hazard without distinct evidence.
6. **Clear ownership:** Tyre owns tyre condition; Brake owns brake condition; Car Health owns general damage/mechanical evidence; Weather owns weather context; Pace owns adjacent classified opponent tactics; Traffic owns physical traffic; Race-State owns session/race-control facts; Pit-Stop owns final pit decision.
7. **Measured/calculated/inferred separation:** every strategy output identifies its evidence class and confidence/limitations.
8. **Read-only:** no shared-memory writes, control inputs, setup/MFD/pit actions or automatic in-game changes.

## 6. Highest-priority validation gaps

| Priority | Gap | Why it blocks downstream work | Required validation |
|---|---|---|---|
| P0 | Decoder and consumer contract audit for every Physics/Graphics field used by the matrix | Prevents stale or incorrect field names/types/units entering strategy services | Inspect actual decoder dataclasses, offsets, consumer snapshots and tests |
| P0 | Cross-stream timestamp alignment policy | Most strategy calculations combine Physics and Graphics; latest samples are not synchronized | Define per-calculation maximum age and timestamp skew; test delayed/stale streams |
| P0 | Race finish and remaining-distance semantics | Blocks fuel-to-finish and pit timing | Controlled timed-race finish-line and lap-race limit tests |
| P0 | Fuel reset/refuel semantics and Static max tank capacity | Blocks reliable fuel projections and stop amount | Observe fuel/used-fuel before, during and after pit refuel; validate capacity per car |
| P0 | Pit entry/exit and service event detection | Blocks reliable pit history and stop-loss calculation | Controlled pit-in, stationary service, pit-out and drive-through scenarios |
| P1 | Tyre compound/set IDs and actual available options | Blocks compound recommendations and tyre-change confirmation | Per-car/session ID mapping and dry/wet selection tests |
| P1 | Brake pad/disc unit, direction, corner mapping and service behaviour | Blocks wear/remaining-life and service urgency | Controlled selected-car baseline, wear and pit service comparison |
| P1 | General/suspension damage mapping and repair behaviour | Blocks component diagnosis and repair urgency | Controlled damage and repair captures; preserve raw values |
| P1 | Position/gap sign, target association and cadence | Blocks immediate-opponent tactical advice | Multi-car controlled position/gap changes |
| P1 | Traffic coordinate frame, association and track wrap-around | Blocks physical proximity/overlap | Multi-car controlled captures around track and start/finish wrap |
| P1 | Race-control, penalty, mandatory-stop enum and lifecycle | Blocks rule-critical race-state advice | Controlled HUD/state correlation and session-type coverage |
| P1 | Weather forecast horizon/cadence and enum semantics | Blocks future-looking tyre/pit advice | Compare forecast fields over time against ACC display |
| P2 | Setup control inventory/ranges and setup-file provenance | Blocks safe numeric setup recommendations | Per-car on-board controls, increments, imported/live/confirmed source tests |
| P2 | Post-stop outcome comparability and confounder tracking | Blocks meaningful pit-history learning/weight review | Comparable before/after lap windows with fuel/traffic/weather/tyre context |
| P2 | Driver confirmation interaction | Blocks unexposed setup/service history fields | Decide text/command entry workflow; voice recognition remains unselected |

## 7. Implementation sequencing derived from shared dependencies

1. **Complete source/API audit:** verify decoder fields, consumer APIs, Static metadata path, history stores and event boundaries. Resolve discrepancies between current code, this matrix and older audit wording.
2. **Harden shared snapshot contract:** add explicit per-field source metadata and cross-stream skew policies without adding readers or changing proven acquisition behaviour.
3. **Build shared event/history foundations:** session identity, lap/sector events, valid-lap filtering, stint boundaries, pit events and compact before/after summaries.
4. **Complete canonical observation services:** fuel, tyre, brake, damage/health, weather, race-state and opponent/traffic observations. Keep unsupported fields unavailable.
5. **Implement specialist calculations behind release gates:** evidence-based trends and recommendations only after their input semantics are validated.
6. **Implement integrated Pit-Stop Strategy:** consume specialist outputs, hard constraints, fixed initial weights (Fuel 25%, Tyres 25%, Car Health 20%, Brakes 15%, Weather 10%, Race-State 5%), Pace/Traffic timing context, and persistent pit history. No independent routine pit instructions from specialist strategies.
7. **Implement shared communication and interaction:** three modes, critical bypass, deduplication, existing Windows TTS and the agreed keyboard hold-to-talk trigger; request-content capture must be resolved separately.
8. **Regression and ACC validation:** automated tests first, then controlled live ACC tests for every release gate, reconnect/session reset and missing/stale stream behaviour.

## 8. Current audit limitations and non-changes

- This matrix does not certify the candidate Graphics or Static memory layouts as official Kunos ABI.
- This pass verified the aggregator and Fuel observation source, not every low-level decoder/consumer implementation. Decoder source audit remains P0.
- Static metadata is not exposed by the current Race Engineer aggregate snapshot, which currently reports Static read health only.
- Existing tests were read but not executed.
- No application code, decoder, consumer, UI or test was changed in this documentation task.
- Do not begin implementation solely from a candidate row. Close its source/API and validation gates first.
