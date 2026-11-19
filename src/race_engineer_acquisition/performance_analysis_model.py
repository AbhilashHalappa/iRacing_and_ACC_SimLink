"""Source-preserving normalized telemetry and timestamp-based stream alignment.

This is an analysis-layer adapter only. It does not acquire, decode, persist,
or mutate source samples. Raw values remain attached to every normalized row.
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from typing import Any


NORMALIZATION_VERSION = 1

# Canonical units are explicit; raw decoder units remain in source_values.
PHYSICS_CHANNELS = {
    "speed_mps": ("speed_kph", 1.0 / 3.6, "m/s"),
    "throttle_ratio": ("throttle", 1.0, "ratio"),
    "brake_ratio": ("brake", 1.0, "ratio"),
    "clutch_ratio": ("clutch", 1.0, "ratio"),
    "steering_angle_rad": ("steering_angle", 1.0, "rad"),
    "fuel_kg": ("fuel_kg", 1.0, "kg"),
    "engine_rpm": ("rpm", 1.0, "rpm"),
    "brake_bias_ratio": ("brake_bias", 1.0, "ratio"),
    "brake_pressure": ("brake_pressure", 1.0, "decoder_unit"),
    "tyre_pressure_psi": ("tyre_pressure_psi", 1.0, "psi"),
    "tyre_temperature_c": ("tyre_temp_c", 1.0, "degC"),
    "brake_temperature_c": ("brake_temp_c", 1.0, "degC"),
    "world_velocity_mps": ("velocity", 1.0, "m/s"),
    "local_velocity_mps": ("local_velocity", 1.0, "m/s"),
    "acceleration_g": ("acc_g", 1.0, "g"),
}

GRAPHICS_CHANNELS = {
    "distance_m": ("distance_traveled_m", 1.0, "m"),
    "track_progress_ratio": ("normalized_car_position", 1.0, "ratio"),
    "sector_index_raw": ("sector", 1.0, "raw_enum"),
    "last_sector_time_ms": ("last_sector_time_ms", 1.0, "ms"),
    "current_lap_time_ms": ("current_time_ms", 1.0, "ms"),
    "last_lap_time_ms": ("last_time_ms", 1.0, "ms"),
    "best_lap_time_ms": ("best_time_ms", 1.0, "ms"),
    "lap_valid_raw": ("is_valid_lap", 1.0, "boolean"),
    "player_world_position_m": ("player_world_position", 1.0, "m"),
}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and value not in (float("inf"), float("-inf"))


def normalize_sample(sample: Any) -> dict[str, Any]:
    """Normalize known channels while preserving raw values and capture provenance."""
    stream = _get(sample, "stream")
    data = _get(sample, "data", sample)
    channels = PHYSICS_CHANNELS if stream == "physics" else GRAPHICS_CHANNELS if stream == "graphics" else None
    if channels is None:
        raise ValueError(f"unsupported telemetry stream: {stream!r}")
    normalized: dict[str, Any] = {}
    units: dict[str, str] = {}
    raw: dict[str, Any] = {}
    for canonical, (source, scale, unit) in channels.items():
        value = _get(data, source)
        raw[source] = value
        if value is not None and scale != 1.0 and _finite(value):
            normalized[canonical] = value * scale
        elif value is not None and scale == 1.0:
            normalized[canonical] = value
        else:
            normalized[canonical] = None
        units[canonical] = unit
    return {
        "normalization_version": NORMALIZATION_VERSION,
        "stream": stream,
        "capture_sequence": _get(sample, "capture_sequence"),
        "capture_timestamp_ns": _get(sample, "capture_timestamp_ns"),
        "source_values": raw,
        "values": normalized,
        "units": units,
    }


def align_by_timestamp(
    physics_rows: Sequence[Mapping[str, Any]],
    graphics_rows: Sequence[Mapping[str, Any]],
    *,
    max_delta_ns: int,
) -> tuple[dict[str, Any], ...]:
    """Pair each Graphics row with its nearest Physics timestamp, never by index.

    The caller must choose max_delta_ns from the actual stream cadence and
    quality policy. Ties select the earlier Physics timestamp. Rows outside
    the tolerance remain explicitly unaligned.
    """
    if max_delta_ns < 0:
        raise ValueError("max_delta_ns must be non-negative")
    physics = sorted(
        (row for row in physics_rows if isinstance(row.get("capture_timestamp_ns"), int)),
        key=lambda row: row["capture_timestamp_ns"],
    )
    timestamps = [row["capture_timestamp_ns"] for row in physics]
    output = []
    for graphics in graphics_rows:
        timestamp = graphics.get("capture_timestamp_ns")
        if not isinstance(timestamp, int) or not timestamps:
            output.append({"graphics": graphics, "physics": None, "alignment_delta_ns": None, "aligned": False})
            continue
        index = bisect_left(timestamps, timestamp)
        candidates = []
        if index < len(physics):
            candidates.append(physics[index])
        if index:
            candidates.append(physics[index - 1])
        nearest = min(candidates, key=lambda row: (abs(row["capture_timestamp_ns"] - timestamp), row["capture_timestamp_ns"]))
        delta = abs(nearest["capture_timestamp_ns"] - timestamp)
        aligned = delta <= max_delta_ns
        output.append({
            "graphics": graphics,
            "physics": nearest if aligned else None,
            "alignment_delta_ns": delta,
            "aligned": aligned,
        })
    return tuple(output)
