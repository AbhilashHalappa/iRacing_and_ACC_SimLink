# ACC Static Field Layout Audit

**Updated:** 9 November 2026  
**Branch:** `feature/acquisition-foundation`  
**Status:** Target-PC candidate inspection strongly favors Variant B (33 UTF-16 code units for TrackConfiguration). Common-prefix values match the active ACC car/track and several Variant B tail strings are coherent. Variant A is rejected for this observed page. Pit-window values/units and several field semantics remain unqualified; this is not official Kunos ABI sign-off.

## 1. Live acquisition evidence

The target-PC 90-second Static acquisition run reported:

| Metric | Result |
|---|---:|
| Mapping | `Local\\acpmf_static` |
| Windows mapping allocation | 4,096 bytes |
| Reads | 90 |
| Emitted snapshots | 1 |
| Unchanged reads | 89 |
| Buffer rejections | 0 |
| Maximum read duration | 14,400 ns |
| Source packet ID / source timestamp | Not defined by the candidate Static layout; represented as null |
| Cross-stream synchronization | None |

This proves repeated full-allocation reads and unchanged-page suppression for a stable page. It does not prove field offsets or changed-page behavior. The 4,096-byte Windows allocation is not, by itself, proof that the logical C structure is 4,096 bytes.


## 2A. Target-PC candidate inspection — 9 November 2026

The user ran `python scripts/inspect_acc_static_candidate.py` with ACC active. The script's automated test suite also passed locally: **3 passed in 0.06s**.

Observed common-prefix values:

| Field | Offset | Observed | Assessment |
|---|---:|---|---|
| SMVersion | 0 | `1.9` | Matches installed ACC shared-memory version |
| ACVersion | 30 | `1.7` | Plausible game version string |
| CarModel | 68 | `porsche_992_gt3_r` | Matches active car |
| Track | 134 | `monza` | Matches active track |
| PlayerName | 200 | `Abhi` | Plausible active profile value |
| PlayerSurname | 266 | `H` | Plausible active profile value |
| PlayerNick | 332 | empty | Plausible optional nickname |
| NumberOfSessions | 60 | 0 | Semantics not confirmed; raw-only |
| NumCars | 64 | 25 | Plausible session entry count |
| SectorCount | 400 | 3 | Matches Monza's three sectors |
| MaxRPM | 412 | 9250 | Plausible Porsche 992 GT3 R metadata |
| MaxFuel | 416 | 120 | Plausible vehicle fuel capacity |
| PenaltiesEnabled | 464 | 1 | Boolean-like enabled value |
| AidFuelRate / AidTireRate / AidMechanicalDamage | 468/472/476 | 1 / 1 / 1 | Plausible neutral multipliers |
| AidAutoClutch / AidAutoBlip | 488/492 | 1 / 1 | Boolean-like enabled values |

Variant B tail observations:

| Field | Offset | Observed | Assessment |
|---|---:|---|---|
| TrackConfiguration | 524 | `track config` | String fits both candidates; does not independently distinguish length |
| ERSMaxJ | 592 | 0 | Plausible unused/zero value; raw-only |
| IsTimedRace | 596 | 0 | Plausible boolean-like value |
| HasExtraLap | 600 | 0 | Plausible boolean-like value |
| CarSkin | 604 | `skin` | Coherent string at Variant B offset; Variant A offset is empty |
| ReversedGridPositions | 672 | 0 | Plausible default |
| PitWindowStart / PitWindowEnd | 676/680 | 600500 / 599500 | Values are plausible integers but start exceeds end by 1,000; units/semantics unresolved; raw-only |
| IsOnline | 684 | 0 | Plausible offline boolean-like value |
| DryTyresName / WetTyresName | 688/754 | `DHE` / `WH` | Coherent tyre-name strings at Variant B offsets; Variant A offsets are empty |

At the corresponding Variant A offsets, `CarSkin`, dry tyre name and wet tyre name all decode as empty strings, while Variant B yields coherent values. Together with the matching car/track prefix, three-sector count, plausible vehicle limits and session settings, this is strong live evidence for Variant B's tail offsets on ACC Shared Memory 1.9. The `TrackConfiguration` string itself is shorter than both candidate capacities, so its content alone cannot distinguish 15 from 33; the shifted tail fields provide the discriminating evidence.

**Disposition:** use Variant B as the leading candidate for subsequent implementation and testing. Do not claim official ABI certification. Keep pit-window values and fields with unconfirmed type/unit semantics raw-only. Do not expose `NumberOfSessions`, `ERSMaxJ`, deprecated members or fields merely because they decode to plausible numbers.

## 2. Candidate source comparison

The following public references describe the ACC Static page:

