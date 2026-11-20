"""Bounded, source-preserving snapshots of the active ACC lap trace."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StreamCaptureProvenance:
    stream: str
    sample_count: int
    first_capture_sequence: int | None
    last_capture_sequence: int | None
    first_capture_timestamp_ns: int | None
    last_capture_timestamp_ns: int | None


@dataclass(frozen=True, slots=True)
class CurrentLapTraceSnapshot:
    """Detached view of one in-progress lap; streams remain independent."""

    schema_version: int
    status: str
    session_id: str | None
    lap_number: int | None
    start_timestamp_ns: int | None
    snapshot_timestamp_ns: int | None
    physics_samples: tuple[Any, ...]
    graphics_samples: tuple[Any, ...]
    physics_provenance: StreamCaptureProvenance
    graphics_provenance: StreamCaptureProvenance
    quality_reasons: tuple[str, ...]
    overflow_streams: tuple[str, ...]
    per_stream_capacity: int
    is_complete: bool
    is_usable_for_coaching: bool


def _get(sample: Any, name: str) -> Any:
    return sample.get(name) if isinstance(sample, dict) else getattr(sample, name, None)


def _provenance(stream: str, samples: tuple[Any, ...]) -> StreamCaptureProvenance:
    if not samples:
        return StreamCaptureProvenance(stream, 0, None, None, None, None)
    first, last = samples[0], samples[-1]
    return StreamCaptureProvenance(
        stream, len(samples), _get(first, "capture_sequence"),
        _get(last, "capture_sequence"), _get(first, "capture_timestamp_ns"),
        _get(last, "capture_timestamp_ns"),
    )


def build_current_lap_trace_snapshot(*, session_id: str | None, lap_number: int | None,
        start_timestamp_ns: int | None, snapshot_timestamp_ns: int | None,
        physics_samples: tuple[Any, ...], graphics_samples: tuple[Any, ...],
        quality_reasons: tuple[str, ...], overflow_streams: tuple[str, ...],
        per_stream_capacity: int, active: bool) -> CurrentLapTraceSnapshot:
    """Build a detached snapshot without joining streams or inventing semantics."""
    physics, graphics = tuple(physics_samples), tuple(graphics_samples)
    reasons, overflow = tuple(sorted(set(quality_reasons))), tuple(sorted(set(overflow_streams)))
    usable = bool(active and session_id and lap_number is not None and physics and graphics
                  and not reasons and not overflow)
    return CurrentLapTraceSnapshot(
        schema_version=1,
        status="waiting_for_boundary" if not active else "degraded" if reasons or overflow else "active",
        session_id=session_id, lap_number=lap_number,
        start_timestamp_ns=start_timestamp_ns, snapshot_timestamp_ns=snapshot_timestamp_ns,
        physics_samples=physics, graphics_samples=graphics,
        physics_provenance=_provenance("physics", physics),
        graphics_provenance=_provenance("graphics", graphics),
        quality_reasons=reasons, overflow_streams=overflow,
        per_stream_capacity=per_stream_capacity, is_complete=False,
        is_usable_for_coaching=usable,
    )
