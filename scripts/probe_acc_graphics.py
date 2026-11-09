"""Read-only diagnostic probe and full-page recorder for ACC Graphics.

This is an ABI investigation utility, not the production acquisition path.
The default mode samples packet_id and saves one final page. The optional
full-page mode records every sampled mapping page with timing and packet-ID
bracketing so field transitions can be inspected offline.

The recorder does not decode fields or write to ACC shared memory.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

GRAPHICS_MAP = r"Local\acpmf_graphics"
FILE_MAP_READ = 0x0004
SECTION_QUERY = 0x0001
CANDIDATE_V1812_SIZE = 1588

RECORD_MAGIC = b"ACCGFXR1"
RECORD_SCHEMA_VERSION = 1
RECORD_FILE_HEADER = struct.Struct("<8sII")
SAMPLE_HEADER = struct.Struct("<Qiii")


class _SectionBasicInformation(ctypes.Structure):
    _fields_ = [
        ("base_address", ctypes.c_void_p),
        ("allocation_attributes", ctypes.c_ulong),
        ("maximum_size", ctypes.c_longlong),
    ]


class _WindowsGraphicsMapping:
    def __init__(self, name: str = GRAPHICS_MAP) -> None:
        if os.name != "nt":
            raise OSError("ACC Graphics shared memory requires Windows")

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ntdll = ctypes.WinDLL("ntdll")

        self._kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
        ]
        self._kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        self._kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_size_t
        ]
        self._kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self._kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self._kernel32.UnmapViewOfFile.restype = ctypes.c_int
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_int

        self._ntdll.NtQuerySection.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
        ]
        self._ntdll.NtQuerySection.restype = ctypes.c_long

        # SECTION_QUERY | SECTION_MAP_READ. The handle itself is never writable.
        self._handle = self._kernel32.OpenFileMappingW(
            SECTION_QUERY | FILE_MAP_READ, 0, name
        )
        if not self._handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"Cannot open {name}. Is ACC running?")

        self._view = None
        try:
            info = _SectionBasicInformation()
            returned = ctypes.c_ulong()
            status = self._ntdll.NtQuerySection(
                self._handle, 0, ctypes.byref(info),
                ctypes.sizeof(info), ctypes.byref(returned)
            )
            if status < 0:
                raise OSError(
                    f"NtQuerySection failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}"
                )
            self.size = int(info.maximum_size)
            if self.size < 4:
                raise ValueError(f"Unexpected Graphics mapping size: {self.size}")

            self._view = self._kernel32.MapViewOfFile(
                self._handle, FILE_MAP_READ, 0, 0, 0
            )
            if not self._view:
                error = ctypes.get_last_error()
                raise OSError(error, f"Cannot map {name}")
        except Exception:
            self.close()
            raise

    def read_packet_id(self) -> int:
        if not self._view:
            raise OSError("Graphics shared-memory view is closed")
        return int(ctypes.c_int32.from_address(self._view).value)

    def copy_complete_mapping(self) -> bytes:
        if not self._view:
            raise OSError("Graphics shared-memory view is closed")
        return ctypes.string_at(self._view, self.size)

    def close(self) -> None:
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=5.0)
    parser.add_argument("--sample-interval-ms", type=float, default=10.0)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("user_data/raw_recordings")
    )
    parser.add_argument(
        "--record-full-pages",
        action="store_true",
        help=(
            "Record every complete Graphics mapping page and a CSV sample index. "
            "Ctrl+C stops early and finalizes the files."
        ),
    )
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.sample_interval_ms <= 0:
        parser.error("duration and sample interval must be positive")
    return args


def record_full_pages(
    mapping: _WindowsGraphicsMapping,
    raw_path: Path,
    index_path: Path,
    duration_seconds: float,
    sample_interval_ms: float,
) -> dict[str, int | float | bool]:
    """Record fixed-size page samples; Ctrl+C is handled as a clean early stop."""
    interval_seconds = sample_interval_ms / 1000.0
    deadline = time.perf_counter() + duration_seconds
    next_sample_at = time.perf_counter()
    sample_count = 0
    packet_ids: list[int] = []
    packet_id_changes = 0
    inconsistent_brackets = 0
    interrupted = False

    with raw_path.open("wb") as raw_file, index_path.open(
        "w", newline="", encoding="utf-8"
    ) as index_file:
        raw_file.write(
            RECORD_FILE_HEADER.pack(
                RECORD_MAGIC, RECORD_SCHEMA_VERSION, mapping.size
            )
        )
        writer = csv.writer(index_file)
        writer.writerow(
            [
                "sample_index",
                "monotonic_ns",
                "packet_id_before_copy",
                "packet_id_in_copied_page",
                "packet_id_after_copy",
                "packet_ids_match",
            ]
        )

        try:
            while time.perf_counter() < deadline:
                monotonic_ns = time.perf_counter_ns()
                packet_before = mapping.read_packet_id()
                payload = mapping.copy_complete_mapping()
                packet_in_payload = struct.unpack_from("<i", payload, 0)[0]
                packet_after = mapping.read_packet_id()

                raw_file.write(
                    SAMPLE_HEADER.pack(
                        monotonic_ns,
                        packet_before,
                        packet_in_payload,
                        packet_after,
                    )
                )
                raw_file.write(payload)

                packet_ids.append(packet_in_payload)
                if sample_count and packet_in_payload != packet_ids[-2]:
                    packet_id_changes += 1
                bracket_matches = (
                    packet_before == packet_in_payload == packet_after
                )
                if not bracket_matches:
                    inconsistent_brackets += 1
                writer.writerow(
                    [
                        sample_count,
                        monotonic_ns,
                        packet_before,
                        packet_in_payload,
                        packet_after,
                        int(bracket_matches),
                    ]
                )
                sample_count += 1

                if sample_count % 100 == 0:
                    raw_file.flush()
                    index_file.flush()

                next_sample_at += interval_seconds
                sleep_seconds = next_sample_at - time.perf_counter()
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            raw_file.flush()
            index_file.flush()

    unique_packet_ids = len(set(packet_ids))
    return {
        "sample_count": sample_count,
        "packet_id_first": packet_ids[0] if packet_ids else 0,
        "packet_id_last": packet_ids[-1] if packet_ids else 0,
        "packet_id_unique_count": unique_packet_ids,
        "packet_id_change_count": packet_id_changes,
        "inconsistent_packet_id_bracket_count": inconsistent_brackets,
        "interrupted_by_user": interrupted,
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(timezone.utc)
    prefix = "acc_graphics_full_lap" if args.record_full_pages else "acc_graphics_probe"
    stem = started_utc.strftime(f"{prefix}_%Y%m%dT%H%M%S_%fZ")

    mapping = _WindowsGraphicsMapping()
    try:
        if args.record_full_pages:
            raw_path = args.output_dir / f"{stem}.graphics-recording.bin"
            index_path = args.output_dir / f"{stem}.samples.csv"
            report_path = args.output_dir / f"{stem}.json"
            capture_started = time.perf_counter()
            stats = record_full_pages(
                mapping,
                raw_path,
                index_path,
                args.duration_seconds,
                args.sample_interval_ms,
            )
            elapsed_seconds = time.perf_counter() - capture_started
            report = {
                "schema_version": 1,
                "page": "graphics",
                "recording_mode": "full_page_samples",
                "mapping_name": GRAPHICS_MAP,
                "started_at_utc": started_utc.isoformat(),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "requested_duration_seconds": args.duration_seconds,
                "actual_duration_seconds": elapsed_seconds,
                "sample_interval_ms": args.sample_interval_ms,
                "mapping_allocation_size_bytes": mapping.size,
                "candidate_v1_8_12_graphics_structure_size_bytes": CANDIDATE_V1812_SIZE,
                "record_magic_ascii": RECORD_MAGIC.decode("ascii"),
                "record_schema_version": RECORD_SCHEMA_VERSION,
                "record_file_header_format": "<8sII (magic, schema_version, page_size)",
                "sample_header_format": (
                    "<Qiii (monotonic_ns, packet_id_before_copy, "
                    "packet_id_in_copied_page, packet_id_after_copy)"
                ),
                "sample_header_size_bytes": SAMPLE_HEADER.size,
                "raw_file": raw_path.name,
                "index_file": index_path.name,
                **stats,
                "interpretation": (
                    "Each record stores a monotonic timestamp, packet IDs read "
                    "before and after the page copy, the packet ID embedded in "
                    "the copied page, and the complete mapped page. Matching "
                    "bracket IDs are a consistency heuristic, not an atomicity "
                    "guarantee. ACC shared memory remains a latest-state "
                    "interface; this recorder cannot guarantee zero source-level "
                    "packet loss. The 1,588-byte structure size remains a "
                    "v1.8.12-derived candidate, not a verified Shared Memory 1.9 ABI."
                ),
            }
            report_path.write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, indent=2))
            print(f"Raw recording: {raw_path}")
            print(f"Sample index:  {index_path}")
            print(f"Report:        {report_path}")
        else:
            sample_ids: list[int] = []
            deadline = time.perf_counter() + args.duration_seconds
            interval = args.sample_interval_ms / 1000.0
            while time.perf_counter() < deadline:
                sample_ids.append(mapping.read_packet_id())
                time.sleep(interval)

            payload = mapping.copy_complete_mapping()
            packet_before = struct.unpack_from("<i", payload, 0)[0]
            raw_path = args.output_dir / f"{stem}.graphics-page.bin"
            report_path = args.output_dir / f"{stem}.json"
            raw_path.write_bytes(payload)

            unique_ids = sorted(set(sample_ids))
            changes = sum(
                1 for previous, current in zip(sample_ids, sample_ids[1:])
                if current != previous
            )
            report = {
                "schema_version": 1,
                "page": "graphics",
                "mapping_name": GRAPHICS_MAP,
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "probe_duration_seconds": args.duration_seconds,
                "sample_interval_ms": args.sample_interval_ms,
                "packet_id_sample_count": len(sample_ids),
                "packet_id_first": sample_ids[0] if sample_ids else None,
                "packet_id_last": sample_ids[-1] if sample_ids else None,
                "packet_id_unique_count": len(unique_ids),
                "packet_id_change_count": changes,
                "packet_id_at_raw_copy": packet_before,
                "mapping_allocation_size_bytes": len(payload),
                "candidate_v1_8_12_graphics_structure_size_bytes": CANDIDATE_V1812_SIZE,
                "raw_payload_size_bytes": len(payload),
                "raw_file": raw_path.name,
                "interpretation": (
                    "The queried mapping allocation size may be page-rounded "
                    "and is not proof of the logical C structure size. The raw "
                    "file preserves the entire mapped section. The 1,588-byte "
                    "value is only the current v1.8.12-derived candidate pending "
                    "Shared Memory 1.9 verification."
                ),
            }
            report_path.write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, indent=2))
            print(f"Raw page: {raw_path}")
            print(f"Report:   {report_path}")
    finally:
        mapping.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
