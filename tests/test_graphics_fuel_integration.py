"""End-to-end tests for ACC Graphics fuel fields through Stage 2 consumers.

These tests exercise the existing Graphics ring/decoder/consumer path and the
Race Engineer's freshness-aware fuel adapter. They do not access raw shared
memory or alter Stage 1 acquisition.
"""
from __future__ import annotations

import math
import struct

import pytest
from types import SimpleNamespace

from src.race_engineer_acquisition.fuel_engineer import build_fuel_engineer_snapshot
from src.race_engineer_acquisition.graphics import GraphicsSnapshot
from src.race_engineer_acquisition.graphics_consumer import GraphicsDecodeConsumer
from src.race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def _graphics_page(
    packet_id: int, *, fuel_per_lap: float, fuel_estimated_laps: float
) -> bytes:
    page = bytearray(4096)
    struct.pack_into("<i", page, 0x000, packet_id)
    struct.pack_into("<i", page, 0x004, 2)  # ACC LIVE
    struct.pack_into("<f", page, 0x504, fuel_per_lap)
    struct.pack_into("<f", page, 0x584, fuel_estimated_laps)
    return bytes(page)


def _publish_graphics(
    ring: AcquisitionRingBuffer,
    consumer: GraphicsDecodeConsumer,
    *,
    sequence: int,
    fuel_per_lap: float,
    fuel_estimated_laps: float,
):
    timestamp_ns = sequence * 1_000_000
    snapshot = GraphicsSnapshot(
        capture_sequence=sequence,
        acc_graphics_packet_id=sequence,
        read_start_ns=timestamp_ns - 100,
        read_complete_ns=timestamp_ns,
        capture_timestamp_ns=timestamp_ns,
        payload=_graphics_page(
            sequence,
            fuel_per_lap=fuel_per_lap,
            fuel_estimated_laps=fuel_estimated_laps,
        ),
    )
    assert ring.try_put(snapshot)
    assert consumer.process_pending() == 1
    return consumer.snapshot.latest


def _fuel_snapshot(graphics_data, *, current_fuel: float, graphics_fresh=True):
    telemetry = SimpleNamespace(
        physics=SimpleNamespace(
            is_fresh=True,
            data=SimpleNamespace(fuel_kg=current_fuel),
        ),
        graphics=SimpleNamespace(
            is_fresh=graphics_fresh,
            data=graphics_data if graphics_fresh else None,
        ),
    )
    return build_fuel_engineer_snapshot(telemetry)


def test_acc_graphics_fuel_fields_reach_race_engineer_without_recalculation():
    ring = AcquisitionRingBuffer(8)
    consumer = GraphicsDecodeConsumer(ring)

    decoded = _publish_graphics(
        ring,
        consumer,
        sequence=1,
        fuel_per_lap=2.72,
        fuel_estimated_laps=4.3,
    )
    result = _fuel_snapshot(decoded, current_fuel=11.8)

    assert result.acc_fuel_per_lap_l == pytest.approx(2.72)
    assert result.acc_fuel_laps_remaining == pytest.approx(4.3)
    assert result.current_fuel_l == 11.8
    assert result.fuel_per_lap_fresh is True
    assert result.fuel_laps_fresh is True


def test_graphics_fuel_values_update_after_refuelling_without_physics_fallback():
    ring = AcquisitionRingBuffer(8)
    consumer = GraphicsDecodeConsumer(ring)

    before = _publish_graphics(
        ring,
        consumer,
        sequence=1,
        fuel_per_lap=2.72,
        fuel_estimated_laps=4.3,
    )
    before_result = _fuel_snapshot(before, current_fuel=11.8)

    after = _publish_graphics(
        ring,
        consumer,
        sequence=2,
        fuel_per_lap=2.72,
        fuel_estimated_laps=21.2,
    )
    after_result = _fuel_snapshot(after, current_fuel=57.8)

    assert before_result.acc_fuel_laps_remaining == pytest.approx(4.3)
    assert after_result.acc_fuel_laps_remaining == pytest.approx(21.2)
    assert after_result.acc_fuel_per_lap_l == pytest.approx(2.72)
    assert before_result.current_fuel_l == 11.8
    assert after_result.current_fuel_l == 57.8


def test_stale_graphics_keeps_physics_fuel_but_hides_graphics_strategy_values():
    ring = AcquisitionRingBuffer(4)
    consumer = GraphicsDecodeConsumer(ring)
    decoded = _publish_graphics(
        ring,
        consumer,
        sequence=1,
        fuel_per_lap=2.72,
        fuel_estimated_laps=4.3,
    )

    result = _fuel_snapshot(decoded, current_fuel=31.0, graphics_fresh=False)

    assert result.current_fuel_l == 31.0
    assert result.current_fuel_fresh is True
    assert result.acc_fuel_per_lap_l is None
    assert result.acc_fuel_laps_remaining is None
    assert result.fuel_per_lap_fresh is False
    assert result.fuel_laps_fresh is False
    assert result.graphics_fresh is False


def test_non_finite_graphics_values_are_neutral_not_estimated():
    ring = AcquisitionRingBuffer(4)
    consumer = GraphicsDecodeConsumer(ring)
    decoded = _publish_graphics(
        ring,
        consumer,
        sequence=1,
        fuel_per_lap=math.nan,
        fuel_estimated_laps=math.inf,
    )

    result = _fuel_snapshot(decoded, current_fuel=31.0)

    assert decoded.fuel_per_lap_l is None
    assert decoded.fuel_estimated_laps is None
    assert result.acc_fuel_per_lap_l is None
    assert result.acc_fuel_laps_remaining is None
    assert result.fuel_per_lap_fresh is False
    assert result.fuel_laps_fresh is False
