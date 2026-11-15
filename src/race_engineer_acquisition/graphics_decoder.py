"""Conservative downstream decoder for the ACC Graphics candidate page.

The field order/offsets are the 1,588-byte v1.8.12-derived candidate cross-
checked against pinned RaceIQ and Pro Engineer layouts. This is not official
Kunos Shared Memory 1.9 ABI certification. Raw 4,096-byte acquisition remains
unchanged; uncertain enum meanings and sentinel values are preserved raw.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

GRAPHICS_CANDIDATE_SIZE = 1588
GRAPHICS_REQUIRED_SIZE = GRAPHICS_CANDIDATE_SIZE

PACKET_ID_OFFSET = 0x000
TC_LEVEL_OFFSET = 0x4F4
ABS_LEVEL_OFFSET = 0x500
FUEL_PER_LAP_OFFSET = 0x504
FUEL_ESTIMATED_LAPS_OFFSET = 0x584
CAR_COORDINATES_OFFSET = 0x100
CAR_IDS_OFFSET = 0x3D0


@dataclass(frozen=True, slots=True)
class DecodedGraphics:
    packet_id: int
    status: int
    session: int
    current_time_str: str
    last_time_str: str
    best_time_str: str
    split_time_str: str
    completed_laps: int
    position: int
    current_time_ms: int
    last_time_ms: int
    best_time_ms: int
    session_time_left_ms: float | None
    distance_traveled_m: float | None
    is_in_pit: bool
    sector: int
    last_sector_time_ms: int
    number_of_laps: int
    tyre_compound: str
    normalized_car_position: float | None
    active_cars: int
    car_ids: tuple[int, ...]
    car_coordinates: tuple[tuple[float | None, float | None, float | None], ...]
    player_car_id: int
    player_world_position: tuple[float | None, float | None, float | None] | None
    penalty_time_s: float | None
    flag: int
    penalty: int
    ideal_line_on: bool
    is_in_pit_lane: bool
    surface_grip: float | None
    mandatory_pit_done: bool
    wind_speed: float | None
    wind_direction: float | None
    setup_menu_visible: bool
    main_display_index: int
    secondary_display_index: int
    tc_level: int
    tc_cut: int
    engine_map: int
    abs_level: int
    fuel_per_lap_l: float | None
    rain_lights: bool
    flashing_lights: bool
    lights_stage: int
    exhaust_temp_c: float | None
    wiper_level: int
    driver_stint_total_ms: int
    driver_stint_left_ms: int
    rain_tyres: bool
    session_index: int
    used_fuel_l: float | None
    delta_lap_time_str: str
    delta_lap_time_ms: int
    estimated_lap_time_str: str
    estimated_lap_time_ms: int
    delta_positive: bool
    split_ms: int
    is_valid_lap: bool
    fuel_estimated_laps: float | None
    track_status: str
    missing_mandatory_pits: int
    clock_s: float | None
    direction_left: bool
    direction_right: bool
    global_yellow: bool
    global_yellow_1: bool
    global_yellow_2: bool
    global_yellow_3: bool
    global_white: bool
    global_green: bool
    global_chequered: bool
    global_red: bool
    mfd_tyre_set: int
    mfd_fuel_to_add: float | None
    mfd_tyre_pressures: tuple[float | None, float | None, float | None, float | None]
    track_grip_status: int
    rain_intensity: int
    rain_10min: int
    rain_30min: int
    current_tyre_set: int
    strategy_tyre_set: int
    gap_ahead_ms: int
    gap_behind_ms: int


def _i32(payload: memoryview, offset: int) -> int:
    return struct.unpack_from("<i", payload, offset)[0]


def _finite_float(payload: memoryview, offset: int) -> float | None:
    value = struct.unpack_from("<f", payload, offset)[0]
    return value if math.isfinite(value) else None


def _read_wide(payload: memoryview, offset: int, code_units: int) -> str:
    raw = bytes(payload[offset:offset + code_units * 2])
    if len(raw) != code_units * 2:
        raise ValueError(f"ACC Graphics string at {offset:#x} exceeds page")
    raw = raw[:next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\x00\x00"), len(raw))]
    return raw.decode("utf-16-le", errors="replace").strip()


def _bool(payload: memoryview, offset: int) -> bool:
    return _i32(payload, offset) != 0


def _float_array(payload: memoryview, offset: int, count: int) -> tuple[float | None, ...]:
    return tuple(_finite_float(payload, offset + index * 4) for index in range(count))


def decode_graphics(payload: bytes | bytearray | memoryview) -> DecodedGraphics:
    """Decode candidate Graphics fields without enum remapping or sentinel guessing."""
    view = memoryview(payload)
    if view.nbytes < GRAPHICS_REQUIRED_SIZE:
        raise ValueError(
            "ACC Graphics payload is too short for the complete candidate page: "
            f"{view.nbytes} < {GRAPHICS_REQUIRED_SIZE}"
        )

    active_cars_raw = _i32(view, 0x0FC)
    active_cars = max(0, min(60, active_cars_raw))
    coordinates = tuple(
        tuple(_finite_float(view, CAR_COORDINATES_OFFSET + (car * 3 + axis) * 4) for axis in range(3))
        for car in range(active_cars)
    )
    car_ids = tuple(_i32(view, CAR_IDS_OFFSET + car * 4) for car in range(active_cars))
    player_car_id = _i32(view, 0x4C0)
    player_position = coordinates[car_ids.index(player_car_id)] if player_car_id in car_ids else None

    return DecodedGraphics(
        packet_id=_i32(view, 0x000),
        status=_i32(view, 0x004),
        session=_i32(view, 0x008),
        current_time_str=_read_wide(view, 0x00C, 15),
        last_time_str=_read_wide(view, 0x02A, 15),
        best_time_str=_read_wide(view, 0x048, 15),
        split_time_str=_read_wide(view, 0x066, 15),
        completed_laps=_i32(view, 0x084),
        position=_i32(view, 0x088),
        current_time_ms=_i32(view, 0x08C),
        last_time_ms=_i32(view, 0x090),
        best_time_ms=_i32(view, 0x094),
        session_time_left_ms=_finite_float(view, 0x098),
        distance_traveled_m=_finite_float(view, 0x09C),
        is_in_pit=_bool(view, 0x0A0),
        sector=_i32(view, 0x0A4),
        last_sector_time_ms=_i32(view, 0x0A8),
        number_of_laps=_i32(view, 0x0AC),
        tyre_compound=_read_wide(view, 0x0B0, 33),
        normalized_car_position=_finite_float(view, 0x0F8),
        active_cars=active_cars_raw,
        car_ids=car_ids,
        car_coordinates=coordinates,
        player_car_id=player_car_id,
        player_world_position=player_position,
        penalty_time_s=_finite_float(view, 0x4C4),
        flag=_i32(view, 0x4C8),
        penalty=_i32(view, 0x4CC),
        ideal_line_on=_bool(view, 0x4D0),
        is_in_pit_lane=_bool(view, 0x4D4),
        surface_grip=_finite_float(view, 0x4D8),
        mandatory_pit_done=_bool(view, 0x4DC),
        wind_speed=_finite_float(view, 0x4E0),
        wind_direction=_finite_float(view, 0x4E4),
        setup_menu_visible=_bool(view, 0x4E8),
        main_display_index=_i32(view, 0x4EC),
        secondary_display_index=_i32(view, 0x4F0),
        tc_level=_i32(view, TC_LEVEL_OFFSET),
        tc_cut=_i32(view, 0x4F8),
        engine_map=_i32(view, 0x4FC),
        abs_level=_i32(view, ABS_LEVEL_OFFSET),
        fuel_per_lap_l=_finite_float(view, FUEL_PER_LAP_OFFSET),
        rain_lights=_bool(view, 0x508),
        flashing_lights=_bool(view, 0x50C),
        lights_stage=_i32(view, 0x510),
        exhaust_temp_c=_finite_float(view, 0x514),
        wiper_level=_i32(view, 0x518),
        driver_stint_total_ms=_i32(view, 0x51C),
        driver_stint_left_ms=_i32(view, 0x520),
        rain_tyres=_bool(view, 0x524),
        session_index=_i32(view, 0x528),
        used_fuel_l=_finite_float(view, 0x52C),
        delta_lap_time_str=_read_wide(view, 0x530, 15),
        delta_lap_time_ms=_i32(view, 0x550),
        estimated_lap_time_str=_read_wide(view, 0x554, 15),
        estimated_lap_time_ms=_i32(view, 0x574),
        delta_positive=_bool(view, 0x578),
        split_ms=_i32(view, 0x57C),
        is_valid_lap=_bool(view, 0x580),
        fuel_estimated_laps=_finite_float(view, FUEL_ESTIMATED_LAPS_OFFSET),
        track_status=_read_wide(view, 0x588, 33),
        missing_mandatory_pits=_i32(view, 0x5CC),
        clock_s=_finite_float(view, 0x5D0),
        direction_left=_bool(view, 0x5D4),
        direction_right=_bool(view, 0x5D8),
        global_yellow=_bool(view, 0x5DC),
        global_yellow_1=_bool(view, 0x5E0),
        global_yellow_2=_bool(view, 0x5E4),
        global_yellow_3=_bool(view, 0x5E8),
        global_white=_bool(view, 0x5EC),
        global_green=_bool(view, 0x5F0),
        global_chequered=_bool(view, 0x5F4),
        global_red=_bool(view, 0x5F8),
        mfd_tyre_set=_i32(view, 0x5FC),
        mfd_fuel_to_add=_finite_float(view, 0x600),
        mfd_tyre_pressures=_float_array(view, 0x604, 4),
        track_grip_status=_i32(view, 0x614),
        rain_intensity=_i32(view, 0x618),
        rain_10min=_i32(view, 0x61C),
        rain_30min=_i32(view, 0x620),
        current_tyre_set=_i32(view, 0x624),
        strategy_tyre_set=_i32(view, 0x628),
        gap_ahead_ms=_i32(view, 0x62C),
        gap_behind_ms=_i32(view, 0x630),
    )
