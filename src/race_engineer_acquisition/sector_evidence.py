"""Conservative sector observations from ACC Graphics source evidence.

ACC sector enum and last-sector-time semantics are deliberately left raw.
This module identifies observed value changes but does not assign a timing
value to a named sector or manufacture missing sector boundaries.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def build_sector_observations(
    graphics_samples: Sequence[Any],
) -> tuple[dict[str, Any], ...]:
    """Emit raw sector/time observations with original Graphics provenance."""
    observations = []
    previous_sector = None
    previous_sector_time = None
    for sample in graphics_samples:
        data = _get(sample, "data", sample)
        sector = _get(data, "sector")
        sector_time = _get(data, "last_sector_time_ms")
        sector_changed = sector is not None and (
            previous_sector is None or sector != previous_sector
        )
        sector_time_changed = sector_time is not None and (
            previous_sector_time is None or sector_time != previous_sector_time
        )
        if sector_changed or sector_time_changed:
            observations.append({
                "observation_kind": "raw_sector_state_observation",
                "source_stream": "graphics",
                "capture_sequence": _get(sample, "capture_sequence"),
                "capture_timestamp_ns": _get(sample, "capture_timestamp_ns"),
                "sector_raw": sector,
                "last_sector_time_ms_raw": sector_time,
                "sector_value_changed": sector_changed,
                "last_sector_time_value_changed": sector_time_changed,
                "sector_time_assignment": "not_inferred",
            })
        if sector is not None:
            previous_sector = sector
        if sector_time is not None:
            previous_sector_time = sector_time
    return tuple(observations)


def summarize_sector_evidence(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize observation coverage without converting it into sector results."""
    sector_changes = sum(bool(row.get("sector_value_changed")) for row in observations)
    timing_changes = sum(bool(row.get("last_sector_time_value_changed")) for row in observations)
    return {
        "observation_count": len(observations),
        "sector_value_change_count": sector_changes,
        "last_sector_time_value_change_count": timing_changes,
        "raw_sector_values": list(dict.fromkeys(
            row.get("sector_raw") for row in observations
            if row.get("sector_raw") is not None
        )),
        "sector_times_ms_raw": list(dict.fromkeys(
            row.get("last_sector_time_ms_raw") for row in observations
            if row.get("last_sector_time_ms_raw") is not None
        )),
        "sector_time_assignment": "not_inferred",
    }
