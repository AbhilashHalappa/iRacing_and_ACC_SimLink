# ACC Physics Page — Field Coverage Audit

**Status:** Structural inventory completed; authoritative-specification cross-check and live field validation pending  
**Page size:** 784 bytes  
**Layout:** Little-endian, `_pack_ = 4`  
**Reference:** `AbhilashHalappa/Race-Engineer-ACC`, branch `diagnostic/high-res-capture-2026-11-07`, `src/acc_shared_memory_extended.py`, blob `e9a54bda008cb6ff1797dfdc14b07b297a461ab9`.

## Architecture boundary

This is an audit only. It does not add a decoder or change the acquisition pipeline.

- The high-priority Physics acquisition thread remains raw-only.
- It copies the complete 784-byte page and timestamps/sequences the observation.
- The independent recorder preserves the complete raw payload.
- Decoding will be a later, separate stage. A future live decoder may receive copied observations through its own independent handoff buffer; it must not consume the recorder's SPSC queue or block acquisition.
- No Graphics or Static adapters are being added as part of this audit.

## Coverage definitions

- **Raw preserved = Yes:** the adapter copies the entire page and the recorder stores that payload; there is no per-field filtering.
- **Reference decoder exposes = Yes:** the cited reference decoder returns a corresponding field/value. This is not a decoder implemented in this greenfield repository.
- **Unused/deprecated:** based on explicit field naming in the reference structure. A field not so marked is not thereby proven to be populated by ACC.
- **Live validation:** no individual field has been validated yet. The prior live smoke test verified page size and packet-ID progression only.

## Complete field inventory

Offsets are zero-based byte offsets. Array sizes are total bytes.

| Field | C type | Offset | Size (bytes) | Raw preserved | Reference decoder exposes | Reference unused/deprecated marker | Live field validated |
|---|---:|---:|---:|---|---|---|---|
| `packet_id` | `c_int32` | 0 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `throttle` | `c_float` | 4 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `brake` | `c_float` | 8 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `fuel_kg` | `c_float` | 12 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `gear_raw` | `c_int32` | 16 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `rpm` | `c_int32` | 20 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `steering` | `c_float` | 24 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `speed_kph` | `c_float` | 28 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `velocity` | `c_float[3]` | 32 | 12 | Yes | Yes | Not marked unused | Not individually validated |
| `acc_g` | `c_float[3]` | 44 | 12 | Yes | Yes | Not marked unused | Not individually validated |
| `wheel_slip` | `c_float[4]` | 56 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `wheel_load` | `c_float[4]` | 72 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_pressure_psi` | `c_float[4]` | 88 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `wheel_angular_speed` | `c_float[4]` | 104 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_wear_unused` | `c_float[4]` | 120 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tyre_dirty` | `c_float[4]` | 136 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_core_temp_c` | `c_float[4]` | 152 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `camber_unused` | `c_float[4]` | 168 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `suspension_travel` | `c_float[4]` | 184 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `drs_unused` | `c_float` | 200 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tc` | `c_float` | 204 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `heading` | `c_float` | 208 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `pitch` | `c_float` | 212 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `roll` | `c_float` | 216 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `cg_height_unused` | `c_float` | 220 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `car_damage` | `c_float[5]` | 224 | 20 | Yes | Yes | Not marked unused | Not individually validated |
| `tyres_out_unused` | `c_int32` | 244 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `pit_limiter_on` | `c_int32` | 248 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `abs` | `c_float` | 252 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `kers_charge_unused` | `c_float` | 256 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `kers_input_unused` | `c_float` | 260 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `autoshifter_on` | `c_int32` | 264 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `ride_height_unused` | `c_float[2]` | 268 | 8 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `turbo_boost` | `c_float` | 276 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `ballast_unused` | `c_float` | 280 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `air_density_unused` | `c_float` | 284 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `air_temp_c` | `c_float` | 288 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `road_temp_c` | `c_float` | 292 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `local_angular_velocity` | `c_float[3]` | 296 | 12 | Yes | Yes | Not marked unused | Not individually validated |
| `final_ff` | `c_float` | 308 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `performance_meter_unused` | `c_float` | 312 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `engine_brake_unused` | `c_int32` | 316 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `ers_recovery_unused` | `c_int32` | 320 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `ers_power_unused` | `c_int32` | 324 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `ers_heat_unused` | `c_int32` | 328 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `ers_charging_unused` | `c_int32` | 332 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `kers_current_unused` | `c_float` | 336 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `drs_available_unused` | `c_int32` | 340 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `drs_enabled_unused` | `c_int32` | 344 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `brake_temp_c` | `c_float[4]` | 348 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `clutch` | `c_float` | 364 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_temp_i_unused` | `c_float[4]` | 368 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tyre_temp_m_unused` | `c_float[4]` | 384 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tyre_temp_o_unused` | `c_float[4]` | 400 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `is_ai_controlled` | `c_int32` | 416 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_contact_point` | `c_float[12]` | 420 | 48 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_contact_normal` | `c_float[12]` | 468 | 48 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_contact_heading` | `c_float[12]` | 516 | 48 | Yes | Yes | Not marked unused | Not individually validated |
| `brake_bias` | `c_float` | 564 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `local_velocity` | `c_float[3]` | 568 | 12 | Yes | Yes | Not marked unused | Not individually validated |
| `p2p_activation_unused` | `c_int32` | 580 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `p2p_status_unused` | `c_int32` | 584 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `current_max_rpm_unused` | `c_float` | 588 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `fx_unused` | `c_float[4]` | 592 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `fy_unused` | `c_float[4]` | 608 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `slip_ratio` | `c_float[4]` | 624 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `slip_angle` | `c_float[4]` | 640 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `tc_in_action_unused` | `c_int32` | 656 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `abs_in_action_unused` | `c_int32` | 660 | 4 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `suspension_damage_unused` | `c_float[4]` | 664 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tyre_temp_unused` | `c_float[4]` | 680 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `water_temp_c` | `c_float` | 696 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `brake_pressure` | `c_float[4]` | 700 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `front_brake_compound` | `c_int32` | 716 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `rear_brake_compound` | `c_int32` | 720 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `pad_life` | `c_float[4]` | 724 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `disc_life` | `c_float[4]` | 740 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `ignition_on` | `c_int32` | 756 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `starter_engine_on` | `c_int32` | 760 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `engine_running` | `c_int32` | 764 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `kerb_vibration` | `c_float` | 768 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `slip_vibration` | `c_float` | 772 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `g_vibration` | `c_float` | 776 | 4 | Yes | Yes | Not marked unused | Not individually validated |
| `abs_vibration` | `c_float` | 780 | 4 | Yes | Yes | Not marked unused | Not individually validated |

