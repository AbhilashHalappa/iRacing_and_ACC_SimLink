from threading import Event

from src.race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from src.race_engineer_acquisition.static import StaticSnapshot
from src.race_engineer_acquisition.static_consumer import StaticDecodeConsumer
from src.race_engineer_acquisition.static_decoder import STATIC_LOGICAL_SIZE


def _snapshot(payload: bytes, sequence: int = 1) -> StaticSnapshot:
    return StaticSnapshot(
        capture_sequence=sequence,
        source_packet_id=None,
        source_timestamp_ns=None,
        read_start_ns=100,
        read_complete_ns=110,
        capture_timestamp_ns=110,
        payload=payload,
    )


def test_static_consumer_decodes_latest_page_outside_acquisition():
    page = bytearray(STATIC_LOGICAL_SIZE)
    encoded = "silverstone".encode("utf-16-le")
    page[134:134 + len(encoded)] = encoded
    page[596:600] = (1).to_bytes(4, "little", signed=True)
    ring = AcquisitionRingBuffer(4)
    consumer = StaticDecodeConsumer(ring)
    assert ring.try_put(_snapshot(bytes(page)))

    assert consumer.process_pending() == 1
    result = consumer.snapshot
    assert result.processed_count == 1
    assert result.decode_error_count == 0
    assert result.latest is not None
    assert result.latest.track == "silverstone"
    assert result.latest.is_timed_race is True
    assert result.last_capture_sequence == 1
    assert result.latest_capture_timestamp_ns == 110


def test_static_consumer_keeps_last_good_page_after_decode_error():
    page = bytearray(STATIC_LOGICAL_SIZE)
    ring = AcquisitionRingBuffer(4)
    consumer = StaticDecodeConsumer(ring)
    assert ring.try_put(_snapshot(bytes(page), 1))
    assert consumer.process_pending() == 1
    good = consumer.snapshot.latest

    assert ring.try_put(_snapshot(bytes(STATIC_LOGICAL_SIZE - 1), 2))
    assert consumer.process_pending() == 1
    result = consumer.snapshot
    assert result.processed_count == 1
    assert result.decode_error_count == 1
    assert result.latest == good
    assert result.last_capture_sequence == 2
    assert "too short" in (result.last_error or "")


def test_static_consumer_drains_pending_page_before_stopping():
    page = bytes(STATIC_LOGICAL_SIZE)
    ring = AcquisitionRingBuffer(4)
    consumer = StaticDecodeConsumer(ring)
    assert ring.try_put(_snapshot(page))
    producer_done = Event()
    producer_done.set()
    consumer.run(Event(), producer_done)
    assert consumer.snapshot.processed_count == 1
    assert consumer.snapshot.lifecycle_state == "stopped"
