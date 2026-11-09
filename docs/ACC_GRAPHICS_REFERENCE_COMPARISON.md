# ACC Graphics: Independent RaceIQ vs Pro Engineer comparison

Date: 9 November 2026

## Purpose

Decode the same full-page ACC Graphics recordings independently using:

1. RaceIQ's executable ACC `GRAPHICS` descriptor map.
2. Pro Engineer's `AccGraphics` field sequence.

Neither decoder imports the other's offsets. The comparison tool is:

`scripts/compare_acc_graphics_structures.py`

## Reference sources

- RaceIQ, pinned revision: https://github.com/SpeedHQ/RaceIQ/blob/64a34783f706722cf342e18ecb7fc06d29f30f8e/packages/capture-formats/src/acc/structs.ts
- Pro Engineer, pinned revision: https://github.com/Rgosh/ac-pro-engineer/blob/b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26/core/src/games/assetto_corsa_competizione/structs.rs

## What the source comparison establishes

Both projects describe a 1,588-byte ACC Graphics structure. Their overlapping offsets for the setup fields below agree:

| Field | Offset (decimal) | Offset (hex) | Type |
|---|---:|---:|---|
| TC | 1268 | 0x4F4 | int32 |
| TC Cut | 1272 | 0x4F8 | int32 |
| Engine Map | 1276 | 0x4FC | int32 |
| ABS | 1280 | 0x500 | int32 |
| Rain Lights | 1288 | 0x508 | int32 |
| Flashing Lights | 1292 | 0x50C | int32 |
| Lights Stage | 1296 | 0x510 | int32 |
| Wiper Stage | 1304 | 0x518 | int32 |
| Left Indicator | 1492 | 0x5D4 | int32 |
| Right Indicator | 1496 | 0x5D8 | int32 |
| Dash display index | 1260 | 0x4EC | int32 |
| Secondary display index | 1264 | 0x4F0 | int32 |

Important distinction:
- TC, TC Cut, Engine Map, ABS and Dash have explicit RaceIQ descriptors.
- RaceIQ's source comments identify the rain-light, flashing-light, light-stage and wiper positions, but does not expose them as executable descriptors.
- RaceIQ does not expose the indicator or secondary-display fields as executable descriptors.
- Pro Engineer declares the above lighting, wiper, indicator and secondary-display fields explicitly.
- Therefore, the two implementations can be compared independently for common fields, but RaceIQ has less explicit field coverage. A field missing from RaceIQ's descriptors is not evidence that ACC does not publish it.

## Values outside the Graphics page

These user-provided settings belong to the Physics page, not Graphics:
- Brake Bias: Physics offset 564, float32.
- Pit Limiter: Physics offset 248, int32.
- Ignition: Physics offset 772, int32.
- Starter: Physics offset 776, int32.

They must not be searched for in the Graphics page or added to its field map.

## Running the comparison on existing recordings

No new capture is required. Run both existing recordings through both independent decoders:

```powershell
python scripts\compare_acc_graphics_structures.py `
  user_data\raw_recordings\acc_graphics_20261109T102951_361905Z.gfxraw `
  user_data\raw_recordings\acc_graphics_20261109T104146_431025Z.gfxraw `
  --json-out user_data\raw_recordings\graphics-structure-comparison.json
```

The terminal output is limited to the requested electronics and display controls. The JSON report retains full field summaries for both candidate maps.

## Interpretation rules

- Where both structures declare the same field at the same offset and type, both decoders must return the same values from the same bytes. That result confirms implementation agreement, not which source is empirically correct.
- Where RaceIQ only comments on a field, its value is shown separately as comment-only and is not treated as a RaceIQ executable descriptor.
- Where only Pro Engineer declares a field, only the Pro Engineer result is available.
- A value matching the final ACC setup is useful evidence, but a single static match is not enough to prove semantics. Transitions and a known setting-change timeline provide stronger validation.
- The supplied final ACC setup is the comparison reference; do not infer that every historical sample was taken after that setup was selected.
- Do not mix offsets between the two structures to manufacture a match.
- Keep the full 4,096-byte raw mapping capture unchanged. The candidate logical structure remains 1,588 bytes; the remaining mapping bytes stay opaque.

## Current status

The two source layouts have been transcribed into separate decoder maps. The raw recordings have not yet been decoded by this new comparison script in the user's local environment. Therefore, no empirical winner is declared at this stage.


## Subsequent full-page capture and candidate audit — 9 November 2026

The separate raw-only Graphics recorder was subsequently validated on the target PC with a six-minute dry-session recording: 36,001 samples, 4,096 bytes per sample, zero acquisition/queue rejects, zero write failures, zero pending records and zero reconciliation delta. CRC, record-sequence and packet-ID checks passed.

The new offline utility `scripts/audit_acc_graphics_all_fields.py` decoded the complete Pro Engineer 87-member / 1,588-byte candidate against that existing recording. The full scalar summaries, per-slot array summaries, UTF-16 strings and event index are documented in [ACC_GRAPHICS_FIELD_COVERAGE_AUDIT.md](ACC_GRAPHICS_FIELD_COVERAGE_AUDIT.md).

This does not retroactively mean the separate RaceIQ-vs-Pro Engineer comparison utility was run against that six-minute file. Source agreement remains corroboration only; the candidate is not an official Kunos Shared Memory 1.9 ABI sign-off. In particular, the Engine Map UI/value mismatch remains unresolved.
