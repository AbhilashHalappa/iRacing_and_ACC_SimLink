"""Stage 2 distribution for immutable, decoded ACC telemetry snapshots.

This broker is deliberately downstream of the existing Physics and Graphics
decoders. It never reads acquisition rings, raw payloads or ACC shared memory.
Decoder notifications only set a waitable dirty flag; aggregation and subscriber
publication happen on this broker's own worker thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, Thread
import time
from typing import Any, Mapping

from .decoded_events import (
    DecodedDomainEvent,
    DecodedEventPublisher,
    DecodedEventSubscription,
)

from .engineering_snapshot import RaceEngineerSnapshotAggregator, RaceEngineerTelemetrySnapshot


@dataclass(frozen=True, slots=True)
class DecodedSnapshotEnvelope:
    """One broker publication with a monotonic revision and publication time."""

    revision: int
    published_at_ns: int
    telemetry: RaceEngineerTelemetrySnapshot


class LatestSnapshotSubscription:
    """Independent coalescing latest-value mailbox for one downstream consumer."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = Lock()
        self._latest: DecodedSnapshotEnvelope | None = None
        self._last_read_revision = 0
        self._coalesced_updates = 0
        self._closed = False

    @property
    def latest(self) -> DecodedSnapshotEnvelope | None:
        with self._lock:
            return self._latest

    @property
    def coalesced_updates(self) -> int:
        with self._lock:
            return self._coalesced_updates

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def read_latest(self) -> DecodedSnapshotEnvelope | None:
        """Read the newest publication and mark all older revisions observed."""
        with self._lock:
            result = self._latest
            if result is not None:
                self._last_read_revision = result.revision
            return result

    def _publish(self, envelope: DecodedSnapshotEnvelope) -> None:
        with self._lock:
            if self._closed:
                return
            if (
                self._latest is not None
                and self._latest.revision > self._last_read_revision
            ):
                self._coalesced_updates += 1
            self._latest = envelope

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._latest = None


class DecodedTelemetryBroker:
    """Publish decoded latest-state snapshots to independent subscribers.

    The broker has no callback execution on decoder threads. Decoder workers
    invoke only `notify_dirty()`, which sets a threading.Event. This worker
    coalesces bursts, reads the existing freshness-aware decoded aggregator,
    and replaces each subscriber's latest-value mailbox.

    History-critical events use a separate bounded, identified event channel.
    Snapshot coalescing and event delivery have independent subscriber mailboxes.
    """

    def __init__(self, runtime: Any, *, clock_ns=time.perf_counter_ns) -> None:
        self._aggregator = RaceEngineerSnapshotAggregator(runtime, clock_ns=clock_ns)
        self._events = DecodedEventPublisher(clock_ns=clock_ns)
        self._clock_ns = clock_ns
        self._dirty = Event()
        self._stop = Event()
        self._lock = Lock()
        self._subscribers: dict[str, LatestSnapshotSubscription] = {}
        self._revision = 0
        self._latest: DecodedSnapshotEnvelope | None = None
        self._published_count = 0
        self._wake_count = 0
        self._error_count = 0
        self._last_error: str | None = None
        self._thread: Thread | None = None
        self._started = False
        self._closed = False

        # The callback performs no aggregation, queue operation or consumer
        # work. It only signals this broker-owned worker.
        runtime.physics_consumer.set_update_notifier(self.notify_dirty)
        runtime.graphics_consumer.set_update_notifier(self.notify_dirty)

    def subscribe(self, name: str) -> LatestSnapshotSubscription:
        if not name or not name.strip():
            raise ValueError("subscriber name must be non-empty")
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded telemetry broker is closed")
            if name in self._subscribers:
                raise ValueError(f"subscriber already registered: {name}")
            subscription = LatestSnapshotSubscription(name)
            if self._latest is not None:
                subscription._publish(self._latest)
            self._subscribers[name] = subscription
            return subscription

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            subscription = self._subscribers.pop(name, None)
        if subscription is not None:
            subscription.close()

    def subscribe_events(
        self, name: str, *, capacity: int = 128
    ) -> DecodedEventSubscription:
        """Register an independent bounded mailbox for important domain events."""
        return self._events.subscribe(name, capacity=capacity)

    def publish_event(
        self,
        event_type: str,
        *,
        session_id: str | None,
        source_stream: str,
        source_capture_sequence: int | None,
        source_timestamp_ns: int | None,
        payload: Mapping[str, Any],
        schema_version: int = 1,
    ) -> DecodedDomainEvent:
        """Publish an event already derived from validated decoded state.

        Producers must not call this with raw ACC payloads or unvalidated
        candidate semantics. Event consumers detect overflow and reconcile
        against authoritative decoded state/history before acting.
        """
        return self._events.publish(
            event_type,
            session_id=session_id,
            source_stream=source_stream,
            source_capture_sequence=source_capture_sequence,
            source_timestamp_ns=source_timestamp_ns,
            payload=payload,
            schema_version=schema_version,
        )

    def notify_dirty(self) -> None:
        """Constant-time decoder hook; safe to call after releasing decoder lock."""
        if not self._closed:
            self._dirty.set()

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded telemetry broker is closed")
            if self._started:
                return
            self._started = True
        try:
            # Seed the first immutable view before any service can subscribe.
            self._publish_once()
        except Exception:
            with self._lock:
                self._started = False
            raise
        with self._lock:
            self._thread = Thread(
                target=self._run,
                name="ACC-Decoded-Telemetry-Broker",
                daemon=True,
            )
            self._thread.start()
        self.notify_dirty()

    def _publish_once(self) -> None:
        telemetry = self._aggregator.snapshot()
        with self._lock:
            self._revision += 1
            envelope = DecodedSnapshotEnvelope(
                revision=self._revision,
                published_at_ns=self._clock_ns(),
                telemetry=telemetry,
            )
            self._latest = envelope
            self._published_count += 1
            self._last_error = None
            subscribers = tuple(self._subscribers.values())
        for subscriber in subscribers:
            # Each mailbox is independently locked and coalescing.
            # No consumer callback runs on this worker.
            subscriber._publish(envelope)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._dirty.wait()
            self._dirty.clear()
            if self._stop.is_set():
                break
            with self._lock:
                self._wake_count += 1
            try:
                self._publish_once()
            except Exception as exc:
                with self._lock:
                    self._error_count += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"

    @property
    def latest(self) -> DecodedSnapshotEnvelope | None:
        with self._lock:
            return self._latest

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started": self._started,
                "closed": self._closed,
                "subscriber_count": len(self._subscribers),
                "revision": self._revision,
                "published_count": self._published_count,
                "wake_count": self._wake_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "event_delivery": self._events.metrics,
            }

    def close(self, *, timeout: float = 2.0) -> bool:
        """Stop the broker worker; return False if it exceeded the timeout."""
        with self._lock:
            if self._closed:
                thread = self._thread
            else:
                self._closed = True
                self._stop.set()
                thread = self._thread
                subscribers = tuple(self._subscribers.values())
                self._subscribers.clear()
                for subscriber in subscribers:
                    subscriber.close()
        self._events.close()
        self._dirty.set()
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True
