#!/usr/bin/env python3
"""Read-only ACC Physics tail correlation probe.

Samples the 800-byte Local\\acpmf_physics mapping and records the four float32
values at offsets 784..799 alongside acceleration, suspension travel, speed,
throttle and brake. Tail channels are deliberately named neutrally: this
probe measures correlation; it does not assign semantic meanings.

Run from the repository root while ACC is running:
  python scripts/probe_acc_physics_correlations.py --label stationary --duration 60
  python scripts/probe_acc_physics_correlations.py --label smooth --duration 60
  python scripts/probe_acc_physics_correlations.py --label kerbs --duration 60

The mapping is opened with FILE_MAP_READ only. No shared-memory writes occur.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import math
import os
import statistics
import sys
import time
from pathlib import Path

MAPPING_NAME = r"Local\acpmf_physics"
MAP_READ = 0x0004
PAGE_BYTES = 800

# ACC Physics offsets used by this read-only probe.
PACKET_ID = 0
THROTTLE = 4
BRAKE = 8
SPEED_KPH = 28
ACC_G = 44                 # float32[3]
SUSPENSION_TRAVEL = 184    # float32[4]
TAIL = 784                 # float32[4]


def read_i32(buf: bytes, offset: int) -> int:
    return int.from_bytes(buf[offset:offset + 4], "little", signed=True)


def read_f32(buf: bytes, offset: int) -> float:
    return ctypes.c_float.from_buffer_copy(buf[offset:offset + 4]).value


def read_f32_array(buf: bytes, offset: int, count: int) -> list[float]:
    return [read_f32(buf, offset + i * 4) for i in range(count)]


class ReadOnlyPhysicsMap:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("This probe requires Windows and ACC Shared Memory.")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
        ]
        self.kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        self.kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_size_t
        ]
        self.kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self.kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self.kernel32.UnmapViewOfFile.restype = ctypes.c_int
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int

        self.handle = self.kernel32.OpenFileMappingW(
            MAP_READ, 0, MAPPING_NAME
        )
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.view = self.kernel32.MapViewOfFile(
            self.handle, MAP_READ, 0, 0, PAGE_BYTES
        )
        if not self.view:
            error = ctypes.get_last_error()
            self.kernel32.CloseHandle(self.handle)
            self.handle = None
            raise ctypes.WinError(error)

    def packet_id(self) -> int:
        return int(ctypes.c_int32.from_address(self.view).value)

    def copy(self) -> bytes:
        return ctypes.string_at(self.view, PAGE_BYTES)

    def close(self) -> None:
        if getattr(self, "view", None):
            self.kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if getattr(self, "handle", None):
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def finite(value: float) -> bool:
    return math.isfinite(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="Capture label, e.g. stationary, smooth, kerbs")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="Capture duration in seconds (default: 60)")
    parser.add_argument("--interval-ms", type=float, default=10.0,
                        help="Sampling interval in milliseconds (default: 10)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional CSV path; defaults to user_data/raw_recordings/")
    args = parser.parse_args()

    if args.duration <= 0 or args.interval_ms <= 0:
        parser.error("--duration and --interval-ms must be positive")

    output = args.output
    if output is None:
        output_dir = Path("user_data") / "raw_recordings"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in args.label)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        output = output_dir / f"physics-correlations-{safe_label}-{stamp}.csv"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "elapsed_s", "packet_id", "speed_kph", "throttle", "brake",
        "acc_g_x", "acc_g_y", "acc_g_z",
        "susp_travel_fl", "susp_travel_fr", "susp_travel_rl", "susp_travel_rr",
        "tail_784", "tail_788", "tail_792", "tail_796",
    ]
    rows: list[dict[str, float | int]] = []
    rejected = 0
    start = time.perf_counter()
    deadline = start + args.duration
    interval = args.interval_ms / 1000.0
    next_sample = start

    print("ACC Physics tail correlation probe — READ ONLY")
    print(f"Mapping: {MAPPING_NAME}")
    print(f"Requested view: {PAGE_BYTES} bytes")
    print(f"Label: {args.label}")
    print(f"Duration: {args.duration:.1f}s; interval: {args.interval_ms:.1f}ms")
    print(f"Output: {output}")

    mapping = ReadOnlyPhysicsMap()
    try:
        while time.perf_counter() < deadline:
            before = mapping.packet_id()
            payload = mapping.copy()
            after = mapping.packet_id()
            payload_id = read_i32(payload, PACKET_ID)

            # Best-effort torn-read rejection. ACC does not publish a formal
            # atomic snapshot guarantee; equal IDs cannot prove atomicity.
            if before != after or payload_id != before:
                rejected += 1
            else:
                acc = read_f32_array(payload, ACC_G, 3)
                susp = read_f32_array(payload, SUSPENSION_TRAVEL, 4)
                tail = read_f32_array(payload, TAIL, 4)
                scalar = [
                    read_f32(payload, SPEED_KPH),
                    read_f32(payload, THROTTLE),
                    read_f32(payload, BRAKE),
                ]
                values = scalar + acc + susp + tail
                if all(finite(v) for v in values):
                    row = {
                        "elapsed_s": time.perf_counter() - start,
                        "packet_id": payload_id,
                        "speed_kph": scalar[0],
                        "throttle": scalar[1],
                        "brake": scalar[2],
                        "acc_g_x": acc[0], "acc_g_y": acc[1], "acc_g_z": acc[2],
                        "susp_travel_fl": susp[0], "susp_travel_fr": susp[1],
                        "susp_travel_rl": susp[2], "susp_travel_rr": susp[3],
                        "tail_784": tail[0], "tail_788": tail[1],
                        "tail_792": tail[2], "tail_796": tail[3],
                    }
                    rows.append(row)
                else:
                    rejected += 1

            next_sample += interval
            delay = next_sample - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_sample = time.perf_counter()

    finally:
        mapping.close()

    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nAccepted samples: {len(rows)}")
    print(f"Rejected samples: {rejected}")
    print(f"CSV: {output}")

    if len(rows) < 3:
        print("Not enough valid samples for correlation analysis.")
        return 0

    def col(name: str) -> list[float]:
        return [float(row[name]) for row in rows]

    print("\nChannel summary (float values):")
    for name in ("tail_784", "tail_788", "tail_792", "tail_796"):
        values = col(name)
        print(
            f"  {name}: min={min(values): .6f} "
            f"median={statistics.median(values): .6f} "
            f"p95={sorted(values)[int(0.95 * (len(values) - 1))]: .6f} "
            f"max={max(values): .6f} sd={statistics.pstdev(values): .6f}"
        )

    # Absolute acceleration and per-sample absolute suspension-travel change
    # are compared to each tail channel. Correlation is descriptive only.
    predictors: dict[str, list[float]] = {
        "speed_kph": col("speed_kph"),
        "throttle": col("throttle"),
        "brake": col("brake"),
        "abs_acc_g_x": [abs(v) for v in col("acc_g_x")],
        "abs_acc_g_y": [abs(v) for v in col("acc_g_y")],
        "abs_acc_g_z": [abs(v) for v in col("acc_g_z")],
    }
    for wheel in ("fl", "fr", "rl", "rr"):
        travel = col(f"susp_travel_{wheel}")
        predictors[f"abs_susp_delta_{wheel}"] = [
            0.0 if i == 0 else abs(travel[i] - travel[i - 1])
            for i in range(len(travel))
        ]

    print("\nPearson correlation by tail channel:")
    for tail_name in ("tail_784", "tail_788", "tail_792", "tail_796"):
        tail_values = col(tail_name)
        print(f"  {tail_name}:")
        for predictor_name, predictor_values in predictors.items():
            r = pearson(tail_values, predictor_values)
            rendered = "n/a" if r is None else f"{r:+.4f}"
            print(f"    {predictor_name:22s} {rendered}")

    print("\nNote: correlation does not establish channel meaning or causation.")
    print("Packet-ID checks are best-effort torn-read rejection, not an atomic snapshot guarantee.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
