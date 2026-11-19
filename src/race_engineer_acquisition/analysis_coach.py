"""Evidence-ranked post-lap coaching opportunities from measured comparisons."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def rank_corner_opportunities(
    reference_reports: Sequence[Mapping[str, Any]],
    comparison_reports: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Rank measurable corner differences without asserting unsupported causes."""
    reference = {
        row.get("corner_id"): row for row in reference_reports
        if row.get("corner_id") is not None
    }
    opportunities = []
    for current in comparison_reports:
        corner_id = current.get("corner_id")
        baseline = reference.get(corner_id)
        if baseline is None or not current.get("available") or not baseline.get("available"):
            continue
        delta = current.get("corner_time_delta_s")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool) or delta <= 0:
            continue
        differences = []
        for key, label, direction in (
            ("braking_point_m", "braking point", "later"),
            ("minimum_speed_mps", "minimum speed", "higher"),
            ("throttle_pickup_point_m", "throttle pickup", "later"),
            ("turn_in_point_m", "steering response point", "later"),
        ):
            current_value = current.get(key)
            reference_value = baseline.get(key)
            if (
                isinstance(current_value, (int, float))
                and not isinstance(current_value, bool)
                and isinstance(reference_value, (int, float))
                and not isinstance(reference_value, bool)
                and current_value != reference_value
            ):
                differences.append({
                    "metric": key,
                    "label": label,
                    "current_value": current_value,
                    "reference_value": reference_value,
                    "difference": current_value - reference_value,
                    "direction": direction if current_value > reference_value else (
                        "lower" if key == "minimum_speed_mps" else "earlier"
                    ),
                })
        if not differences:
            continue
        opportunities.append({
            "corner_id": corner_id,
            "time_loss_s": float(delta),
            "measured_differences": differences,
            "evidence_level": "measured_comparison",
            "recommendation": (
                f"Review {differences[0]['label']} at {corner_id}: "
                f"the comparison lap is {float(delta):.3f} s slower through this region."
            ),
            "causal_claim": "not_made",
        })
    opportunities.sort(key=lambda item: item["time_loss_s"], reverse=True)
    for rank, item in enumerate(opportunities, start=1):
        item["rank"] = rank
    return tuple(opportunities)


def summarize_recurring_opportunities(
    session_opportunities: Sequence[Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    """Count repeated measured opportunity types across supplied session reports."""
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for session_index, report in enumerate(session_opportunities):
        seen = set()
        for item in report:
            corner = str(item.get("corner_id", "unknown"))
            for difference in item.get("measured_differences", ()):
                metric = str(difference.get("metric", "unknown"))
                key = (corner, metric)
                if key in seen:
                    continue
                seen.add(key)
                aggregate = counts.setdefault(key, {
                    "corner_id": corner,
                    "metric": metric,
                    "session_count": 0,
                    "session_indices": [],
                })
                aggregate["session_count"] += 1
                aggregate["session_indices"].append(session_index)
    return tuple(sorted(
        counts.values(),
        key=lambda item: (-item["session_count"], item["corner_id"], item["metric"]),
    ))
