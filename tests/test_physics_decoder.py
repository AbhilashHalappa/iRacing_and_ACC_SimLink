import math
import struct

import pytest

from src.race_engineer_acquisition.physics_decoder import (
    MIN_PHYSICS_DECODE_SIZE,
    WHEEL_ORDER,
    decode_physics,
)


def _page(size=800):
    return bytearray(size)


def _put_i(page, offset, value):
    struct.pack_into("<i", page, offset, value)


def _put_f(page, offset, value):
    struct.pack_into("<f", page, offset, value)


def _put_floats(page, offset, values):
    struct.pack_into("<" + "f" * len(values), page, offset, *values)


def test_decodes_core_driving_values_and_units():
    page = _page()
    _put_i(page, 0, 1234)
    _put_f(page, 4, 0.75)
    _put_f(page, 8, 0.2)
    _put_f(page, 12, 82.5)
    _put_i(page, 16, 4)  # ACC raw gear 4 = third
    _put_i(page, 20, 6400)
    _put_f(page, 24, -0.12)
    _put_f(page, 28, 187.25)
    _put_floats(page, 88, (27.1, 27.2, 27.3, 27.4))
    _put_floats(page, 152, (81.0, 82.0, 83.0, 84.0))
    _put_floats(page, 348, (410.0, 420.0, 390.0, 400.0))
    _put_floats(page, 640, (0.01, 0.02, 0.03, 0.04))
    _put_floats(page, 656, (-1.0, -2.0, 1.0, 2.0))
    _put_i(page, 772, 1)
    _put_i(page, 780, 1)

    decoded = decode_physics(page)

    assert decoded.packet_id == 1234
    assert decoded.throttle == pytest.approx(0.75)
    assert decoded.brake == pytest.approx(0.2)
    assert decoded.fuel_kg == pytest.approx(82.5)
    assert decoded.gear_display == "3"
    assert decoded.rpm == 6400
    assert decoded.speed_kph == pytest.approx(187.25)
    assert decoded.tyre_pressure_psi == pytest.approx((27.1, 27.2, 27.3, 27.4))
    assert decoded.brake_temp_c == pytest.approx((410, 420, 390, 400))
    assert decoded.ignition_on is True
    assert decoded.engine_running is True


def test_accepts_784_byte_payload_and_ignores_opaque_tail():
    page = _page(MIN_PHYSICS_DECODE_SIZE)
    _put_i(page, 0, 77)
    decoded = decode_physics(page)
    assert decoded.packet_id == 77
    assert len(WHEEL_ORDER) == 4


def test_rejects_short_payload():
    with pytest.raises(ValueError, match="too short"):
        decode_physics(bytes(MIN_PHYSICS_DECODE_SIZE - 1))


def test_rejects_non_finite_decoded_values():
    page = _page()
    _put_f(page, 4, math.nan)
    with pytest.raises(ValueError, match="non-finite"):
        decode_physics(page)


def test_wheel_data_uses_fl_fr_rl_rr_order():
    page = _page()
    _put_floats(page, 88, (26.0, 27.0, 28.0, 29.0))
    decoded = decode_physics(page)
    assert list(decoded.wheel_data) == ["FL", "FR", "RL", "RR"]
    assert decoded.wheel_data["RL"]["tyre_pressure_psi"] == pytest.approx(28.0)
