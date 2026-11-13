from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import time

from src.race_engineer_acquisition.decoded_distribution import (
    DecodedSnapshotEnvelope,
    DecodedTelemetryBroker,
    LatestSnapshotSubscription,
)


@dataclass(frozen=True)
class _Health:
    lifecycle_state: str = "running"
    last_successful_read_ns: int | None = None
    source_read_failures: int = 0
    buffer_rejections: int = 0
    last_error: str | None = None


class _Consumer:
    def __init__(self, stream: str) -> None:
        now = time.perf_counter_ns()
        self._snapshot = SimpleNamespace(
            lifecycle_state="running",
            processed_count=1,
            decode_error_count=0,
            last_capture_sequence=1,
            last_error=None,
            latest=SimpleNamespace(packet_id=1, stream=stream),
            latest_capture_timestamp_ns=now,
        )
        self._notifier = None

    @property
    def snapshot(self):
        return self._snapshot

    def set_update_notifier(self, notifier):
        self._notifier = notifier

    def publish(self, sequence: int) -> None:
        now = time.perf_counter_ns()
        self._snapshot = SimpleNamespace(
            lifecycle_state="running",
            processed_count=sequence,
            decode_error_count=0,
            last_capture_sequence=sequence,
            last_error=None,
            latest=SimpleNamespace(packet_id=sequence, stream="physics"),
            latest_capture_timestamp_ns=now,
        )
        if self._notifier is not None:
            self._notifier()


class _HealthOwner:
    def __init__(self) -> None:
        self.snapshot = _Health(last_successful_read_ns=time.perf_counter_ns())


class _Runtime:
    def __init__(self) -> None:
        self.physics_consumer = _Consumer("physics")
        self.graphics_consumer = _Consumer("graphics")
        self.acquirers = {
            "physics": SimpleNamespace(health=_HealthOwner()),
            "graphics": SimpleNamespace(health=_HealthOwner()),
            "static": SimpleNamespace(health=_HealthOwner()),
        }


def _wait_for(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_broker_publishes_decoded_state_to_independent_subscribers():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    fuel = broker.subscribe("fuel")
    tyre = broker.subscribe("tyre")
    broker.start()
    try:
        assert fuel.latest is not None
        first = fuel.read_latest()
        assert first is not None
        assert tyre.latest == first
        assert first.telemetry.physics.data.packet_id == 1

        runtime.physics_consumer.publish(2)
        assert _wait_for(
            lambda: fuel.latest is not None and fuel.latest.revision > first.revision
        )
        second = fuel.read_latest()
        assert second is not None
        assert second.telemetry.physics.capture_sequence == 2
        assert tyre.latest == second
        assert broker.metrics["published_count"] >= 2
    finally:
        assert broker.close()


def test_latest_snapshot_subscription_coalesces_unread_updates():
    subscription = LatestSnapshotSubscription("slow-consumer")
    first = DecodedSnapshotEnvelope(1, 10, None)  # type: ignore[arg-type]
    second = DecodedSnapshotEnvelope(2, 20, None)  # type: ignore[arg-type]
    third = DecodedSnapshotEnvelope(3, 30, None)  # type: ignore[arg-type]

    subscription._publish(first)
    subscription._publish(second)
    subscription._publish(third)

    assert subscription.latest == third
    assert subscription.coalesced_updates == 2
    assert subscription.read_latest() == third
    subscription._publish(DecodedSnapshotEnvelope(4, 40, None))  # type: ignore[arg-type]
    assert subscription.coalesced_updates == 2


def test_closed_subscriber_does_not_affect_other_subscribers():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    first = broker.subscribe("first")
    second = broker.subscribe("second")
    broker.start()
    try:
        assert _wait_for(lambda: first.latest is not None and second.latest is not None)
        first.close()
        runtime.graphics_consumer.publish(2)
        assert _wait_for(lambda: second.latest is not None and second.latest.revision >= 2)
        assert first.latest is None
        assert second.latest.telemetry.graphics.capture_sequence == 2
    finally:
        assert broker.close()
