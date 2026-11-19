"""Distance-aligned lap comparison derived only from normalized source observations."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_lap_profile(
    aligned_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, float], ...]:
    """Build distance/time/speed points from timestamp-aligned stream observations."""
    points = []
    for pair in aligned_rows:
        if not pair.get("aligned"):
            continue
        physics = pair.get("physics")
        graphics = pair.get("graphics")
        if not isinstance(physics, Mapping) or not isinstance(graphics, Mapping):
            continue
        physics_values = physics.get("values") or {}
        graphics_values = graphics.get("values") or {}
        timestamp = physics.get("capture_timestamp_ns")
        distance = graphics_values.get("distance_m")
        speed = physics_values.get("speed_mps")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            continue
        if not isinstance(distance, (int, float)) or isinstance(distance, bool):
            continue
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            continue
        points.append((
            float(distance), timestamp, float(speed),
            physics_values.get("throttle_ratio"),
            physics_values.get("brake_ratio"),
            physics_values.get("steering_angle_rad"),
            physics_values.get("gear_index"),
            physics_values.get("engine_rpm"),
            physics_values.get("brake_pressure"),
        ))
    points.sort(key=lambda item: item[1])
    if len(points) < 2:
        return ()
    origin_ns = points[0][1]
    result = []
    previous_distance = None
    previous_timestamp = None
    distance_origin = points[0][0]
    for source_distance, timestamp, speed, throttle, brake, steering, gear, rpm, brake_pressure in points:
        distance = source_distance - distance_origin
        if previous_distance is not None and (distance <= previous_distance or timestamp <= previous_timestamp):
            return ()
        result.append({
            "distance_m": distance,
            "source_distance_m": source_distance,
            "elapsed_s": (timestamp - origin_ns) / 1_000_000_000,
            "speed_mps": speed,
            "throttle_ratio": throttle,
            "brake_ratio": brake,
            "steering_angle_rad": steering,
            "gear_index": gear,
            "engine_rpm": rpm,
            "brake_pressure": brake_pressure,
        })
        previous_distance = distance
        previous_timestamp = timestamp
    return tuple(result) if len(result) >= 2 else ()


def _time_at_distance(
    profile: Sequence[Mapping[str, float]], distance: float, *,
    max_bracket_gap_m: float,
) -> float | None:
    for left, right in zip(profile, profile[1:]):
        x0, x1 = left["distance_m"], right["distance_m"]
        if x0 <= distance <= x1:
            gap = x1 - x0
            if gap <= 0 or gap > max_bracket_gap_m:
                return None
            ratio = (distance - x0) / gap
            return left["elapsed_s"] + ratio * (right["elapsed_s"] - left["elapsed_s"])
    return None


def _value_at_distance(
    profile: Sequence[Mapping[str, Any]], key: str, distance: float, *,
    max_bracket_gap_m: float, discrete: bool = False,
) -> Any:
    for left, right in zip(profile, profile[1:]):
        x0, x1 = left["distance_m"], right["distance_m"]
        if x0 <= distance <= x1:
            gap = x1 - x0
            if gap <= 0 or gap > max_bracket_gap_m:
                return None
            a, b = left.get(key), right.get(key)
            if a is None or b is None:
                return None
            ratio = (distance - x0) / gap
            if discrete:
                return a if ratio <= 0.5 else b
            if not isinstance(a, (int, float)) or isinstance(a, bool):
                return None
            if not isinstance(b, (int, float)) or isinstance(b, bool):
                return None
            return float(a) + ratio * (float(b) - float(a))
    return None


def compare_lap_profiles(
    reference: Sequence[Mapping[str, float]],
    comparison: Sequence[Mapping[str, float]],
    *,
    distance_step_m: float,
    max_bracket_gap_m: float,
) -> dict[str, Any]:
    """Return comparison-minus-reference elapsed time on a shared distance grid.

    Positive delta means the comparison lap is behind the reference at that
    distance. No extrapolation is performed outside either recorded profile.
    """
    if distance_step_m <= 0 or max_bracket_gap_m <= 0:
        raise ValueError("distance_step_m and max_bracket_gap_m must be positive")
    if len(reference) < 2 or len(comparison) < 2:
        return {"available": False, "reason": "insufficient_profile_points", "samples": []}
    start = max(reference[0]["distance_m"], comparison[0]["distance_m"])
    end = min(reference[-1]["distance_m"], comparison[-1]["distance_m"])
    if end <= start:
        return {"available": False, "reason": "no_common_distance_range", "samples": []}
    sample_count = int((end - start) / distance_step_m) + 1
    if sample_count > 100_000:
        raise ValueError("distance grid exceeds the 100000-sample safety limit")
    samples = []
    distance = start
    while distance <= end + 1e-9:
        reference_time = _time_at_distance(reference, distance, max_bracket_gap_m=max_bracket_gap_m)
        comparison_time = _time_at_distance(comparison, distance, max_bracket_gap_m=max_bracket_gap_m)
        if reference_time is not None and comparison_time is not None:
            sample = {
                "distance_m": distance,
                "reference_elapsed_s": reference_time,
                "comparison_elapsed_s": comparison_time,
                "delta_s": comparison_time - reference_time,
            }
            for channel in (
                "speed_mps", "throttle_ratio", "brake_ratio",
                "steering_angle_rad", "engine_rpm",
            ):
                ref_value = _value_at_distance(
                    reference, channel, distance, max_bracket_gap_m=max_bracket_gap_m
                )
                cmp_value = _value_at_distance(
                    comparison, channel, distance, max_bracket_gap_m=max_bracket_gap_m
                )
                sample[f"reference_{channel}"] = ref_value
                sample[f"comparison_{channel}"] = cmp_value
                sample[f"{channel}_delta"] = (
                    cmp_value - ref_value
                    if ref_value is not None and cmp_value is not None else None
                )
            ref_gear = _value_at_distance(
                reference, "gear_index", distance,
                max_bracket_gap_m=max_bracket_gap_m, discrete=True,
            )
            cmp_gear = _value_at_distance(
                comparison, "gear_index", distance,
                max_bracket_gap_m=max_bracket_gap_m, discrete=True,
            )
            sample["reference_gear_index"] = ref_gear
            sample["comparison_gear_index"] = cmp_gear
            sample["gear_changed"] = (
                cmp_gear != ref_gear
                if ref_gear is not None and cmp_gear is not None else None
            )
            samples.append(sample)
        distance += distance_step_m
    return {
        "available": bool(samples),
        "reason": None if samples else "no_samples_within_bracket_gap_policy",
        "distance_step_m": distance_step_m,
        "max_bracket_gap_m": max_bracket_gap_m,
        "samples": samples,
    }
