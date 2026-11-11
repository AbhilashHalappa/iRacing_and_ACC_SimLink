# ACC Physics Page — Field Coverage Audit

**Status:** Physics acquisition and raw recording validation closed for the current scope. The 800-byte layout is strongly corroborated by three independent reader implementations and live read-only mapping probes; exact Kunos v1.9 ABI/header confirmation remains unavailable. A 600-second target-PC Physics recording on 10 November 2026 also passed acquisition, persistence, recovery and reconciliation checks. Field semantics and the version-matched Kunos ABI qualification remain separately tracked.  
**Page size:** 800 bytes  
**Layout:** Little-endian, `_pack_ = 4`  
**Layout evidence:** three independent ACC readers include `mz[4]` after `currentMaxRpm`; the outlying 784-byte transcription omits this member. The live read-only probe confirmed readable data through byte 799. The final 16 bytes are preserved opaquely.  
**Secondary decoder reference:** `AbhilashHalappa/Race-Engineer-ACC`, branch `diagnostic/high-res-capture-2026-11-07`, `src/acc_shared_memory_extended.py`, blob `e9a54bda008cb6ff1797dfdc14b07b297a461ab9`.

## Architecture boundary

This audit documents the corrected raw ABI. It does not add a decoder or semantic interpretation for the opaque tail.

- The high-priority Physics acquisition thread remains raw-only.
- It copies the complete 800-byte page and timestamps/sequences the observation.
- The independent recorder preserves the complete raw payload.
- Decoding will be a later, separate stage. A future live decoder may receive copied observations through its own independent handoff buffer; it must not consume the recorder's SPSC queue or block acquisition.
- No Graphics or Static adapters are being added as part of this audit.

## Coverage definitions

- **Raw preserved = Yes:** the adapter copies the entire page and the recorder stores that payload; there is no per-field filtering.
- **Reference decoder exposes = Yes:** the cited reference decoder includes a corresponding output key. For `wheel_load` and `tyre_dirty`, it deliberately returns `None` because the reference comments identify those ACC values as unused. This is not a decoder implemented in this greenfield repository.
- **Unused/deprecated:** based on explicit field naming in the reference structure. A field not so marked is not thereby proven to be populated by ACC.
- **Live validation:** statuses below summarize evidence through the 2026-11-10 600-second capture. “Validated” means a plausible signal was correlated with a controlled action or repeatable driving state; it does not automatically establish calibrated units or complete semantics.
- **Observed:** a field changed in a live capture, but controlled causality, axis/sign calibration or semantic confirmation is missing.
- **Unresolved:** latest evidence is contradictory or implausible; do not use the declared interpretation.
- **Reference unused:** this reflects the cited third-party reference, not an official Kunos guarantee.

## Complete field inventory

Offsets are zero-based byte offsets. Array sizes are total bytes.

