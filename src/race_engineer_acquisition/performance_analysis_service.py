"""Offline orchestration for archive-backed Performance Hub lap analysis."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math

from .analysis_coach import rank_corner_opportunities
from .corner_analysis import analyze_corner
from .corner_identity import match_corner_identities
from .lap_comparison import build_lap_profile, compare_lap_profiles
from .performance_analysis_model import align_by_timestamp, normalize_sample
from .performance_data_quality import (
    analysis_readiness, check_progress_continuity,
    check_capture_timestamp_continuity, summarize_alignment,
)
from .racing_line_analysis import build_track_trajectory, compare_racing_lines
from .track_model import build_track_model


_REQUIRED_POLICY = (
    "max_alignment_delta_ns",
    "distance_step_m",
    "max_bracket_gap_m",
    "minimum_point_spacing_m",
    "minimum_channel_coverage",
    "minimum_alignment_coverage",
    "max_progress_step",
    "minimum_turn_angle_rad",
    "minimum_corner_length_m",
    "max_corner_apex_separation_m",
    "max_corner_apex_distance_delta_m",
    "merge_gap_m",
    "brake_onset_threshold",
    "throttle_pickup_threshold",
    "full_throttle_threshold",
    "steering_threshold_rad",
    "required_physics_channels",
    "required_graphics_channels",
)


def _normalized_trace(trace: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    physics = [
        normalize_sample({
            "stream": "physics",
            "capture_sequence": sample.get("capture_sequence"),
            "capture_timestamp_ns": sample.get("capture_timestamp_ns"),
            "data": sample.get("data", {}),
        })
        for sample in trace.get("physics", ())
    ]
    graphics = [
        normalize_sample({
            "stream": "graphics",
            "capture_sequence": sample.get("capture_sequence"),
            "capture_timestamp_ns": sample.get("capture_timestamp_ns"),
            "data": sample,
        })
        for sample in trace.get("graphics", ())
    ]
    return physics, graphics


def _load_eligible_trace(archive: Any, session_id: str, lap_number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = archive.read_lap_metadata(session_id, lap_number)
    if metadata is None:
        raise LookupError(f"lap not found in archive: {session_id}:{lap_number}")
    if metadata.get("lap_valid") != 1 or metadata.get("out_lap") != 0:
        raise ValueError(f"lap is not an eligible valid non-out lap: {session_id}:{lap_number}")
    if metadata.get("trace_status") not in ("retained", "identity_incomplete"):
        raise ValueError(f"lap has no retained full trace: {session_id}:{lap_number}")
    trace = archive.read_trace(session_id, lap_number)
    if not isinstance(trace, dict) or not isinstance(trace.get("physics"), list) or not isinstance(trace.get("graphics"), list):
        raise ValueError(f"lap trace is unavailable or corrupt: {session_id}:{lap_number}")
    return metadata, trace


def _analyse_one_lap(
    metadata: Mapping[str, Any], trace: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    physics, graphics = _normalized_trace(trace)
    aligned = align_by_timestamp(
        physics, graphics, max_delta_ns=policy["max_alignment_delta_ns"]
    )
    profile = build_lap_profile(aligned)
    trajectory = build_track_trajectory(
        trace.get("graphics", ()),
        minimum_point_spacing_m=policy["minimum_point_spacing_m"],
    )
    progress = check_progress_continuity(
        graphics, max_progress_step=policy["max_progress_step"]
    )
    physics_timestamp_quality = check_capture_timestamp_continuity(
        physics, stream="physics"
    )
    alignment_quality = summarize_alignment(aligned)
    readiness = analysis_readiness(
        physics, graphics,
        required_physics_channels=policy["required_physics_channels"],
        required_graphics_channels=policy["required_graphics_channels"],
        minimum_channel_coverage=policy["minimum_channel_coverage"],
        progress_check=progress,
        alignment_check=alignment_quality,
        minimum_alignment_coverage=policy["minimum_alignment_coverage"],
        physics_timestamp_check=physics_timestamp_quality,
    )
    return {
        "metadata": dict(metadata),
        "physics": physics,
        "graphics": graphics,
        "aligned": aligned,
        "profile": profile,
        "trajectory": trajectory,
        "progress_quality": progress,
        "physics_timestamp_quality": physics_timestamp_quality,
        "alignment_quality": alignment_quality,
        "readiness": readiness,
    }


def analyze_archived_laps(
    archive: Any,
    *,
    reference_session_id: str,
    reference_lap_number: int,
    comparison_session_id: str,
    comparison_lap_number: int,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Run archive-backed comparison, geometry, corner metrics and coaching.

    Policy values are mandatory and measured/tuned by the caller. This keeps
    sample cadence, alignment tolerance, geometry thresholds and channel
    coverage out of guessed defaults.
    """
    missing_policy = [name for name in _REQUIRED_POLICY if name not in policy]
    if missing_policy:
        raise ValueError("missing analysis policy values: " + ", ".join(missing_policy))
    numeric_policy = (
        "max_alignment_delta_ns", "distance_step_m", "max_bracket_gap_m",
        "minimum_point_spacing_m", "minimum_channel_coverage", "minimum_alignment_coverage",
        "max_progress_step", "minimum_turn_angle_rad",
        "minimum_corner_length_m", "merge_gap_m",
        "max_corner_apex_separation_m", "max_corner_apex_distance_delta_m",
        "brake_onset_threshold", "throttle_pickup_threshold", "full_throttle_threshold",
        "steering_threshold_rad",
    )
    if any(
        not isinstance(policy[name], (int, float))
        or isinstance(policy[name], bool)
        or not math.isfinite(float(policy[name]))
        for name in numeric_policy
    ):
        raise ValueError("all numeric analysis policy values must be finite numbers")
    if policy["max_alignment_delta_ns"] < 0:
        raise ValueError("max_alignment_delta_ns must be non-negative")
    if policy["distance_step_m"] <= 0 or policy["max_bracket_gap_m"] <= 0:
        raise ValueError("distance comparison policy values must be positive")
    if policy["minimum_point_spacing_m"] < 0:
        raise ValueError("minimum_point_spacing_m must be non-negative")
    if not 0 <= policy["minimum_channel_coverage"] <= 1:
        raise ValueError("minimum_channel_coverage must be between 0 and 1")
    if policy["max_progress_step"] <= 0:
        raise ValueError("max_progress_step must be positive")
    if not 0 < policy["minimum_turn_angle_rad"] < math.pi:
        raise ValueError("minimum_turn_angle_rad must be between 0 and pi")
    if policy["minimum_corner_length_m"] <= 0 or policy["merge_gap_m"] < 0:
        raise ValueError("corner geometry policy is invalid")
    if policy["max_corner_apex_separation_m"] <= 0 or policy["max_corner_apex_distance_delta_m"] <= 0:
        raise ValueError("corner identity tolerances must be positive")
    if not 0 <= policy["brake_onset_threshold"] <= 1 or not 0 <= policy["throttle_pickup_threshold"] <= 1 or not 0 <= policy["full_throttle_threshold"] <= 1:
        raise ValueError("pedal event thresholds must be between 0 and 1")
    if policy["full_throttle_threshold"] < policy["throttle_pickup_threshold"]:
        raise ValueError("full_throttle_threshold must not be below throttle_pickup_threshold")
    if policy["steering_threshold_rad"] <= 0:
        raise ValueError("steering_threshold_rad must be positive")

    reference_metadata, reference_trace = _load_eligible_trace(
        archive, reference_session_id, reference_lap_number
    )
    comparison_metadata, comparison_trace = _load_eligible_trace(
        archive, comparison_session_id, comparison_lap_number
    )
    reference = _analyse_one_lap(reference_metadata, reference_trace, policy)
    comparison = _analyse_one_lap(comparison_metadata, comparison_trace, policy)

    delta = compare_lap_profiles(
        reference["profile"], comparison["profile"],
        distance_step_m=policy["distance_step_m"],
        max_bracket_gap_m=policy["max_bracket_gap_m"],
    )
    track_model = build_track_model(
        reference["trajectory"],
        minimum_turn_angle_rad=policy["minimum_turn_angle_rad"],
        minimum_corner_length_m=policy["minimum_corner_length_m"],
        merge_gap_m=policy["merge_gap_m"],
    )
    comparison_track_model = build_track_model(
        comparison["trajectory"],
        minimum_turn_angle_rad=policy["minimum_turn_angle_rad"],
        minimum_corner_length_m=policy["minimum_corner_length_m"],
        merge_gap_m=policy["merge_gap_m"],
    )
    comparison_track_model = match_corner_identities(
        track_model,
        comparison_track_model,
        max_apex_separation_m=policy["max_corner_apex_separation_m"],
        max_apex_distance_delta_m=policy["max_corner_apex_distance_delta_m"],
    )
    reference_corners = []
    comparison_corners = []
    if track_model["available"]:
        for corner in track_model["corners"]:
            reference_corners.append(analyze_corner(
                reference["profile"], corner,
                brake_onset_threshold=policy["brake_onset_threshold"],
                throttle_pickup_threshold=policy["throttle_pickup_threshold"],
                full_throttle_threshold=policy["full_throttle_threshold"],
                steering_threshold_rad=policy["steering_threshold_rad"],
                max_bracket_gap_m=policy["max_bracket_gap_m"],
            ))
            comparison_corners.append(analyze_corner(
                comparison["profile"], corner,
                brake_onset_threshold=policy["brake_onset_threshold"],
                throttle_pickup_threshold=policy["throttle_pickup_threshold"],
                full_throttle_threshold=policy["full_throttle_threshold"],
                steering_threshold_rad=policy["steering_threshold_rad"],
                reference_profile=reference["profile"],
            ))

    racing_line = compare_racing_lines(
        reference["trajectory"], comparison["trajectory"],
        distance_step_m=policy["distance_step_m"],
        max_bracket_gap_m=policy["max_bracket_gap_m"],
    )
    coaching = rank_corner_opportunities(reference_corners, comparison_corners)
    return {
        "reference": {
            "session_id": reference_session_id,
            "lap_number": reference_lap_number,
            "lap_time_ms": reference_metadata.get("lap_time_ms"),
            "readiness": reference["readiness"],
            "progress_quality": reference["progress_quality"],
            "physics_timestamp_quality": reference["physics_timestamp_quality"],
            "alignment_quality": reference["alignment_quality"],
        },
        "comparison": {
            "session_id": comparison_session_id,
            "lap_number": comparison_lap_number,
            "lap_time_ms": comparison_metadata.get("lap_time_ms"),
            "readiness": comparison["readiness"],
            "progress_quality": comparison["progress_quality"],
            "physics_timestamp_quality": comparison["physics_timestamp_quality"],
            "alignment_quality": comparison["alignment_quality"],
        },
        "lap_delta": delta,
        "track_model": track_model,
        "comparison_track_model": comparison_track_model,
        "reference_corner_metrics": reference_corners,
        "comparison_corner_metrics": comparison_corners,
        "racing_line": racing_line,
        "analysis_coach_opportunities": coaching,
        "analysis_policy": dict(policy),
        "status": "complete" if reference["readiness"]["eligible"] and comparison["readiness"]["eligible"] else "partial_data_quality",
    }
