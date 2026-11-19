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


def analyze_corner(
    lap_profile: Sequence[Mapping[str, Any]],
    corner: Mapping[str, Any],
    *,
    brake_onset_threshold: float,
    throttle_pickup_threshold: float,
    steering_threshold_rad: float,
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
    if steering_threshold_rad <= 0:
        raise ValueError("steering_threshold_rad must be positive")
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
    turn_in = next((
        point for point in points
        if isinstance(point.get("steering_angle_rad"), (int, float))
        and abs(point["steering_angle_rad"]) >= steering_threshold_rad
    ), None)
    peak_brake = max(
        (point["brake_ratio"] for point in points
         if isinstance(point.get("brake_ratio"), (int, float))),
        default=None,
    )
    entry_speed = points[0].get("speed_mps")
    exit_speed = points[-1].get("speed_mps")
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
        "profile_point_count": len(points),
        "braking_point_m": braking.get("distance_m") if braking else None,
        "peak_brake_ratio": peak_brake,
        "turn_in_point_m": turn_in.get("distance_m") if turn_in else None,
        "minimum_speed_mps": minimum_speed.get("speed_mps") if minimum_speed else None,
        "minimum_speed_point_m": minimum_speed.get("distance_m") if minimum_speed else None,
        "throttle_pickup_point_m": throttle_pickup.get("distance_m") if throttle_pickup else None,
        "entry_speed_mps": entry_speed,
        "exit_speed_mps": exit_speed,
        "corner_time_delta_s": delta,
        "missing_metrics": [
            name for name, value in (
                ("braking_point", braking),
                ("turn_in", turn_in),
                ("minimum_speed", minimum_speed),
                ("throttle_pickup", throttle_pickup),
                ("entry_speed", entry_speed),
                ("exit_speed", exit_speed),
            ) if value is None
        ],
        "interpretation": "measured_events_only",
    }
