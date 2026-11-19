"""Geometry-only track model and configurable turn-region detection.

The model retains source XYZ coordinates and lap distance. Corner thresholds
are explicit policy inputs; no track-specific constants or coordinate-axis
assumptions are embedded here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math


def _vector(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def _length(v: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in v))


def _turn_angle(a: Sequence[float], b: Sequence[float]) -> float | None:
    la, lb = _length(a), _length(b)
    if la <= 0 or lb <= 0:
        return None
    cosine = sum(x * y for x, y in zip(a, b)) / (la * lb)
    return math.acos(max(-1.0, min(1.0, cosine)))


def build_track_model(
    trajectory: Sequence[Mapping[str, Any]],
    *,
    minimum_turn_angle_rad: float,
    minimum_corner_length_m: float,
    merge_gap_m: float = 0.0,
) -> dict[str, Any]:
    """Build a track path and ordered geometric turn regions from one lap."""
    if not 0 < minimum_turn_angle_rad < math.pi:
        raise ValueError("minimum_turn_angle_rad must be between 0 and pi")
    if minimum_corner_length_m <= 0 or merge_gap_m < 0:
        raise ValueError("corner length must be positive and merge gap non-negative")
    if len(trajectory) < 3:
        return {"available": False, "reason": "insufficient_trajectory_points", "points": [], "corners": []}

    points = list(trajectory)
    if any(
        points[i + 1]["distance_m"] <= points[i]["distance_m"]
        for i in range(len(points) - 1)
    ):
        return {"available": False, "reason": "non_monotonic_distance", "points": [], "corners": []}

    turn_segments = []
    for index in range(1, len(points) - 1):
        p0 = points[index - 1]["position_xyz_m"]
        p1 = points[index]["position_xyz_m"]
        p2 = points[index + 1]["position_xyz_m"]
        angle = _turn_angle(_vector(p0, p1), _vector(p1, p2))
        if angle is not None and angle >= minimum_turn_angle_rad:
            turn_segments.append({
                "start_distance_m": points[index - 1]["distance_m"],
                "end_distance_m": points[index + 1]["distance_m"],
                "turn_angle_rad": angle,
                "source_point_index": index,
            })

    merged = []
    for segment in turn_segments:
        if merged and segment["start_distance_m"] - merged[-1]["end_distance_m"] <= merge_gap_m:
            merged[-1]["end_distance_m"] = segment["end_distance_m"]
            merged[-1]["turn_angle_sum_rad"] += segment["turn_angle_rad"]
            if segment["turn_angle_rad"] > merged[-1]["max_turn_angle_rad"]:
                merged[-1]["max_turn_angle_rad"] = segment["turn_angle_rad"]
                merged[-1]["apex_point_index"] = segment["source_point_index"]
            merged[-1]["source_point_indices"].append(segment["source_point_index"])
        else:
            merged.append({
                "start_distance_m": segment["start_distance_m"],
                "end_distance_m": segment["end_distance_m"],
                "turn_angle_sum_rad": segment["turn_angle_rad"],
                "max_turn_angle_rad": segment["turn_angle_rad"],
                "apex_point_index": segment["source_point_index"],
                "source_point_indices": [segment["source_point_index"]],
            })

    corners = []
    for ordinal, region in enumerate(merged, start=1):
        length = region["end_distance_m"] - region["start_distance_m"]
        if length < minimum_corner_length_m:
            continue
        apex_point = points[region["apex_point_index"]]
        corners.append({
            "corner_id": f"turn-{ordinal:02d}",
            "ordinal": ordinal,
            "start_distance_m": region["start_distance_m"],
            "end_distance_m": region["end_distance_m"],
            "apex_distance_m": apex_point["distance_m"],
            "apex_position_xyz_m": tuple(apex_point["position_xyz_m"]),
            "length_m": length,
            "accumulated_turn_angle_rad": region["turn_angle_sum_rad"],
            "maximum_turn_angle_rad": region["max_turn_angle_rad"],
            "geometry_confidence": "candidate",
            "identity_scope": "lap_order_only",
        })

    return {
        "available": True,
        "coordinate_system": "source_xyz_unrotated",
        "point_count": len(points),
        "distance_start_m": points[0]["distance_m"],
        "distance_end_m": points[-1]["distance_m"],
        "turn_threshold_rad": minimum_turn_angle_rad,
        "minimum_corner_length_m": minimum_corner_length_m,
        "merge_gap_m": merge_gap_m,
        "points": [dict(point) for point in points],
        "corners": corners,
        "corner_identity_warning": "IDs are ordered within this lap and are not cross-session stable.",
    }
