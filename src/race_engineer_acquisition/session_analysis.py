"""Session and lap-history summaries from archived lap metadata only."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean, pstdev
from typing import Any


def build_session_summary(
    lap_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize classification, timing, consistency and recording coverage."""
    ordered = sorted(
        lap_rows,
        key=lambda row: (
            row.get("end_timestamp_ns")
            if isinstance(row.get("end_timestamp_ns"), int) else -1,
            row.get("lap_number") if isinstance(row.get("lap_number"), int) else -1,
        ),
    )
    eligible = [
        row for row in ordered
        if row.get("lap_valid") == 1
        and row.get("out_lap") == 0
        and isinstance(row.get("lap_time_ms"), int)
        and not isinstance(row.get("lap_time_ms"), bool)
        and row["lap_time_ms"] > 0
    ]
    times = [row["lap_time_ms"] for row in eligible]
    best = min(times) if times else None
    last = eligible[-1] if eligible else None
    valid_count = sum(row.get("lap_valid") == 1 and row.get("out_lap") == 0 for row in ordered)
    invalid_count = sum(row.get("lap_valid") == 0 for row in ordered)
    out_lap_count = sum(row.get("out_lap") == 1 for row in ordered)
    unknown_count = sum(row.get("lap_valid") is None or row.get("out_lap") is None for row in ordered)
    full_trace_count = sum(
        row.get("trace_status") in ("retained", "identity_incomplete")
        for row in ordered
    )
    compact_count = sum(row.get("trace_status") == "compact_metadata" for row in ordered)

    history = []
    for row in ordered:
        lap_time = row.get("lap_time_ms")
        eligible_time = (
            isinstance(lap_time, int) and not isinstance(lap_time, bool)
            and lap_time > 0 and row.get("lap_valid") == 1 and row.get("out_lap") == 0
        )
        quality = row.get("quality") if isinstance(row.get("quality"), Mapping) else {}
        history.append({
            "lap_number": row.get("lap_number"),
            "lap_time_ms": lap_time,
            "delta_to_best_ms": lap_time - best if eligible_time and best is not None else None,
            "lap_valid": row.get("lap_valid"),
            "out_lap": row.get("out_lap"),
            "trace_status": row.get("trace_status"),
            "physics_sample_count": row.get("physics_sample_count"),
            "graphics_sample_count": row.get("graphics_sample_count"),
            "graphics_position_sample_count": quality.get("graphics_position_sample_count"),
            "graphics_timing_observation_count": quality.get("graphics_timing_observation_count"),
            "reason": row.get("reason"),
        })

    return {
        "lap_count": len(ordered),
        "eligible_valid_lap_count": len(eligible),
        "valid_classified_lap_count": valid_count,
        "invalid_lap_count": invalid_count,
        "out_lap_count": out_lap_count,
        "classification_unknown_count": unknown_count,
        "full_trace_count": full_trace_count,
        "compact_metadata_count": compact_count,
        "best_lap_time_ms": best,
        "last_eligible_lap_time_ms": last.get("lap_time_ms") if last else None,
        "average_lap_time_ms": mean(times) if times else None,
        "lap_time_stddev_ms": pstdev(times) if len(times) >= 2 else None,
        "consistency_sample_count": len(times),
        "theoretical_best": {
            "available": False,
            "reason": "authoritative_sector_time_assignment_not_verified",
        },
        "lap_history": history,
    }
