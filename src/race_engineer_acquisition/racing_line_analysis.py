"""Position-qualified track trajectories and distance-aligned racing-line comparison.

Coordinates are retained as source XYZ vectors. This module does not assume
which horizontal axes ACC uses, rotate coordinates, or infer a track heading.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math


def _xyz(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        return None
    if any(
        not isinstance(item, (int, float)) or isinstance(item, bool)
        or not math.isfinite(float(item))
        for item in value
    ):
        return None
    return float(value[0]), float(value[1]), float(value[2])


def _sample_data(sample: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = sample.get("data")
    return nested if isinstance(nested, Mapping) else sample


def build_track_trajectory(
    graphics_samples: Sequence[Mapping[str, Any]],
    *,
    minimum_point_spacing_m: float = 0.25,
) -> tuple[dict[str, Any], ...]:
    """Extract ordered XYZ path points with source timing and lap distance."""
    if minimum_point_spacing_m < 0:
        raise ValueError("minimum_point_spacing_m must be non-negative")
    points = []
    last_position = None
    source_distance_origin = None
    for sample in graphics_samples:
        data = _sample_data(sample)
        position = _xyz(data.get("player_world_position"))
        distance = data.get("distance_traveled_m")
        timestamp = sample.get("capture_timestamp_ns")
        sequence = sample.get("capture_sequence")
        if not isinstance(distance, (int, float)) or isinstance(distance, bool):
            continue
        if not math.isfinite(float(distance)):
            continue
        if source_distance_origin is None:
            source_distance_origin = float(distance)
        if position is None or not isinstance(timestamp, int) or isinstance(timestamp, bool):
            continue
        if points and timestamp <= points[-1]["capture_timestamp_ns"]:
            return ()
        lap_distance = float(distance) - source_distance_origin
        if points and lap_distance <= points[-1]["distance_m"]:
            return ()
        if last_position is not None:
            spacing = math.dist(last_position, position)
            if spacing < minimum_point_spacing_m:
                continue
        points.append({
            "distance_m": lap_distance,
            "source_distance_m": float(distance),
            "position_xyz_m": position,
            "capture_timestamp_ns": timestamp,
            "capture_sequence": sequence,
        })
        last_position = position
    if len(points) < 2:
        return ()
    if any(
        right["capture_timestamp_ns"] <= left["capture_timestamp_ns"]
        or right["distance_m"] <= left["distance_m"]
        for left, right in zip(points, points[1:])
    ):
        return ()
    return tuple(points)


def _position_at_distance(
    trajectory: Sequence[Mapping[str, Any]],
    distance_m: float,
    *,
    max_bracket_gap_m: float,
) -> tuple[float, float, float] | None:
    for left, right in zip(trajectory, trajectory[1:]):
        d0, d1 = left["distance_m"], right["distance_m"]
        if d0 <= distance_m <= d1:
            gap = d1 - d0
            if gap <= 0 or gap > max_bracket_gap_m:
                return None
            ratio = (distance_m - d0) / gap
            a, b = left["position_xyz_m"], right["position_xyz_m"]
            return tuple(a[i] + ratio * (b[i] - a[i]) for i in range(3))
    return None


def compare_racing_lines(
    reference: Sequence[Mapping[str, Any]],
    comparison: Sequence[Mapping[str, Any]],
    *,
    distance_step_m: float,
    max_bracket_gap_m: float,
) -> dict[str, Any]:
    """Compare XYZ separation at common lap distances; no spatial extrapolation."""
    if distance_step_m <= 0 or max_bracket_gap_m <= 0:
        raise ValueError("distance_step_m and max_bracket_gap_m must be positive")
    if len(reference) < 2 or len(comparison) < 2:
        return {"available": False, "reason": "insufficient_position_points", "samples": []}
    start = max(reference[0]["distance_m"], comparison[0]["distance_m"])
    end = min(reference[-1]["distance_m"], comparison[-1]["distance_m"])
    if end <= start:
        return {"available": False, "reason": "no_common_distance_range", "samples": []}
    output = []
    distance = start
    while distance <= end + 1e-9:
        ref_pos = _position_at_distance(reference, distance, max_bracket_gap_m=max_bracket_gap_m)
        cmp_pos = _position_at_distance(comparison, distance, max_bracket_gap_m=max_bracket_gap_m)
        if ref_pos is not None and cmp_pos is not None:
            output.append({
                "distance_m": distance,
                "reference_position_xyz_m": ref_pos,
                "comparison_position_xyz_m": cmp_pos,
                "separation_m": math.dist(ref_pos, cmp_pos),
            })
        distance += distance_step_m
    return {
        "available": bool(output),
        "reason": None if output else "no_samples_within_bracket_gap_policy",
        "distance_step_m": distance_step_m,
        "max_bracket_gap_m": max_bracket_gap_m,
        "samples": output,
    }
