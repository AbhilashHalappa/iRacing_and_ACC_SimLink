"""Acquisition loop independent of ACC-specific memory mapping."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Callable, Protocol

from .models import PhysicsSnapshot, RawPhysicsRead
from .ring_buffer import AcquisitionRingBuffer


class PhysicsSource(Protocol):
    def read_physics(self) -> RawPhysicsRead:
        """Copy one Physics page, bracketing the copy with packet-ID reads."""
        ...


@dataclass(slots=True)
class AcquisitionMetrics:
    capture_count: int = 0
    read_attempt_count: int = 0
    total_read_attempt_duration_ns: int = 0
    max_read_attempt_duration_ns: int = 0
    inconsistent_snapshot_count: int = 0
    consistency_retry_count: int = 0
    source_packet_gap_count: int = 0
    duplicate_packet_observation_count: int = 0
    packet_id_regression_count: int = 0
    last_packet_id: int | None = None
    last_capture_sequence: int = 0
    last_acquisition_duration_ns: int = 0
    max_acquisition_duration_ns: int = 0
    last_poll_interval_ns: int = 0
    max_poll_interval_ns: int = 0
    buffer_rejection_count: int = 0
    _previous_read_start_ns: int | None = None


class PhysicsAcquirer:
    """Continuously capture Physics snapshots and publish them to an SPSC ring.

    The source adapter must do only the bounded shared-memory copy and return
    application-owned bytes. This loop does no decoding, serialization or I/O.
    """

    def __init__(
        self,
        source: PhysicsSource,
        buffer: AcquisitionRingBuffer[PhysicsSnapshot],
        *,
        max_consistency_attempts: int = 3,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if max_consistency_attempts < 1:
            raise ValueError("max_consistency_attempts must be at least one")
        self._source = source
        self._buffer = buffer
        self._max_attempts = max_consistency_attempts
        self._clock_ns = clock_ns
        self.metrics = AcquisitionMetrics()
        self._next_sequence = 1

    def capture_once(self) -> PhysicsSnapshot | None:
        for attempt in range(self._max_attempts):
            read_start_ns = self._clock_ns()
            if self.metrics._previous_read_start_ns is not None:
                interval = read_start_ns - self.metrics._previous_read_start_ns
                self.metrics.last_poll_interval_ns = interval
                self.metrics.max_poll_interval_ns = max(
                    self.metrics.max_poll_interval_ns, interval
                )
            self.metrics._previous_read_start_ns = read_start_ns
            raw: RawPhysicsRead = self._source.read_physics()
            read_complete_ns = self._clock_ns()
            read_duration = read_complete_ns - read_start_ns
            self.metrics.read_attempt_count += 1
            self.metrics.total_read_attempt_duration_ns += read_duration
            self.metrics.max_read_attempt_duration_ns = max(
                self.metrics.max_read_attempt_duration_ns, read_duration
            )
            if raw.is_consistent:
                break
            self.metrics.inconsistent_snapshot_count += 1
            if attempt + 1 < self._max_attempts:
                self.metrics.consistency_retry_count += 1
        else:
            return None

        packet_id = raw.packet_id_after
        previous = self.metrics.last_packet_id
        if previous is not None and packet_id == previous:
            self.metrics.duplicate_packet_observation_count += 1
            return None

        # Assign sequence numbers only to distinct, consistent source snapshots.
        # Duplicate observations must not create holes in the capture sequence.
        sequence = self._next_sequence
        self._next_sequence += 1
        if previous is not None and packet_id > previous + 1:
            self.metrics.source_packet_gap_count += packet_id - previous - 1
        elif previous is not None and packet_id < previous:
            # Counter wrap/reset semantics must be verified against ACC before
            # deriving a gap count. Preserve the observation and flag regression.
            self.metrics.packet_id_regression_count += 1

        snapshot = PhysicsSnapshot(
            capture_sequence=sequence,
            acc_physics_packet_id=packet_id,
            read_start_ns=read_start_ns,
            read_complete_ns=read_complete_ns,
            capture_timestamp_ns=read_complete_ns,
            payload=bytes(raw.payload),
        )
        self.metrics.capture_count += 1
        self.metrics.last_capture_sequence = sequence
        self.metrics.last_packet_id = packet_id
        duration = snapshot.acquisition_duration_ns
        self.metrics.last_acquisition_duration_ns = duration
        self.metrics.max_acquisition_duration_ns = max(
            self.metrics.max_acquisition_duration_ns, duration
        )
        if not self._buffer.try_put(snapshot):
            self.metrics.buffer_rejection_count += 1
        return snapshot

    def run(self, stop_event: Event) -> None:
        """Run until stopped. Source errors intentionally propagate to the host."""
        while not stop_event.is_set():
            self.capture_once()
