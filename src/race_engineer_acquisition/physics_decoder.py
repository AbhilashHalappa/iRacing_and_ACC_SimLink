"""Conservative decoder for the documented ACC SPageFilePhysics layout.

The decoder runs downstream of acquisition. It never touches shared memory,
allocates UI objects, or performs persistence. ACC wheel arrays are retained in
the documented FL, FR, RL, RR order. The final 16 bytes in the 800-byte
candidate page remain opaque; all decoded fields end at byte 784.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Final

MIN_PHYSICS_DECODE_SIZE: Final[int] = 784
PHYSICS_LAYOUT_SIZE: Final[int] = 800
WHEEL_ORDER: Final[tuple[str, ...]] = ("FL", "FR", "RL", "RR")


@dataclass(frozen=True, slots=True)
class DecodedPhysics:
    packet_id: int
    throttle: float
    brake: float
    fuel_kg: float
    gear_raw: int
    rpm: int
    steering_angle: float
    speed_kph: float
    velocity: tuple[float, float, float]
    acc_g: tuple[float, float, float]
    wheel_slip: tuple[float, float, float, float]
    wheel_load: tuple[float, float, float, float]
    tyre_pressure_psi: tuple[float, float, float, float]
    wheel_angular_speed: tuple[float, float, float, float]
    tyre_core_temp_c: tuple[float, float, float, float]
    suspension_travel: tuple[float, float, float, float]
    tc_level: float
    heading: float
    pitch: float
    roll: float
    car_damage: tuple[float, float, float, float, float]
    pit_limiter_on: bool
    abs_level: float
    autoshifter_on: bool
    turbo_boost: float
    air_temp_c: float
    road_temp_c: float
    local_angular_velocity: tuple[float, float, float]
    brake_temp_c: tuple[float, float, float, float]
    clutch: float
    is_ai_controlled: bool
    brake_bias: float
    local_velocity: tuple[float, float, float]
    current_max_rpm: int
    slip_ratio: tuple[float, float, float, float]
    slip_angle: tuple[float, float, float, float]
    tc_in_action: bool
    abs_in_action: bool
    suspension_damage: tuple[float, float, float, float]
    tyre_temp_c: tuple[float, float, float, float]
    water_temp_c: float
    brake_pressure: tuple[float, float, float, float]
    front_brake_compound: int
    rear_brake_compound: int
    pad_life: tuple[float, float, float, float]
    disc_life: tuple[float, float, float, float]
    ignition_on: bool
    starter_engine_on: bool
    engine_running: bool

    @property
    def gear_display(self) -> str:
        # ACC encodes R=0, N=1, first gear=2, etc.
        if self.gear_raw == 0:
            return "R"
        if self.gear_raw == 1:
            return "N"
        return str(self.gear_raw - 1)

    @property
    def wheel_data(self) -> dict[str, dict[str, float]]:
        """Return a detached FL/FR/RL/RR mapping for tile consumers."""
        fields = {
            "tyre_pressure_psi": self.tyre_pressure_psi,
            "tyre_core_temp_c": self.tyre_core_temp_c,
            "tyre_temp_c": self.tyre_temp_c,
            "slip_ratio": self.slip_ratio,
            "slip_angle": self.slip_angle,
            "brake_temp_c": self.brake_temp_c,
            "brake_pressure": self.brake_pressure,
            "suspension_damage": self.suspension_damage,
            "pad_life": self.pad_life,
            "disc_life": self.disc_life,
        }
        return {
            corner: {name: values[index] for name, values in fields.items()}
            for index, corner in enumerate(WHEEL_ORDER)
        }


def _i32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<i", payload, offset)[0]


def _f32(payload: bytes, offset: int) -> float:
    value = struct.unpack_from("<f", payload, offset)[0]
    if not math.isfinite(value):
        raise ValueError(f"non-finite ACC Physics float at byte offset {offset}")
    return float(value)


def _floats(payload: bytes, offset: int, count: int) -> tuple[float, ...]:
    return tuple(_f32(payload, offset + index * 4) for index in range(count))


def _bool(payload: bytes, offset: int) -> bool:
    return _i32(payload, offset) != 0


def decode_physics(payload: bytes | bytearray | memoryview) -> DecodedPhysics:
    """Decode verified ACC Physics fields from a 784-byte-or-larger page.

    Bytes 784 onward are deliberately ignored. A short or non-finite payload
    fails closed, allowing the consumer to retain its previous good sample.
    """
    page = bytes(payload)
    if len(page) < MIN_PHYSICS_DECODE_SIZE:
        raise ValueError(
            f"ACC Physics page too short: {len(page)} < {MIN_PHYSICS_DECODE_SIZE}"
        )

    return DecodedPhysics(
        packet_id=_i32(page, 0),
        throttle=_f32(page, 4),
        brake=_f32(page, 8),
        fuel_kg=_f32(page, 12),
        gear_raw=_i32(page, 16),
        rpm=_i32(page, 20),
        steering_angle=_f32(page, 24),
        speed_kph=_f32(page, 28),
        velocity=_floats(page, 32, 3),
        acc_g=_floats(page, 44, 3),
        wheel_slip=_floats(page, 56, 4),
        wheel_load=_floats(page, 72, 4),
        tyre_pressure_psi=_floats(page, 88, 4),
        wheel_angular_speed=_floats(page, 104, 4),
        tyre_core_temp_c=_floats(page, 152, 4),
        suspension_travel=_floats(page, 184, 4),
        tc_level=_f32(page, 204),
        heading=_f32(page, 208),
        pitch=_f32(page, 212),
        roll=_f32(page, 216),
        car_damage=_floats(page, 224, 5),
        pit_limiter_on=_bool(page, 248),
        abs_level=_f32(page, 252),
        autoshifter_on=_bool(page, 264),
        turbo_boost=_f32(page, 276),
        air_temp_c=_f32(page, 288),
        road_temp_c=_f32(page, 292),
        local_angular_velocity=_floats(page, 296, 3),
        brake_temp_c=_floats(page, 348, 4),
        clutch=_f32(page, 364),
        is_ai_controlled=_bool(page, 416),
        brake_bias=_f32(page, 564),
        local_velocity=_floats(page, 568, 3),
        current_max_rpm=_i32(page, 588),
        slip_ratio=_floats(page, 640, 4),
        slip_angle=_floats(page, 656, 4),
        tc_in_action=_bool(page, 672),
        abs_in_action=_bool(page, 676),
        suspension_damage=_floats(page, 680, 4),
        tyre_temp_c=_floats(page, 696, 4),
        water_temp_c=_f32(page, 712),
        brake_pressure=_floats(page, 716, 4),
        front_brake_compound=_i32(page, 732),
        rear_brake_compound=_i32(page, 736),
        pad_life=_floats(page, 740, 4),
        disc_life=_floats(page, 756, 4),
        ignition_on=_bool(page, 772),
        starter_engine_on=_bool(page, 776),
        engine_running=_bool(page, 780),
    )
