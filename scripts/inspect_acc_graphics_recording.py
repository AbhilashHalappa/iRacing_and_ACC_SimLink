#!/usr/bin/env python3
"""Offline inspector for ACC Graphics full-page recordings.

Supports the CRC-block .gfxraw format from record_acc_graphics.py and the
older diagnostic format from probe_acc_graphics.py. It never connects to ACC
or modifies the source recording. All decoded offsets remain candidate
mappings and are not ABI sign-off.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

HEADER = struct.Struct("<8sII")
SAMPLE = struct.Struct("<Qiii")
MAGIC = b"ACCGFXR1"
RAW_HEADER = struct.Struct("<8sIIQI")
RAW_BLOCK = struct.Struct("<4sQIII")
RAW_RECORD = struct.Struct("<QQQQQI")
RAW_MAGIC = b"ACCGFX01"
RAW_BLOCK_MAGIC = b"GFXB"
CANDIDATE_STRUCT_SIZE = 1588

SCALARS: dict[str, tuple[int, str]] = {
    "status": (0x004, "i"),
    "session": (0x008, "i"),
    "completed_laps": (0x084, "i"),
    "position": (0x088, "i"),
    "current_time_ms": (0x08C, "i"),
    "last_time_ms": (0x090, "i"),
    "best_time_ms": (0x094, "i"),
    "last_sector_time_ms": (0x0A8, "i"),
    "normalized_car_position": (0x0F8, "f"),
    "active_cars": (0x0FC, "i"),
    "tc": (0x4F4, "i"),
    "tc_cut": (0x4F8, "i"),
    "engine_map": (0x4FC, "i"),
    "abs": (0x500, "i"),
    "rain_lights": (0x508, "i"),
    "flashing_lights": (0x50C, "i"),
    "lights_stage": (0x510, "i"),
    "wiper_level": (0x518, "i"),
    "direction_lights_left": (0x5D4, "i"),
    "direction_lights_right": (0x5D8, "i"),
    "used_fuel": (0x52C, "f"),
    "i_delta_lap_time": (0x550, "i"),
    "i_estimated_lap_time": (0x574, "i"),
    "is_delta_positive": (0x578, "i"),
    "is_valid_lap": (0x580, "i"),
}

def decode(page: bytes, offset: int, fmt: str) -> Any:
    return struct.unpack_from("<" + fmt, page, offset)[0]

def scalar_summary(values: list[Any]) -> dict[str, Any]:
    counts = Counter(str(v) for v in values)
    changes = []
    previous = object()
    for index, value in enumerate(values):
        if index and value != previous:
            changes.append({
                "sample": index,
                "from": previous,
                "to": value,
            })
        previous = value

    numeric = [v for v in values if isinstance(v, (int, float))
               and not isinstance(v, bool)
               and (not isinstance(v, float) or math.isfinite(v))]
    result: dict[str, Any] = {
        "samples": len(values),
        "unique_count": len(counts),
        "counts": dict(counts.most_common(20)),
        "transitions": changes[:30],
        "transitions_total": len(changes),
    }
    if numeric:
        result["first"] = numeric[0]
        result["last"] = numeric[-1]
        result["min"] = min(numeric)
        result["max"] = max(numeric)
    return result

def array_summary(pages: list[bytes], offset: int, count: int,
                  fmt: str, stride: int = 4) -> dict[str, Any]:
    values_by_slot: list[list[Any]] = [[] for _ in range(count)]
    for page in pages:
        for slot in range(count):
            values_by_slot[slot].append(decode(page, offset + slot * stride, fmt))

    slots = []
    for slot, values in enumerate(values_by_slot):
        finite = [v for v in values if not isinstance(v, float) or math.isfinite(v)]
        changed = sum(1 for a, b in zip(values, values[1:]) if a != b)
        slots.append({
            "slot": slot,
            "first": values[0] if values else None,
            "last": values[-1] if values else None,
            "min": min(finite) if finite else None,
            "max": max(finite) if finite else None,
            "unique_count": len(set(values)),
            "changed_samples": changed,
        })
    return {
        "offset_hex": hex(offset),
        "element_type": "float32" if fmt == "f" else "int32",
        "slots": slots,
    }


def read_raw_gfxraw(data: bytes) -> tuple[int, list[bytes], list[dict[str, int]]]:
    """Read and CRC-check the production .gfxraw block/record format."""
    if len(data) < RAW_HEADER.size:
        raise SystemExit("Graphics raw recording header is incomplete.")
    magic, version, page_size, _created_ns, header_crc = RAW_HEADER.unpack_from(data)
    if magic != RAW_MAGIC or version != 1:
        raise SystemExit("Unsupported .gfxraw recording header.")
    if zlib.crc32(data[:RAW_HEADER.size - 4]) != header_crc:
        raise SystemExit("Graphics raw recording header CRC mismatch.")
    if page_size < CANDIDATE_STRUCT_SIZE:
        raise SystemExit(f"Page size {page_size} is smaller than candidate structure.")

    pages: list[bytes] = []
    metadata: list[dict[str, int]] = []
    cursor = RAW_HEADER.size
    expected_block = 1
    previous_capture = 0
    while cursor < len(data):
        if len(data) - cursor < RAW_BLOCK.size:
            raise SystemExit("Truncated Graphics block header.")
        block_magic, block_seq, count, payload_len, checksum = RAW_BLOCK.unpack_from(data, cursor)
        cursor += RAW_BLOCK.size
        if block_magic != RAW_BLOCK_MAGIC or block_seq != expected_block or count <= 0:
            raise SystemExit(f"Invalid Graphics block header at block {expected_block}.")
        end = cursor + payload_len
        if end > len(data):
            raise SystemExit(f"Truncated Graphics block {block_seq}.")
        block = data[cursor:end]
        if zlib.crc32(block) != checksum:
            raise SystemExit(f"Graphics block {block_seq} CRC mismatch.")
        block_cursor = 0
        for _ in range(count):
            if len(block) - block_cursor < RAW_RECORD.size:
                raise SystemExit(f"Truncated record header in block {block_seq}.")
            sequence, packet, started, completed, captured, size = RAW_RECORD.unpack_from(block, block_cursor)
            block_cursor += RAW_RECORD.size
            if size != page_size or block_cursor + size > len(block):
                raise SystemExit(f"Invalid page size in capture sequence {sequence}.")
            if sequence <= previous_capture:
                raise SystemExit("Graphics capture sequence is not strictly increasing.")
            page = block[block_cursor:block_cursor + size]
            block_cursor += size
            if struct.unpack_from("<i", page, 0)[0] != packet:
                raise SystemExit(f"Packet ID mismatch in capture sequence {sequence}.")
            pages.append(page)
            metadata.append({
                "capture_sequence": sequence,
                "packet_id": packet,
                "read_start_ns": started,
                "read_complete_ns": completed,
                "capture_timestamp_ns": captured,
            })
            previous_capture = sequence
        if block_cursor != len(block):
            raise SystemExit(f"Unexpected trailing bytes in Graphics block {block_seq}.")
        cursor = end
        expected_block += 1
    if not pages:
        raise SystemExit("Graphics recording contains no snapshots.")
    return page_size, pages, metadata

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="*.gfxraw or legacy *.graphics-recording.bin file")
    parser.add_argument("--json-out", type=Path, help="optional JSON report path")
    parser.add_argument("--max-transitions", type=int, default=30)
    args = parser.parse_args()

    data = args.recording.read_bytes()
    if len(data) < 8:
        raise SystemExit("Recording is shorter than its magic header.")

    if data[:8] == RAW_MAGIC:
        page_size, pages, raw_metadata = read_raw_gfxraw(data)
        schema = 1
        sample_meta = [
            {
                "sample": i,
                "monotonic_ns": item["capture_timestamp_ns"],
                "packet_id_before": item["packet_id"],
                "packet_id_copy": item["packet_id"],
                "packet_id_after": item["packet_id"],
                "bracket_consistent": True,
            }
            for i, item in enumerate(raw_metadata)
        ]
        first_ns = raw_metadata[0]["capture_timestamp_ns"]
        last_ns = raw_metadata[-1]["capture_timestamp_ns"]
        sample_count = len(pages)
        sample_stride = RAW_RECORD.size + page_size
        bracket_inconsistent = 0
        packet_changes = sum(
            1 for a, b in zip(raw_metadata, raw_metadata[1:])
            if a["packet_id"] != b["packet_id"]
        )
        recording_format = "ACCGFX01 CRC-block .gfxraw"
    else:
        if len(data) < HEADER.size:
            raise SystemExit("Recording is shorter than its header.")
        magic, schema, page_size = HEADER.unpack_from(data)
        if magic != MAGIC:
            raise SystemExit(f"Unexpected recording magic {magic!r}.")
        if schema != 1:
            raise SystemExit(f"Unsupported recording schema: {schema}.")
        if page_size < CANDIDATE_STRUCT_SIZE:
            raise SystemExit(f"Page size {page_size} is smaller than candidate structure.")
        stride = SAMPLE.size + page_size
        payload_size = len(data) - HEADER.size
        sample_count, remainder = divmod(payload_size, stride)
        if remainder:
            raise SystemExit(
                f"Truncated/invalid diagnostic recording: {remainder} trailing bytes."
            )
        if not sample_count:
            raise SystemExit("Recording contains no samples.")
        pages = []
        sample_meta = []
        cursor = HEADER.size
        bracket_inconsistent = 0
        packet_changes = 0
        previous_packet = None
        first_ns = last_ns = None
        for index in range(sample_count):
            monotonic_ns, before, copied, after = SAMPLE.unpack_from(data, cursor)
            page = data[cursor + SAMPLE.size:cursor + stride]
            pages.append(page)
            if before != copied or copied != after:
                bracket_inconsistent += 1
            if previous_packet is not None and copied != previous_packet:
                packet_changes += 1
            previous_packet = copied
            first_ns = monotonic_ns if first_ns is None else first_ns
            last_ns = monotonic_ns
            sample_meta.append({
                "sample": index, "monotonic_ns": monotonic_ns,
                "packet_id_before": before, "packet_id_copy": copied,
                "packet_id_after": after,
                "bracket_consistent": before == copied == after,
            })
            cursor += stride
        sample_stride = stride
        recording_format = "ACCGFXR1 diagnostic full-page format"

    if page_size < CANDIDATE_STRUCT_SIZE:
        raise SystemExit("Mapping page is smaller than the 1,588-byte candidate.")

    scalar_values = {name: [] for name in SCALARS}
    for page in pages:
        for name, (offset, fmt) in SCALARS.items():
            scalar_values[name].append(decode(page, offset, fmt))

    scalars = {}
    for name, values in scalar_values.items():
        scalars[name] = scalar_summary(values)
        scalars[name]["offset_hex"] = hex(SCALARS[name][0])
        scalars[name]["type"] = "float32" if SCALARS[name][1] == "f" else "int32"
        scalars[name]["transitions"] = scalars[name]["transitions"][:args.max_transitions]

    coords = array_summary(pages, 0x100, 60 * 3, "f")
    coords["layout"] = "60 cars × (x, y, z), consecutive float32 values"
    coords["first_sample_first_10_values"] = [
        decode(pages[0], 0x100 + i * 4, "f") for i in range(10)
    ]

    car_ids = array_summary(pages, 0x3D0, 60, "i")
    car_ids["first_sample_values"] = [
        decode(pages[0], 0x3D0 + i * 4, "i") for i in range(60)
    ]

    trailing = [page[CANDIDATE_STRUCT_SIZE:] for page in pages]
    trailing_changes = sum(
        1 for a, b in zip(trailing, trailing[1:]) if a != b
    )
    trailing_nonzero_bytes = [
        sum(byte != 0 for byte in block) for block in trailing
    ]

    report = {
        "recording": str(args.recording),
        "file_size_bytes": len(data),
        "schema_version": schema,
        "recording_format": recording_format,
        "page_size_bytes": page_size,
        "candidate_structure_size_bytes": CANDIDATE_STRUCT_SIZE,
        "sample_count": sample_count,
        "sample_stride_bytes": sample_stride,
        "duration_seconds_monotonic": (
            (last_ns - first_ns) / 1_000_000_000 if sample_count > 1 else 0
        ),
        "packet_id": {
            "first": sample_meta[0]["packet_id_copy"],
            "last": sample_meta[-1]["packet_id_copy"],
            "unique_count": len({m["packet_id_copy"] for m in sample_meta}),
            "duplicate_observations": sample_count - len({m["packet_id_copy"] for m in sample_meta}),
            "changed_samples": packet_changes,
            "inconsistent_brackets": bracket_inconsistent,
        },
        "candidate_scalars": scalars,
        "car_coordinates": coords,
        "car_ids": car_ids,
        "bytes_after_candidate_1588": {
            "offset_hex": hex(CANDIDATE_STRUCT_SIZE),
            "length_bytes": page_size - CANDIDATE_STRUCT_SIZE,
            "samples_with_any_nonzero_byte": sum(n > 0 for n in trailing_nonzero_bytes),
            "nonzero_bytes_min": min(trailing_nonzero_bytes),
            "nonzero_bytes_max": max(trailing_nonzero_bytes),
            "samples_different_from_previous": trailing_changes,
            "first_sample_nonzero_ranges": [
                [start, end]
                for start, end in _nonzero_ranges(trailing[0])
            ][:50],
        },
        "notes": [
            "All offsets and field names are candidate mappings, not ABI sign-off.",
            "Packet-ID brackets are a copy-consistency heuristic, not an atomicity guarantee.",
            "The recording samples latest-state shared memory; it is not a source event queue.",
        ],
    }

    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")

    print("ACC GRAPHICS RECORDING INSPECTION")
    print(f"Format: {recording_format}")
    print(
        f"Capture: {sample_count:,} samples | {page_size:,}-byte mapping | "
        f"{report['duration_seconds_monotonic']:.1f}s"
    )
    print(
        f"Packet IDs: {report['packet_id']['unique_count']:,} unique | "
        f"{packet_changes:,} changes | "
        f"{bracket_inconsistent:,} inconsistent brackets"
    )
    print("\nCANDIDATE SCALARS")
    print(f"{'Field':<27} {'First':>12} {'Last':>12} {'Minimum':>12} {'Maximum':>12} {'Changes':>9}")
    for name, values in scalars.items():
        print(
            f"{name:<27} {str(values.get('first')):>12} "
            f"{str(values.get('last')):>12} {str(values.get('min')):>12} "
            f"{str(values.get('max')):>12} {values['transitions_total']:>9,}"
        )

    changed_coords = [
        slot for slot in coords["slots"] if slot["changed_samples"] > 0
    ]
    changed_ids = [
        slot for slot in car_ids["slots"] if slot["changed_samples"] > 0
    ]
    print(f"\nCar coordinate slots changing: {len(changed_coords)}/180")
    if changed_coords:
        print("  " + ", ".join(
            f"{slot['slot']} (range {slot['min']:.3g}..{slot['max']:.3g})"
            for slot in changed_coords[:18]
        ))
        if len(changed_coords) > 18:
            print(f"  ... {len(changed_coords) - 18} more; see JSON report")
    print(f"Car ID slots changing: {len(changed_ids)}/60")
    if changed_ids:
        print("  " + ", ".join(
            f"{slot['slot']} ({slot['first']} -> {slot['last']})"
            for slot in changed_ids[:18]
        ))
        if len(changed_ids) > 18:
            print(f"  ... {len(changed_ids) - 18} more; see JSON report")

    tail = report["bytes_after_candidate_1588"]
    print(
        f"\nBytes after candidate 1,588: {tail['length_bytes']:,} bytes | "
        f"{tail['samples_with_any_nonzero_byte']:,}/{sample_count:,} samples "
        f"contain non-zero bytes | {tail['samples_different_from_previous']:,} "
        "sample-to-sample changes"
    )
    print("\nNote: offsets and field names remain candidate mappings, not ABI sign-off.")
    if args.json_out:
        print(f"Detailed JSON saved: {args.json_out}")
    return 0

def _nonzero_ranges(data: bytes) -> list[tuple[int, int]]:
    ranges = []
    start = None
    for index, value in enumerate(data):
        if value and start is None:
            start = index
        elif not value and start is not None:
            ranges.append((start, index - 1))
            start = None
    if start is not None:
        ranges.append((start, len(data) - 1))
    return ranges

if __name__ == "__main__":
    raise SystemExit(main())
