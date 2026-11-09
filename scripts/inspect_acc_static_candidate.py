"""Inspect candidate ACC Static layouts without modifying shared memory.

Prints a compact decoded view of the common prefix and both competing tail
layouts (15- and 33-code-unit TrackConfiguration). This is diagnostic only;
it does not promote either candidate into the production decoder.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.static import WindowsACCStaticSource  # noqa: E402


def u16_string(data: bytes, offset: int, count: int) -> str:
    raw = data[offset : offset + count * 2]
    if len(raw) != count * 2:
        return "<out-of-range>"
    try:
        return raw.decode("utf-16-le", errors="replace").split("\\0", 1)[0]
    except Exception as exc:
        return f"<decode-error:{type(exc).__name__}>"


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def show_common(data: bytes) -> None:
    strings = [
        ("SMVersion", 0, 15), ("ACVersion", 30, 15),
        ("CarModel", 68, 33), ("Track", 134, 33),
        ("PlayerName", 200, 33), ("PlayerSurname", 266, 33),
        ("PlayerNick", 332, 33),
    ]
    for name, offset, count in strings:
        print(f"{name}@{offset}={u16_string(data, offset, count)!r}")

    ints = [("NumberOfSessions", 60), ("NumCars", 64), ("SectorCount", 400),
            ("MaxRPM", 412), ("PenaltiesEnabled", 464),
            ("AidAutoClutch", 488), ("AidAutoBlip", 492)]
    for name, offset in ints:
        print(f"{name}@{offset}={i32(data, offset)}")

    floats = [("MaxTorque", 404), ("MaxPower", 408), ("MaxFuel", 416),
              ("MaxTurboBoost", 452), ("AidFuelRate", 468),
              ("AidTireRate", 472), ("AidMechanicalDamage", 476),
              ("AidStability", 484)]
    for name, offset in floats:
        print(f"{name}@{offset}={f32(data, offset):.6g}")

    raw = data[480:484]
    print(f"AidAllowTyreBlankets@480 raw={raw.hex()} "
          f"as_float={struct.unpack('<f', raw)[0]:.6g} as_int={struct.unpack('<i', raw)[0]}")


def show_tail(data: bytes, label: str, track_chars: int, offsets: dict[str, int]) -> None:
    print(f"--- TAIL {label} (TrackConfiguration[{track_chars}]) ---")
    print(f"TrackConfiguration@524={u16_string(data, 524, track_chars)!r}")
    print(f"ERSMaxJ@{offsets['ers']}={f32(data, offsets['ers']):.6g}")
    print(f"IsTimedRace@{offsets['timed']}={i32(data, offsets['timed'])}")
    print(f"HasExtraLap@{offsets['extra']}={i32(data, offsets['extra'])}")
    print(f"CarSkin@{offsets['skin']}={u16_string(data, offsets['skin'], 33)!r}")
    print(f"ReversedGridPositions@{offsets['grid']}={i32(data, offsets['grid'])}")
    print(f"PitWindowStart@{offsets['pit_start']}={i32(data, offsets['pit_start'])}")
    print(f"PitWindowEnd@{offsets['pit_end']}={i32(data, offsets['pit_end'])}")
    print(f"IsOnline@{offsets['online']}={i32(data, offsets['online'])}")
    print(f"DryTyresName@{offsets['dry']}={u16_string(data, offsets['dry'], 33)!r}")
    print(f"WetTyresName@{offsets['wet']}={u16_string(data, offsets['wet'], 33)!r}")


def main() -> int:
    source = WindowsACCStaticSource()
    try:
        raw = source.read_static().payload
    finally:
        source.close()

    print("ACC STATIC CANDIDATE INSPECTION (read-only; not a validated decoder)")
    print(f"mapping_bytes={len(raw)}")
    print("source_packet_id=None source_timestamp_ns=None")
    show_common(raw)
    show_tail(raw, "A", 15, {
        "ers": 556, "timed": 560, "extra": 564, "skin": 568,
        "grid": 636, "pit_start": 640, "pit_end": 644,
        "online": 648, "dry": 652, "wet": 718,
    })
    show_tail(raw, "B", 33, {
        "ers": 592, "timed": 596, "extra": 600, "skin": 604,
        "grid": 672, "pit_start": 676, "pit_end": 680,
        "online": 684, "dry": 688, "wet": 754,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