| Field | C type | Offset | Size (bytes) | Raw preserved | Reference decoder exposes | Reference unused/deprecated marker | Current live-validation status |
|---|---:|---:|---:|---|---|---|---|
| `packet_id` | `c_int32` | 0 | 4 | Yes | Yes | Not marked unused | Validated — advancing packet IDs |
| `throttle` | `c_float` | 4 | 4 | Yes | Yes | Not marked unused | Validated — controlled input response |
| `brake` | `c_float` | 8 | 4 | Yes | Yes | Not marked unused | Validated — controlled input response |
| `fuel_kg` | `c_float` | 12 | 4 | Yes | Yes | Not marked unused | Observed — controlled fuel-change test pending |
| `gear_raw` | `c_int32` | 16 | 4 | Yes | Yes | Not marked unused | Validated — gear changes observed |
| `rpm` | `c_int32` | 20 | 4 | Yes | Yes | Not marked unused | Validated — integer RPM response; engine on/off and driving captures |
| `steering` | `c_float` | 24 | 4 | Yes | Yes | Not marked unused | Validated — controlled steering response |
| `speed_kph` | `c_float` | 28 | 4 | Yes | Yes | Not marked unused | Validated — stationary and driving ranges |
| `velocity` | `c_float[3]` | 32 | 12 | Yes | Yes | Not marked unused | Observed — plausible motion response; axis/sign calibration pending |
| `acc_g` | `c_float[3]` | 44 | 12 | Yes | Yes | Not marked unused | Validated — dynamic driving variation |
| `wheel_slip` | `c_float[4]` | 56 | 16 | Yes | Yes | Not marked unused | Observed — varies; controlled wheel-slip event pending |
| `wheel_load` | `c_float[4]` | 72 | 16 | Yes | Yes — key returned as None | Not marked unused | Stable zero in tested captures; reference marks unused in ACC |
| `tyre_pressure_psi` | `c_float[4]` | 88 | 16 | Yes | Yes | Not marked unused | Validated — four live channels; tyre-service effect not isolated |
| `wheel_angular_speed` | `c_float[4]` | 104 | 16 | Yes | Yes | Not marked unused | Validated — four live wheel channels |
| `tyre_wear_unused` | `c_float[4]` | 120 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `tyre_dirty` | `c_float[4]` | 136 | 16 | Yes | Yes — key returned as None | Not marked unused | Stable zero in tested captures; reference returns None/marks unused |
| `tyre_core_temp_c` | `c_float[4]` | 152 | 16 | Yes | Yes | Not marked unused | Validated — four live wheel channels |
| `camber_unused` | `c_float[4]` | 168 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `suspension_travel` | `c_float[4]` | 184 | 16 | Yes | Yes | Not marked unused | Validated — four live channels vary during driving |
| `drs_unused` | `c_float` | 200 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `tc` | `c_float` | 204 | 4 | Yes | Yes | Not marked unused | Observed — varies; controlled TC-setting correlation pending |
| `heading` | `c_float` | 208 | 4 | Yes | Yes | Not marked unused | Observed — varies; coordinate calibration pending |
| `pitch` | `c_float` | 212 | 4 | Yes | Yes | Not marked unused | Observed — varies; sign/range calibration pending |
| `roll` | `c_float` | 216 | 4 | Yes | Yes | Not marked unused | Observed — varies; sign/range calibration pending |
| `cg_height_unused` | `c_float` | 220 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `car_damage` | `c_float[5]` | 224 | 20 | Yes | Yes | Not marked unused | Validated — damage response and repair observed in controlled pit test |
| `tyres_out_unused` | `c_int32` | 244 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `pit_limiter_on` | `c_int32` | 248 | 4 | Yes | Yes | Not marked unused | Validated — 0/1 transition correlated with pit entry/exit |
| `abs` | `c_float` | 252 | 4 | Yes | Yes | Not marked unused | Observed — value present; controlled ABS-setting correlation pending |
| `kers_charge_unused` | `c_float` | 256 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `kers_input_unused` | `c_float` | 260 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `autoshifter_on` | `c_int32` | 264 | 4 | Yes | Yes | Not marked unused | Pending — controlled setting test not completed |
| `ride_height_unused` | `c_float[2]` | 268 | 8 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `turbo_boost` | `c_float` | 276 | 4 | Yes | Yes | Not marked unused | Pending — controlled operating-state test not completed |
| `ballast_unused` | `c_float` | 280 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `air_density_unused` | `c_float` | 284 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `air_temp_c` | `c_float` | 288 | 4 | Yes | Yes | Not marked unused | Pending — isolated environmental validation absent |
| `road_temp_c` | `c_float` | 292 | 4 | Yes | Yes | Not marked unused | Pending — isolated environmental validation absent |
| `local_angular_velocity` | `c_float[3]` | 296 | 12 | Yes | Yes | Not marked unused | Observed — varies; axes/sign calibration pending |
| `final_ff` | `c_float` | 308 | 4 | Yes | Yes | Not marked unused | Pending — controlled steering/FF correlation absent |
| `performance_meter_unused` | `c_float` | 312 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `engine_brake_unused` | `c_int32` | 316 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `ers_recovery_unused` | `c_int32` | 320 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `ers_power_unused` | `c_int32` | 324 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `ers_heat_unused` | `c_int32` | 328 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `ers_charging_unused` | `c_int32` | 332 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `kers_current_unused` | `c_float` | 336 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `drs_available_unused` | `c_int32` | 340 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `drs_enabled_unused` | `c_int32` | 344 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `brake_temp_c` | `c_float[4]` | 348 | 16 | Yes | Yes | Not marked unused | Validated — four live wheel channels |
| `clutch` | `c_float` | 364 | 4 | Yes | Yes | Not marked unused | Validated — controlled clutch input varied 0–1 |
| `tyre_temp_i_unused` | `c_float[4]` | 368 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; zero in tested captures |
| `tyre_temp_m_unused` | `c_float[4]` | 384 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; zero in tested captures |
| `tyre_temp_o_unused` | `c_float[4]` | 400 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; zero in tested captures |
| `is_ai_controlled` | `c_int32` | 416 | 4 | Yes | Yes | Not marked unused | Partially validated — zero in human-driven captures; AI untested |
| `tyre_contact_point` | `c_float[12]` | 420 | 48 | Yes | Yes | Not marked unused | Observed — components vary; coordinate calibration pending |
| `tyre_contact_normal` | `c_float[12]` | 468 | 48 | Yes | Yes | Not marked unused | Observed — components vary; coordinate calibration pending |
| `tyre_contact_heading` | `c_float[12]` | 516 | 48 | Yes | Yes | Not marked unused | Observed — components vary; coordinate calibration pending |
| `brake_bias` | `c_float` | 564 | 4 | Yes | Yes | Not marked unused | Observed — varies; controlled adjustment correlation pending |
| `local_velocity` | `c_float[3]` | 568 | 12 | Yes | Yes | Not marked unused | Observed — varies; axes/sign calibration pending |
| `p2p_activation_unused` | `c_int32` | 580 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `p2p_status_unused` | `c_int32` | 584 | 4 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `current_max_rpm` | `c_int32` | 588 | 4 | Yes | No | Not marked unused | Observed — integer field at the corrected offset; controlled limiter-range validation pending |
| `mz_unused` | `c_float[4]` | 592 | 16 | Yes | No | Unverified/reserved in current reference comparison | Not a target field; retained for ABI alignment |
| `fx_unused` | `c_float[4]` | 608 | 16 | Yes | No | Marked unused/deprecated in reference naming | Stable zero in tested capture; reference marks unused/deprecated |
| `fy_unused` | `c_float[4]` | 624 | 16 | Yes | No | Marked unused/deprecated in reference naming | Stable zero in tested capture; reference marks unused/deprecated |
| `slip_ratio` | `c_float[4]` | 640 | 16 | Yes | Yes | Not marked unused | Observed — four channels vary in D-BOX drive; controlled event pending |
| `slip_angle` | `c_float[4]` | 656 | 16 | Yes | Yes | Not marked unused | Observed — four channels vary in D-BOX drive; controlled cornering correlation pending |
| `tc_in_action` | `c_int32` | 672 | 4 | Yes | No | Intervention indicator; not a selected TC level | Stable zero in the 9 November capture; no intervention observed in sampled data |
| `abs_in_action` | `c_int32` | 676 | 4 | Yes | No | Intervention indicator; not a selected ABS level | Stable zero in the 9 November capture; no intervention observed in sampled data |
| `suspension_damage_unused` | `c_float[4]` | 680 | 16 | Yes | No | Conditional field in older reference; not approved as unused | Observed — components 0 and 1 varied (max 0.107493 and 0.062567); components 2 and 3 remained zero. Semantics remain conditional/unconfirmed |
| `tyre_temp_unused` | `c_float[4]` | 696 | 16 | Yes | No | Duplicate core-temperature alias in newer references | Confirmed byte-for-byte alias for this 224,956-snapshot capture: bytes 152–167 equalled bytes 696–711 in every sample; 0 mismatches. Do not expose as independent telemetry |
| `water_temp_c` | `c_float` | 712 | 4 | Yes | Yes | Not marked unused | Observed — maximum 86.663; semantic/unit validation remains open |
| `brake_pressure` | `c_float[4]` | 716 | 16 | Yes | Yes | Not marked unused | Observed — maxima by component 0.742, 0.742, 0.258, 0.258; scale/meaning remain unvalidated |
| `front_brake_compound` | `c_int32` | 732 | 4 | Yes | Yes | Not marked unused | Observed — integer values 0–1 in the 10 Nov capture; enum mapping not validated |
| `rear_brake_compound` | `c_int32` | 736 | 4 | Yes | Yes | Not marked unused | Observed — integer values 0–1 in the 10 Nov capture; enum mapping not validated |
| `pad_life` | `c_float[4]` | 740 | 16 | Yes | Yes | Not marked unused | Observed — components varied; maximum approximately 29; units, corner mapping and direction remain unvalidated |
| `disc_life` | `c_float[4]` | 756 | 16 | Yes | Yes | Not marked unused | Observed — components varied; maximum approximately 32; units, corner mapping and direction remain unvalidated |
| `ignition_on` | `c_int32` | 772 | 4 | Yes | Yes | Not marked unused | Observed — 0/1 values in this capture; full engine-state transition validation remains open |
| `starter_engine_on` | `c_int32` | 776 | 4 | Yes | Yes | Not marked unused | Observed — remained zero in this capture; start transition not exercised |
| `engine_running` | `c_int32` | 780 | 4 | Yes | Yes | Not marked unused | Observed — 0/1 values in this capture; full engine-state transition validation remains open |
| `tail_reserved` | `c_ubyte[16]` | 784 | 16 | Yes | No | Four vibration-float candidates in RaceIQ/Pro Engineer; opaque in Greenfield | Raw bytes preserved. Interpreting four little-endian floats is numerically possible in this capture, but field semantics are not independently established; keep opaque in production |