1. The ACC Shared Memory v1.8.12 documentation describes the Static page as initialized at instance start and lists the session, car, track, aid, pit-window and tyre-name fields. It gives `trackConfiguration` without a clear array length in the extracted text. [Reference](https://www.scribd.com/document/829667458/ACCSharedMemoryDocumentationV1-8-12)
2. The `ebnerdm/accshm` field inventory lists the Static fields in memory order, including `TrackConfiguration [33]uint16`, `CarSkin [33]uint16`, and dry/wet tyre names. [FIELDS.md](https://github.com/ebnerdm/accshm/blob/main/FIELDS.md)
3. The `rrennoir/PyAccSharedMemory` reader lists a 784-byte mapping, but its parser reads `trackConfiguration` as 33 UTF-16 code units plus two padding bytes. Its sequential parser therefore attempts to consume 820 bytes. This is an internal size/decoder inconsistency and must not be treated as validated evidence. [Source](https://github.com/rrennoir/PyAccSharedMemory/blob/d08ae99739fe638de2785c67e8684bafcadf80de/src/pyaccsharedmemory.py)
4. The `MorGuux/AssettoCorsaCompetizioneSharedMemory` C# `StaticInfo` struct declares `TrackConfiguration` as 15 UTF-16 code units and uses Pack=4, which yields a 784-byte structure with the remaining fields. [Source](https://github.com/MorGuux/AssettoCorsaCompetizioneSharedMemory/blob/59b65ac875ae956e2218808d86e0ec0ea0e8cfb3/StaticInfo.cs)
5. The ACC v1.8 field listing and related references describe the rest of the Static members, including 4-element suspension travel and tyre radius arrays. [Reference](https://www.scribd.com/document/1043572003/ACCSharedMemoryDocumentationV1-8)

**Conclusion:** public references disagree on TrackConfiguration length, but the target-PC values strongly favor the 33-code-unit Variant B tail: CarSkin and dry/wet tyre names are coherent at B offsets and empty at A offsets. The 4,096-byte allocation itself does not resolve the logical structure size. Variant B is the evidence-backed candidate for the observed ACC 1.9 page, not official Kunos ABI certification.

## 3. Common-prefix candidate offsets

Offsets below are byte offsets from the beginning of the Static mapping. UTF-16 strings are 2 bytes per code unit. Four-byte fields are aligned to 4-byte boundaries.

| Offset | Field | Candidate type / size | Interpretation status |
|---:|---|---|---|
| 0 | SMVersion | UTF-16[15], 30 B | Version string |
| 30 | ACVersion | UTF-16[15], 30 B | Game version string |
| 60 | NumberOfSessions | int32 | Count; semantics not independently tested |
| 64 | NumCars | int32 | Car count/capacity; semantics not independently tested |
| 68 | CarModel | UTF-16[33], 66 B | Player car identifier |
| 134 | Track | UTF-16[33], 66 B | Track identifier/name |
| 200 | PlayerName | UTF-16[33], 66 B | Player first/name field |
| 266 | PlayerSurname | UTF-16[33], 66 B | Player surname |
| 332 | PlayerNick | UTF-16[33], 66 B | Player nickname |
| 398 | Alignment | 2 B | Padding before int32 |
| 400 | SectorCount | int32 | Number of sectors |
| 404 | MaxTorque | float32 | Documented as unused/not shown in ACC |
| 408 | MaxPower | float32 | Documented as unused/not shown in ACC |
| 412 | MaxRPM | int32 | Maximum engine RPM |
| 416 | MaxFuel | float32 | Maximum tank capacity |
| 420 | SuspensionMaxTravel | float32[4], 16 B | Documented as unused/not shown in ACC |
| 436 | TyreRadius | float32[4], 16 B | Documented as unused/not shown in ACC |
| 452 | MaxTurboBoost | float32 | Candidate vehicle capability |
| 456 | Deprecated1 | float32 | Deprecated; preserve raw, do not expose |
| 460 | Deprecated2 | float32 | Deprecated; preserve raw, do not expose |
| 464 | PenaltiesEnabled | int32 | Penalties enabled |
| 468 | AidFuelRate | float32 | Fuel-use multiplier candidate |
| 472 | AidTireRate | float32 | Tyre-wear multiplier candidate |
| 476 | AidMechanicalDamage | float32 | Mechanical-damage multiplier candidate |
| 480 | AidAllowTyreBlankets | float32 / int32 conflict | Raw bits must be checked before choosing a type |
| 484 | AidStability | float32 | Stability-assist setting |
| 488 | AidAutoClutch | int32 | Boolean-like setting |
| 492 | AidAutoBlip | int32 | Boolean-like setting |
| 496 | HasDRS | int32 | Documented as unused/not shown in ACC |
| 500 | HasERS | int32 | Documented as unused/not shown in ACC |
| 504 | HasKERS | int32 | Documented as unused/not shown in ACC |
| 508 | KERSMaxJ | float32 | Documented as unused/not shown in ACC |
| 512 | EngineBrakeSettingsCount | int32 | Documented as unused/not shown in ACC |
| 516 | ERSPowerControllerCount | int32 | Documented as unused/not shown in ACC |
| 520 | TrackSplineLength | float32 | Documented as unused/not shown in ACC |
| 524 | TrackConfiguration | UTF-16[15] or UTF-16[33] | **Unresolved length; see variants below** |

## 4. Competing tail layouts

### Variant A — 15-character TrackConfiguration (784-byte candidate)

| Offset | Field | Candidate type |
|---:|---|---|
| 524 | TrackConfiguration | UTF-16[15], 30 B |
| 554 | Alignment | 2 B |
| 556 | ERSMaxJ | float32 |
| 560 | IsTimedRace | int32 |
| 564 | HasExtraLap | int32 |
| 568 | CarSkin | UTF-16[33], 66 B |
| 634 | Alignment | 2 B |
| 636 | ReversedGridPositions | int32 |
| 640 | PitWindowStart | int32 |
| 644 | PitWindowEnd | int32 |
| 648 | IsOnline | int32 |
| 652 | DryTyresName | UTF-16[33], 66 B |
| 718 | WetTyresName | UTF-16[33], 66 B |
| 784 | End | Candidate logical size |

### Variant B — 33-character TrackConfiguration (820-byte candidate)

| Offset | Field | Candidate type |
|---:|---|---|
| 524 | TrackConfiguration | UTF-16[33], 66 B |
| 590 | Alignment | 2 B |
| 592 | ERSMaxJ | float32 |
| 596 | IsTimedRace | int32 |
| 600 | HasExtraLap | int32 |
| 604 | CarSkin | UTF-16[33], 66 B |
| 670 | Alignment | 2 B |
| 672 | ReversedGridPositions | int32 |
| 676 | PitWindowStart | int32 |
| 680 | PitWindowEnd | int32 |
| 684 | IsOnline | int32 |
| 688 | DryTyresName | UTF-16[33], 66 B |
| 754 | WetTyresName | UTF-16[33], 66 B |
| 820 | End | Candidate logical size |

## 5. Semantic disposition

- **Car identity:** `CarModel` is the primary car identifier. `CarSkin` is a candidate skin identifier, but is in the unresolved tail.
- **Track identity:** `Track` is the primary track identifier. `TrackConfiguration` decodes as `track config`; its actual string capacity cannot be inferred from this value alone. Variant B tail offsets are strongly favored by the car-skin and tyre-name strings.
- **Session configuration:** `NumberOfSessions`, `NumCars`, `SectorCount`, `PenaltiesEnabled`, aid rates/toggles, `IsOnline`, and pit-window fields are candidate settings. Pit-window units/encoding and several setting semantics still need value-based confirmation.
- **Vehicle metadata:** `MaxRPM`, `MaxFuel`, `MaxTurboBoost` are candidates for useful vehicle capability metadata. The torque/power/suspension/tyre-radius fields are marked unused/not shown by references and should remain raw-only until demonstrated.
- **Tyre metadata:** dry/wet tyre names are candidate strings in the tail layout; their offsets depend on the TrackConfiguration variant.
- **Deprecated/unused members:** retain in the raw page and audit, but do not expose as application features without evidence.
- **Source provenance:** Static has no documented packet ID or source timestamp. Keep both null; local capture sequence/timestamps remain acquisition metadata only. Do not synchronize Static with Physics or Graphics.

## 6. Next evidence step

The focused candidate inspector has now been run on the target PC. Its observed values and interpretation are recorded above. No repeat run is needed for the common-prefix/tail comparison.

```powershell
python scripts/inspect_acc_static_candidate.py
```

It reads the current mapping once and prints a compact candidate decode for the common prefix plus both competing tail layouts. It does not write, alter, or dump the raw mapping. Compare the printed strings and numeric plausibility with the active car, track and session shown in ACC.

This was a targeted field-layout check, not another recording. Variant B is the leading candidate based on multiple coherent live values. The remaining implementation decision is to define a conservative typed decoder for only the qualified fields, while preserving raw bytes and leaving unresolved fields raw-only.

## 7. Acceptance gates

- [x] Runtime allocation size discovered and full 4,096-byte page copied on target PC.
- [x] Stable-page polling and unchanged-page suppression passed (90 reads, 89 unchanged, zero rejects).
- [x] Common-prefix candidate strings and representative numeric values match the active ACC car/track/session (user-confirmed output, 9 November 2026).
- [x] Variant B (33-code-unit TrackConfiguration / shifted tail offsets) strongly favored by coherent CarSkin and dry/wet tyre-name strings; Variant A produces empty strings at those offsets.
- [x] CarSkin, dry/wet tyre-name and candidate online-flag offsets have coherent Variant B values; pit-window integer offsets are observed but units/semantics remain unresolved.
- [ ] Field types and units for aid/penalty/pit-window values confirmed or explicitly left raw-only.
- [ ] Production decoder added only after the above evidence; all raw bytes remain preserved.
