"""ACC-native source contract for the Performance Hub Live Coach migration.

This adapter is intentionally lossless about source provenance and conservative
about semantics. It does not manufacture F1-shaped lap distance, lap clocks,
session time, or reference-lap objects from unverified ACC fields.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ACCLiveCoachSource:
    """Detached ACC decoded inputs available to a future Live Coach adapter."""

    schema_version: int
    session_id: str | None
    decoded_source_ready: bool
    physics_fresh: bool
    physics_capture_sequence: int | None
    physics_capture_timestamp_ns: int | None
    speed_kph: float | None
    throttle: float | None
    brake: float | None
    steering_angle_raw: float | None
    gear_raw: int | None
    rpm: int | None
    graphics_fresh: bool
    graphics_capture_sequence: int | None
    graphics_capture_timestamp_ns: int | None
    graphics_status_raw: int | None
    session_index_raw: int | None
    completed_laps_raw: int | None
    current_time_ms_raw: int | None
    last_time_ms_raw: int | None
    is_valid_lap_raw: bool | None
    is_in_pit_raw: bool | None
    is_in_pit_lane_raw: bool | None
    distance_traveled_m_raw: float | None
    normalized_car_position_raw: float | None
    sector_raw: int | None
    static_fresh: bool
    static_capture_sequence: int | None
    static_capture_timestamp_ns: int | None
    car_model: str | None
    track: str | None
    track_configuration: str | None
    out_lap_fresh: bool
    out_lap_active: bool | None
    unresolved_contracts: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _value(data: Any | None, name: str) -> Any | None:
    return getattr(data, name, None) if data is not None else None


def build_acc_live_coach_source(
    telemetry: Any,
    *,
    session_id: str | None,
    out_lap_status: Any,
) -> ACCLiveCoachSource:
    """Build a detached, provenance-preserving view of the current ACC streams.

    Only fresh decoded data values are exposed. Capture sequence/timestamp
    metadata remains visible even when a stream is stale so diagnostics can
    explain why the coach is gated.
    """
    physics_view = getattr(telemetry, "physics", None)
    graphics_view = getattr(telemetry, "graphics", None)
    static_view = getattr(telemetry, "static_decoded", None)

    physics_fresh = bool(getattr(physics_view, "is_fresh", False))
    graphics_fresh = bool(getattr(graphics_view, "is_fresh", False))
    static_fresh = bool(getattr(static_view, "is_fresh", False))

    physics = getattr(physics_view, "data", None) if physics_fresh else None
    graphics = getattr(graphics_view, "data", None) if graphics_fresh else None
    static = getattr(static_view, "data", None) if static_fresh else None

    out_lap_fresh = bool(
        out_lap_status.get("fresh", False)
        if isinstance(out_lap_status, dict)
        else getattr(out_lap_status, "fresh", False)
    )
    out_lap_active = (
        out_lap_status.get("active")
        if isinstance(out_lap_status, dict)
        else getattr(out_lap_status, "active", None)
    ) if out_lap_fresh else None

    decoded_source_ready = bool(
        session_id and physics_fresh and graphics_fresh and static_fresh
        and _value(static, "track")
    )

    return ACCLiveCoachSource(
        schema_version=1,
        session_id=session_id,
        decoded_source_ready=decoded_source_ready,
        physics_fresh=physics_fresh,
        physics_capture_sequence=getattr(physics_view, "capture_sequence", None),
        physics_capture_timestamp_ns=getattr(physics_view, "capture_timestamp_ns", None),
        speed_kph=_value(physics, "speed_kph"),
        throttle=_value(physics, "throttle"),
        brake=_value(physics, "brake"),
        steering_angle_raw=_value(physics, "steering_angle"),
        gear_raw=_value(physics, "gear_raw"),
        rpm=_value(physics, "rpm"),
        graphics_fresh=graphics_fresh,
        graphics_capture_sequence=getattr(graphics_view, "capture_sequence", None),
        graphics_capture_timestamp_ns=getattr(graphics_view, "capture_timestamp_ns", None),
        graphics_status_raw=_value(graphics, "status"),
        session_index_raw=_value(graphics, "session_index"),
        completed_laps_raw=_value(graphics, "completed_laps"),
        current_time_ms_raw=_value(graphics, "current_time_ms"),
        last_time_ms_raw=_value(graphics, "last_time_ms"),
        is_valid_lap_raw=_value(graphics, "is_valid_lap"),
        is_in_pit_raw=_value(graphics, "is_in_pit"),
        is_in_pit_lane_raw=_value(graphics, "is_in_pit_lane"),
        distance_traveled_m_raw=_value(graphics, "distance_traveled_m"),
        normalized_car_position_raw=_value(graphics, "normalized_car_position"),
        sector_raw=_value(graphics, "sector"),
        static_fresh=static_fresh,
        static_capture_sequence=getattr(static_view, "capture_sequence", None),
        static_capture_timestamp_ns=getattr(static_view, "capture_timestamp_ns", None),
        car_model=_value(static, "car_model"),
        track=_value(static, "track"),
        track_configuration=_value(static, "track_configuration"),
        out_lap_fresh=out_lap_fresh,
        out_lap_active=out_lap_active if isinstance(out_lap_active, bool) else None,
        unresolved_contracts=(
            "lap_local_distance_semantics",
            "current_lap_clock_semantics",
            "monotonic_session_clock",
            "selected_high_resolution_reference_lap",
            "current_lap_trace_provider",
            "corner_coach_runtime_and_voice_delivery",
        ),
    )