## Layout regression tests

The automated test module, `tests/acquisition/test_physics_layout.py`, locks all 82 field names, ctypes scalar types, array lengths, byte offsets and sizes, plus the 800-byte total and contiguous layout. This is a regression guard against accidental edits to the current transcription; it does not independently prove the transcription matches Kunos' authoritative specification. The inspection tests also verify that RPM is reported as `int32` at offset 20 and that capped unique-value counts are explicitly identified.

## Offline raw inspection utility

Use `scripts/inspect_acc_physics.py` to inspect a completed `.accraw` file without changing it or touching the acquisition thread:

```powershell
$env:PYTHONPATH = "src"
python scripts/inspect_acc_physics.py "user_data\\raw_recordings\\<recording>.accraw" --csv-out "user_data\\raw_recordings\\<recording>.physics.csv"
```
The utility validates the recording header, block sequence, payload lengths and CRCs, then reports per-field/per-array-component sample count, finite/non-finite count, zero/non-zero count, min/max, first/last value and whether the observed value was constant or varied. Each component now includes its scalar type (`int32` or `float32`), field byte offset, field byte size, array length and component byte offset. The JSON and optional CSV carry the same metadata.

Unique-value tracking is capped at 4,096 distinct values per component to bound offline memory use. `unique_values_count_exact` is true only when fewer than 4,096 values were observed. If the limit is reached, `unique_values_observed` is a lower bound, not an exact cardinality. The report also records the tracking limit. The utility writes a JSON report beside the recording by default and an optional CSV. It never truncates or modifies the source recording.

Observed variation is only descriptive evidence. It does not establish semantic correctness; controlled actions must be correlated with the relevant fields. This utility is an offline diagnostic reader, not a production decoder and is not used by the acquisition hot path.

## Live validation evidence

ACC game build observed during these captures: **1.10.4**. Shared-memory identifiers observed during the session: `smVersion = 1.9`, `acVersion = 1.7`. These identifiers are not the game build number.

| Capture | Controlled activity | Evidence |
|---|---|---|
| Stationary baseline — `acc_physics_20261108T163710_467685Z.accraw` | Stationary baseline | 10,662 snapshots; complete 800-byte payloads; 109 of 196 inspected components varied |
| Input test — `acc_physics_20261108T164030_324828Z.accraw` | Throttle, brake, steering and gear inputs | 22,519 snapshots; throttle, brake, RPM, steering and other expected driving signals varied |
| Engine OFF — `acc_physics_20261108T170533_325744Z.accraw` | Engine switched off | 6,019 snapshots; RPM remained zero while stationary |
| Engine ON — `acc_physics_20261108T170557_631094Z.accraw` | Engine switched on | 5,780 snapshots; RPM rose to approximately 1,712 during the controlled test |
| Candidate-prefix stationary — `acc_physics_20261108T173458_003331Z.accraw` | Stationary input sequence | 22,171 snapshots; candidate offsets for throttle, brake, RPM, steering and speed behaved plausibly |
| Candidate-prefix drive — `acc_physics_20261108T173813_569096Z.accraw` | 120-second drive | 46,878 snapshots; throttle, brake, RPM, steering, speed and clutch varied; clutch at offset 364 varied from 0 to 1 |
| D-BOX-enabled drive — `acc_physics_20261108T174852_787372Z.accraw` | 120-second drive with D-BOX motion enabled | 46,897 snapshots; all 45,223 blocks and all records passed CRC/structure checks |
| D-BOX tail-field inspection — same capture | Driving; tail decoded using current 800-byte offsets | `slip_ratio` -0.9862..0.1719; `slip_angle` -0.1479..0.1600; `water_temp` 0..88.5092; brake pressure 0..0.7900; compounds 0/1; pad life 0..28.9669; disc life 0..31.9822; ignition and engine-running flags both 0/1 |

### Fields observed varying in driving captures

The following fields showed plausible variation in at least one controlled driving capture:

- Driver/control and vehicle state: `throttle`, `brake`, `rpm` (int32 at offset 20), `steering`, `speed_kph`, `clutch`.
- Motion/dynamics: `acc_g`, `suspension_travel`.
- Tyre/wheel: `tyre_pressure_psi`, `wheel_angular_speed`, `tyre_core_temp_c`.
- Brakes: `brake_temp_c`.

In the D-BOX-enabled drive, observed ranges included acceleration components from -3.4587 to 2.2346, suspension travel from 0 to 0.0846 m, core temperature from 0 to 86.4095, brake temperature from 0 to 681.0502, tyre pressure from 0 to 26.2209, and wheel angular speed from 0 to 218.824. These are raw observed ranges, not calibrated engineering limits. The later 2026-11-09 capture raises concerns about interpretation from offset 696 onward; earlier tail observations are now historical/provisional, not validation.

### Tail-field observations and stable-zero interpretation

In the D-BOX capture, `fx` and `fy` were zero; TC-in-action and ABS-in-action were also zero. These agree with the reference's unused markers. The earlier D-BOX inspection reported plausible-looking values for fields from offset 696 onward. The newer five-minute inspection found implausible integer values for compound/engine flags, subnormal rear pad-life values, and exact statistical matches between `water_temp_c` and `tyre_core_temp_c[0]`, and between several `brake_pressure` components and tyre-core-temperature components. The earlier tail interpretation is therefore downgraded to provisional historical observation, not validation. Do not consume these fields semantically until raw-offset/type discrepancies are resolved.



- `wheel_load` (offset 72) was zero in the tested captures; the independent older C++ reference also labels this value unused in ACC.
- `tyre_temp_i/m/o` (offsets 368/384/400) were zero in the tested captures; the independent older C++ reference labels these arrays unused in ACC.
- `is_ai_controlled` (offset 416) was zero during the human-driven captures. This only validates the observed human-driven value; it does not prove the field is unused.
- Do not infer that every field not listed above is unused. Unlisted fields remain unverified or conditional.

The D-BOX-enabled recording confirms that the same candidate Physics signals remain available while using motion hardware. It does **not** establish that D-BOX actuator positions are published in ACC Physics shared memory, nor does this single capture establish a controlled before/after effect of enabling D-BOX.

### RPM inspection correction

The repository inspector reads RPM through the declared `ctypes.c_int32` field. It converts numeric values to Python floats only for common statistical calculations; the underlying interpretation remains integer. A temporary PowerShell diagnostic incorrectly unpacked offset 20 as a float, producing an all-zero summary. A direct `<i` check of the D-BOX recording confirmed 5,195 unique RPM values from 0 to 9,346. No production RPM or acquisition code change was needed.

### Raw capture integrity

The D-BOX-enabled capture recorded 46,897 acquired and persisted snapshots, zero rejects, zero recorder write failures, zero pending records and reconciliation delta zero. Its offline prefix parser validated 45,223 blocks and 46,897 records with no invalid blocks or records.

### Layout cross-check — 420-byte prefix versus 800-byte ACC layout