## Current evidence

| Check | Result | Interpretation |
|---|---|---|
| Structure-derived layout size | 784 bytes | Matches the adapter's 784-byte expected page |
| Live page-copy smoke test | 100 reads; 784 expected/actual bytes; 100 unique advancing packet IDs | Confirms mapping access, page length and packet progression |
| Field-by-field live validation | Not performed | No claim that each field is populated or correctly interpreted |
| Raw recording preservation | Complete raw page payload per sample | No field is removed by acquisition/recording filtering |

## Important limitations

The inventory describes all members in the cited 784-byte reference structure. It does not prove that every member is actively populated by the current ACC build. Some are explicitly named unused/deprecated; others may be reserved, version-dependent, constant or conditionally populated.

The offset inventory is calculated from the cited ctypes declaration using its little-endian scalar widths and 4-byte packing. It still needs a cross-check against the authoritative ACC shared-memory specification. Matching page size alone does not prove every field offset against the running game.

## Remaining work before Graphics/Static acquisition

- [ ] Cross-check every field, offset, type and array length against the authoritative ACC shared-memory specification.
- [ ] Add automated layout regression tests for all field offsets, sizes, alignment and total page size.
- [ ] Add an offline raw-record inspection/validation tool; keep it outside acquisition.
- [ ] Capture controlled live states: stationary, engine on, throttle, brake, steering, gear changes, pit, tyre changes and any safely reproducible damage state.
- [ ] Classify each field as changing, stable, conditional, unused/reserved or not observed.
- [ ] Record ACC game build and Shared Memory version for every live validation session.
- [ ] Sign off Physics coverage before beginning Graphics and Static layout/adapters.

## Explicit non-goals

- No decoder implementation.
- No live decode consumer yet.
- No Graphics or Static acquisition.
- No changes to the proven Physics acquisition or recorder hot path.
