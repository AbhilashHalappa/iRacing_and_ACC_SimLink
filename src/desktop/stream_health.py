"""Independent freshness classification for ACC telemetry streams.

Physics and Graphics freshness follows the timestamp of the latest successfully
decoded sample. Static has no source packet timestamp and emits changed pages
only, so its freshness follows the Static acquirer's latest successful read.
All timestamps use the same local monotonic clock (perf_counter_ns).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Physics is polled at 480 Hz, Graphics at 100 Hz, and Static at 1 Hz.
# The thresholds tolerate short scheduling pauses without masking a stalled
# stream. Static allows three missed refresh intervals plus a small margin.
STREAM_FRESHNESS_THRESHOLDS_NS = {
    "physics": 1_000_000_000,
    "graphics": 1_500_000_000,
    "static": 3_500_000_000,
}


def build_stream_freshness(
    *,
    now_ns: int,
    timestamps_ns: Mapping[str, int | None],
    lifecycle_states: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Classify each stream independently as fresh, stale, missing or unavailable."""
    result: dict[str, dict[str, Any]] = {}
    for stream, threshold_ns in STREAM_FRESHNESS_THRESHOLDS_NS.items():
        timestamp_ns = timestamps_ns.get(stream)
        lifecycle_state = lifecycle_states.get(stream, "missing")
        age_ns = None if timestamp_ns is None else max(0, now_ns - timestamp_ns)

        if lifecycle_state in {"failed", "stopped"}:
            state = "unavailable"
        elif timestamp_ns is None:
            state = "missing"
        elif age_ns is not None and age_ns > threshold_ns:
            state = "stale"
        else:
            state = "fresh"

        result[stream] = {
            "state": state,
            "age_ms": None if age_ns is None else age_ns // 1_000_000,
            "threshold_ms": threshold_ns // 1_000_000,
            "lifecycle_state": lifecycle_state,
        }
    return result
