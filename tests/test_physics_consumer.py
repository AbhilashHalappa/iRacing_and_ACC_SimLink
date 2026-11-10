import struct
from threading import Event, Thread

from src.race_engineer_acquisition.models import PhysicsSnapshot
from src.race_engineer_acquisition.physics_consumer import PhysicsDecodeConsumer
from src.race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def _snapshot(sequence: int, packet_id: int, *, size: int = 800) -> PhysicsSnapshot:
    page = bytearray(size)
    struct.pack_into("<i", page, 0, packet_id)
    struct.pack_into("<f", page, 4, 0.5)
    struct.pack_into("<f", page, 8, 0.1)
    struct.pack_into("<f", page, 28, 123.0)
    return PhysicsSnapshot(
        capture_sequence=sequence,
        acc_physics_packet_id=packet_id,
        read_start_ns=sequence * 100,
        read_complete_ns=sequence * 100 + 10,
        capture_timestamp_ns=sequence * 100 + 10,
        payload=bytes(page),
    )


def test_consumer_decodes_ring_samples_and_publishes_latest():
    ring = AcquisitionRingBuffer[PhysicsSnapshot](8)
    consumer = PhysicsDecodeConsumer(ring)
    assert ring.try_put(_snapshot(1, 10))
    assert ring.try_put(_snapshot(2, 11))

    assert consumer.process_pending() == 2
    state = consumer.snapshot
    assert state.lifecycle_state == "idle"
    assert state.processed_count == 2
    assert state.decode_error_count == 0
    assert state.last_capture_sequence == 2
    assert state.latest is not None
    assert state.latest.packet_id == 11
    assert state.latest.speed_kph == 123.0
    assert state.latest_capture_timestamp_ns == 210


def test_consumer_keeps_last_good_sample_when_decode_fails():
    ring = AcquisitionRingBuffer[PhysicsSnapshot](8)
    consumer = PhysicsDecodeConsumer(ring)
    assert ring.try_put(_snapshot(1, 10))
    bad = _snapshot(2, 999)
    # Payload packet ID does not match the acquisition metadata.
    assert ring.try_put(PhysicsSnapshot(
        capture_sequence=bad.capture_sequence,
        acc_physics_packet_id=1000,
        read_start_ns=bad.read_start_ns,
        read_complete_ns=bad.read_complete_ns,
        capture_timestamp_ns=bad.capture_timestamp_ns,
        payload=bad.payload,
    ))

    assert consumer.process_pending() == 2
    state = consumer.snapshot
    assert state.processed_count == 1
    assert state.decode_error_count == 1
    assert state.latest is not None
    assert state.latest.packet_id == 10
    assert "does not match" in (state.last_error or "")


def test_consumer_payload_is_json_compatible_and_labels_wheel_order():
    ring = AcquisitionRingBuffer[PhysicsSnapshot](2)
    consumer = PhysicsDecodeConsumer(ring)
    assert ring.try_put(_snapshot(1, 10))
    consumer.process_pending()

    payload = consumer.snapshot.to_payload()
    assert payload["stream"] == "physics"
    assert payload["data"]["gear_display"] == "R"
    assert payload["data"]["wheel_order"] == ["FL", "FR", "RL", "RR"]
    assert payload["data"]["wheels"]["FL"]["tyre_pressure_psi"] == 0.0



def test_worker_drains_final_samples_after_producer_stops():
    ring = AcquisitionRingBuffer[PhysicsSnapshot](4)
    consumer = PhysicsDecodeConsumer(ring)
    stop_event = Event()
    producer_done = Event()
    worker = Thread(target=consumer.run, args=(stop_event, producer_done))
    worker.start()

    assert ring.try_put(_snapshot(1, 20))
    producer_done.set()
    stop_event.set()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert consumer.snapshot.processed_count == 1
    assert consumer.snapshot.latest is not None
    assert consumer.snapshot.latest.packet_id == 20
    assert consumer.snapshot.lifecycle_state == "stopped"
