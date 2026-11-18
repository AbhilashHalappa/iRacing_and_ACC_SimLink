"""Loss-accounted, bounded fan-out for decoded high-rate samples.

This is a Stage 2 distribution primitive. It accepts already-decoded immutable
samples and offers each sample independently to bounded subscriber queues.
It never reads ACC shared memory, raw acquisition rings or recorder files.
"""
from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class DecodedSample:
    """One decoded observation with its original stream identity."""

    stream: str
    capture_sequence: int
    capture_timestamp_ns: int
    data: Any


@dataclass(frozen=True, slots=True)
class DecodedSampleQueueMetrics:
    name: str
    capacity: int
    offered_count: int
    accepted_count: int
    delivered_count: int
    rejected_count: int
    queued_count: int
    high_water_mark: int
    first_rejected_sequence: int | None
    last_rejected_sequence: int | None
    closed: bool


class DecodedSampleSubscription:
    """One independent bounded FIFO mailbox for decoded samples.

    Overflow policy is drop-newest: already queued samples retain their order,
    and every rejected sample is counted with its source sequence. Consumers
    can therefore detect that their historical trace is incomplete.
    """

    def __init__(self, name: str, capacity: int) -> None:
        if not name or not name.strip():
            raise ValueError("subscriber name must be non-empty")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.name = name
        self.capacity = capacity
        self._queue: Queue[DecodedSample] = Queue(maxsize=capacity)
        self._lock = Lock()
        self._offered_count = 0
        self._accepted_count = 0
        self._delivered_count = 0
        self._rejected_count = 0
        self._high_water_mark = 0
        self._first_rejected_sequence: int | None = None
        self._last_rejected_sequence: int | None = None
        self._closed = False

    def _offer(self, sample: DecodedSample) -> bool:
        # Keep the closed check and nonblocking offer under one lock so close()
        # cannot race an in-flight offer into a queue after shutdown.
        with self._lock:
            if self._closed:
                return False
            self._offered_count += 1
            try:
                self._queue.put_nowait(sample)
            except Full:
                self._rejected_count += 1
                if self._first_rejected_sequence is None:
                    self._first_rejected_sequence = sample.capture_sequence
                self._last_rejected_sequence = sample.capture_sequence
                return False
            self._accepted_count += 1
            self._high_water_mark = max(self._high_water_mark, self._queue.qsize())
            return True

    def read_nowait(self) -> DecodedSample | None:
        """Return the oldest queued sample, or None when currently empty."""
        try:
            sample = self._queue.get_nowait()
        except Empty:
            return None
        with self._lock:
            self._delivered_count += 1
        return sample

    def read_batch(self, max_items: int) -> tuple[DecodedSample, ...]:
        """Drain up to max_items in FIFO order without waiting."""
        if max_items < 0:
            raise ValueError("max_items cannot be negative")
        result: list[DecodedSample] = []
        for _ in range(max_items):
            sample = self.read_nowait()
            if sample is None:
                break
            result.append(sample)
        return tuple(result)

    @property
    def metrics(self) -> DecodedSampleQueueMetrics:
        with self._lock:
            return DecodedSampleQueueMetrics(
                name=self.name,
                capacity=self.capacity,
                offered_count=self._offered_count,
                accepted_count=self._accepted_count,
                delivered_count=self._delivered_count,
                rejected_count=self._rejected_count,
                queued_count=self._queue.qsize(),
                high_water_mark=self._high_water_mark,
                first_rejected_sequence=self._first_rejected_sequence,
                last_rejected_sequence=self._last_rejected_sequence,
                closed=self._closed,
            )

    def close(self, *, discard_pending: bool = False) -> None:
        with self._lock:
            self._closed = True
        if discard_pending:
            while True:
                try:
                    self._queue.get_nowait()
                except Empty:
                    break


class DecodedSampleFanOut:
    """Publish decoded samples to independent bounded subscribers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._subscriptions: dict[str, DecodedSampleSubscription] = {}
        self._closed = False
        self._published_count = 0

    def subscribe(
        self, name: str, *, capacity: int
    ) -> DecodedSampleSubscription:
        subscription = DecodedSampleSubscription(name, capacity)
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded sample fan-out is closed")
            if name in self._subscriptions:
                raise ValueError(f"subscriber already registered: {name}")
            self._subscriptions[name] = subscription
        return subscription

    def unsubscribe(self, name: str, *, discard_pending: bool = False) -> None:
        with self._lock:
            subscription = self._subscriptions.pop(name, None)
        if subscription is not None:
            subscription.close(discard_pending=discard_pending)

    def publish(
        self,
        *,
        stream: str,
        capture_sequence: int,
        capture_timestamp_ns: int,
        data: Any,
    ) -> dict[str, bool]:
        """Offer one decoded sample to each subscriber without blocking.

        The returned map reports acceptance per subscriber. A rejected sample
        is not retried because retries could stall the decoder worker.
        """
        if not stream or not stream.strip():
            raise ValueError("stream must be non-empty")
        if capture_sequence < 0 or capture_timestamp_ns < 0:
            raise ValueError("capture sequence and timestamp must be non-negative")
        sample = DecodedSample(stream, capture_sequence, capture_timestamp_ns, data)
        with self._lock:
            if self._closed:
                return {}
            subscriptions = tuple(self._subscriptions.items())
            self._published_count += 1
        return {
            name: subscription._offer(sample)
            for name, subscription in subscriptions
        }

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            subscriptions = tuple(self._subscriptions.items())
            published_count = self._published_count
            closed = self._closed
        return {
            "published_count": published_count,
            "subscriber_count": len(subscriptions),
            "closed": closed,
            "subscribers": {
                name: subscription.metrics
                for name, subscription in subscriptions
            },
        }

    def close(self, *, discard_pending: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = tuple(self._subscriptions.values())
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.close(discard_pending=discard_pending)
