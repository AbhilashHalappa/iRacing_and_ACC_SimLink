"""Explicit ACC Live Coach reference selection from retained lap archives.

This module returns the original ACC archive trace and provenance. It does not
translate it into the legacy F1 reference-lap shape or invent lap semantics.
"""
from __future__ import annotations

from typing import Any, Protocol


class ReferenceArchive(Protocol):
    def read_laps(
        self, *, session_id: str | None = None, car_model: str | None = None,
        track: str | None = None, track_configuration: str | None = None,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]: ...

    def read_lap_metadata(self, session_id: str, lap_number: int) -> dict[str, Any] | None: ...

    def read_trace(self, session_id: str, lap_number: int) -> dict[str, Any] | None: ...


def _eligible(metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("lap_valid") == 1
        and not isinstance(metadata.get("lap_valid"), bool)
        and metadata.get("out_lap") == 0
        and not isinstance(metadata.get("out_lap"), bool)
        and metadata.get("trace_status") == "retained"
        and isinstance(metadata.get("session_id"), str)
        and bool(metadata.get("session_id"))
        and isinstance(metadata.get("lap_number"), int)
        and not isinstance(metadata.get("lap_number"), bool)
        and metadata.get("lap_number") >= 1
        and isinstance(metadata.get("car_model"), str)
        and bool(metadata.get("car_model").strip())
        and isinstance(metadata.get("track"), str)
        and bool(metadata.get("track").strip())
        and isinstance(metadata.get("track_configuration"), str)
        and bool(metadata.get("track_configuration").strip())
        and isinstance(metadata.get("physics_sample_count"), int)
        and metadata.get("physics_sample_count") > 0
        and isinstance(metadata.get("graphics_sample_count"), int)
        and metadata.get("graphics_sample_count") > 0
    )


def list_live_coach_reference_candidates(
    archive: ReferenceArchive,
    *,
    car_model: str,
    track: str,
    track_configuration: str,
    session_id: str | None = None,
    limit: int = 100,
) -> tuple[dict[str, Any], ...]:
    """List retained, valid, non-out laps for one exact ACC identity."""
    for name, value in (
        ("car_model", car_model), ("track", track),
        ("track_configuration", track_configuration),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if limit < 1:
        raise ValueError("limit must be positive")

    rows = archive.read_laps(
        session_id=session_id,
        car_model=car_model,
        track=track,
        track_configuration=track_configuration,
        limit=limit,
    )
    candidates = []
    for row in rows:
        if not _eligible(row):
            continue
        candidates.append({
            "session_id": row["session_id"],
            "lap_number": row["lap_number"],
            "car_model": row["car_model"],
            "track": row["track"],
            "track_configuration": row["track_configuration"],
            "lap_time_ms": row.get("lap_time_ms"),
            "completed_at_utc": row.get("completed_at_utc"),
            "physics_sample_count": row["physics_sample_count"],
            "graphics_sample_count": row["graphics_sample_count"],
            "trace_status": row["trace_status"],
            "pinned_pb": bool(row.get("pinned_pb", False)),
        })
    return tuple(candidates)


def load_live_coach_reference(
    archive: ReferenceArchive,
    *,
    session_id: str,
    lap_number: int,
    car_model: str,
    track: str,
    track_configuration: str,
) -> dict[str, Any]:
    """Load one explicitly selected, eligible ACC reference without conversion."""
    metadata = archive.read_lap_metadata(session_id, lap_number)
    if metadata is None:
        raise LookupError(f"reference lap not found: {session_id}:{lap_number}")
    if not _eligible(metadata):
        raise ValueError("reference must be a retained, valid, non-out lap with complete identity and both streams")
    expected = {
        "car_model": car_model,
        "track": track,
        "track_configuration": track_configuration,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"reference {key} does not match the requested ACC identity")

    trace = archive.read_trace(session_id, lap_number)
    if not isinstance(trace, dict) or not isinstance(trace.get("physics"), list) or not isinstance(trace.get("graphics"), list):
        raise ValueError("selected reference trace is unavailable, incomplete, or corrupt")
    if not trace["physics"] or not trace["graphics"]:
        raise ValueError("selected reference must contain Physics and Graphics samples")

    return {
        "schema_version": 1,
        "reference_id": f"{session_id}:{lap_number}",
        "session_id": session_id,
        "lap_number": lap_number,
        "car_model": car_model,
        "track": track,
        "track_configuration": track_configuration,
        "lap_time_ms": metadata.get("lap_time_ms"),
        "completed_at_utc": metadata.get("completed_at_utc"),
        "physics_sample_count": len(trace["physics"]),
        "graphics_sample_count": len(trace["graphics"]),
        "source": "performance_lap_archive",
        "trace_semantics": "original_acc_samples_with_capture_provenance",
        "physics": trace["physics"],
        "graphics": trace["graphics"],
    }
