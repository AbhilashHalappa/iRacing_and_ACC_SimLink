"""Bounded preallocated single-producer/single-consumer ring buffer.

The producer never waits for the consumer: lock contention or a full buffer
rejects the new sample and increments explicit loss accounting. The buffer
never overwrites unread records. Multi-consumer fan-out is a separate layer.
"""

from __future__ import annotations

from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class AcquisitionRingBuffer(Generic[T]):
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._slots: list[T | None] = [None] * capacity
        self._capacity = capacity
        self._head = 0
        self._tail = 0
        self._size = 0
        self._lock = Lock()
        self.overflow_count = 0
        self.full_buffer_rejection_count = 0
        self.lock_contention_count = 0
        self.total_rejection_count = 0
        self.first_lost_sequence: int | None = None
        self.last_lost_sequence: int | None = None
        self.high_water_mark = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def size(self) -> int:
        if not self._lock.acquire(blocking=False):
            # A transiently contended read must not block the acquisition path.
            return self._size
        try:
            return self._size
        finally:
            self._lock.release()

    def _record_loss(self, item: T) -> None:
        self.total_rejection_count += 1
        sequence = getattr(item, "capture_sequence", None)
        if isinstance(sequence, int):
            if self.first_lost_sequence is None:
                self.first_lost_sequence = sequence
            self.last_lost_sequence = sequence

    def try_put(self, item: T) -> bool:
        """Insert without waiting; return False and account for rejected data."""
        if not self._lock.acquire(blocking=False):
            self.lock_contention_count += 1
            self._record_loss(item)
            return False
        try:
            if self._size == self._capacity:
                self.overflow_count += 1
                self.full_buffer_rejection_count += 1
                self._record_loss(item)
                return False
            self._slots[self._head] = item
            self._head = (self._head + 1) % self._capacity
            self._size += 1
            self.high_water_mark = max(self.high_water_mark, self._size)
            return True
        finally:
            self._lock.release()

    def try_get(self) -> T | None:
        """Remove one item, or return None when empty/temporarily contended."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            if self._size == 0:
                return None
            item = self._slots[self._tail]
            self._slots[self._tail] = None
            self._tail = (self._tail + 1) % self._capacity
            self._size -= 1
            return item
        finally:
            self._lock.release()
