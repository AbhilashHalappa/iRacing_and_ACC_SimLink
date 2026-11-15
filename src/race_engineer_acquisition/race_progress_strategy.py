"""Conservative race-progress observations from fresh decoded ACC Graphics.

The current Stage 2 aggregate exposes Graphics but not decoded Static metadata.
Consequently this module reports validated observations only: it does not map
ACC session enum values, infer timed-vs-lap race mode, or estimate finish fuel.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class RaceProgressAssessment:
    status: str
    session_mode: str
    session_type_code: int | None
    completed_laps: int | None
    session_time_remaining_s: float | None
    lap_limit_candidate: int | None
    lap_limit_qualified: bool
    laps_remaining: int | None
    projected_fuel_required_l: float | None
    blockers: tuple[str, ...]


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def assess_race_progress(telemetry: Any) -> RaceProgressAssessment:
    """Expose fresh LIVE progress fields without guessing session semantics.

    Graphics.session_time_left_ms is validated from live ACC observations and
    converted to seconds for the public race-progress payload. The numeric
    session enum is retained but not mapped. Graphics.number_of_laps is exposed
    only as an unqualified candidate because the current live audit has not
    validated it against a known lap-limited session. Static.is_timed_race is
    not consumed here because Static is not part of the decoded Stage 2 view.
    """
    view = getattr(telemetry, "graphics", None)
    graphics = getattr(view, "data", None) if view is not None else None
    fresh = bool(getattr(view, "is_fresh", False)) if view is not None else False
    blockers: list[str] = []

    if not fresh or graphics is None or getattr(graphics, "status", None) != 2:
        return RaceProgressAssessment(
            status="unavailable",
            session_mode="unknown",
            session_type_code=None,
            completed_laps=None,
            session_time_remaining_s=None,
            lap_limit_candidate=None,
            lap_limit_qualified=False,
            laps_remaining=None,
            projected_fuel_required_l=None,
            blockers=("Fresh LIVE ACC Graphics data is unavailable.",),
        )

    session_type = _integer(getattr(graphics, "session", None))
    completed_laps = _integer(getattr(graphics, "completed_laps", None))
    raw_time_remaining_ms = _finite_nonnegative(
        getattr(graphics, "session_time_left_ms", None)
    )
    time_remaining = (
        raw_time_remaining_ms / 1000.0
        if raw_time_remaining_ms is not None
        else None
    )
    lap_limit = _integer(getattr(graphics, "number_of_laps", None))
    if time_remaining is None:
        blockers.append("ACC session time remaining is unavailable or invalid.")
    blockers.append("ACC Graphics session-type enum mapping is not qualified.")
    blockers.append("ACC Graphics number_of_laps has not been live-qualified as a lap limit.")
    blockers.append("Decoded Static race-mode metadata is not yet connected to Stage 2.")

    return RaceProgressAssessment(
        status="observing",
        session_mode="unknown",
        session_type_code=session_type,
        completed_laps=completed_laps,
        session_time_remaining_s=time_remaining,
        lap_limit_candidate=lap_limit if lap_limit and lap_limit > 0 else None,
        lap_limit_qualified=False,
        laps_remaining=None,
        projected_fuel_required_l=None,
        blockers=tuple(blockers),
    )


def race_progress_payload(assessment: RaceProgressAssessment) -> dict[str, Any]:
    """Return a JSON-serializable service payload."""
    return asdict(assessment)
