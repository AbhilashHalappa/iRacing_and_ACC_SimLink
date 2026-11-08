# ACC Physics Page — Field Coverage Audit

**Status:** 784-byte ACC Physics layout strongly corroborated by the ACC v1.8.12 reference transcription and controlled live captures; exact Kunos v1.9 ABI/header confirmation remains unavailable.  
**Page size:** 784 bytes  
**Layout:** Little-endian, `_pack_ = 4`  
**Primary layout baseline:** `SolusDev-sys/CppAccSharedMemory`, `C++AccSharedMemory.cpp` on `main`, which its README identifies as based on the ACC Shared Memory v1.8.12 documentation attributed to KS Dev Team. This third-party transcription uses 4-byte packing and the same 784-byte Physics field sequence as this adapter.  
**Secondary decoder reference:** `AbhilashHalappa/Race-Engineer-ACC`, branch `diagnostic/high-res-capture-2026-11-07`, `src/acc_shared_memory_extended.py`, blob `e9a54bda008cb6ff1797dfdc14b07b297a461ab9`.

## Architecture boundary

This is an audit only. It does not add a decoder or change the acquisition pipeline.

- The high-priority Physics acquisition thread remains raw-only.
- It copies the complete 784-byte page and timestamps/sequences the observation.
- The independent recorder preserves the complete raw payload.
- Decoding will be a later, separate stage. A future live decoder may receive copied observations through its own independent handoff buffer; it must not consume the recorder's SPSC queue or block acquisition.
- No Graphics or Static adapters are being added as part of this audit.

## Coverage definitions

- **Raw preserved = Yes:** the adapter copies the entire page and the recorder stores that payload; there is no per-field filtering.
- **Reference decoder exposes = Yes:** the cited reference decoder includes a corresponding output key. For `wheel_load` and `tyre_dirty`, it deliberately returns `None` because the reference comments identify those ACC values as unused. This is not a decoder implemented in this greenfield repository.
- **Unused/deprecated:** based on explicit field naming in the reference structure. A field not so marked is not thereby proven to be populated by ACC.
- **Live validation:** controlled recordings now cover the prefix and multiple tail fields, including slip ratio/angle, water temperature, brake pressure, compounds, pad/disc life and engine flags. This is strong corroboration of the current 784-byte field sequence, but is not a substitute for a version-matched official ABI header.
- **Inventory table status:** the per-row “Not individually validated” entries record the original inventory baseline; they are not a statement that no later live captures have been performed.

## Complete field inventory

Offsets are zero-based byte offsets. Array sizes are total bytes.

| Field | C type | Offset | Size (bytes) | Raw preserved | Reference decoder exposes | Reference unused/deprecated marker | Live field validated at inventory baseline |
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
| `wheel_load` | `c_float[4]` | 72 | 16 | Yes | Yes — key returned as None | Not marked unused | Not individually validated |
| `tyre_pressure_psi` | `c_float[4]` | 88 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `wheel_angular_speed` | `c_float[4]` | 104 | 16 | Yes | Yes | Not marked unused | Not individually validated |
| `tyre_wear_unused` | `c_float[4]` | 120 | 16 | Yes | No | Marked unused/deprecated in reference naming | Not individually validated |
| `tyre_dirty` | `c_float[4]` | 136 | 16 | Yes | Yes — key returned as None | Not marked unused | Not individually validated |
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

## Layout regression tests

