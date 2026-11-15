"""Conservative race-progress observations from fresh decoded ACC streams.

Race mode comes from fresh Static metadata. Graphics session codes, lap limits,
and the chequered flag remain unqualified observations until live-validated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class RaceProgressAssessment:
    status: str
    session_mode: str
    session_mode_source: str | None
    has_extra_lap: bool | None
    chequered_flag_candidate: bool | None
    chequered_flag_qualified: bool
    session_type_code: int | None
    session_type_label: str | None
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
    converted to seconds for the public race-progress payload. Graphics session codes 0 (Practice) and 2 (Race) are mapped from the
    user's live ACC observations; all other codes remain unknown. Graphics.number_of_laps is exposed
    only as an unqualified candidate because the current live audit has not
    validated it against a known lap-limited session. Static.is_timed_race classifies mode only when Static metadata is fresh. The
    Graphics global_chequered value is exposed as an unqualified candidate.
    """
    view = getattr(telemetry, "graphics", None)
    graphics = getattr(view, "data", None) if view is not None else None
    fresh = bool(getattr(view, "is_fresh", False)) if view is not None else False
    blockers: list[str] = []

    if not fresh or graphics is None or getattr(graphics, "status", None) != 2:
        return RaceProgressAssessment(
            status="unavailable",
            session_mode="unknown",
            session_mode_source=None,
            has_extra_lap=None,
            chequered_flag_candidate=None,
            chequered_flag_qualified=False,
            session_type_code=None,
            session_type_label=None,
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
    static_view = getattr(telemetry, "static_decoded", None)
    static_data = (
        getattr(static_view, "data", None)
        if static_view is not None and getattr(static_view, "is_fresh", False)
        else None
    )
    timed_flag = getattr(static_data, "is_timed_race", None)
    has_extra_lap = getattr(static_data, "has_extra_lap", None)
    chequered_candidate = getattr(graphics, "global_chequered", None)
    if not isinstance(chequered_candidate, bool):
        chequered_candidate = None
    if isinstance(timed_flag, bool):
        session_mode = "timed" if timed_flag else "lap_based"
        session_mode_source = "ACC_Static.is_timed_race"
    else:
        session_mode = "unknown"
        session_mode_source = None
        blockers.append("Fresh decoded ACC Static race-mode metadata is unavailable.")
    if not isinstance(has_extra_lap, bool):
        has_extra_lap = None
    session_type_label = {0: "practice", 2: "race"}.get(session_type)
    if session_type_label is None:
        blockers.append("ACC Graphics session-type code is not yet qualified for this value.")
    blockers.append("ACC Graphics number_of_laps has not been live-qualified as a lap limit.")
    blockers.append("ACC Graphics global_chequered has not been live-qualified against a chequered finish.")

    return RaceProgressAssessment(
        status="observing",
        session_mode=session_mode,
        session_mode_source=session_mode_source,
        has_extra_lap=has_extra_lap,
        chequered_flag_candidate=chequered_candidate,
        chequered_flag_qualified=False,
        session_type_code=session_type,
        session_type_label=session_type_label,
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
