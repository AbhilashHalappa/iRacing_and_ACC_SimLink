"""Configurable data-quality checks for normalized Performance Hub samples.

Thresholds are caller-supplied because cadence and acceptable progress deltas
must be established from measured ACC sessions, not guessed here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def channel_availability(
    rows: Sequence[Mapping[str, Any]], *, stream: str,
) -> dict[str, Any]:
    """Report per-channel present/missing counts without treating zero as missing."""
    if stream not in ("physics", "graphics"):
        raise ValueError("stream must be 'physics' or 'graphics'")
    keys = set()
    for row in rows:
        keys.update((row.get("values") or {}).keys())
    channels = {}
    total = len(rows)
    for key in sorted(keys):
        present = sum(
            1 for row in rows
            if key in (row.get("values") or {})
            and (row.get("values") or {}).get(key) is not None
        )
        channels[key] = {
            "present_samples": present,
            "missing_samples": total - present,
            "coverage_ratio": (present / total) if total else None,
            "status": "unavailable" if total == 0 or present == 0 else (
                "complete" if present == total else "partial"
            ),
        }
    return {"stream": stream, "sample_count": total, "channels": channels}


def check_progress_continuity(
    graphics_rows: Sequence[Mapping[str, Any]], *,
    max_progress_step: float,
) -> dict[str, Any]:
    """Check monotonic capture order and bounded forward progress.

    The maximum step is an explicit caller policy. Reverse/wrap transitions
    are reported rather than silently normalized because lap-boundary context
    is required to interpret them correctly.
    """
    if max_progress_step <= 0:
        raise ValueError("max_progress_step must be positive")
    rows = list(graphics_rows)
    values = [
        (row.get("values") or {}).get("track_progress_ratio")
        for row in rows
    ]
    issues = []
    timestamps = [row.get("capture_timestamp_ns") for row in rows]
    for index, (before, after) in enumerate(zip(values, values[1:])):
        left_timestamp, right_timestamp = timestamps[index:index + 2]
        if (
            not isinstance(left_timestamp, int) or isinstance(left_timestamp, bool)
            or not isinstance(right_timestamp, int) or isinstance(right_timestamp, bool)
        ):
            issues.append({"index": index, "kind": "capture_timestamp_unavailable"})
        elif right_timestamp <= left_timestamp:
            issues.append({
                "index": index, "kind": "capture_timestamp_not_increasing",
                "delta_ns": right_timestamp - left_timestamp,
            })
        if before is None or after is None:
            continue
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            issues.append({"index": index, "kind": "non_numeric_progress"})
            continue
        delta = after - before
        if delta < 0:
            issues.append({"index": index, "kind": "progress_regression", "delta": delta})
        elif delta > max_progress_step:
            issues.append({"index": index, "kind": "progress_jump", "delta": delta})
    return {
        "sample_count": len(rows),
        "checked_transitions": max(0, len(values) - 1),
        "max_progress_step": max_progress_step,
        "issues": issues,
        "ok": not issues,
    }


def check_capture_timestamp_continuity(
    rows: Sequence[Mapping[str, Any]], *, stream: str,
) -> dict[str, Any]:
    """Check source-order timestamp monotonicity for either decoded stream."""
    if stream not in ("physics", "graphics"):
        raise ValueError("stream must be 'physics' or 'graphics'")
    timestamps = [row.get("capture_timestamp_ns") for row in rows]
    issues = []
    for index, (left, right) in enumerate(zip(timestamps, timestamps[1:])):
        if (
            not isinstance(left, int) or isinstance(left, bool)
            or not isinstance(right, int) or isinstance(right, bool)
        ):
            issues.append({"index": index, "kind": "capture_timestamp_unavailable"})
        elif right <= left:
            issues.append({
                "index": index,
                "kind": "capture_timestamp_not_increasing",
                "delta_ns": right - left,
            })
    return {
        "stream": stream,
        "sample_count": len(rows),
        "checked_transitions": max(0, len(rows) - 1),
        "issues": issues,
        "ok": not issues,
    }


def summarize_alignment(
    aligned_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize timestamp-pair coverage and observed alignment error."""
    total = len(aligned_rows)
    matched = [
        row for row in aligned_rows
        if row.get("aligned") is True
        and isinstance(row.get("alignment_delta_ns"), int)
        and not isinstance(row.get("alignment_delta_ns"), bool)
    ]
    deltas = sorted(row["alignment_delta_ns"] for row in matched)
    coverage = len(matched) / total if total else None
    median = None
    if deltas:
        middle = len(deltas) // 2
        median = (
            deltas[middle] if len(deltas) % 2
            else (deltas[middle - 1] + deltas[middle]) / 2
        )
    return {
        "sample_count": total,
        "aligned_sample_count": len(matched),
        "unaligned_sample_count": total - len(matched),
        "coverage_ratio": coverage,
        "median_alignment_delta_ns": median,
        "max_alignment_delta_ns": max(deltas) if deltas else None,
        "status": "unavailable" if total == 0 or not matched else (
            "complete" if len(matched) == total else "partial"
        ),
    }


