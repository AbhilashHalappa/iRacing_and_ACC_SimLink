"""Offline inspection of recorded ACC Physics pages.

This module is deliberately downstream of acquisition. It reads completed
.accraw files and interprets their payloads using the audited ctypes layout.
It is not imported by the acquisition loop.
"""
from __future__ import annotations

import csv
import json
import math
import struct
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .acc_windows import PHYSICS_SIZE, _Physics

_FILE_MAGIC = b"ACCPHY01"
_FILE_VERSION = 1
_FILE_HEADER = struct.Struct("<8sIIQI")
_BLOCK_MAGIC = b"PHBK"
_BLOCK_HEADER = struct.Struct("<4sQIII")
_RECORD_HEADER = struct.Struct("<QQQQQI")


def read_raw_payloads(path: str | Path) -> tuple[int, list[tuple[int, bytes]]]:
    """Read every complete CRC-valid snapshot without modifying the file."""
    recording = Path(path)
    samples: list[tuple[int, bytes]] = []
    with recording.open("rb") as stream:
        header = stream.read(_FILE_HEADER.size)
        if len(header) != _FILE_HEADER.size:
            raise ValueError("Recording header is incomplete")
        magic, version, payload_size, _created_ns, checksum = _FILE_HEADER.unpack(header)
        if magic != _FILE_MAGIC or version != _FILE_VERSION:
            raise ValueError("Unsupported raw Physics recording format")
        if zlib.crc32(header[:-4]) != checksum:
            raise ValueError("Recording header checksum mismatch")
        if payload_size != PHYSICS_SIZE:
            raise ValueError(
                f"Recording payload size {payload_size} does not match current "
                f"Physics layout size {PHYSICS_SIZE}"
            )

        expected_block = 1
        last_capture_sequence = 0
        while True:
            block_header = stream.read(_BLOCK_HEADER.size)
            if not block_header:
                break
            if len(block_header) != _BLOCK_HEADER.size:
                raise ValueError("Incomplete block header at end of recording")
            block_magic, block_sequence, count, payload_length, block_crc = (
                _BLOCK_HEADER.unpack(block_header)
            )
            if block_magic != _BLOCK_MAGIC or block_sequence != expected_block or count <= 0:
                raise ValueError(f"Invalid block header at block {expected_block}")
            block = stream.read(payload_length)
            if len(block) != payload_length:
                raise ValueError(f"Incomplete payload in block {block_sequence}")
            if zlib.crc32(block) != block_crc:
                raise ValueError(f"Checksum mismatch in block {block_sequence}")

            offset = 0
            for _ in range(count):
                if len(block) - offset < _RECORD_HEADER.size:
                    raise ValueError(f"Truncated record header in block {block_sequence}")
                sequence, _packet_id, _started, _completed, _captured, size = (
                    _RECORD_HEADER.unpack_from(block, offset)
                )
                offset += _RECORD_HEADER.size
                end = offset + size
                if size != payload_size or end > len(block):
                    raise ValueError(f"Invalid payload size in block {block_sequence}")
                if sequence <= last_capture_sequence:
                    raise ValueError("Capture sequence is not strictly increasing")
                samples.append((sequence, block[offset:end]))
                last_capture_sequence = sequence
                offset = end
            if offset != len(block):
                raise ValueError(f"Unexpected trailing bytes in block {block_sequence}")
            expected_block += 1

    if not samples:
        raise ValueError("Recording contains no snapshots")
    return payload_size, samples


def inspect_recording(path: str | Path) -> dict[str, Any]:
    """Summarize observed values for every scalar and array component."""
    payload_size, samples = read_raw_payloads(path)
    accumulators: dict[str, dict[str, Any]] = {}
    field_specs = _Physics._fields_

    for field_name, field_type, *array_length in field_specs:
        length = array_length[0] if array_length else 1
        for component in range(length):
            key = field_name if length == 1 else f"{field_name}[{component}]"
            accumulators[key] = {
                "field": field_name,
                "component": component if length > 1 else None,
                "sample_count": 0,
                "finite_count": 0,
                "non_finite_count": 0,
                "zero_count": 0,
                "nonzero_count": 0,
                "minimum": None,
                "maximum": None,
                "first_value": None,
                "last_value": None,
                "_unique": set(),
            }

    for _sequence, payload in samples:
        page = _Physics.from_buffer_copy(payload)
        for field_name, field_type, *array_length in field_specs:
            value = getattr(page, field_name)
            values = list(value) if array_length else [value]
            for component, raw_value in enumerate(values):
                key = field_name if not array_length else f"{field_name}[{component}]"
                row = accumulators[key]
                number = float(raw_value)
                row["sample_count"] += 1
                if not math.isfinite(number):
                    row["non_finite_count"] += 1
                    continue
                row["finite_count"] += 1
                row["zero_count"] += number == 0.0
                row["nonzero_count"] += number != 0.0
                if row["first_value"] is None:
                    row["first_value"] = number
                row["last_value"] = number
                row["minimum"] = number if row["minimum"] is None else min(row["minimum"], number)
                row["maximum"] = number if row["maximum"] is None else max(row["maximum"], number)
                if len(row["_unique"]) < 4096:
                    row["_unique"].add(number)

    fields = []
    for key, row in accumulators.items():
        unique = row.pop("_unique")
        row["name"] = key
        row["unique_values_observed"] = len(unique)
        row["observed_behavior"] = (
            "no_finite_values" if row["finite_count"] == 0
            else "varies" if row["minimum"] != row["maximum"]
            else "constant"
        )
        fields.append(row)

    return {
        "recording": str(Path(path)),
        "payload_size_bytes": payload_size,
        "snapshot_count": len(samples),
        "first_capture_sequence": samples[0][0],
        "last_capture_sequence": samples[-1][0],
        "field_component_count": len(fields),
        "interpretation": (
            "Observed variation is descriptive only. It does not prove a field's "
            "meaning or correctness; correlate with a controlled ACC action."
        ),
        "fields": fields,
    }


def write_inspection_outputs(report: dict[str, Any], json_path: str | Path,
                             csv_path: str | Path | None = None) -> None:
    json_target = Path(json_path)
    json_target.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if csv_path is not None:
        with Path(csv_path).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "name", "field", "component", "sample_count", "finite_count",
                "non_finite_count", "zero_count", "nonzero_count", "minimum",
                "maximum", "first_value", "last_value", "unique_values_observed",
                "observed_behavior",
            ])
            writer.writeheader()
            writer.writerows(report["fields"])