The 420-byte boundary is the end of the prefix through `is_ai_controlled`; it is not the end of the Physics page. The ACC v1.8.12 reference transcription continues with tyre contact vectors, brake bias, local velocity, slip ratio/angle, water temperature, brake pressure, compounds, pad/disc life and engine state; the final 16 bytes are opaque, matching the corrected field order and 800-byte size in this adapter. The latest live capture independently supports many of those tail fields at the adapter's declared offsets. Therefore, the 420-byte candidate is rejected as a complete Physics layout; it remains only a useful prefix boundary.

A separate C# implementation (`heikowulf/ACCsharedmemory/Physics.cs`) has additional `mz[4]` before `fx[4]` and version comments for later fields. That produces a different tail layout and is not consistent with the ACC v1.8.12 800-byte transcription used here. It is treated as a different/version-expanded layout, not silently merged into this ACC 1.10.4 adapter. We have not found a Kunos-published v1.9 header that conclusively settles this variant question, so the exact v1.9 ABI claim remains open.


## Five-minute pit-service capture — 2026-11-09

**Recording:** `user_data/raw_recordings/acc_physics_20261109T044553_356416Z.accraw`  
**Inspection reports:** matching `.physics-inspection.json` and `.physics-inspection.csv`.  
**Duration / polling:** 300 seconds / 480 Hz.  
**Capture integrity:** 116,580 acquired and persisted; 301 checkpoint writes; zero checkpoint failures, acquisition rejects, recorder rejects or recorder write failures; pending 0; reconciliation delta 0; maximum persist and block-write duration 4.3 ms; one-core CPU 16.16%.

This establishes a clean recording, not correctness of every decoded field. The inspector caps unique-value tracking at 4,096 per component. A row showing 4,096 unique values has a lower-bound count because `unique_values_count_exact = false`.

### Direct observations from this capture

| Field(s) | Observed evidence | Current conclusion |
|---|---|---|
| `tyre_pressure_psi[0..3]` | All four varied; minima 0; maxima approximately 25.52–25.95; final values approximately 24.03–25.17 | Four live channels validated. Initial zeros reflect an unpopulated interval. Tyre-change effect not isolated. |
| `tyre_core_temp_c[0..3]` | All four varied; maxima approximately 67.31–84.19; final values approximately 59.99–68.42 | Four live channels validated. |
| `car_damage[0..4]` | All five varied; maxima approximately 10.88–143.04; nonzero final values | Damage channels show live variation. A prior controlled pit test showed damage returning to zero after requested repair. This capture ended with nonzero damage. |
| `pit_limiter_on` | Exactly two values, 0 and 1; final value 1 | Boolean-like transition observed. Earlier capture correlated limiter with pit entry/exit; exact timing in this capture still needs user action markers. |
| `brake_temp_c[0..3]` | All four varied; maxima approximately 448.77–631.71; final values approximately 245.98–293.98 | Four live brake-temperature channels validated. |
| `pad_life[0..3]` | Components 0–1: maximum/final 0.210000038; components 2–3: maximum/final 1.401298464e-45 | Not validated. Rear values are not credible life readings; front values alone do not validate the four-component field. |
| `disc_life[0..3]` | All four varied; maxima approximately 28.9765–28.9780; final values approximately 28.9488–28.9519 | Numeric variation observed; units, direction and service semantics unknown. Not approved as validated life percentages. |
| `brake_pressure[0..3]` | Varied; component maxima approximately 67.31–86.08 | Not validated. Several component statistics exactly match tyre-core-temperature components; raw-byte correlation required. |
| `water_temp_c` | Maximum 73.75045 and final 63.06319, exactly matching `tyre_core_temp_c[0]` summary values | Unresolved; do not treat as valid water-temperature data yet. |
| `front_brake_compound`, `rear_brake_compound` | Both interpreted as int32 reach 1,061,830,000 | Implausible compound identifiers under declared int32 interpretation. Type/offset/ABI mapping unresolved. |
| `ignition_on`, `starter_engine_on`, `engine_running` | Interpreted int32 values around 1.107 billion, not clean 0/1 | Not validated as flags. Possible type/offset/layout interpretation issue. |

### Tail-field caution

These anomalies do **not** prove that the entire 800-byte structure is wrong. They establish that the current declared interpretation of some members from offset 696 onward is not sufficiently trustworthy. The exact equality between `water_temp_c` and `tyre_core_temp_c[0]` summary statistics, and the corresponding overlap between brake-pressure and tyre-core-temperature components, must be checked against raw payload bytes and field types. The ctypes regression test proves internal consistency of the declaration, not conformance to the live Kunos ABI.

The pad-life value `1.401298464e-45` is the smallest positive IEEE-754 float32 subnormal. It is not a credible brake-life reading for validation purposes.

## Issue #11 — unresolved-field inventory and reference reconciliation

**Review branch:** `feature/acquisition-foundation`  
**Review date:** 10 November 2026  
**Scope:** documentation/reference audit only. No acquisition, recorder, ABI declaration, decoder or test code changed by this review.

### Reference comparison

The current Greenfield declaration is `src/race_engineer_acquisition/acc_windows.py::_Physics`. It declares an 800-byte little-endian structure with 4-byte packing.

| Reference | Relevant evidence | Comparison with Greenfield |
|---|---|---|
| RaceIQ, pinned commit `64a34783f706722cf342e18ecb7fc06d29f30f8e`, `packages/capture-formats/src/acc/structs.ts` | Explicit offsets: `currentMaxRpm` int32 at 588; `mz[4]` at 592; `slipRatio` at 640; `tyreTemp` at 696; `waterTemp` at 712; `brakePressure` at 716; `padLife` at 740; `discLife` at 756; engine flags at 772–780; vibration fields at 784–796. | Matches the Greenfield offsets and types through the final 16-byte region, except Greenfield currently leaves 784–799 opaque. RaceIQ says its offsets derive from the v1.8.12 header and that later tail members were checked against live data. |
| Pro Engineer, pinned commit `b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26`, `core/src/games/assetto_corsa_competizione/structs.rs` | Declares an 800-byte ACC Physics structure; compile-time size and offset assertions include 588, 640, 696, 712, 716, 740, 756 and 780. Its documented live recording reports 8,376 samples and values at several tail offsets. | Matches the Greenfield layout at the asserted offsets. This is independent empirical corroboration, not an official Kunos header and not a capture from this project's target PC. |
| Grafana Simracing Telemetry Go ACC package (published 2022) | Declares `currentMaxRpm` as int32 followed by `mz[4]`, `fx[4]`, `fy[4]`, slip ratio and slip angle. | Corroborates the int32 + MZ sequence through the pre-tail fields; its age and incomplete extended-tail coverage limit its value for the current v1.9 tail. |
| ACC Shared Memory Documentation v1.8.12 transcription | Lists `currentMaxRpm` as float, followed by `mz[4]`, then `fx[4]` and `fy[4]`; lists the later brake, wear, engine and vibration members. | Confirms member order and presence of MZ, but conflicts with the int32 type at offset 588 used by Greenfield, RaceIQ and Pro Engineer. It is v1.8.12, not a version-matched v1.9 header. |
| heikowulf C# `ACCsharedmemory/Physics.cs` | Declares `currentMaxRpm` as float and includes `mz[4]`; its comments identify fields added in older AC/ACC revisions. | Another older float-typed transcription. It does not settle the target v1.9 type. |
| Legacy F1 reference decoder `Race-Engineer-ACC/src/acc_shared_memory_extended.py` | Uses float `current_max_rpm`, omits the MZ array, and ends with four vibration floats. | Not layout-equivalent to Greenfield. Do not port this structure or its decoder as the ACC v1.9 ABI. Its downstream fields are 16 bytes earlier than the Greenfield declaration after the omitted MZ member. |

