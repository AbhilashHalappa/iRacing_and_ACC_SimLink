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
        self.static_consumer = _Consumer("static")
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


def test_broker_exposes_separate_ordered_event_subscription():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    snapshots = broker.subscribe("snapshot-consumer")
    events = broker.subscribe_events("event-consumer", capacity=2)
    broker.start()
    try:
        broker.publish_event(
            "lap.completed",
            session_id="session-1",
            source_stream="graphics",
            source_capture_sequence=12,
            source_timestamp_ns=1200,
            payload={"completed_laps": 12, "valid": True},
        )
        batch = events.read_batch()
        assert len(batch.events) == 1
        assert batch.events[0].event_type == "lap.completed"
        assert batch.events[0].source_capture_sequence == 12
        assert snapshots.latest is not None
        assert broker.metrics["event_delivery"]["published_count"] == 1
    finally:
        assert broker.close()
        assert events.closed


def test_broker_emits_completed_lap_event_from_fresh_decoded_graphics():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    events = broker.subscribe_events("fuel-lap-events", capacity=8)
    broker.start()
    try:
        def publish_graphics(completed_laps: int, sequence: int, valid: bool = True):
            now = time.perf_counter_ns()
            runtime.graphics_consumer._snapshot = SimpleNamespace(
                lifecycle_state="running",
                processed_count=sequence,
                decode_error_count=0,
                last_capture_sequence=sequence,
                last_error=None,
                latest=SimpleNamespace(
                    packet_id=sequence,
                    status=2,
                    completed_laps=completed_laps,
                    session_index=1,
                    session=2,
                    last_time_ms=101234,
                    last_time_str="1:41.234",
                    is_valid_lap=valid,
                ),
                latest_capture_timestamp_ns=now,
            )
            runtime.graphics_consumer._notifier()

        publish_graphics(0, 1)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.is_fresh
            and broker.latest.telemetry.graphics.data is not None
            and getattr(
                broker.latest.telemetry.graphics.data, "completed_laps", None
            ) == 0
        )
        publish_graphics(1, 2, valid=False)
        assert _wait_for(
            lambda: broker.metrics["event_delivery"]["published_count"] >= 1
        )
        first_batch = events.read_batch()
        assert len(first_batch.events) == 1
        first_event = first_batch.events[0]
        assert first_event.event_type == "lap.completed"
        assert first_event.payload["lap_number"] == 1
        assert first_event.payload["lap_valid"] is False
        assert first_event.source_stream == "graphics"
        assert first_event.source_capture_sequence == 2

        # The observer classifies a lap from validity observed during
        # that lap. Supply an in-lap ACC observation before its completion
        # boundary; a true value only on the boundary cannot classify it.
        publish_graphics(1, 3, valid=True)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.capture_sequence == 3
        )
        publish_graphics(2, 4, valid=True)
        assert _wait_for(
            lambda: broker.metrics["event_delivery"]["published_count"] >= 2
        )
        second_batch = events.read_batch()
        assert len(second_batch.events) == 1
        event = second_batch.events[0]
        assert event.event_type == "lap.completed"
        assert event.payload["lap_number"] == 2
        assert event.payload["lap_valid"] is True
        assert event.source_stream == "graphics"
        assert event.source_capture_sequence == 4
        reconciliation = broker.reconcile_lap_progress()
        assert reconciliation is not None
        assert reconciliation.completed_laps == 2
    finally:
        broker.close()



def test_broker_emits_lap_one_start_from_existing_initial_out_lap_crossing():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    events = broker.subscribe_events("performance-lap-start", capacity=8)
    broker.start()
    try:
        def publish_frame(sequence: int, position: float, *, in_pit: bool,
                          speed_kph: float):
            now = time.perf_counter_ns()
            runtime.graphics_consumer._snapshot = SimpleNamespace(
                lifecycle_state="running",
                processed_count=sequence,
                decode_error_count=0,
                last_capture_sequence=sequence,
                last_error=None,
                latest=SimpleNamespace(
                    packet_id=sequence,
                    status=2,
                    completed_laps=0,
                    session_index=1,
                    session=2,
                    normalized_car_position=position,
                    is_in_pit=in_pit,
                    is_in_pit_lane=False,
                    setup_menu_visible=False,
                    is_valid_lap=True,
                ),
                latest_capture_timestamp_ns=now,
            )
            runtime.physics_consumer._snapshot = SimpleNamespace(
                lifecycle_state="running",
                processed_count=sequence,
                decode_error_count=0,
                last_capture_sequence=sequence,
                last_error=None,
                latest=SimpleNamespace(packet_id=sequence, speed_kph=speed_kph),
                latest_capture_timestamp_ns=now,
            )
            runtime.graphics_consumer._notifier()
            runtime.physics_consumer._notifier()

        # Overview observer sees the car in the garage, then moving on the
        # initial out-lap, then crossing start/finish.
        publish_frame(1, 0.10, in_pit=True, speed_kph=0.0)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.capture_sequence == 1
        )
        publish_frame(2, 0.90, in_pit=False, speed_kph=80.0)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.capture_sequence == 2
        )
        publish_frame(3, 0.05, in_pit=False, speed_kph=90.0)
        assert _wait_for(
            lambda: broker.metrics["event_delivery"]["published_count"] == 1
        )

        batch = events.read_batch()
        assert len(batch.events) == 1
        start = batch.events[0]
        assert start.event_type == "lap.started"
        assert start.payload["lap_number"] == 1
        assert start.payload["boundary_source"] == "ACCOutLapObserver"
        assert start.source_stream == "graphics"
        assert start.source_capture_sequence == 3
        assert start.source_timestamp_ns is not None
    finally:
        broker.close()