The automated test module, `tests/acquisition/test_physics_layout.py`, locks all 84 field names, ctypes scalar types, array lengths, byte offsets and sizes, plus the 784-byte total and contiguous layout. This is a regression guard against accidental edits to the current transcription; it does not independently prove the transcription matches Kunos' authoritative specification. The inspection tests also verify that RPM is reported as `int32` at offset 20 and that capped unique-value counts are explicitly identified.

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
| Stationary baseline — `acc_physics_20261108T163710_467685Z.accraw` | Stationary baseline | 10,662 snapshots; complete 784-byte payloads; 109 of 196 inspected components varied |
| Input test — `acc_physics_20261108T164030_324828Z.accraw` | Throttle, brake, steering and gear inputs | 22,519 snapshots; throttle, brake, RPM, steering and other expected driving signals varied |
| Engine OFF — `acc_physics_20261108T170533_325744Z.accraw` | Engine switched off | 6,019 snapshots; RPM remained zero while stationary |
| Engine ON — `acc_physics_20261108T170557_631094Z.accraw` | Engine switched on | 5,780 snapshots; RPM rose to approximately 1,712 during the controlled test |
| Candidate-prefix stationary — `acc_physics_20261108T173458_003331Z.accraw` | Stationary input sequence | 22,171 snapshots; candidate offsets for throttle, brake, RPM, steering and speed behaved plausibly |
| Candidate-prefix drive — `acc_physics_20261108T173813_569096Z.accraw` | 120-second drive | 46,878 snapshots; throttle, brake, RPM, steering, speed and clutch varied; clutch at offset 364 varied from 0 to 1 |
| D-BOX-enabled drive — `acc_physics_20261108T174852_787372Z.accraw` | 120-second drive with D-BOX motion enabled | 46,897 snapshots; all 45,223 blocks and all records passed CRC/structure checks |
| D-BOX tail-field inspection — same capture | Driving; tail decoded using current 784-byte offsets | `slip_ratio` -0.9862..0.1719; `slip_angle` -0.1479..0.1600; `water_temp` 0..88.5092; brake pressure 0..0.7900; compounds 0/1; pad life 0..28.9669; disc life 0..31.9822; ignition and engine-running flags both 0/1 |

### Fields observed varying in driving captures

The following fields showed plausible variation in at least one controlled driving capture:

- Driver/control and vehicle state: `throttle`, `brake`, `rpm` (int32 at offset 20), `steering`, `speed_kph`, `clutch`.
- Motion/dynamics: `acc_g`, `suspension_travel`.
- Tyre/wheel: `tyre_pressure_psi`, `wheel_angular_speed`, `tyre_core_temp_c`.
- Brakes: `brake_temp_c`.

In the D-BOX-enabled drive, observed ranges included acceleration components from -3.4587 to 2.2346, suspension travel from 0 to 0.0846 m, core temperature from 0 to 86.4095, brake temperature from 0 to 681.0502, tyre pressure from 0 to 26.2209, and wheel angular speed from 0 to 218.824. These are raw observed ranges, not calibrated engineering limits.

### Tail-field observations and stable-zero interpretation

In the D-BOX capture, `fx` and `fy` were zero; TC-in-action and ABS-in-action were also zero. These agree with the reference's unused markers for those members. `starter_engine_on` remained zero in this test, while ignition and engine-running changed between zero and one. The observed water-temperature, brake-pressure, compound and wear ranges are consistent with their documented meanings, but should still be checked across additional controlled states before being treated as calibrated engineering values.



- `wheel_load` (offset 72) was zero in the tested captures; the independent older C++ reference also labels this value unused in ACC.
- `tyre_temp_i/m/o` (offsets 368/384/400) were zero in the tested captures; the independent older C++ reference labels these arrays unused in ACC.
- `is_ai_controlled` (offset 416) was zero during the human-driven captures. This only validates the observed human-driven value; it does not prove the field is unused.
- Do not infer that every field not listed above is unused. Unlisted fields remain unverified or conditional.

The D-BOX-enabled recording confirms that the same candidate Physics signals remain available while using motion hardware. It does **not** establish that D-BOX actuator positions are published in ACC Physics shared memory, nor does this single capture establish a controlled before/after effect of enabling D-BOX.

### RPM inspection correction

The repository inspector reads RPM through the declared `ctypes.c_int32` field. It converts numeric values to Python floats only for common statistical calculations; the underlying interpretation remains integer. A temporary PowerShell diagnostic incorrectly unpacked offset 20 as a float, producing an all-zero summary. A direct `<i` check of the D-BOX recording confirmed 5,195 unique RPM values from 0 to 9,346. No production RPM or acquisition code change was needed.

