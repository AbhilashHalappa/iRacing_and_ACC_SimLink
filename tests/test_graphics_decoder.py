import math
import struct
from threading import Event, Thread

import pytest

from src.race_engineer_acquisition.graphics import GraphicsSnapshot
from src.race_engineer_acquisition.graphics_consumer import GraphicsDecodeConsumer
from src.race_engineer_acquisition.graphics_decoder import decode_graphics
from src.race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def _page(packet_id=23, tc=7, abs_level=6, fuel_lap=3.25, estimated=18.5):
    page = bytearray(4096)
    struct.pack_into("<i", page, 0x000, packet_id)
    struct.pack_into("<i", page, 0x4F4, tc)
    struct.pack_into("<i", page, 0x500, abs_level)
    struct.pack_into("<f", page, 0x504, fuel_lap)
    struct.pack_into("<f", page, 0x584, estimated)
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


def test_decoder_reads_four_fields_at_candidate_offsets():
    decoded = decode_graphics(_page())
    assert decoded.packet_id == 23
    assert decoded.tc_level == 7
    assert decoded.abs_level == 6
    assert decoded.fuel_per_lap_l == pytest.approx(3.25)
    assert decoded.fuel_estimated_laps == pytest.approx(18.5)


def test_decoder_rejects_page_shorter_than_last_required_field():
    with pytest.raises(ValueError, match="too short"):
        decode_graphics(bytes(1415))


def test_decoder_does_not_return_non_finite_fuel_values():
    page = bytearray(_page())
    struct.pack_into("<f", page, 0x504, math.nan)
    struct.pack_into("<f", page, 0x584, math.inf)
    decoded = decode_graphics(page)
    assert decoded.fuel_per_lap_l is None
    assert decoded.fuel_estimated_laps is None


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
