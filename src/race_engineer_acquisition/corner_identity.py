"""Conservative cross-lap corner identity matching from track-space evidence."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math


def _valid_corner_position(corner: Mapping[str, Any]) -> bool:
    position = corner.get("apex_position_xyz_m")
    distance = corner.get("apex_distance_m")
    return (
        isinstance(position, (tuple, list))
        and len(position) == 3
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in position
        )
        and isinstance(distance, (int, float))
        and not isinstance(distance, bool)
        and math.isfinite(float(distance))
    )


def match_corner_identities(
    reference_model: Mapping[str, Any],
    candidate_model: Mapping[str, Any],
    *,
    max_apex_separation_m: float,
    max_apex_distance_delta_m: float,
) -> dict[str, Any]:
    """Match candidate corners to reference corners using explicit tolerances.

    The reference model defines stable IDs. Ambiguous/unmatched candidates
    remain unassigned; no nearest-corner match is forced outside policy.
    """
    if max_apex_separation_m <= 0 or max_apex_distance_delta_m <= 0:
        raise ValueError("corner matching tolerances must be positive")
    if not reference_model.get("available") or not candidate_model.get("available"):
        return {
            **dict(candidate_model),
            "identity_matching_available": False,
            "identity_matching_reason": "track_model_unavailable",
        }
    references = [
        row for row in reference_model.get("corners", ())
        if _valid_corner_position(row)
    ]
    candidates = [
        row for row in candidate_model.get("corners", ())
        if _valid_corner_position(row)
    ]
    pairs = []
    for candidate in candidates:
        for reference in references:
            separation = math.dist(
                candidate["apex_position_xyz_m"], reference["apex_position_xyz_m"]
            )
            distance_delta = abs(
                candidate["apex_distance_m"] - reference["apex_distance_m"]
            )
            if separation <= max_apex_separation_m and distance_delta <= max_apex_distance_delta_m:
                pairs.append((separation, distance_delta, candidate, reference))
    pairs.sort(key=lambda item: (item[0], item[1]))
    used_candidates = set()
    used_references = set()
    matches = {}
    for separation, distance_delta, candidate, reference in pairs:
        candidate_key = candidate["corner_id"]
        reference_key = reference["corner_id"]
        if candidate_key in used_candidates or reference_key in used_references:
            continue
        matches[candidate_key] = {
            "stable_corner_id": reference.get("stable_corner_id") or reference_key,
            "matched_reference_corner_id": reference_key,
            "apex_separation_m": separation,
            "apex_distance_delta_m": distance_delta,
            "identity_status": "matched",
        }
        used_candidates.add(candidate_key)
        used_references.add(reference_key)
    output_corners = []
    for candidate in candidate_model.get("corners", ()):
        item = dict(candidate)
        item.update(matches.get(candidate["corner_id"], {
            "stable_corner_id": None,
            "matched_reference_corner_id": None,
            "identity_status": "unmatched",
            "apex_separation_m": None,
            "apex_distance_delta_m": None,
        }))
        output_corners.append(item)
    return {
        **dict(candidate_model),
        "corners": output_corners,
        "identity_matching_available": True,
        "identity_matching_policy": {
            "max_apex_separation_m": max_apex_separation_m,
            "max_apex_distance_delta_m": max_apex_distance_delta_m,
            "coordinate_system": "source_xyz_unrotated",
        },
    }