### Raw capture integrity

The D-BOX-enabled capture recorded 46,897 acquired and persisted snapshots, zero rejects, zero recorder write failures, zero pending records and reconciliation delta zero. Its offline prefix parser validated 45,223 blocks and 46,897 records with no invalid blocks or records.

### Layout cross-check — 420-byte prefix versus 784-byte ACC layout

The 420-byte boundary is the end of the prefix through `is_ai_controlled`; it is not the end of the Physics page. The ACC v1.8.12 reference transcription continues with tyre contact vectors, brake bias, local velocity, slip ratio/angle, water temperature, brake pressure, compounds, pad/disc life and engine/vibration state, matching the field order and 784-byte size in this adapter. The latest live capture independently supports many of those tail fields at the adapter's declared offsets. Therefore, the 420-byte candidate is rejected as a complete Physics layout; it remains only a useful prefix boundary.

A separate C# implementation (`heikowulf/ACCsharedmemory/Physics.cs`) has additional `mz[4]` before `fx[4]` and version comments for later fields. That produces a different tail layout and is not consistent with the ACC v1.8.12 784-byte transcription used here. It is treated as a different/version-expanded layout, not silently merged into this ACC 1.10.4 adapter. We have not found a Kunos-published v1.9 header that conclusively settles this variant question, so the exact v1.9 ABI claim remains open.

## Structural and capture checks

| Check | Result | Interpretation |
|---|---|---|
| Structure-derived layout size | 784 bytes | Matches the ACC v1.8.12 reference transcription; exact Kunos v1.9 header not independently available |
| Live page-copy smoke test | 100 reads; 784 expected/actual bytes; 100 unique advancing packet IDs | Confirms mapping access, page length and packet progression |
| Controlled field validation | Subset listed above | Evidence applies only to those fields and tested states |
| Raw recording preservation | Complete raw page payload per sample | No field is removed by acquisition/recording filtering |

## Important limitations

The inventory describes the ACC v1.8.12-derived 784-byte reference transcription and the current adapter. It does not prove that every member is actively populated by ACC 1.10.4. Some are explicitly named unused/deprecated; others may be reserved, constant or conditionally populated.

The offset inventory is calculated from the ctypes declaration using little-endian scalar widths and 4-byte packing. The matching ACC-specific v1.8.12 field sequence, 784-byte size and live tail-field behaviour provide strong corroboration. The remaining uncertainty is whether Kunos changed any member in the observed Shared Memory v1.9 build; the official version-matched header was not located.

## Remaining work before Graphics/Static acquisition

- [x] Cross-check the 784-byte field sequence against the third-party transcription of ACC Shared Memory v1.8.12 documentation and the controlled live tail-field capture.
- [ ] Obtain/verify a Kunos-published Shared Memory v1.9 header or equivalent authoritative version-matched ABI evidence.
- [x] Add automated layout regression tests for field offsets, sizes, alignment and total page size.
- [x] Add an offline raw-record inspection/validation tool; keep it outside acquisition.
- [x] Capture controlled stationary, engine on/off, driver-input and driving states.
- [ ] Validate remaining fields, including conditional states such as pit, tyre changes and safely reproducible damage.
- [x] Record ACC game build and Shared Memory identifiers for the current validation set.
- [x] Reject the 420-byte prefix as a complete Physics layout; retain it only as the prefix ending at `is_ai_controlled`.
- [ ] Resolve the separate C# `mz[4]` layout variant against a Kunos-published v1.9 ABI source.
- [ ] Classify every field as changing, stable, conditional, unused/reserved or not observed, with evidence and confidence.
- [ ] Sign off Physics coverage before beginning Graphics and Static layout/adapters.

## Explicit non-goals

- No decoder implementation.
- No live decode consumer yet.
- No Graphics or Static acquisition.
- No changes to the proven Physics acquisition or recorder hot path.
