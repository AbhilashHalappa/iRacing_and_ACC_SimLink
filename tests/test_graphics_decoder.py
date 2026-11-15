import math
import struct
from threading import Event, Thread

import pytest

from src.race_engineer_acquisition.graphics import GraphicsSnapshot
from src.race_engineer_acquisition.graphics_consumer import GraphicsDecodeConsumer
from src.race_engineer_acquisition.graphics_decoder import decode_graphics
from src.race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def _wide(page, offset, value, units):
    encoded = value.encode("utf-16-le")[: units * 2]
    page[offset:offset + units * 2] = encoded.ljust(units * 2, b"\x00")


def _page(packet_id=23, tc=7, abs_level=6, fuel_lap=3.25, estimated=18.5):
    page = bytearray(4096)
    struct.pack_into("<i", page, 0x000, packet_id)
    struct.pack_into("<i", page, 0x004, 2)
    struct.pack_into("<i", page, 0x008, 0)
    _wide(page, 0x00C, "01:24.500", 15)
    _wide(page, 0x02A, "01:25.000", 15)
    _wide(page, 0x048, "01:24.000", 15)
    _wide(page, 0x066, "00:28.000", 15)
    struct.pack_into("<i", page, 0x084, 4)
    struct.pack_into("<i", page, 0x088, 2)
    struct.pack_into("<i", page, 0x08C, 84500)
    struct.pack_into("<i", page, 0x090, 85000)
    struct.pack_into("<i", page, 0x094, 84000)
    struct.pack_into("<f", page, 0x098, 1200.0)
    struct.pack_into("<f", page, 0x0A0, 0.0)
    struct.pack_into("<i", page, 0x0A4, 1)
    struct.pack_into("<i", page, 0x0A8, 28000)
    struct.pack_into("<i", page, 0x0AC, 20)
    _wide(page, 0x0B0, "dry_compound", 33)
    struct.pack_into("<f", page, 0x0F8, 0.42)
    struct.pack_into("<i", page, 0x0FC, 1)
    struct.pack_into("<fff", page, 0x100, 1.0, 2.0, 3.0)
    struct.pack_into("<i", page, 0x3D0, 77)
    struct.pack_into("<i", page, 0x4C0, 77)
    struct.pack_into("<f", page, 0x4C4, 0.0)
    struct.pack_into("<i", page, 0x4C8, 0)
    struct.pack_into("<i", page, 0x4CC, 0)
    struct.pack_into("<i", page, 0x4D4, 1)
    struct.pack_into("<f", page, 0x4D8, 0.98)
    struct.pack_into("<f", page, 0x4E0, 2.5)
    struct.pack_into("<f", page, 0x4E4, 1.2)
    struct.pack_into("<i", page, 0x4F4, tc)
    struct.pack_into("<i", page, 0x4F8, 3)
    struct.pack_into("<i", page, 0x4FC, 2)
    struct.pack_into("<i", page, 0x500, abs_level)
    struct.pack_into("<f", page, 0x504, fuel_lap)
    struct.pack_into("<i", page, 0x508, 1)
    struct.pack_into("<i", page, 0x50C, 0)
    struct.pack_into("<i", page, 0x510, 2)
    struct.pack_into("<f", page, 0x514, 650.0)
    struct.pack_into("<i", page, 0x518, 3)
    struct.pack_into("<i", page, 0x51C, 3600000)
    struct.pack_into("<i", page, 0x520, 1200000)
    struct.pack_into("<i", page, 0x524, 0)
    struct.pack_into("<f", page, 0x52C, 12.5)
    _wide(page, 0x530, "+0.250", 15)
    struct.pack_into("<i", page, 0x550, 250)
    _wide(page, 0x554, "01:24.250", 15)
    struct.pack_into("<i", page, 0x574, 84250)
    struct.pack_into("<i", page, 0x578, 0)
    struct.pack_into("<i", page, 0x57C, 28000)
    struct.pack_into("<i", page, 0x580, 1)
    struct.pack_into("<f", page, 0x584, estimated)
    _wide(page, 0x588, "1", 33)
    struct.pack_into("<f", page, 0x5D0, 15.5)
    struct.pack_into("<i", page, 0x5D4, 1)
    struct.pack_into("<i", page, 0x5D8, 0)
    struct.pack_into("<i", page, 0x5DC, 1)
    struct.pack_into("<i", page, 0x5F0, 1)
    struct.pack_into("<i", page, 0x5FC, 2)
    struct.pack_into("<f", page, 0x600, 25.0)
    struct.pack_into("<ffff", page, 0x604, 26.0, 26.1, 26.2, 26.3)
    struct.pack_into("<i", page, 0x614, 2)
    struct.pack_into("<iii", page, 0x618, 1, 2, 3)
    struct.pack_into("<iiii", page, 0x624, 4, 5, 1500, 1800)
    return bytes(page)


