"""Evidence-gated corner metrics derived from distance-aligned lap profiles."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _first_at_or_above(
    points: Sequence[Mapping[str, Any]], channel: str, threshold: float,
    *, after_distance_m: float,
) -> Mapping[str, Any] | None:
    return next((
        point for point in points
        if point["distance_m"] >= after_distance_m
        and isinstance(point.get(channel), (int, float))
        and not isinstance(point.get(channel), bool)
        and point[channel] >= threshold
    ), None)


def _time_at_distance(
    profile: Sequence[Mapping[str, Any]], distance_m: float,
) -> float | None:
    for left, right in zip(profile, profile[1:]):
        if left["distance_m"] <= distance_m <= right["distance_m"]:
            span = right["distance_m"] - left["distance_m"]
            if span <= 0:
                return None
            ratio = (distance_m - left["distance_m"]) / span
            return left["elapsed_s"] + ratio * (right["elapsed_s"] - left["elapsed_s"])
    return None


def _value_at_distance(
    profile: Sequence[Mapping[str, Any]], channel: str, distance_m: float, *,
    max_bracket_gap_m: float, discrete: bool = False,
) -> Any:
    for left, right in zip(profile, profile[1:]):
        d0, d1 = left["distance_m"], right["distance_m"]
        if d0 <= distance_m <= d1:
            gap = d1 - d0
            if gap <= 0 or gap > max_bracket_gap_m:
                return None
            a, b = left.get(channel), right.get(channel)
            if a is None or b is None:
                return None
            ratio = (distance_m - d0) / gap
            if discrete:
                return a if ratio <= 0.5 else b
            if not isinstance(a, (int, float)) or isinstance(a, bool):
                return None
            if not isinstance(b, (int, float)) or isinstance(b, bool):
                return None
            return float(a) + ratio * (float(b) - float(a))
    return None


def analyze_corner(
    lap_profile: Sequence[Mapping[str, Any]],
    corner: Mapping[str, Any],
    *,
    brake_onset_threshold: float,
    throttle_pickup_threshold: float,
    full_throttle_threshold: float,
    steering_threshold_rad: float,
    max_bracket_gap_m: float,
    reference_profile: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure supported events in a corner distance interval.

    All thresholds are explicit feature policy. Missing channels remain
    unavailable; no brake pressure, apex, or turn-in is fabricated.
    """
    if not 0 <= brake_onset_threshold <= 1:
        raise ValueError("brake_onset_threshold must be between 0 and 1")
    if not 0 <= throttle_pickup_threshold <= 1:
        raise ValueError("throttle_pickup_threshold must be between 0 and 1")
    if not throttle_pickup_threshold <= full_throttle_threshold <= 1:
        raise ValueError("full_throttle_threshold must be at least throttle pickup and at most 1")
    if steering_threshold_rad <= 0:
        raise ValueError("steering_threshold_rad must be positive")
    if max_bracket_gap_m <= 0:
        raise ValueError("max_bracket_gap_m must be positive")
    start = corner.get("start_distance_m")
    end = corner.get("end_distance_m")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
        raise ValueError("corner must have an increasing distance interval")
    points = [
        point for point in lap_profile
        if start <= point.get("distance_m", float("-inf")) <= end
    ]
    if len(points) < 2:
        return {
            "available": False, "reason": "insufficient_corner_profile_points",
            "corner_id": corner.get("corner_id"),
        }

    braking = _first_at_or_above(
        points, "brake_ratio", brake_onset_threshold, after_distance_m=start
    )
    minimum_speed = min(
        (point for point in points if isinstance(point.get("speed_mps"), (int, float))),
        key=lambda point: point["speed_mps"],
        default=None,
    )
    throttle_start = (
        minimum_speed["distance_m"] if minimum_speed is not None else start
    )
    throttle_pickup = _first_at_or_above(
        points, "throttle_ratio", throttle_pickup_threshold,
        after_distance_m=throttle_start,
    )
    full_throttle = _first_at_or_above(
        points, "throttle_ratio", full_throttle_threshold,
        after_distance_m=throttle_start,
    )
    turn_in = next((
        point for point in points
        if isinstance(point.get("steering_angle_rad"), (int, float))
        and abs(point["steering_angle_rad"]) >= steering_threshold_rad
    ), None)
    brake_points = [
        point for point in points
        if isinstance(point.get("brake_ratio"), (int, float))
        and not isinstance(point.get("brake_ratio"), bool)
    ]
    peak_brake_point = max(
        brake_points, key=lambda point: point["brake_ratio"], default=None
    )
    peak_brake = peak_brake_point.get("brake_ratio") if peak_brake_point else None
    brake_release = None
    if peak_brake_point is not None:
        brake_release = next((
            point for point in brake_points
            if point["distance_m"] > peak_brake_point["distance_m"]
            and point["brake_ratio"] < brake_onset_threshold
        ), None)
    entry_speed = points[0].get("speed_mps")
    exit_speed = points[-1].get("speed_mps")
    geometry_apex_distance = corner.get("apex_distance_m")
    apex_metrics = {}
    if isinstance(geometry_apex_distance, (int, float)) and not isinstance(geometry_apex_distance, bool):
        for channel in (
            "speed_mps", "throttle_ratio", "brake_ratio",
            "steering_angle_rad", "engine_rpm", "brake_pressure",
        ):
            apex_metrics[channel] = _value_at_distance(
                lap_profile, channel, float(geometry_apex_distance),
                max_bracket_gap_m=max_bracket_gap_m,
            )
        apex_metrics["gear_index"] = _value_at_distance(
            lap_profile, "gear_index", float(geometry_apex_distance),
            max_bracket_gap_m=max_bracket_gap_m, discrete=True,
        )
    delta = None
    if reference_profile is not None:
        ref_entry = _time_at_distance(reference_profile, start)
        ref_exit = _time_at_distance(reference_profile, end)
        lap_entry = _time_at_distance(lap_profile, start)
        lap_exit = _time_at_distance(lap_profile, end)
        if None not in (ref_entry, ref_exit, lap_entry, lap_exit):
            delta = (lap_exit - lap_entry) - (ref_exit - ref_entry)

    return {
        "available": True,
        "corner_id": corner.get("corner_id"),
        "distance_interval_m": [start, end],
        "geometry_apex_candidate_m": geometry_apex_distance,
        "geometry_apex_position_xyz_m": corner.get("apex_position_xyz_m"),
        "apex_candidate_metrics": apex_metrics,
        "profile_point_count": len(points),
        "braking_point_m": braking.get("distance_m") if braking else None,
        "peak_brake_ratio": peak_brake,
        "peak_brake_point_m": peak_brake_point.get("distance_m") if peak_brake_point else None,
        "brake_release_point_m": brake_release.get("distance_m") if brake_release else None,
        "trail_braking_distance_m": (
            max(0.0, brake_release["distance_m"] - turn_in["distance_m"])
            if brake_release is not None and turn_in is not None else None
        ),
        "trail_braking_active_at_turn_in": (
            brake_release["distance_m"] > turn_in["distance_m"]
            if brake_release is not None and turn_in is not None else None
        ),
        "turn_in_point_m": turn_in.get("distance_m") if turn_in else None,
        "minimum_speed_mps": minimum_speed.get("speed_mps") if minimum_speed else None,
        "minimum_speed_point_m": minimum_speed.get("distance_m") if minimum_speed else None,
        "throttle_pickup_point_m": throttle_pickup.get("distance_m") if throttle_pickup else None,
        "full_throttle_point_m": full_throttle.get("distance_m") if full_throttle else None,
        "entry_speed_mps": entry_speed,
        "exit_speed_mps": exit_speed,
        "corner_time_delta_s": delta,
        "missing_metrics": [
            name for name, value in (
                ("braking_point", braking),
                ("turn_in", turn_in),
                ("minimum_speed", minimum_speed),
                ("throttle_pickup", throttle_pickup),
                ("full_throttle", full_throttle),
                ("brake_release", brake_release),
                ("entry_speed", entry_speed),
                ("exit_speed", exit_speed),
            ) if value is None
        ],
        "interpretation": "measured_events_only",
    }
