#!/usr/bin/env python3
"""Offline inspector for ACC Graphics full-page recordings.

This tool reads the diagnostic format emitted by probe_acc_graphics.py:
  file header: <8sII  (magic, schema version, page size)
  each sample: <Qiii  (monotonic_ns, packet_id_before, packet_id_copy,
                       packet_id_after), followed by one complete page.

It does not connect to ACC, decode application state, or modify the recording.
All offsets are candidate offsets and remain subject to ABI sign-off.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any

HEADER = struct.Struct("<8sII")
SAMPLE = struct.Struct("<Qiii")
MAGIC = b"ACCGFXR1"
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

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="*.graphics-recording.bin file")
    parser.add_argument("--json-out", type=Path, help="optional JSON report path")
    parser.add_argument("--max-transitions", type=int, default=30)
    args = parser.parse_args()

    data = args.recording.read_bytes()
    if len(data) < HEADER.size:
        raise SystemExit("Recording is shorter than its header.")

    magic, schema, page_size = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise SystemExit(f"Unexpected magic {magic!r}; expected {MAGIC!r}.")
    if schema != 1:
        raise SystemExit(f"Unsupported recording schema: {schema}.")
    if page_size < CANDIDATE_STRUCT_SIZE:
        raise SystemExit(f"Page size {page_size} is smaller than candidate structure.")

    stride = SAMPLE.size + page_size
    payload_size = len(data) - HEADER.size
    sample_count, remainder = divmod(payload_size, stride)
    if remainder:
        raise SystemExit(
            f"Truncated/invalid recording: {remainder} trailing bytes after "
            f"{sample_count} complete samples."
        )
    if not sample_count:
        raise SystemExit("Recording contains no samples.")

    scalar_values = {name: [] for name in SCALARS}
    pages: list[bytes] = []
    bracket_inconsistent = 0
    packet_changes = 0
    previous_packet = None
    first_ns = last_ns = None
    sample_meta = []

    cursor = HEADER.size
    for index in range(sample_count):
        monotonic_ns, before, copied, after = SAMPLE.unpack_from(data, cursor)
        page_start = cursor + SAMPLE.size
        page = data[page_start:page_start + page_size]
        pages.append(page)
        if before != copied or copied != after:
            bracket_inconsistent += 1
        if previous_packet is not None and copied != previous_packet:
            packet_changes += 1
        previous_packet = copied
        first_ns = monotonic_ns if first_ns is None else first_ns
        last_ns = monotonic_ns
        sample_meta.append({
            "sample": index,
            "monotonic_ns": monotonic_ns,
            "packet_id_before": before,
            "packet_id_copy": copied,
            "packet_id_after": after,
            "bracket_consistent": before == copied == after,
        })
        for name, (offset, fmt) in SCALARS.items():
            scalar_values[name].append(decode(page, offset, fmt))
        cursor += stride

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
        "page_size_bytes": page_size,
        "sample_count": sample_count,
        "sample_stride_bytes": stride,
        "duration_seconds_monotonic": (
            (last_ns - first_ns) / 1_000_000_000 if sample_count > 1 else 0
        ),
        "packet_id": {
            "first": sample_meta[0]["packet_id_copy"],
            "last": sample_meta[-1]["packet_id_copy"],
            "unique_count": len({m["packet_id_copy"] for m in sample_meta}),
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
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
        print(f"\nJSON report written to: {args.json_out}")
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
