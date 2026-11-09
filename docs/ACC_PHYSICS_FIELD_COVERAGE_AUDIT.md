# ACC Physics Page — Field Coverage Audit

**Status:** 800-byte ACC Physics layout strongly corroborated by the ACC v1.8.12 reference transcription and controlled live captures; exact Kunos v1.9 ABI/header confirmation remains unavailable.  
**Page size:** 800 bytes  
**Layout:** Little-endian, `_pack_ = 4`  
**Primary layout baseline:** `SolusDev-sys/CppAccSharedMemory`, `C++AccSharedMemory.cpp` on `main`, which its README identifies as based on the ACC Shared Memory v1.8.12 documentation attributed to KS Dev Team. This third-party transcription uses 4-byte packing and the same 800-byte Physics field sequence as this adapter.  
**Secondary decoder reference:** `AbhilashHalappa/Race-Engineer-ACC`, branch `diagnostic/high-res-capture-2026-11-07`, `src/acc_shared_memory_extended.py`, blob `e9a54bda008cb6ff1797dfdc14b07b297a461ab9`.

## Architecture boundary

This is an audit only. It does not add a decoder or change the acquisition pipeline.

- The high-priority Physics acquisition thread remains raw-only.
- It copies the complete 800-byte page and timestamps/sequences the observation.
- The independent recorder preserves the complete raw payload.
- Decoding will be a later, separate stage. A future live decoder may receive copied observations through its own independent handoff buffer; it must not consume the recorder's SPSC queue or block acquisition.
- No Graphics or Static adapters are being added as part of this audit.

## Coverage definitions

- **Raw preserved = Yes:** the adapter copies the entire page and the recorder stores that payload; there is no per-field filtering.
- **Reference decoder exposes = Yes:** the cited reference decoder includes a corresponding output key. For `wheel_load` and `tyre_dirty`, it deliberately returns `None` because the reference comments identify those ACC values as unused. This is not a decoder implemented in this greenfield repository.
- **Unused/deprecated:** based on explicit field naming in the reference structure. A field not so marked is not thereby proven to be populated by ACC.
- **Live validation:** statuses below summarize evidence through the 2026-11-09 five-minute capture. “Validated” means a plausible signal was correlated with a controlled action or repeatable driving state; it does not automatically establish calibrated units or complete semantics.
- **Observed:** a field changed in a live capture, but controlled causality, axis/sign calibration or semantic confirmation is missing.
- **Unresolved:** latest evidence is contradictory or implausible; do not use the declared interpretation.
- **Reference unused:** this reflects the cited third-party reference, not an official Kunos guarantee.

| `tail_reserved` | `c_ubyte[16]` | 784 | 16 | Yes | No | Opaque/reserved bytes | Preserved raw; semantics intentionally not assigned |

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
| `tc_in_action_unused` | `c_int32` | 672 | 4 | Yes | No | Marked unused/deprecated in reference naming | Stable zero in tested capture; reference marks unused/deprecated |
| `abs_in_action_unused` | `c_int32` | 676 | 4 | Yes | No | Marked unused/deprecated in reference naming | Stable zero in tested capture; reference marks unused/deprecated |
| `suspension_damage_unused` | `c_float[4]` | 680 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `tyre_temp_unused` | `c_float[4]` | 696 | 16 | Yes | No | Marked unused/deprecated in reference naming | Reference marks unused/deprecated; not a live target |
| `water_temp_c` | `c_float` | 712 | 4 | Yes | Yes | Not marked unused | Unresolved — latest capture aliases tyre_core_temp_c[0] statistics |
| `brake_pressure` | `c_float[4]` | 716 | 16 | Yes | Yes | Not marked unused | Unresolved — latest capture overlaps tyre-core-temperature statistics |
| `front_brake_compound` | `c_int32` | 732 | 4 | Yes | Yes | Not marked unused | Unresolved — int32 value 1.06183e9 is not a credible compound ID |
| `rear_brake_compound` | `c_int32` | 736 | 4 | Yes | Yes | Not marked unused | Unresolved — int32 value 1.06183e9 is not a credible compound ID |
| `pad_life` | `c_float[4]` | 740 | 16 | Yes | Yes | Not marked unused | Unresolved — rear components show 1.4013e-45 subnormal values |
| `disc_life` | `c_float[4]` | 756 | 16 | Yes | Yes | Not marked unused | Unresolved — changing values; units/meaning not established |
| `ignition_on` | `c_int32` | 772 | 4 | Yes | Yes | Not marked unused | Unresolved — values around 1.107e9, not clean 0/1 flags |
| `starter_engine_on` | `c_int32` | 776 | 4 | Yes | Yes | Not marked unused | Unresolved — values around 1.107e9, not clean 0/1 flags |
| `engine_running` | `c_int32` | 780 | 4 | Yes | Yes | Not marked unused | Unresolved — values around 1.107e9, not clean 0/1 flags |

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

The 420-byte boundary is the end of the prefix through `is_ai_controlled`; it is not the end of the Physics page. The ACC v1.8.12 reference transcription continues with tyre contact vectors, brake bias, local velocity, slip ratio/angle, water temperature, brake pressure, compounds, pad/disc life and engine/vibration state, matching the field order and 800-byte size in this adapter. The latest live capture independently supports many of those tail fields at the adapter's declared offsets. Therefore, the 420-byte candidate is rejected as a complete Physics layout; it remains only a useful prefix boundary.

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

### Remaining Physics work

1. Keep the corrected 800-byte ABI stable; investigate individual unresolved field semantics only when a required feature needs them.
2. Verify all four `pad_life` components and establish units/direction.
3. Establish the meaning and units of all four `disc_life` components.
4. Validate brake-pressure channels using controlled brake application and raw bytes at offsets 700, 704, 708 and 712.
5. Confirm front/rear brake compound representation and scalar type.
6. Confirm engine flags with engine-off, start, running and stop transitions.
7. Resolve the separate C# `mz[4]` layout variant against authoritative Kunos v1.9 ABI evidence.
8. Keep unresolved Physics fields out of production semantic decoding until individually resolved.


## Structural and capture checks

| Check | Result | Interpretation |
|---|---|---|
| Structure-derived layout size | 784 bytes | Matches the ACC v1.8.12 reference transcription; exact Kunos v1.9 header not independently available |
| Live page-copy smoke test | 100 reads; 784 expected/actual bytes; 100 unique advancing packet IDs | Confirms mapping access, page length and packet progression |
| Controlled field validation | Subset listed above | Evidence applies only to those fields and tested states |
| Raw recording preservation | Complete raw page payload per sample | No field is removed by acquisition/recording filtering |

## Important limitations

The inventory describes the ACC v1.8.12-derived 800-byte reference transcription and the current adapter. It does not prove that every member is actively populated by ACC 1.10.4. Some are explicitly named unused/deprecated; others may be reserved, constant or conditionally populated.

The offset inventory is calculated from the ctypes declaration using little-endian scalar widths and 4-byte packing. The matching ACC-specific v1.8.12 field sequence, 800-byte size and live tail-field behaviour provide strong corroboration. The remaining uncertainty is whether Kunos changed any member in the observed Shared Memory v1.9 build; the official version-matched header was not located.

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
