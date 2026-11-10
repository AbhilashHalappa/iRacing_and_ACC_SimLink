"""Acquisition loop independent of ACC-specific memory mapping."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Callable, Protocol

from .models import PhysicsSnapshot, RawPhysicsRead
from .health import AcquisitionHealth
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
    first_packet_id: int | None = None
    last_packet_id: int | None = None
    last_capture_sequence: int = 0
    last_acquisition_duration_ns: int = 0
    max_acquisition_duration_ns: int = 0
    poll_interval_count: int = 0
    total_poll_interval_ns: int = 0
    min_poll_interval_ns: int = 0
    last_poll_interval_ns: int = 0
    max_poll_interval_ns: int = 0
    poll_schedule_overrun_count: int = 0
    last_poll_lateness_ns: int = 0
    max_poll_lateness_ns: int = 0
    buffer_rejection_count: int = 0
    _previous_poll_start_ns: int | None = None


class PhysicsAcquirer:
    """Capture Physics snapshots and publish them to an SPSC ring.

    The source adapter performs only the bounded shared-memory copy and returns
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
        self.health = AcquisitionHealth()
        self._next_sequence = 1

    def capture_once(self) -> PhysicsSnapshot | None:
        poll_start_ns = self._clock_ns()
        previous_start = self.metrics._previous_poll_start_ns
        if previous_start is not None:
            interval = poll_start_ns - previous_start
            self.metrics.poll_interval_count += 1
            self.metrics.total_poll_interval_ns += interval
            self.metrics.last_poll_interval_ns = interval
            self.metrics.min_poll_interval_ns = (
                interval if self.metrics.min_poll_interval_ns == 0
                else min(self.metrics.min_poll_interval_ns, interval)
            )
            self.metrics.max_poll_interval_ns = max(
                self.metrics.max_poll_interval_ns, interval
            )
        self.metrics._previous_poll_start_ns = poll_start_ns

        for attempt in range(self._max_attempts):
            read_start_ns = self._clock_ns()
            try:
                raw: RawPhysicsRead = self._source.read_physics()
            except Exception as exc:
                self.health.record_read_failure(exc)
                raise
            read_complete_ns = self._clock_ns()
            self.health.record_read_success(
                read_complete_ns, read_complete_ns - read_start_ns
            )
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

        # Sequence numbers identify distinct, consistent source observations.
        sequence = self._next_sequence
        self._next_sequence += 1
        if previous is not None and packet_id > previous + 1:
            self.metrics.source_packet_gap_count += packet_id - previous - 1
        elif previous is not None and packet_id < previous:
            # Counter wrap/reset semantics are not guessed.
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
        if self.metrics.first_packet_id is None:
            self.metrics.first_packet_id = packet_id
        self.metrics.last_packet_id = packet_id
        duration = snapshot.acquisition_duration_ns
        self.metrics.last_acquisition_duration_ns = duration
        self.metrics.max_acquisition_duration_ns = max(
            self.metrics.max_acquisition_duration_ns, duration
        )
        if not self._buffer.try_put(snapshot):
            self.metrics.buffer_rejection_count += 1
            self.health.record_buffer_rejection()
        return snapshot

    def run(self, stop_event: Event, *, poll_interval_ns: int = 0) -> None:
        """Run until stopped.

        A zero interval means maximum-throughput polling with no intentional
        wait. A positive interval uses monotonic deadlines and Event.wait().
        Missed deadlines are skipped rather than followed by catch-up bursts.
        The actual start-to-start interval and schedule lateness are measured.
        """
        if poll_interval_ns < 0:
            raise ValueError("poll_interval_ns cannot be negative")
        if poll_interval_ns == 0:
            while not stop_event.is_set():
                self.capture_once()
            return

        next_deadline_ns = self._clock_ns()
        while not stop_event.is_set():
            now_ns = self._clock_ns()
            wait_ns = next_deadline_ns - now_ns
            if wait_ns > 0 and stop_event.wait(wait_ns / 1_000_000_000):
                break
            if stop_event.is_set():
                break

            actual_start_ns = self._clock_ns()
            lateness_ns = max(0, actual_start_ns - next_deadline_ns)
            self.metrics.last_poll_lateness_ns = lateness_ns
            self.metrics.max_poll_lateness_ns = max(
                self.metrics.max_poll_lateness_ns, lateness_ns
            )
            self.capture_once()

            next_deadline_ns += poll_interval_ns
            finished_ns = self._clock_ns()
            if next_deadline_ns <= finished_ns:
                missed = ((finished_ns - next_deadline_ns) // poll_interval_ns) + 1
                self.metrics.poll_schedule_overrun_count += missed
                next_deadline_ns += missed * poll_interval_ns