def _snapshot(sequence, packet_id, payload):
    return GraphicsSnapshot(
        capture_sequence=sequence,
        acc_graphics_packet_id=packet_id,
        read_start_ns=sequence * 100,
        read_complete_ns=sequence * 100 + 10,
        capture_timestamp_ns=sequence * 100 + 10,
        payload=payload,
    )


def test_decoder_reads_priority_and_session_fields_at_candidate_offsets():
    decoded = decode_graphics(_page())
    assert decoded.packet_id == 23
    assert decoded.tc_level == 7
    assert decoded.abs_level == 6
    assert decoded.fuel_per_lap_l == pytest.approx(3.25)
    assert decoded.fuel_estimated_laps == pytest.approx(18.5)
    assert decoded.current_time_str == "01:24.500"
    assert decoded.last_time_str == "01:25.000"
    assert decoded.best_time_str == "01:24.000"
    assert decoded.completed_laps == 4
    assert decoded.session_time_left_ms == pytest.approx(1200.0)
    assert decoded.position == 2
    assert decoded.is_in_pit_lane is True
    assert decoded.tyre_compound == "dry_compound"
    assert decoded.normalized_car_position == pytest.approx(0.42)
    assert decoded.player_world_position == pytest.approx((1.0, 2.0, 3.0))
    assert decoded.rain_lights is True
    assert decoded.wiper_level == 3
    assert decoded.delta_lap_time_str == "+0.250"
    assert decoded.track_status == "1"
    assert decoded.mfd_tyre_pressures == pytest.approx((26.0, 26.1, 26.2, 26.3))
    assert decoded.gap_ahead_ms == 1500
    assert decoded.gap_behind_ms == 1800


def test_decoder_bounds_active_car_arrays_and_preserves_reported_count():
    page = bytearray(_page())
    struct.pack_into("<i", page, 0x0FC, 1000)
    decoded = decode_graphics(page)
    assert decoded.active_cars == 1000
    assert len(decoded.car_ids) == 60
    assert len(decoded.car_coordinates) == 60


def test_decoder_rejects_page_shorter_than_complete_candidate_layout():
    with pytest.raises(ValueError, match="too short"):
        decode_graphics(bytes(1587))


def test_decoder_does_not_return_non_finite_float_values():
    page = bytearray(_page())
    struct.pack_into("<f", page, 0x504, math.nan)
    struct.pack_into("<f", page, 0x584, math.inf)
    struct.pack_into("<f", page, 0x4D8, math.nan)
    decoded = decode_graphics(page)
    assert decoded.fuel_per_lap_l is None
    assert decoded.fuel_estimated_laps is None
    assert decoded.surface_grip is None


def test_consumer_publishes_latest_and_checks_packet_id():
    ring = AcquisitionRingBuffer(8)
    consumer = GraphicsDecodeConsumer(ring)
    assert ring.try_put(_snapshot(1, 23, _page()))
    assert consumer.process_pending() == 1
    state = consumer.snapshot
    assert state.processed_count == 1
    assert state.decode_error_count == 0
    assert state.latest is not None
    assert state.latest.tc_level == 7
    assert state.latest.abs_level == 6
    payload = state.to_payload()
    assert payload["stream"] == "graphics"
    assert payload["data"]["fuel_per_lap_l"] == pytest.approx(3.25)
    assert payload["data"]["wiper_level"] == 3


def test_consumer_keeps_last_good_sample_after_packet_mismatch():
    ring = AcquisitionRingBuffer(8)
    consumer = GraphicsDecodeConsumer(ring)
    assert ring.try_put(_snapshot(1, 23, _page()))
    assert ring.try_put(_snapshot(2, 24, _page(packet_id=23, tc=8)))
    assert consumer.process_pending() == 2
    state = consumer.snapshot
    assert state.processed_count == 1
    assert state.decode_error_count == 1
    assert state.latest is not None and state.latest.tc_level == 7
    assert "does not match" in (state.last_error or "")


def test_worker_drains_final_graphics_samples():
    ring = AcquisitionRingBuffer(4)
    consumer = GraphicsDecodeConsumer(ring)
    stop_event, producer_done = Event(), Event()
    worker = Thread(target=consumer.run, args=(stop_event, producer_done))
    worker.start()
    assert ring.try_put(_snapshot(1, 23, _page()))
    producer_done.set()
    stop_event.set()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert consumer.snapshot.processed_count == 1
    assert consumer.snapshot.latest is not None
    assert consumer.snapshot.latest.packet_id == 23