def test_acc_pause_and_resume_preserves_strategy_session_identity_and_lap_cursor():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    events = broker.subscribe_events("pause-resume-events", capacity=8)
    broker.start()
    try:
        def publish_graphics(status: int, completed_laps: int, sequence: int):
            now = time.perf_counter_ns()
            runtime.graphics_consumer._snapshot = SimpleNamespace(
                lifecycle_state="running",
                processed_count=sequence,
                decode_error_count=0,
                last_capture_sequence=sequence,
                last_error=None,
                latest=SimpleNamespace(
                    packet_id=sequence,
                    status=status,
                    completed_laps=completed_laps,
                    session_index=0,
                    session=0,
                    last_time_ms=100000,
                    last_time_str="1:40.000",
                    is_valid_lap=True,
                ),
                latest_capture_timestamp_ns=now,
            )
            runtime.graphics_consumer._notifier()

        publish_graphics(2, 0, 1)
        assert _wait_for(lambda: broker.strategy_session_id is not None)
        original_session_id = broker.strategy_session_id

        publish_graphics(2, 1, 2)
        assert _wait_for(lambda: broker.metrics["event_delivery"]["published_count"] == 1)
        first_batch = events.read_batch()
        assert len(first_batch.events) == 1
        assert first_batch.events[0].session_id == original_session_id
        assert first_batch.events[0].payload["lap_number"] == 1

        # ACC_STATUS.AC_PAUSE == 3. The session identity and lap observer
        # must survive this temporary state.
        publish_graphics(3, 1, 3)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.data is not None
            and broker.latest.telemetry.graphics.data.status == 3
        )
        assert broker.strategy_session_id == original_session_id

        publish_graphics(2, 1, 4)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.data is not None
            and broker.latest.telemetry.graphics.data.status == 2
        )
        assert broker.strategy_session_id == original_session_id

        publish_graphics(2, 2, 5)
        assert _wait_for(lambda: broker.metrics["event_delivery"]["published_count"] == 2)
        second_batch = events.read_batch()
        assert len(second_batch.events) == 1
        assert second_batch.events[0].session_id == original_session_id
        assert second_batch.events[0].payload["lap_number"] == 2
    finally:
        broker.close()

def test_same_acc_session_labels_get_distinct_ids_after_non_live_boundary():
    runtime = _Runtime()
    broker = DecodedTelemetryBroker(runtime)
    events = broker.subscribe_events("session-boundary-events", capacity=8)
    broker.start()
    try:
        def publish_graphics(status: int, completed_laps: int, sequence: int):
            now = time.perf_counter_ns()
            runtime.graphics_consumer._snapshot = SimpleNamespace(
                lifecycle_state="running",
                processed_count=sequence,
                decode_error_count=0,
                last_capture_sequence=sequence,
                last_error=None,
                latest=SimpleNamespace(
                    packet_id=sequence,
                    status=status,
                    completed_laps=completed_laps,
                    session_index=0,
                    session=0,
                    last_time_ms=100000,
                    last_time_str="1:40.000",
                    is_valid_lap=True,
                ),
                latest_capture_timestamp_ns=now,
            )
            runtime.graphics_consumer._notifier()

        publish_graphics(2, 0, 1)
        assert _wait_for(lambda: broker.strategy_session_id is not None)
        publish_graphics(2, 1, 2)
        assert _wait_for(lambda: broker.metrics["event_delivery"]["published_count"] >= 1)

        first = events.read_batch()
        assert len(first.events) == 1
        first_session_id = first.events[0].session_id
        assert first_session_id is not None and first_session_id.startswith("acc-run:")

        publish_graphics(0, 1, 3)
        assert _wait_for(
            lambda: broker.latest is not None
            and broker.latest.telemetry.graphics.data is not None
            and broker.latest.telemetry.graphics.data.status == 0
            and broker.strategy_session_id is None
        )
        publish_graphics(2, 0, 4)
        assert _wait_for(lambda: broker.strategy_session_id is not None)
        publish_graphics(2, 1, 5)
        assert _wait_for(lambda: broker.metrics["event_delivery"]["published_count"] >= 2)

        second = events.read_batch()
        assert len(second.events) == 1
        second_session_id = second.events[0].session_id
        assert second_session_id is not None and second_session_id.startswith("acc-run:")
        assert second_session_id != first_session_id
    finally:
        broker.close()
