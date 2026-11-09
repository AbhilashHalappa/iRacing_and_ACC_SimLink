#!/usr/bin/env python3
"""Decode the same ACC Graphics .gfxraw recording independently using the
RaceIQ and Pro Engineer candidate layouts.

This is an offline comparison only. It does not connect to ACC and does not
promote either third-party layout to an official ACC 1.9 ABI.
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

RAW_HEADER = struct.Struct("<8sIIQI")
RAW_BLOCK = struct.Struct("<4sQIII")
RAW_RECORD = struct.Struct("<QQQQQI")
RAW_MAGIC = b"ACCGFX01"
BLOCK_MAGIC = b"GFXB"
EXPECTED_PAGE_SIZE = 4096
MIN_STRUCT_SIZE = 1588

# RaceIQ's executable descriptors. Fields only mentioned in comments are
# deliberately not silently promoted to executable descriptors.
RACEIQ_FIELDS: dict[str, tuple[int, str]] = {
    "status": (4, "i"),
    "session": (8, "i"),
    "completed_laps": (132, "i"),
    "position": (136, "i"),
    "current_time_ms": (140, "i"),
    "last_time_ms": (144, "i"),
    "best_time_ms": (148, "i"),
    "last_sector_time_ms": (168, "i"),
    "normalized_car_position": (248, "f"),
    "active_cars": (252, "i"),
    "main_display_index_dash": (1260, "i"),
    "tc": (1268, "i"),
    "tc_cut": (1272, "i"),
    "engine_map": (1276, "i"),
    "abs": (1280, "i"),
    "fuel_per_lap": (1284, "f"),
    "rain_tyres": (1316, "i"),
    "session_index": (1320, "i"),
    "used_fuel": (1324, "f"),
    "delta_lap_time_ms": (1360, "i"),
    "estimated_lap_time_ms": (1396, "i"),
    "is_delta_positive": (1400, "i"),
    "split_time_ms": (1404, "i"),
    "is_valid_lap": (1408, "i"),
    "fuel_estimated_laps": (1412, "f"),
    "missing_mandatory_pits": (1484, "i"),
    "clock_seconds": (1488, "f"),
}

# Pro Engineer's explicit AccGraphics field sequence. The overlapping
# offsets intentionally remain independently declared here.
PRO_ENGINEER_FIELDS: dict[str, tuple[int, str]] = {
    "status": (4, "i"),
    "session": (8, "i"),
    "completed_laps": (132, "i"),
    "position": (136, "i"),
    "current_time_ms": (140, "i"),
    "last_time_ms": (144, "i"),
    "best_time_ms": (148, "i"),
    "last_sector_time_ms": (168, "i"),
    "normalized_car_position": (248, "f"),
    "active_cars": (252, "i"),
    "is_in_pit": (160, "i"),
    "current_sector_index": (164, "i"),
    "is_in_pit_lane": (1236, "i"),
    "main_display_index_dash": (1260, "i"),
    "secondary_display_index_racelogic": (1264, "i"),
    "tc": (1268, "i"),
    "tc_cut": (1272, "i"),
    "engine_map": (1276, "i"),
    "abs": (1280, "i"),
    "fuel_per_lap": (1284, "f"),
    "rain_lights": (1288, "i"),
    "flashing_lights": (1292, "i"),
    "lights_stage": (1296, "i"),
    "exhaust_temperature": (1300, "f"),
    "wiper_stage": (1304, "i"),
    "driver_stint_total_time_left": (1308, "i"),
    "driver_stint_time_left": (1312, "i"),
    "rain_tyres": (1316, "i"),
    "session_index": (1320, "i"),
    "used_fuel": (1324, "f"),
    "delta_lap_time_ms": (1360, "i"),
    "estimated_lap_time_ms": (1396, "i"),
    "is_delta_positive": (1400, "i"),
    "split_time_ms": (1404, "i"),
    "is_valid_lap": (1408, "i"),
    "fuel_estimated_laps": (1412, "f"),
    "missing_mandatory_pits": (1484, "i"),
    "clock_seconds": (1488, "f"),
    "direction_lights_left": (1492, "i"),
    "direction_lights_right": (1496, "i"),
    "global_yellow": (1500, "i"),
    "global_yellow_1": (1504, "i"),
    "global_yellow_2": (1508, "i"),
    "global_yellow_3": (1512, "i"),
    "global_white": (1516, "i"),
    "global_green": (1520, "i"),
    "global_chequered": (1524, "i"),
    "global_red": (1528, "i"),
    "mfd_tyre_set": (1532, "i"),
    "mfd_fuel_to_add": (1536, "f"),
    "mfd_tyre_pressure_lf": (1540, "f"),
    "mfd_tyre_pressure_rf": (1544, "f"),
    "mfd_tyre_pressure_lr": (1548, "f"),
    "mfd_tyre_pressure_rr": (1552, "f"),
    "track_grip_status": (1556, "i"),
    "rain_intensity": (1560, "i"),
    "rain_intensity_in_10min": (1564, "i"),
    "rain_intensity_in_30min": (1568, "i"),
    "current_tyre_set": (1572, "i"),
    "strategy_tyre_set": (1576, "i"),
    "gap_ahead_ms": (1580, "i"),
    "gap_behind_ms": (1584, "i"),
}

# RaceIQ comments document these offsets but do not expose them as descriptors.
RACEIQ_COMMENTED_FIELDS: dict[str, tuple[int, str]] = {
    "rain_lights": (1288, "i"),
    "flashing_lights": (1292, "i"),
    "lights_stage": (1296, "i"),
    "exhaust_temperature": (1300, "f"),
    "wiper_stage": (1304, "i"),
    "secondary_display_index_racelogic": (1264, "i"),
}


def read_recording(path: Path) -> tuple[int, list[bytes]]:
    data = path.read_bytes()
    if len(data) < RAW_HEADER.size:
        raise ValueError("Recording header is incomplete.")
    magic, version, page_size, _created_ns, header_crc = RAW_HEADER.unpack_from(data)
    if magic != RAW_MAGIC or version != 1:
        raise ValueError("Unsupported recording format; expected ACCGFX01 v1.")
    if zlib.crc32(data[:RAW_HEADER.size - 4]) != header_crc:
        raise ValueError("Header CRC mismatch.")
    if page_size < MIN_STRUCT_SIZE:
        raise ValueError(f"Page size {page_size} is smaller than 1,588 bytes.")

    pages: list[bytes] = []
    cursor = RAW_HEADER.size
    expected_block = 1
    expected_record = 1
    while cursor < len(data):
        if len(data) - cursor < RAW_BLOCK.size:
            raise ValueError("Truncated block header.")
        magic_b, block_seq, count, payload_len, checksum = RAW_BLOCK.unpack_from(data, cursor)
        cursor += RAW_BLOCK.size
        if magic_b != BLOCK_MAGIC or block_seq != expected_block or count <= 0:
            raise ValueError(f"Invalid block header at block {expected_block}.")
        end = cursor + payload_len
        if end > len(data):
            raise ValueError(f"Truncated block {block_seq}.")
        payload = data[cursor:end]
        if zlib.crc32(payload) != checksum:
            raise ValueError(f"CRC mismatch in block {block_seq}.")
        inner = 0
        for _ in range(count):
            if len(payload) - inner < RAW_RECORD.size:
                raise ValueError(f"Truncated record in block {block_seq}.")
            seq, packet, _start, _complete, _captured, size = RAW_RECORD.unpack_from(payload, inner)
            inner += RAW_RECORD.size
            if seq != expected_record or size != page_size or inner + size > len(payload):
                raise ValueError(f"Invalid record {seq} in block {block_seq}.")
            page = payload[inner:inner + size]
            inner += size
            if struct.unpack_from("<i", page, 0)[0] != packet:
                raise ValueError(f"Packet ID mismatch in record {seq}.")
            pages.append(page)
            expected_record += 1
        if inner != len(payload):
            raise ValueError(f"Unexpected trailing payload in block {block_seq}.")
        cursor = end
        expected_block += 1
    if not pages:
        raise ValueError("Recording contains no samples.")
    return page_size, pages


def unpack(page: bytes, spec: tuple[int, str]) -> int | float:
    offset, fmt = spec
    return struct.unpack_from("<" + fmt, page, offset)[0]


def summarize(pages: list[bytes], fields: dict[str, tuple[int, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, spec in fields.items():
        values = [unpack(page, spec) for page in pages]
        finite = [v for v in values if not isinstance(v, float) or math.isfinite(v)]
        result[name] = {
            "offset": spec[0],
            "offset_hex": hex(spec[0]),
            "type": "float32" if spec[1] == "f" else "int32",
            "first": values[0],
            "last": values[-1],
            "min": min(finite) if finite else None,
            "max": max(finite) if finite else None,
            "unique_count": len(set(values)),
            "most_common": Counter(values).most_common(8),
            "transitions": sum(a != b for a, b in zip(values, values[1:])),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    reports = []
    for recording in args.recordings:
        page_size, pages = read_recording(recording)
        raceiq = summarize(pages, RACEIQ_FIELDS)
        raceiq_comments = summarize(pages, RACEIQ_COMMENTED_FIELDS)
        pro = summarize(pages, PRO_ENGINEER_FIELDS)
        shared_names = sorted(set(raceiq) & set(pro))
        shared_comparison = {
            name: {
                "raceiq_offset": raceiq[name]["offset"],
                "pro_engineer_offset": pro[name]["offset"],
                "offsets_agree": raceiq[name]["offset"] == pro[name]["offset"],
                "values_agree": (
                    raceiq[name]["first"] == pro[name]["first"]
                    and raceiq[name]["last"] == pro[name]["last"]
                    and raceiq[name]["min"] == pro[name]["min"]
                    and raceiq[name]["max"] == pro[name]["max"]
                ),
            }
            for name in shared_names
        }
        reports.append({
            "recording": str(recording),
            "page_size_bytes": page_size,
            "sample_count": len(pages),
            "raceiq": raceiq,
            "raceiq_comment_only": raceiq_comments,
            "pro_engineer": pro,
            "shared_field_comparison": shared_comparison,
            "notes": [
                "RaceIQ and Pro Engineer are decoded independently from their own field maps.",
                "Matching offsets and values do not constitute independent empirical confirmation when both implementations derive from the same ACC SDK layout.",
                "RaceIQ comment-only fields are kept separate from its executable descriptors.",
                "Brake Bias, Pit Limiter, Ignition and Starter are Physics-page fields, not Graphics-page fields.",
                "ACC final setup values supplied by the user are not assumed to describe the exact instant of either historical recording.",
            ],
        })

    rendered = json.dumps({"reports": reports}, indent=2, allow_nan=False)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")

    for report in reports:
        print(f"\n{report['recording']}")
        print(f"Samples: {report['sample_count']:,} | mapping: {report['page_size_bytes']:,} bytes")
        print("\nFIELD                         RACEIQ (last / range)          PRO ENGINEER (last / range)")
        target_names = [
            "tc", "tc_cut", "engine_map", "abs", "rain_lights",
            "flashing_lights", "lights_stage", "wiper_stage",
            "direction_lights_left", "direction_lights_right",
            "main_display_index_dash", "secondary_display_index_racelogic",
        ]
        names = target_names
        for name in names:
            a = report["raceiq"].get(name) or report["raceiq_comment_only"].get(name)
            b = report["pro_engineer"].get(name)
            left = f"{a['last']} / {a['min']}..{a['max']}" if a else "not exposed"
            right = f"{b['last']} / {b['min']}..{b['max']}" if b else "not declared"
            print(f"{name:<29} {left:<30} {right}")
    if args.json_out:
        print(f"\nDetailed JSON: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
