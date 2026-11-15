"""Freshness-aware read-only aggregation for Race Engineer telemetry.

This module reads the existing decoded Physics/Graphics consumer snapshots and
acquisition health. It does not read shared memory, drain acquisition queues,
or mutate acquisition/recording state. Static remains raw-only: its health
freshness describes the latest successful mapping read, not decoded metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True, slots=True)
class TelemetryStreamView:
    """One decoded stream plus explicit acquisition/consumer health."""

    stream: str
    data: Any | None
    capture_timestamp_ns: int | None
    capture_sequence: int | None
    packet_id: int | None
    sample_age_ns: int | None
    max_age_ns: int
    acquisition_lifecycle: str
    consumer_lifecycle: str
    decode_error_count: int
    last_error: str | None
    is_fresh: bool

    @property
    def is_available(self) -> bool:
        return self.data is not None and self.capture_timestamp_ns is not None


@dataclass(frozen=True, slots=True)
class RawStreamHealthView:
    """Health-only view for a stream that intentionally has no live decoder."""

    stream: str
    lifecycle_state: str
    last_successful_read_ns: int | None
    read_age_ns: int | None
    source_read_failures: int
    buffer_rejections: int
    last_error: str | None
    is_read_fresh: bool


@dataclass(frozen=True, slots=True)
class RaceEngineerTelemetrySnapshot:
    """A point-in-time view; Physics and Graphics are not time-synchronized."""

    captured_at_ns: int
    physics: TelemetryStreamView
    graphics: TelemetryStreamView
    static: RawStreamHealthView
    static_decoded: TelemetryStreamView

    @property
    def live_vehicle_data_fresh(self) -> bool:
        return self.physics.is_fresh

    @property
    def race_session_data_fresh(self) -> bool:
        return self.graphics.is_fresh

    @property
    def combined_live_data_fresh(self) -> bool:
        """True only when both independent decoded streams pass freshness gates."""
        return self.physics.is_fresh and self.graphics.is_fresh


class RaceEngineerSnapshotAggregator:
    """Read existing consumers without taking ownership of their queues.

    Timestamps are local monotonic perf_counter_ns values. Physics and
    Graphics remain independent observations; this class reports each age
    separately and never claims that their latest samples are synchronized.
    """

    def __init__(
        self,
        runtime: Any,
        *,
        physics_max_age_ms: float = 500.0,
        graphics_max_age_ms: float = 1_000.0,
        static_read_max_age_ms: float = 3_000.0,
        clock_ns=time.perf_counter_ns,
    ) -> None:
        limits = (physics_max_age_ms, graphics_max_age_ms, static_read_max_age_ms)
        if any(value <= 0 for value in limits):
            raise ValueError("all stream freshness limits must be positive")
        self._runtime = runtime
        self._physics_max_age_ns = round(physics_max_age_ms * 1_000_000)
        self._graphics_max_age_ns = round(graphics_max_age_ms * 1_000_000)
        self._static_read_max_age_ns = round(static_read_max_age_ms * 1_000_000)
        self._clock_ns = clock_ns

    def snapshot(self) -> RaceEngineerTelemetrySnapshot:
        """Return latest good samples and their independent freshness state."""
        now_ns = self._clock_ns()
        physics_consumer = self._runtime.physics_consumer.snapshot
        graphics_consumer = self._runtime.graphics_consumer.snapshot
        physics_health = self._runtime.acquirers["physics"].health.snapshot
        graphics_health = self._runtime.acquirers["graphics"].health.snapshot
        static_health = self._runtime.acquirers["static"].health.snapshot
        static_consumer = self._runtime.static_consumer.snapshot

        physics = self._decoded_view(
            "physics", physics_consumer, physics_health, now_ns,
            self._physics_max_age_ns,
        )
        graphics = self._decoded_view(
            "graphics", graphics_consumer, graphics_health, now_ns,
            self._graphics_max_age_ns,
        )
        static_age = self._age(now_ns, static_health.last_successful_read_ns)
        static = RawStreamHealthView(
            stream="static",
            lifecycle_state=static_health.lifecycle_state,
            last_successful_read_ns=static_health.last_successful_read_ns,
            read_age_ns=static_age,
            source_read_failures=static_health.source_read_failures,
            buffer_rejections=static_health.buffer_rejections,
            last_error=static_health.last_error,
            is_read_fresh=(
                static_health.lifecycle_state == "running"
                and static_age is not None
                and 0 <= static_age <= self._static_read_max_age_ns
            ),
        )
        static_decoded = self._decoded_view(
            "static", static_consumer, static_health, now_ns,
            self._static_read_max_age_ns,
        )
        return RaceEngineerTelemetrySnapshot(
            captured_at_ns=now_ns,
            physics=physics,
            graphics=graphics,
            static=static,
            static_decoded=static_decoded,
        )

    @classmethod
    def _age(cls, now_ns: int, timestamp_ns: int | None) -> int | None:
        if timestamp_ns is None:
            return None
        return now_ns - timestamp_ns

    @classmethod
    def _decoded_view(
        cls,
        stream: str,
        consumer: Any,
        acquisition_health: Any,
        now_ns: int,
        max_age_ns: int,
    ) -> TelemetryStreamView:
        timestamp_ns = consumer.latest_capture_timestamp_ns
        age_ns = cls._age(now_ns, timestamp_ns)
        lifecycle_ok = (
            acquisition_health.lifecycle_state == "running"
            and consumer.lifecycle_state == "running"
        )
        fresh = (
            lifecycle_ok
            and consumer.latest is not None
            and age_ns is not None
            and 0 <= age_ns <= max_age_ns
        )
        latest = consumer.latest
        return TelemetryStreamView(
            stream=stream,
            data=latest,
            capture_timestamp_ns=timestamp_ns,
            capture_sequence=consumer.last_capture_sequence,
            packet_id=(getattr(latest, "packet_id", None) if latest is not None else None),
            sample_age_ns=age_ns,
            max_age_ns=max_age_ns,
            acquisition_lifecycle=acquisition_health.lifecycle_state,
            consumer_lifecycle=consumer.lifecycle_state,
            decode_error_count=consumer.decode_error_count,
            last_error=consumer.last_error or acquisition_health.last_error,
            is_fresh=fresh,
        )