def analysis_readiness(
    physics_rows: Sequence[Mapping[str, Any]],
    graphics_rows: Sequence[Mapping[str, Any]],
    *,
    required_physics_channels: Sequence[str],
    required_graphics_channels: Sequence[str],
    minimum_channel_coverage: float,
    progress_check: Mapping[str, Any] | None = None,
    alignment_check: Mapping[str, Any] | None = None,
    minimum_alignment_coverage: float | None = None,
    physics_timestamp_check: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate analysis eligibility independently of ACC lap validity.

    This function does not decide ACC validity. Required channels and coverage
    thresholds are supplied by the analysis feature/policy using measured data.
    """
    if not 0.0 <= minimum_channel_coverage <= 1.0:
        raise ValueError("minimum_channel_coverage must be between 0 and 1")
    if minimum_alignment_coverage is not None and not 0.0 <= minimum_alignment_coverage <= 1.0:
        raise ValueError("minimum_alignment_coverage must be between 0 and 1")
    physics = channel_availability(physics_rows, stream="physics")
    graphics = channel_availability(graphics_rows, stream="graphics")
    missing = []
    for stream_name, summary, required in (
        ("physics", physics, required_physics_channels),
        ("graphics", graphics, required_graphics_channels),
    ):
        for channel in required:
            item = summary["channels"].get(channel)
            coverage = item["coverage_ratio"] if item else None
            if coverage is None or coverage < minimum_channel_coverage:
                missing.append({
                    "stream": stream_name, "channel": channel,
                    "coverage_ratio": coverage,
                })
    progress_ok = progress_check is None or bool(progress_check.get("ok"))
    physics_timestamps_ok = (
        physics_timestamp_check is None or bool(physics_timestamp_check.get("ok"))
    )
    alignment_coverage = (
        alignment_check.get("coverage_ratio")
        if isinstance(alignment_check, Mapping) else None
    )
    alignment_ok = (
        minimum_alignment_coverage is None
        or (
            isinstance(alignment_coverage, (int, float))
            and alignment_coverage >= minimum_alignment_coverage
        )
    )
    eligible = (
        bool(physics_rows and graphics_rows) and not missing and progress_ok
        and physics_timestamps_ok and alignment_ok
    )
    return {
        "eligible": eligible,
        "acc_lap_validity": "not_evaluated",
        "minimum_channel_coverage": minimum_channel_coverage,
        "physics": physics,
        "graphics": graphics,
        "required_channel_failures": missing,
        "progress_check": dict(progress_check) if progress_check is not None else None,
        "alignment_check": dict(alignment_check) if alignment_check is not None else None,
        "minimum_alignment_coverage": minimum_alignment_coverage,
        "physics_timestamp_check": dict(physics_timestamp_check) if physics_timestamp_check is not None else None,
        "reason": None if eligible else (
            "required_channels_unavailable_or_below_coverage"
            if missing else "alignment_coverage_below_policy"
            if not alignment_ok else "physics_timestamp_continuity_failed"
            if not physics_timestamps_ok else "progress_continuity_failed_or_stream_empty"
        ),
    }
