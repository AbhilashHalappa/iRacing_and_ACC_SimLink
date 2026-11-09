"""Read-only diagnostic probe for ACC Graphics shared memory.

This is an ABI investigation utility, not the production acquisition path.
It records one complete mapped-section byte copy and samples packet_id to
confirm that the Graphics mapping is present and updating.
"""
from __future__ import annotations

import argparse
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
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.sample_interval_ms <= 0:
        parser.error("duration and sample interval must be positive")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(timezone.utc)
    stem = started_utc.strftime("acc_graphics_probe_%Y%m%dT%H%M%S_%fZ")
    raw_path = args.output_dir / f"{stem}.graphics-page.bin"
    report_path = args.output_dir / f"{stem}.json"

    mapping = _WindowsGraphicsMapping()
    try:
        sample_ids: list[int] = []
        deadline = time.perf_counter() + args.duration_seconds
        interval = args.sample_interval_ms / 1000.0
        while time.perf_counter() < deadline:
            sample_ids.append(mapping.read_packet_id())
            time.sleep(interval)

        # One complete copy of the mapped section; no field decoding or writes
        # occur in a persistent/high-priority acquisition thread.
        payload = mapping.copy_complete_mapping()
        packet_before = struct.unpack_from("<i", payload, 0)[0]
        raw_path.write_bytes(payload)
    finally:
        mapping.close()

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
            "The queried mapping allocation size may be page-rounded and is not "
            "proof of the logical C structure size. The raw file preserves the "
            "entire mapped section. The 1,588-byte value is only the current "
            "v1.8.12-derived candidate pending Shared Memory 1.9 verification."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Raw page: {raw_path}")
    print(f"Report:   {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