**Reference conclusion:** the Greenfield 800-byte sequence with int32 `current_max_rpm` at 588 and `mz[4]` at 592 is supported by two current ACC-focused independent implementations and an older Go implementation. However, the v1.8.12 transcription and C# reader disagree on the type of `currentMaxRpm`, and no authoritative Kunos Shared Memory v1.9 header has been obtained. Keep the existing 800-byte raw capture unchanged; do not treat the current regression test as proof of official ABI conformance.

### Important inventory corrections to investigate

1. **Offset 696, `tyre_temp_unused[4]`:** RaceIQ describes this as a second core-temperature channel; Pro Engineer reports it byte-for-byte identical to `tyre_core_temp[4]` at offset 152. The v1.8.12 transcription marks this field as a duplicate (asterisk), not simply unused. Greenfield currently labels it unused. Candidate disposition: duplicate core-temperature alias, pending exact per-sample raw-byte comparison on this project's capture.
2. **Offsets 784–799, `tail_reserved[16]`:** RaceIQ and Pro Engineer identify four float vibration channels at offsets 784, 788, 792 and 796. Pro Engineer reports the final channel varying in its own capture. Greenfield currently preserves these bytes opaquely. Candidate disposition: four vibration fields; keep opaque/untrusted until exact target-PC raw-byte evidence and a controlled FFB/motion correlation are available.
3. **Offset 680, `suspension_damage[4]`:** the v1.8.12 field list describes suspension damage levels; Pro Engineer declares the array but notes it was zero in a session with no damage. The current Greenfield table labels it unused/deprecated based on the legacy reference naming. That is not sufficient to call it unused. Candidate disposition: conditional field; controlled damage evidence required before semantic use.
4. **Offset 588, `current_max_rpm`:** type disagreement remains (int32 in Greenfield/RaceIQ/Pro Engineer/Go versus float in the v1.8.12 transcription and C# reader). Pro Engineer's independent live recording reports 8650 at this offset and the Static page reports the same maximum RPM. Candidate disposition: int32 strongly supported for the observed ACC layout, but retain the v1.9 ABI qualification until version-matched authoritative evidence is found.
5. **Offsets 712–783:** the field order is independently corroborated, but the target capture's anomalous values/statistical overlap mean semantic decoding is not approved. Do not use plausible values from an earlier capture to override the later anomaly.

### Complete open-finding register

The following register consolidates every field currently marked observed, pending, partially validated, unverified or unresolved in the 82-member audit. “Candidate” is not approval for production telemetry.

| Field(s) / offset(s) | Open question | Current disposition | Evidence needed to close |
|---|---|---|---|
| `fuel_kg` / 12 | Confirm actual unit and response to known fuel addition/refuelling; references disagree between kg and litres. | Observed; unit unresolved. | Controlled before/after fuel change compared with ACC Static max fuel and known added quantity. |
| `velocity[3]` / 32 | Axis order, coordinate frame and sign. | Observed; calibration open. | Controlled straight-line motion and known direction changes, correlated with another position/velocity reference. |
| `wheel_slip[4]` / 56 | Per-wheel sign/range and behaviour during controlled slip. | Observed; semantics not calibrated. | Controlled wheel-lock/spin event with wheel identity preserved. |
| `tc` / 204 and `abs` / 252 | Whether these represent intervention activity, selected aid level, or another value. | Observed; must not be represented as selected setup levels. | Controlled setup changes and interventions, separately logged and compared. || `heading`, `pitch`, `roll` / 208–216 | Coordinate convention, axis and sign. | Observed; calibration open. | Known orientation changes or track-aligned controlled manoeuvres. |
| `autoshifter_on` / 264 | Boolean encoding and transition. | Pending. | Toggle automatic shifting in a controlled session and inspect raw int32 values. |
| `turbo_boost` / 276 | Whether populated for the tested car and its units. | Pending. | Controlled boost/load comparison on a car that exposes turbo boost. |
| `air_temp_c`, `road_temp_c` / 288–292 | Independent environmental meaning and units. | Pending. | Compare with known ACC session weather/track temperatures; avoid inferring from plausible ranges alone. |
| `local_angular_velocity[3]` / 296 | Axis order, frame and sign. | Observed; calibration open. | Controlled yaw/pitch/roll manoeuvres and cross-check against orientation changes. |
| `final_ff` / 308 | Sign, scale and relation to force-feedback output. | Pending. | Controlled FFB change/steering test with a known output reference. |
| `is_ai_controlled` / 416 | AI-controlled state transition. | Partially validated (zero in human-driven captures only). | A controlled AI/replay or AI-car capture where this field should change. |
| `tyre_contact_point[4][3]` / 420 | Coordinate frame, axis order and units. | Observed; calibration open. | Compare wheel contact positions with independently known car/world coordinates. |
| `tyre_contact_normal[4][3]` / 468 | Axis order, normalization and coordinate frame. | Observed; calibration open. | Compare with flat and banked/kerbed surface orientations; check vector magnitude. |
| `tyre_contact_heading[4][3]` / 516 | Axis order, normalization and coordinate frame. | Observed; calibration open. | Compare with known wheel/car heading and check vector magnitude. |
| `brake_bias` / 564 | Scale and relationship to setup percentage. | Observed; controlled adjustment pending. | Change brake bias by a known amount and compare raw value. |
| `local_velocity[3]` / 568 | Axis order, frame and sign. | Observed; calibration open. | Compare with controlled forward, lateral and reverse movement. |
| `current_max_rpm` / 588 | int32 versus float ABI disagreement and relationship to active rev limiter/engine map. | Candidate int32; ABI type qualification remains. | Version-matched authoritative definition or controlled engine-map/limiter changes with raw int32 and float interpretations recorded. |
| `mz[4]` / 592 | ACC population/use. | Candidate unused/reserved; raw preserved. | Controlled target capture; do not expose unless non-zero/meaningful use is established. |
| `fx[4]`, `fy[4]` / 608–636 | ACC population/use. | Reference-unused candidate; stable zero in current capture. | Controlled target capture if a feature requires tyre force data. |
| `slip_ratio[4]` / 640 | Per-wheel semantics, sign and units. | Observed; controlled event pending. | Controlled acceleration/braking slip with per-wheel correlation. |
| `slip_angle[4]` / 656 | Per-wheel semantics, sign and units. | Observed; cornering correlation pending. | Controlled cornering in both directions with wheel identity and sign correlation. |
| `tc_in_action`, `abs_in_action` / 672–676 | Whether and how the intervention flags assert. | Stable zero; no intervention observed in current capture. | Deliberately trigger TC and ABS independently and record transitions. |
| `suspension_damage[4]` / 680 | Whether this is a populated conditional damage field or unused. | Conditional candidate; current “unused” label is not adequately supported. | Controlled suspension damage event or authoritative target-version definition. |
| `tyre_temp[4]` / 696 | Duplicate alias versus unused field. | Strong duplicate-alias candidate; not approved as independent telemetry. | Exact per-sample byte equality against offset 152 in the 10 Nov 2026 recording (completed: all 224,956 samples, zero mismatches). |
| `water_temp` / 712 | Whether field is real water temperature or an offset/type alias. | Unresolved; later capture statistics overlap core-temperature data. | Engine warm-up/cool-down transition if water-temperature semantics are needed; the new capture did not establish units or causal meaning. |
| `brake_pressure[4]` / 716 | Whether four channels align and how raw values map to pressure. | Unresolved; later capture statistics overlap core-temperature data. | Controlled brake-pressure event and comparison with brake bias and the documented car-specific coefficient; retain raw float interpretation as a candidate only. |
| `front_brake_compound`, `rear_brake_compound` / 732–736 | Integer encoding, offset and valid enum values. | Unresolved; current int32 values implausible. | Inspect same four bytes as int32 and float32; compare with selected compound and known valid enum mapping. |
| `pad_life[4]` / 740 | All four components and units/direction. | Unresolved; rear values are subnormal in current capture. | Raw-byte validation for all corners and controlled pad wear/service or authoritative unit definition. |
| `disc_life[4]` / 756 | Units, direction and service semantics. | Numeric variation observed; not approved as life percentage. | Raw-byte validation and controlled wear/service comparison; confirm whether unit is thickness. |
| `ignition_on`, `starter_engine_on`, `engine_running` / 772–780 | Correct offsets and boolean/integer encoding. | Unresolved; current int32 interpretations are not clean flags. | Capture engine off → ignition → starter → running → stop and inspect raw bytes at each transition. |
| Candidate vibration channels / 784–799 | Whether four float channels are present and what each represents. | Reference-supported candidate; Greenfield keeps opaque. | Exact target-PC raw-byte decoding and controlled kerb/slide/G/ABS/FFB correlation. |

### Disposition rules for this issue

- Keep all raw Physics bytes and the existing 800-byte acquisition/recording path unchanged.
- Do not expose a field as trusted telemetry solely because a third-party structure names it.
- A reference-supported field with no target-PC semantic evidence remains a candidate.
- Fields explicitly documented as unused may remain in the layout for offset correctness but must not be exposed as live telemetry.
- Unknown/reserved bytes remain opaque. Candidate vibration fields at 784–799 are not promoted until target evidence is available.
- Do not add a production decoder as part of this inventory step. First close the ABI/type and raw-byte correlation questions; decoder work remains a separate downstream task.
- The 10 Nov 2026 recording now supplies the target-PC byte-level evidence listed below. Do not repeat already completed RaceIQ/Pro Engineer comparisons or run additional exploratory correlations without a specific unresolved acceptance criterion.

### Remaining Physics work

1. Keep the corrected 800-byte ABI stable; investigate individual unresolved field semantics only when a required feature needs them.
2. Verify all four `pad_life` components and establish units/direction.
3. Establish the meaning and units of all four `disc_life` components.
4. Validate brake-pressure channels using controlled brake application and raw bytes at offsets 716, 720, 724 and 728.
5. Confirm front/rear brake compound representation and scalar type.
6. Confirm engine flags with engine-off, start, running and stop transitions.
7. Resolve the separate C# `mz[4]` layout variant against authoritative Kunos v1.9 ABI evidence.
8. Keep unresolved Physics fields out of production semantic decoding until individually resolved.


## Structural and capture checks

| Check | Result | Interpretation |
|---|---|---|
| Structure-derived layout size | 800 bytes | Corrected layout includes int32 `current_max_rpm` and `mz[4]`; three independent readers plus live mapping probe support this size |
| Earlier live page-copy smoke test | 100 reads; 784 bytes under the superseded layout | Historical evidence only; new read-only probe requested an 800-byte view and observed data through byte 799 |
| Controlled field validation | Subset listed above | Evidence applies only to those fields and tested states |
| Raw recording preservation | Complete raw page payload per sample | No field is removed by acquisition/recording filtering |

## Important limitations

The inventory describes the corroborated 800-byte reference layout and the current adapter. It does not prove that every member is actively populated by ACC 1.10.4. Some are explicitly named unused/deprecated; others may be reserved, constant or conditionally populated.

The offset inventory is calculated from the ctypes declaration using little-endian scalar widths and 4-byte packing. Independent readers and live 800-byte mapping reads support the added `mz[4]` member and corrected downstream offsets. The final 16 bytes remain opaque. An official version-matched Kunos header was not located.

## Remaining Physics work and next page

The Physics audit is now sufficiently documented to proceed to Graphics-page discovery and raw collection. This is **not Physics sign-off**: unresolved Physics fields remain tracked below and can be revisited without changing the acquisition/recorder path.

- [x] Cross-check the 800-byte field sequence against the third-party transcription of ACC Shared Memory v1.8.12 documentation and the controlled live tail-field capture.
- [ ] Obtain/verify a Kunos-published Shared Memory v1.9 header or equivalent authoritative version-matched ABI evidence.
- [x] Add automated layout regression tests for field offsets, sizes, alignment and total page size.
- [x] Add an offline raw-record inspection/validation tool; keep it outside acquisition.
- [x] Capture controlled stationary, engine on/off, driver-input and driving states.
- [x] Validate damage response and repair in a controlled pit-service capture; tyre pressure/core temperature are live signals, but a tyre-change-specific before/after effect is not isolated.
- [ ] Resolve the latest tail-field anomalies from offsets 696–783 using raw-byte/offset correlation and a version-matched ABI source.
- [ ] Validate all four pad-life and disc-life components and establish their units/direction.
- [x] Record ACC game build and Shared Memory identifiers for the current validation set.
- [x] Reject the 420-byte prefix as a complete Physics layout; retain it only as the prefix ending at `is_ai_controlled`.
- [ ] Retain `mz[4]` at offset 592 as part of the corroborated 800-byte ABI.
- [x] Add a current per-field status to the complete 82-member inventory; unresolved and untested fields remain individually identified.
- [ ] Complete conditional-field tests and obtain authoritative Kunos v1.9 ABI evidence; Physics remains provisionally open.
- [ ] Graphics page is the next acquisition investigation. Static page remains out of scope until separately planned.

## Explicit non-goals

- No decoder implementation.
- No live decode consumer yet.
- No Graphics or Static acquisition.
- No changes to the proven Physics acquisition or recorder hot path.


## Physics acquisition closure — 9 November 2026

**Result: PASSED for the defined Physics acquisition and raw-recording scope.** This closes the Physics acquisition layer; it does not claim that every one of the 82 fields has fully validated semantics or calibrated units.

### Live target-PC recording

Recording: `user_data/raw_recordings/acc_physics_20261109T093514_229225Z.accraw`

- Duration: 120 seconds; requested polling cadence: 480 Hz.
- Payload size: 800 bytes per snapshot.
- Acquired: 46,717; persisted: 46,717.
- Recorder write failures: 0; acquisition rejects: 0; recorder queue rejects: 0.
- Pending at completion: 0; reconciliation delta: 0.
- Checkpoint writes: 121; checkpoint write failures: 0.
- Recorder queue high-water mark: 2.
- Maximum persist/block-write duration: 3.9 ms.
- CPU: 13.84% of one core.

### Offline inspection and independent cross-check

The offline inspector examined all 46,717 snapshots: 212 field components, 135 varying and 77 constant. Variation is descriptive only.

An independent raw-byte script separately parsed the recording container, checked block CRCs and decoded 16 selected fields using explicit offsets/types (not the production ctypes structure or inspector decoder). It compared recomputed minima/maxima against the inspection CSV. All 16 fields matched; result: **DIRECT RAW-BYTE CROSS-CHECK: PASSED**. The recording contained 45,253 valid CRC-checked blocks and 800-byte payloads.

This establishes agreement between the raw recording bytes and the selected inspection outputs for those 16 fields. It does not independently establish the semantic meaning of every field. Semantic validation remains field-specific as shown in the inventory.

### TC and ABS naming clarification

The Physics fields at offsets 672 and 676 are intervention indicators (`tc_in_action` and `abs_in_action`), not the driver's selected TC and ABS setup levels. Both were zero in this capture. These are distinct from the earlier Physics fields named `tc` at offset 204 and `abs` at offset 252; those fields are preserved and observed, but this capture and cross-check do not establish that they represent the selected setup levels. No Graphics data or selected setup levels are included in this Physics audit.

### Scope and closure boundary

- Physics mapping and 800-byte payload acquisition: validated.
- Raw recording and normal final reconciliation: validated on the target PC.
- Recording structure/CRC inspection: validated.
- Independent raw-byte comparison for 16 selected fields: passed.
- Full semantic validation of every field: not claimed; individual statuses remain in the inventory.
- Graphics and Static acquisition: explicitly outside this closure and unchanged.- No Physics decoder, Graphics reader, or Graphics/Physics merge is introduced by this closure.

## Additional target-PC Physics evidence — 10 November 2026

This capture extends the existing RaceIQ and Pro Engineer reference comparison; it does not repeat or replace that work.

Recording: `user_data/raw_recordings/acc_physics_20261110T100629_533039Z.accraw`  
Manifest recording ID: `b6d606e2-44de-4614-b944-7d0fe92ee14d`

### Acquisition and recording integrity

- ACC game build: 1.10.4; shared-memory identifiers: `smVersion = 1.9`, `acVersion = 1.7`.
- Duration: 600 seconds; requested Physics polling: 480 Hz; raw payload: 800 bytes.
- Acquired and persisted: 224,956 snapshots; capture sequence 1–224,956.
- Source packet IDs: 14,221–254,467; packet regressions: 0.
- Acquisition rejects, recorder rejects, recorder write failures, failed samples and pending samples: all 0.
- Reconciliation delta: 0.
- Recovery: valid; 46,142 blocks; 224,956 recovered samples; 0 truncated bytes.
- Persisted payload bytes: 179,964,800 (224,956 × 800); full recording size is larger due to recording headers and block metadata.
- Checkpoint writes: 600; failures: 0.
- Maximum persist duration: 13.3 ms; maximum block write: 13.2 ms; CPU: 10.22% of one core.
- Source packet gap observations (15,291) and duplicate packet observations (59,259) are source-side observations, not missing persisted capture sequences; all 224,956 acquired snapshots were persisted.
- Manifest session metadata is null because the separate Static metadata decoder warned on `AidAutoClutch=2`. This does not indicate Physics payload or recording loss.

### Field-level observations from this capture

| Offset | Candidate field | Target-PC observation | Disposition |
|---:|---|---|---|
| 152–167 and 696–711 | Core-temperature array and duplicate alias | Exact raw-byte equality for every one of 224,956 snapshots; zero mismatches | Confirms duplicate alias for this capture; not an independent telemetry channel |
| 680–695 | Suspension damage [4] | Components 0 and 1 varied (maximum 0.107493 and 0.062567); components 2 and 3 remained zero | Conditional field is populated in this session; meaning and component mapping remain unvalidated |
| 712 | Water temperature candidate | Maximum 86.663 | Numeric observation only; units and semantic identity remain open |
| 716–731 | Brake pressure [4] | Component maxima 0.742, 0.742, 0.258 and 0.258 | Numeric observation only; scale and calibration remain open |
| 732 / 736 | Front/rear brake compound | Integer values 0–1 | Plausible enum range in this capture; enum mapping not established |
| 740–755 | Pad life [4] | Maximum approximately 29 | Units, direction and corner mapping remain open |
| 756–771 | Disc life [4] | Maximum approximately 32 | Units, direction and corner mapping remain open |
| 772 / 780 | Ignition / engine-running flags | Integer values 0/1 | Observed; complete state-transition validation remains open |
| 776 | Starter-engine flag | Remained zero | Start transition was not exercised |
| 784–799 | Reference vibration candidates | Four little-endian float interpretations are finite in all samples. Channel at 784 is mostly zero with occasional ±0.1; channel 788 ranges approximately -1..1; channel 792 approximately -1..1; channel 796 takes only -1, 0 or +1. | Consistent with treating the bytes as reference-supported candidate channels, but not proof of each channel's semantics. Preserve as opaque bytes in production. |

The tail observations above do not justify more correlation experiments: the existing RaceIQ and Pro Engineer comparison already identifies the four vibration candidates. The current implementation's conservative opaque representation remains appropriate until a feature requires a semantic decoder.

### Reference reconciliation and remaining ABI qualification

The previously recorded pinned references remain the layout evidence:
- RaceIQ commit `64a34783f706722cf342e18ec7fc06d29f30f8e`, `packages/capture-formats/src/acc/structs.ts`.
- Pro Engineer commit `b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26`, `core/src/games/assetto_corsa_competizione/structs.rs`.

Their offset/size evidence for the 800-byte structure remains consistent with Greenfield, including `currentMaxRpm` at 588, `mz[4]` at 592 and the tail vibration candidates at 784–799. The 10 Nov target-PC capture adds full-page integrity and the offset-696 exact-alias observation. It does not resolve the separate type disagreement: newer ACC-focused references use int32 for `currentMaxRpm`, while the v1.8.12 transcription and older C# reader declare float. No official Kunos Shared Memory v1.9 header was located. Therefore the 800-byte layout remains strongly corroborated, not officially version-certified.

### Issue #11 disposition after this capture

- The complete 800-byte raw capture, persistence, CRC recovery and reconciliation are confirmed for this 600-second run.
- The RaceIQ and Pro Engineer comparisons are already complete and remain the independent reference basis; no further repeat comparison is required.
- Offset 696 is confirmed as a byte-for-byte duplicate of offset 152 in this recording.
- Offset 680 is demonstrably populated in at least two components in this recording; conditional semantics remain unconfirmed.
- Offsets 712–783 now have current target-PC observations, but units, enum mapping and engine-state transitions are not all fully calibrated.
- Offsets 784–799 remain opaque in production, consistent with the current conservative boundary.
- Remaining true limitation: no official version-matched Kunos v1.9 ABI/header evidence, plus field-specific semantics/units only where a future feature actually needs them.
- No production code, ABI declaration, acquisition path, recorder, queue capacity or hot-loop behavior changed for this evidence update. No tests were run; this is a documentation-only update based on the user's completed capture and inspection.



## Overview-facing Physics audit reconciliation — 11 November 2026

This section reconciles the Physics field inventory with the current Overview implementation and the user's latest source-of-truth decisions. It does not change the decoder, acquisition path, raw recorder, or frontend code.

### Scope boundary: Physics versus Graphics

The following Overview fields are to be sourced from ACC Graphics, not inferred from Physics:

| Overview field | Expected Graphics field | Current status |
|---|---|---|
| Fuel per lap | `fuel_x_lap` | Graphics decode/integration and live validation pending |
| Estimated laps remaining | `fuel_estimated_laps` | Graphics decode/integration and live validation pending |
| TC setup level | Graphics setup-level value | Graphics decode/integration and live validation pending |
| ABS setup level | Graphics setup-level value | Graphics decode/integration and live validation pending |
| Rain light | Graphics vehicle/light state | Graphics decode/integration and live validation pending |
| Wiper | Graphics vehicle/light state | Graphics decode/integration and live validation pending |
| Left/right indicators | Graphics vehicle/light state | Graphics decode/integration and live validation pending |

The Physics fields named `tc` and `abs` are not accepted as selected TC/ABS setup levels. The Physics fields `tc_in_action` and `abs_in_action` are intervention indicators; they are distinct from setup levels and require controlled activation tests before they can be shown as trusted intervention states.

ACC Graphics is currently acquired as raw data only. The values above must be decoded from the existing Graphics acquisition stream and passed through the established consumer/bridge path. Do not open another Physics SPSC reader or add Graphics decoding to the Physics consumer.

### Current Overview Physics status

| Feature | Current state | Remaining action |
|---|---|---|
| Speed, gear, RPM/max RPM | Implemented; user-confirmed live basics | Regression validation only |
| Throttle, brake and clutch inputs | Implemented | Regression validation only |
| Steering angle and centre-zero bar | Implemented; user confirmed steering works | No known feature gap |
| Actual tyre pressure, FL/FR/RL/RR | Implemented; user confirmed live PSI appears | Regression validation only |
| Brake pressure | Implemented; user confirmed it passes | Do not infer calibration for all four raw channels from this confirmation |
| Tyre and brake temperatures | Implemented | Verify wheel mapping/units during regression |
| Fuel remaining | Implemented from Physics | Fuel bar is relative to highest observed value since app start, not verified tank capacity |
| Vehicle damage Front/Rear/Left/Right/Centre | Implemented | Preserve raw values; do not label as percentages |
| Suspension damage FL/FR/RL/RR | Implemented/displayed | Meaning, wheel mapping and normalized scale still require validation |
| Brake bias | Implemented but mismatched against ACC | Open issue #13; no speculative offset |
| Brake pad/disc life and brake compounds | Decoder/audit candidates; semantics not fully established | Keep units/direction/mapping provisional; validate only if retained as user-facing fields |
| TC/ABS setup levels | Must come from Graphics | Remove/replace any Physics-derived setup-level interpretation during Graphics integration |
| TC/ABS intervention | Physics candidate flags at offsets 672/676 | Controlled independent TC and ABS activation required before display |
| Auto shifter / turbo | UI fields exist; field-specific semantics not fully validated | Controlled state/load validation |
| Ignition/starter/engine-running | UI fields exist; transitions not fully validated | Engine off → ignition → starter → running → stop capture |
| Water temperature | Candidate at offset 712; units/semantic identity unresolved in the 10 Nov capture | Do not claim validated water temperature without transition/ABI evidence |

### Settings and UI items that affect Physics presentation

- Four editable target PSI values (FL, FR, RL, RR) exist in Settings → Vehicle & Telemetry. Overview compares actual Physics pressure with a configured target only when that wheel's target is set.
- Tyre-temperature thresholds, brake-temperature thresholds, damage thresholds and glow intensity controls exist in the same settings tab.
- User reports that settings persistence still fails in the desktop app. Track under [issue #15](https://github.com/AbhilashHalappa/Race-Engineer-ACC-New/issues/15); do not mark restart persistence as complete.
- Brake-bias mismatch remains [issue #13](https://github.com/AbhilashHalappa/Race-Engineer-ACC-New/issues/13).
- Existing issue #14 should be treated as a Graphics fuel-field integration/validation task because ACC's Graphics page exposes fuel per lap and estimated laps remaining. Do not implement a duplicate Physics lap-consumption estimator unless the Graphics values are proven unavailable or unsuitable.

### Remaining Physics-specific work for Overview

1. Resolve the brake-bias mismatch using authoritative field interpretation and controlled setup changes (issue #13).
2. Validate suspension-damage component mapping and scale before labelling it as a percentage.
3. Validate the intervention flags independently by deliberately triggering TC and ABS; do not confuse these with setup levels.
4. Validate the semantics/units of any exposed pad-life, disc-life, brake-compound, turbo and engine-state fields that remain in the UI.
5. Keep candidate/unknown fields out of trusted UI presentation until their meaning is supported.
6. Re-test existing live fields after Graphics integration to ensure the single-consumer Physics architecture remains unchanged.

### Audit conclusion

The Physics acquisition and raw-recording layer was closed for its defined scope on 9 November 2026, with additional target-PC evidence recorded on 10 November 2026. This is not semantic sign-off for every Physics field. The Overview's core Physics telemetry is implemented; remaining Physics work is targeted validation/correction, not a broad new tile implementation phase.

The next acquisition work is Graphics decoding and integration for fuel per lap, estimated laps, TC/ABS setup levels and vehicle light/wiper/indicator states. Static-page work remains separate.

