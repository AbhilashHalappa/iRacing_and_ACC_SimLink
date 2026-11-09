"""Independent bounded downstream fan-out outside acquisition workers.

The source remains a single-producer/single-consumer acquisition ring. One
dispatcher consumes it and offers each immutable snapshot independently to
registered per-consumer queues. A slow or failed consumer never owns or removes
another consumer's queue entries.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Generic, TypeVar

from .ring_buffer import AcquisitionRingBuffer

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ConsumerQueueMetrics:
    name: str
    required: bool
    offered_count: int
    dispatched_count: int
    processed_count: int
    failed_count: int
    rejected_count: int
    queued_count: int
    in_flight_count: int
    pending_count: int
    capacity: int
    high_water_mark: int
    first_lost_sequence: int | None
    last_lost_sequence: int | None
    first_failed_sequence: int | None
    last_failed_sequence: int | None
    closed: bool
    failed: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class FanOutMetrics:
    source_dequeued_count: int
    dispatched_item_count: int
    required_delivery_rejection_count: int
    in_flight_sequence: int | None
    error: str | None


class BoundedConsumerQueue(Generic[T]):
    """One consumer's bounded queue with explicit processing acknowledgements.

    Dispatched means accepted into this consumer's queue. Processed means the
    consumer explicitly acknowledged successful completion (for a recorder,
    only after the batch write/flush/fsync succeeds). Dequeue alone is not
    considered processing. Every accepted item is therefore either processed,
    failed, or pending (queued plus in-flight).
    """

    def __init__(self, name: str, capacity: int, *, required: bool = False) -> None:
        if not name or not name.strip():
            raise ValueError("consumer name must be non-empty")
        self.name = name
        self.required = bool(required)
        self._buffer: AcquisitionRingBuffer[T] = AcquisitionRingBuffer(capacity)
        self._lock = Lock()
        self._in_flight: dict[int, T] = {}
        self._offered_count = 0
        self._dispatched_count = 0
        self._processed_count = 0
        self._failed_count = 0
        self._rejected_count = 0
        self._first_lost_sequence: int | None = None
        self._last_lost_sequence: int | None = None
        self._first_failed_sequence: int | None = None
        self._last_failed_sequence: int | None = None
        self._closed = False
        self._failed = False
        self._error: str | None = None

    @staticmethod
    def _sequence(item: T) -> int | None:
        value = getattr(item, "capture_sequence", None)
        return value if isinstance(value, int) else None

    def _record_rejection(self, item: T) -> None:
        self._rejected_count += 1
        sequence = self._sequence(item)
        if sequence is not None:
            if self._first_lost_sequence is None:
                self._first_lost_sequence = sequence
            self._last_lost_sequence = sequence

    def _record_failure(self, item: T) -> None:
        self._failed_count += 1
        sequence = self._sequence(item)
        if sequence is not None:
            if self._first_failed_sequence is None:
                self._first_failed_sequence = sequence
            self._last_failed_sequence = sequence

    def offer(self, item: T) -> bool:
        """Offer without waiting; a full/closed/failed queue rejects explicitly."""
        with self._lock:
            self._offered_count += 1
            if self._closed or self._failed:
                self._record_rejection(item)
                return False
            if not self._buffer.try_put(item):
                self._record_rejection(item)
                return False
            self._dispatched_count += 1
            return True

    def try_get(self) -> T | None:
        """Get one item and mark it in-flight until explicitly acknowledged."""
        with self._lock:
            item = self._buffer.try_get()
            if item is None:
                return None
            sequence = self._sequence(item)
            if sequence is None:
                raise ValueError("consumer items must expose integer capture_sequence")
            if sequence in self._in_flight:
                raise RuntimeError(f"duplicate in-flight capture sequence: {sequence}")
            self._in_flight[sequence] = item
            return item

    def acknowledge(self, item_or_sequence: T | int, *, success: bool = True) -> None:
        """Complete a dequeued item after processing has actually finished."""
        sequence = (
            item_or_sequence
            if isinstance(item_or_sequence, int)
            else self._sequence(item_or_sequence)
        )
        if sequence is None:
            raise ValueError("acknowledgement requires an integer capture sequence")
        with self._lock:
            item = self._in_flight.pop(sequence, None)
            if item is None:
                raise KeyError(f"capture sequence {sequence} is not in flight")
            if success:
                self._processed_count += 1
            else:
                self._record_failure(item)

    def close_dispatch(self) -> None:
        """Stop new offers while allowing the consumer to drain accepted work."""
        with self._lock:
            self._closed = True

    def mark_failed(self, reason: str) -> int:
        """Fail the consumer and account all queued/in-flight work as failed."""
        with self._lock:
            if not self._failed:
                self._failed = True
                self._closed = True
                self._error = reason
            count = 0
            while True:
                item = self._buffer.try_get()
                if item is None:
                    break
                self._record_failure(item)
                count += 1
            for item in self._in_flight.values():
                self._record_failure(item)
                count += 1
            self._in_flight.clear()
            return count

    @property
    def size(self) -> int:
        return self._buffer.size

    @property
    def capacity(self) -> int:
        return self._buffer.capacity

    @property
    def metrics(self) -> ConsumerQueueMetrics:
        with self._lock:
            queued = self._buffer.size
            in_flight = len(self._in_flight)
            return ConsumerQueueMetrics(
                name=self.name,
                required=self.required,
                offered_count=self._offered_count,
                dispatched_count=self._dispatched_count,
                processed_count=self._processed_count,
                failed_count=self._failed_count,
                rejected_count=self._rejected_count,
                queued_count=queued,
                in_flight_count=in_flight,
                pending_count=queued + in_flight,
                capacity=self.capacity,
                high_water_mark=self._buffer.high_water_mark,
                first_lost_sequence=self._first_lost_sequence,
                last_lost_sequence=self._last_lost_sequence,
                first_failed_sequence=self._first_failed_sequence,
                last_failed_sequence=self._last_failed_sequence,
                closed=self._closed,
                failed=self._failed,
                error=self._error,
            )


class FanOutDispatcher(Generic[T]):
    """Move source SPSC samples to independent bounded consumer queues."""

    def __init__(self, source: AcquisitionRingBuffer[T]) -> None:
        self.source = source
        self._consumers: dict[str, BoundedConsumerQueue[T]] = {}
        self._lock = Lock()
        self._started = False
        self._source_dequeued_count = 0
        self._dispatched_item_count = 0
        self._required_delivery_rejection_count = 0
        self._in_flight_sequence: int | None = None
        self._error: str | None = None

    def register(
        self, name: str, capacity: int, *, required: bool = False
    ) -> BoundedConsumerQueue[T]:
        """Register a bounded independent consumer before dispatcher start."""
        with self._lock:
            if self._started:
                raise RuntimeError("consumers must be registered before dispatch starts")
            if name in self._consumers:
                raise ValueError(f"consumer {name!r} is already registered")
            consumer = BoundedConsumerQueue[T](name, capacity, required=required)
            self._consumers[name] = consumer
            return consumer

    @property
    def consumers(self) -> dict[str, BoundedConsumerQueue[T]]:
        with self._lock:
            return dict(self._consumers)

    @property
    def metrics(self) -> FanOutMetrics:
        with self._lock:
            return FanOutMetrics(
                source_dequeued_count=self._source_dequeued_count,
                dispatched_item_count=self._dispatched_item_count,
                required_delivery_rejection_count=self._required_delivery_rejection_count,
                in_flight_sequence=self._in_flight_sequence,
                error=self._error,
            )

    def run(self, stop_event: Event) -> None:
        """Drain source after stop is requested, then close consumer dispatch."""
        with self._lock:
            if self._started:
                raise RuntimeError("fan-out dispatcher can only be run once")
            consumers = tuple(self._consumers.values())
            if not consumers:
                raise RuntimeError("at least one downstream consumer must be registered")
            self._started = True

        try:
            while not stop_event.is_set() or self.source.size > 0:
                item = self.source.try_get()
                if item is None:
                    stop_event.wait(0.0005)
                    continue
                sequence = BoundedConsumerQueue._sequence(item)
                with self._lock:
                    self._source_dequeued_count += 1
                    self._in_flight_sequence = sequence
                for consumer in consumers:
                    try:
                        accepted = consumer.offer(item)
                    except Exception as exc:
                        consumer.mark_failed(f"{type(exc).__name__}: {exc}")
                        accepted = False
                    if not accepted and consumer.required:
                        with self._lock:
                            self._required_delivery_rejection_count += 1
                with self._lock:
                    self._dispatched_item_count += 1
                    self._in_flight_sequence = None
        except Exception as exc:
            with self._lock:
                self._error = f"{type(exc).__name__}: {exc}"
            for consumer in consumers:
                consumer.mark_failed(f"fan-out dispatcher failed: {self._error}")
            raise
        finally:
            for consumer in consumers:
                consumer.close_dispatch()
