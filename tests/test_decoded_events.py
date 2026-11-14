from __future__ import annotations

import pytest

from src.race_engineer_acquisition.decoded_events import DecodedEventPublisher


def _publish(publisher, index: int):
    return publisher.publish(
        "lap.completed",
        session_id="session-1",
        source_stream="graphics",
        source_capture_sequence=index,
        source_timestamp_ns=1_000 + index,
        payload={"completed_laps": index, "valid": True},
    )


def test_event_delivery_is_ordered_and_independent_per_subscriber():
    publisher = DecodedEventPublisher(clock_ns=lambda: 99)
    fuel = publisher.subscribe("fuel", capacity=4)
    tyre = publisher.subscribe("tyre", capacity=4)

    first = _publish(publisher, 1)
    second = _publish(publisher, 2)

    fuel_batch = fuel.read_batch()
    tyre_batch = tyre.read_batch()
    assert [event.sequence for event in fuel_batch.events] == [1, 2]
    assert [event.sequence for event in tyre_batch.events] == [1, 2]
    assert fuel_batch.gap_detected is False
    assert first.event_id == "session-1:1"
    assert second.event_type == "lap.completed"
    assert second.emitted_at_ns == 99
    assert second.payload["completed_laps"] == 2


def test_bounded_event_mailbox_reports_gap_instead_of_silent_loss():
    publisher = DecodedEventPublisher()
    slow = publisher.subscribe("slow", capacity=2)
    for index in range(1, 5):
        _publish(publisher, index)

    batch = slow.read_batch()
    assert [event.sequence for event in batch.events] == [3, 4]
    assert batch.gap_detected is True
    assert batch.expected_sequence == 1
    assert batch.first_available_sequence == 3
    assert slow.dropped_count == 2


def test_event_subscriber_failure_isolation_and_unsubscribe():
    publisher = DecodedEventPublisher()
    closed = publisher.subscribe("closed", capacity=1)
    active = publisher.subscribe("active", capacity=2)
    publisher.unsubscribe("closed")

    _publish(publisher, 1)
    batch = active.read_batch()
    assert [event.sequence for event in batch.events] == [1]
    assert closed.closed is True
    assert publisher.metrics["subscriber_count"] == 1


def test_event_payload_is_detached_from_publisher_input():
    publisher = DecodedEventPublisher()
    subscriber = publisher.subscribe("consumer")
    payload = {"nested": {"value": 1}}
    publisher.publish(
        "damage.changed",
        session_id="session-1",
        source_stream="physics",
        source_capture_sequence=7,
        source_timestamp_ns=70,
        payload=payload,
    )
    payload["nested"]["value"] = 9
    event = subscriber.read_batch().events[0]
    assert event.payload["nested"]["value"] == 1
    with pytest.raises(TypeError):
        event.payload["nested"]["value"] = 2


def test_event_subscription_requires_positive_capacity():
    publisher = DecodedEventPublisher()
    with pytest.raises(ValueError):
        publisher.subscribe("invalid", capacity=0)


def test_event_payload_rejects_opaque_mutable_objects():
    publisher = DecodedEventPublisher()
    with pytest.raises(TypeError):
        publisher.publish(
            "invalid.payload",
            session_id="session-1",
            source_stream="graphics",
            source_capture_sequence=1,
            source_timestamp_ns=10,
            payload={"mutable": object()},
        )
