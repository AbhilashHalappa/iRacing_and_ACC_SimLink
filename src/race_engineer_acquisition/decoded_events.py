"""Bounded, identified event delivery for Stage 2 decoded telemetry.

State snapshots are coalescible and belong to decoded_distribution. Events are
not: each subscriber receives an ordered bounded queue and an explicit gap
signal if it cannot keep up. After a gap, a consumer must reconcile against
the latest authoritative decoded snapshot/history before acting.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
import time
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    """Detach common payload containers so published events cannot be mutated."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class DecodedDomainEvent:
    """An identified event derived from decoded application state."""

    event_id: str
    sequence: int
    event_type: str
    session_id: str | None
    source_stream: str
    source_capture_sequence: int | None
    source_timestamp_ns: int | None
    emitted_at_ns: int
    schema_version: int
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EventDeliveryBatch:
    """Events delivered to one subscriber plus explicit loss/reconciliation state."""

    events: tuple[DecodedDomainEvent, ...]
    gap_detected: bool
    expected_sequence: int
    first_available_sequence: int | None
    latest_sequence: int


class DecodedEventSubscription:
    """Independent bounded FIFO mailbox for one Stage 2 event consumer."""

    def __init__(self, name: str, capacity: int, next_sequence: int) -> None:
        if capacity < 1:
            raise ValueError("event subscription capacity must be positive")
        self.name = name
        self.capacity = capacity
        self._lock = Lock()
        self._events: deque[DecodedDomainEvent] = deque()
        self._next_sequence = next_sequence
        self._dropped_count = 0
        self._closed = False

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def _offer(self, event: DecodedDomainEvent) -> None:
        with self._lock:
            if self._closed:
                return
            if len(self._events) >= self.capacity:
                self._events.popleft()
                self._dropped_count += 1
            self._events.append(event)

    def read_batch(self, *, max_events: int | None = None) -> EventDeliveryBatch:
        if max_events is not None and max_events < 1:
            raise ValueError("max_events must be positive")
        with self._lock:
            expected = self._next_sequence
            first = self._events[0].sequence if self._events else None
            gap = first is not None and first > expected
            count = len(self._events) if max_events is None else min(max_events, len(self._events))
            events = tuple(self._events.popleft() for _ in range(count))
            if events:
                self._next_sequence = events[-1].sequence + 1
            latest = events[-1].sequence if events else (first - 1 if first else expected - 1)
            return EventDeliveryBatch(
                events=events,
                gap_detected=gap,
                expected_sequence=expected,
                first_available_sequence=first,
                latest_sequence=latest,
            )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._events.clear()


class DecodedEventPublisher:
    """Assign event identity/order and fan out to isolated bounded mailboxes."""

    def __init__(self, *, clock_ns=time.perf_counter_ns) -> None:
        self._clock_ns = clock_ns
        self._lock = Lock()
        self._sequence = 0
        self._subscribers: dict[str, DecodedEventSubscription] = {}
        self._published_count = 0
        self._closed = False

    def subscribe(self, name: str, *, capacity: int = 128) -> DecodedEventSubscription:
        if not name or not name.strip():
            raise ValueError("subscriber name must be non-empty")
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded event publisher is closed")
            if name in self._subscribers:
                raise ValueError(f"subscriber already registered: {name}")
            subscription = DecodedEventSubscription(name, capacity, self._sequence + 1)
            self._subscribers[name] = subscription
            return subscription

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            subscription = self._subscribers.pop(name, None)
        if subscription is not None:
            subscription.close()

    def publish(
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
        if not event_type or not event_type.strip():
            raise ValueError("event_type must be non-empty")
        if not source_stream or not source_stream.strip():
            raise ValueError("source_stream must be non-empty")
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded event publisher is closed")
            self._sequence += 1
            sequence = self._sequence
            event = DecodedDomainEvent(
                event_id=f"{session_id or 'session-unknown'}:{sequence}",
                sequence=sequence,
                event_type=event_type,
                session_id=session_id,
                source_stream=source_stream,
                source_capture_sequence=source_capture_sequence,
                source_timestamp_ns=source_timestamp_ns,
                emitted_at_ns=self._clock_ns(),
                schema_version=schema_version,
                payload=_freeze(payload),
            )
            self._published_count += 1
            # Fan-out remains inside the publisher lock so concurrent producers
            # cannot deliver sequence N+1 before sequence N to any subscriber.
            for subscriber in self._subscribers.values():
                subscriber._offer(event)
            return event

    @property
    def metrics(self) -> dict[str, int | bool]:
        with self._lock:
            return {
                "closed": self._closed,
                "subscriber_count": len(self._subscribers),
                "latest_sequence": self._sequence,
                "published_count": self._published_count,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = tuple(self._subscribers.values())
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.close()
