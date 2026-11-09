"""Common lock-free, single-writer acquisition health snapshots.

Each tracker is written only by its stream worker. Readers obtain the latest
immutable snapshot through one reference read; no application-wide lock or
logging is used in the acquisition path.
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


class AcquisitionHealth:
    """Single-writer health accumulator; snapshot reads never acquire a lock."""

    __slots__ = ("_snapshot",)

    def __init__(self) -> None:
        self._snapshot = AcquisitionHealthSnapshot()

    @property
    def snapshot(self) -> AcquisitionHealthSnapshot:
        return self._snapshot

    def set_lifecycle(self, state: str) -> None:
        self._snapshot = replace(self._snapshot, lifecycle_state=state)

    def record_read_success(self, timestamp_ns: int, duration_ns: int) -> None:
        current = self._snapshot
        self._snapshot = replace(
            current,
            successful_reads=current.successful_reads + 1,
            consecutive_failures=0,
            last_successful_read_ns=timestamp_ns,
            last_read_duration_ns=duration_ns,
            max_read_duration_ns=max(current.max_read_duration_ns, duration_ns),
        )

    def record_read_failure(self, error: BaseException) -> None:
        current = self._snapshot
        self._snapshot = replace(
            current,
            source_read_failures=current.source_read_failures + 1,
            consecutive_failures=current.consecutive_failures + 1,
            last_error=f"{type(error).__name__}: {error}",
        )

    def record_buffer_rejection(self) -> None:
        current = self._snapshot
        self._snapshot = replace(
            current, buffer_rejections=current.buffer_rejections + 1
        )
