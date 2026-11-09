"""Conservative decoder for the live-qualified ACC Static 1.9 candidate.

Variant B (33 UTF-16 code units for TrackConfiguration) is selected from
target-PC evidence. This is not an official Kunos ABI declaration. Only fields
with coherent reference definitions and/or live values are exposed. Unknown,
deprecated, and unresolved fields remain available in the untouched raw page.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


STATIC_LAYOUT_VARIANT_B = "acc-static-v1.9-candidate-b"
STATIC_LOGICAL_SIZE = 820


@dataclass(frozen=True, slots=True)
class DecodedStatic:
    layout_id: str
    sm_version: str
    ac_version: str
    car_model: str
    track: str
    player_name: str
    player_surname: str
    player_nick: str
    num_cars: int
    sector_count: int
    max_rpm: int
    max_fuel: float
    penalties_enabled: bool
    aid_fuel_rate: float
    aid_tire_rate: float
    aid_mechanical_damage: float
    aid_stability: float
    auto_clutch: bool
    auto_blip: bool
    track_configuration: str
    ers_max_j: float
    is_timed_race: bool
    has_extra_lap: bool
    car_skin: str
    reversed_grid_positions: int
    is_online: bool
    dry_tyres_name: str
    wet_tyres_name: str


def _read_string(page: bytes, offset: int, code_units: int) -> str:
    end = offset + code_units * 2
    if offset < 0 or end > len(page):
        raise ValueError(f"Static string at offset {offset} exceeds page")
    raw = page[offset:end]
    # ACC strings are fixed-width UTF-16LE; stop at the first NUL code unit.
    terminator = next(
        (index for index in range(0, len(raw), 2) if raw[index:index + 2] == b"\x00\x00"),
        len(raw),
    )
    return raw[:terminator].decode("utf-16-le", errors="strict")


def _i32(page: bytes, offset: int) -> int:
    return struct.unpack_from("<i", page, offset)[0]


def _f32(page: bytes, offset: int) -> float:
    return struct.unpack_from("<f", page, offset)[0]


def _boolean(page: bytes, offset: int, name: str) -> bool:
    value = _i32(page, offset)
    if value not in (0, 1):
        raise ValueError(f"Unsupported {name} value in Static page: {value}")
    return bool(value)


def decode_static_candidate_b(page: bytes) -> DecodedStatic:
    """Decode qualified fields using candidate B offsets; preserve raw page separately."""
    if len(page) < STATIC_LOGICAL_SIZE:
        raise ValueError(
            f"ACC Static page too short for candidate B: {len(page)} < {STATIC_LOGICAL_SIZE}"
        )

    return DecodedStatic(
        layout_id=STATIC_LAYOUT_VARIANT_B,
        sm_version=_read_string(page, 0, 15),
        ac_version=_read_string(page, 30, 15),
        car_model=_read_string(page, 68, 33),
        track=_read_string(page, 134, 33),
        player_name=_read_string(page, 200, 33),
        player_surname=_read_string(page, 266, 33),
        player_nick=_read_string(page, 332, 33),
        num_cars=_i32(page, 64),
        sector_count=_i32(page, 400),
        max_rpm=_i32(page, 412),
        max_fuel=_f32(page, 416),
        penalties_enabled=_boolean(page, 464, "PenaltiesEnabled"),
        aid_fuel_rate=_f32(page, 468),
        aid_tire_rate=_f32(page, 472),
        aid_mechanical_damage=_f32(page, 476),
        aid_stability=_f32(page, 484),
        auto_clutch=_boolean(page, 488, "AidAutoClutch"),
        auto_blip=_boolean(page, 492, "AidAutoBlip"),
        track_configuration=_read_string(page, 524, 33),
        ers_max_j=_f32(page, 592),
        is_timed_race=_boolean(page, 596, "IsTimedRace"),
        has_extra_lap=_boolean(page, 600, "HasExtraLap"),
        car_skin=_read_string(page, 604, 33),
        reversed_grid_positions=_i32(page, 672),
        is_online=_boolean(page, 684, "IsOnline"),
        dry_tyres_name=_read_string(page, 688, 33),
        wet_tyres_name=_read_string(page, 754, 33),
    )
