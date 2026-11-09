"""Common lock-free, single-writer acquisition health snapshots.

The supervisor owns lifecycle state; the corresponding acquisition worker
owns read and buffer counters. These independent fields are published without
a shared lock, so neither writer can overwrite the other's updates.

Worker counters are mutable and updated in place to avoid allocating a new
dataclass for every source read. A small sequence counter lets snapshot readers
obtain a coherent detached view without putting a lock in the acquisition path.
"""
from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(slots=True)
class _ReadHealth:
    """Mutable counters with exactly one acquisition-worker writer."""

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

    __slots__ = ("_lifecycle_state", "_read_health", "_read_version")

    def __init__(self) -> None:
        self._lifecycle_state = "idle"
        self._read_health = _ReadHealth()
        # Even values are stable; odd values mean the worker is updating.
        self._read_version = 0

    @property
    def snapshot(self) -> AcquisitionHealthSnapshot:
        """Return a coherent immutable view without locking the writer."""
        reads = self._read_health
        while True:
            version_before = self._read_version
            if version_before & 1:
                continue

            successful_reads = reads.successful_reads
            source_read_failures = reads.source_read_failures
            consecutive_failures = reads.consecutive_failures
            last_successful_read_ns = reads.last_successful_read_ns
            last_read_duration_ns = reads.last_read_duration_ns
            max_read_duration_ns = reads.max_read_duration_ns
            buffer_rejections = reads.buffer_rejections
            last_error = reads.last_error
            lifecycle_state = self._lifecycle_state

            version_after = self._read_version
            if version_before == version_after:
                return AcquisitionHealthSnapshot(
                    lifecycle_state=lifecycle_state,
                    successful_reads=successful_reads,
                    source_read_failures=source_read_failures,
                    consecutive_failures=consecutive_failures,
                    last_successful_read_ns=last_successful_read_ns,
                    last_read_duration_ns=last_read_duration_ns,
                    max_read_duration_ns=max_read_duration_ns,
                    buffer_rejections=buffer_rejections,
                    last_error=last_error,
                )

    def set_lifecycle(self, state: str) -> None:
        """Supervisor-only writer for lifecycle state."""
        self._lifecycle_state = state

    def record_read_success(self, timestamp_ns: int, duration_ns: int) -> None:
        """Update worker-owned read metrics in place; allocate no health object."""
        reads = self._read_health
        self._read_version += 1
        try:
            reads.successful_reads += 1
            reads.consecutive_failures = 0
            reads.last_successful_read_ns = timestamp_ns
            reads.last_read_duration_ns = duration_ns
            reads.max_read_duration_ns = max(reads.max_read_duration_ns, duration_ns)
        finally:
            self._read_version += 1

    def record_read_failure(self, error: BaseException) -> None:
        """Record a source exception without replacing the worker state object."""
        reads = self._read_health
        error_text = f"{type(error).__name__}: {error}"
        self._read_version += 1
        try:
            reads.source_read_failures += 1
            reads.consecutive_failures += 1
            reads.last_error = error_text
        finally:
            self._read_version += 1

    def record_buffer_rejection(self) -> None:
        """Record bounded-buffer loss in the worker-owned counters."""
        reads = self._read_health
        self._read_version += 1
        try:
            reads.buffer_rejections += 1
        finally:
            self._read_version += 1
