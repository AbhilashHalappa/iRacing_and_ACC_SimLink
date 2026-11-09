"""Common lock-free, single-writer acquisition health snapshots.

The supervisor owns lifecycle state; the corresponding acquisition worker
owns read and buffer counters. These independent fields are published without
a shared lock, so neither writer can overwrite the other's updates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class AcquisitionHealthSnapshot:
    lifecycle_state: str = "idle"
    successful_reads: int = 0
    source_read_failures: int = 0
    consecutive_failures: int = 0
    last_successful_read_ns: int | None = None
    last_read_duration_ns: int = 0
    max_read_duration_ns: int = 0
    buffer_rejections: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class _ReadHealth:
    successful_reads: int = 0
    source_read_failures: int = 0
    consecutive_failures: int = 0
    last_successful_read_ns: int | None = None
    last_read_duration_ns: int = 0
    max_read_duration_ns: int = 0
    buffer_rejections: int = 0
    last_error: str | None = None


class AcquisitionHealth:
    """Lock-free health state with disjoint supervisor/worker ownership."""

    __slots__ = ("_lifecycle_state", "_read_health")

    def __init__(self) -> None:
        self._lifecycle_state = "idle"
        self._read_health = _ReadHealth()

    @property
    def snapshot(self) -> AcquisitionHealthSnapshot:
        reads = self._read_health
        return AcquisitionHealthSnapshot(
            lifecycle_state=self._lifecycle_state,
            successful_reads=reads.successful_reads,
            source_read_failures=reads.source_read_failures,
            consecutive_failures=reads.consecutive_failures,
            last_successful_read_ns=reads.last_successful_read_ns,
            last_read_duration_ns=reads.last_read_duration_ns,
            max_read_duration_ns=reads.max_read_duration_ns,
            buffer_rejections=reads.buffer_rejections,
            last_error=reads.last_error,
        )

    def set_lifecycle(self, state: str) -> None:
        """Supervisor-only writer for lifecycle state."""
        self._lifecycle_state = state

    def record_read_success(self, timestamp_ns: int, duration_ns: int) -> None:
        """Acquisition-worker-only writer for read metrics."""
        current = self._read_health
        self._read_health = replace(
            current,
            successful_reads=current.successful_reads + 1,
            consecutive_failures=0,
            last_successful_read_ns=timestamp_ns,
            last_read_duration_ns=duration_ns,
            max_read_duration_ns=max(current.max_read_duration_ns, duration_ns),
        )

    def record_read_failure(self, error: BaseException) -> None:
        """Acquisition-worker-only writer for source exceptions."""
        current = self._read_health
        self._read_health = replace(
            current,
            source_read_failures=current.source_read_failures + 1,
            consecutive_failures=current.consecutive_failures + 1,
            last_error=f"{type(error).__name__}: {error}",
        )

    def record_buffer_rejection(self) -> None:
        """Acquisition-worker-only writer for bounded-buffer loss."""
        current = self._read_health
        self._read_health = replace(
            current, buffer_rejections=current.buffer_rejections + 1
        )
