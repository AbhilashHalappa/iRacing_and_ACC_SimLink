"""Race-progress estimates from fresh decoded ACC streams and lap history.

Timed-race lap estimates use ACC's remaining session time and the average of
the latest five valid, classified, non-out completed laps from this session.
Lap-based arithmetic is gated on explicit qualification of the ACC lap-limit field. Finish-line and chequered-flag behaviour remains observational until validated in live sessions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable


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
    average_lap_time_ms: float | None
    lap_time_sample_count: int
    lap_limit_candidate: int | None
    lap_limit_qualified: bool
    laps_remaining: int | None
    estimated_race_laps_remaining: int | None
    estimated_race_laps_source: str | None
    estimated_race_laps_qualified: bool
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


def _recent_valid_lap_times(lap_records: Iterable[Any], *, count: int = 5) -> tuple[int, ...]:
    valid_times: list[int] = []
    for record in lap_records:
        if (
            getattr(record, "lap_valid", None) is True
            and getattr(record, "out_lap", None) is False
            and getattr(record, "classification", None) == "classified"
        ):
            lap_time = getattr(record, "lap_time_ms", None)
            if isinstance(lap_time, int) and not isinstance(lap_time, bool) and lap_time > 0:
                valid_times.append(lap_time)
    return tuple(valid_times[-count:])


def assess_race_progress(
    telemetry: Any,
    *,
    lap_records: Iterable[Any] = (),
    lap_limit_qualified: bool = False,
) -> RaceProgressAssessment:
    """Expose progress and estimate timed-race laps from five valid lap times.

    Graphics.session_time_left_ms is converted to seconds. Session codes 0
    (Practice) and 2 (Race) are mapped from live observations; distance
    estimates are produced only for Race. Static metadata classifies timed vs
    lap-based mode. For timed races, the estimate is floor(remaining seconds /
    average of the latest five valid timed laps). Lap-based arithmetic is
    enabled only when the caller explicitly confirms the lap-limit field has
    been live-qualified. Finish-line/chequered semantics remain unqualified.
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
            average_lap_time_ms=None,
            lap_time_sample_count=0,
            lap_limit_candidate=None,
            lap_limit_qualified=False,
            laps_remaining=None,
            estimated_race_laps_remaining=None,
            estimated_race_laps_source=None,
            estimated_race_laps_qualified=False,
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
    static_view = getattr(telemetry, "static_decoded", None)
    static_data = (
        getattr(static_view, "data", None)
        if static_view is not None and getattr(static_view, "is_fresh", False)
        else None
    )
    static_identity_ready = bool(
        static_data is not None
        and isinstance(getattr(static_data, "track", None), str)
        and getattr(static_data, "track", "").strip()
        and isinstance(getattr(static_data, "car_model", None), str)
        and getattr(static_data, "car_model", "").strip()
    )
    # A newly opened mapping can initially contain a zero-filled page. Do not
    # interpret its default false race-mode flag as a lap-based session.
    timed_flag = (
        getattr(static_data, "is_timed_race", None)
        if static_identity_ready else None
    )
    has_extra_lap = (
        getattr(static_data, "has_extra_lap", None)
        if static_identity_ready else None
    )
    chequered_candidate = getattr(graphics, "global_chequered", None)
    if not isinstance(chequered_candidate, bool):
        chequered_candidate = None
    if session_type != 2:
        session_mode = "unknown"
        session_mode_source = None
        blockers.append(
            "Race-distance estimation is unavailable because ACC session type is not Race."
        )
    elif timed_flag is True:
        session_mode = "timed"
        session_mode_source = "ACC_Static.is_timed_race"
    elif (
        static_identity_ready
        and session_type == 2
        and time_remaining is not None
        and time_remaining > 0.0
        and lap_limit in (None, 0)
    ):
        # In the user's live ACC race, Static.is_timed_race was false even
        # though Graphics reported a running countdown and no lap limit.
        # Prefer the live race-session evidence over the contradictory Static
        # boolean. Keep the conflict visible for continued qualification.
        session_mode = "timed"
        session_mode_source = "ACC_Graphics.race_countdown_without_lap_limit"
        if timed_flag is False:
            blockers.append(
                "ACC Static is_timed_race=false conflicts with the live Race countdown and zero lap limit; using Graphics evidence."
            )
    elif timed_flag is False and session_type == 2 and time_remaining is None:
        session_mode = "lap_based"
        session_mode_source = "ACC_Static.is_timed_race"
    elif isinstance(timed_flag, bool):
        session_mode = "lap_based" if timed_flag is False else "timed"
        session_mode_source = "ACC_Static.is_timed_race"
    else:
        session_mode = "unknown"
        session_mode_source = None
        blockers.append("Fresh decoded ACC Static race-mode metadata is unavailable.")
    if not isinstance(has_extra_lap, bool):
        has_extra_lap = None

    if time_remaining is None and session_mode != "lap_based":
        blockers.append("ACC session time remaining is unavailable or invalid.")

    session_type_label = {0: "practice", 2: "race"}.get(session_type)
    if session_type_label is None:
        blockers.append("ACC Graphics session-type code is not yet qualified for this value.")

    lap_times = _recent_valid_lap_times(lap_records)
    average_lap_time_ms = (
        sum(lap_times) / len(lap_times)
        if len(lap_times) == 5
        else None
    )
    laps_remaining = None
    laps_remaining_source = None
    laps_remaining_qualified = False
    qualified_lap_limit = (
        session_mode == "lap_based"
        and lap_limit_qualified
        and lap_limit is not None
        and lap_limit > 0
    )
    if session_mode == "timed":
        if average_lap_time_ms is None:
            blockers.append(
                f"Timed-race lap estimate needs five valid completed lap times; "
                f"currently have {len(lap_times)}."
            )
        elif time_remaining is not None:
            # Preserve the established estimate: number of average laps that
            # fit into the remaining timer. This is an estimate, not a
            # finish-distance guarantee until ACC's final-crossing behaviour
            # is validated with live sessions.
            laps_remaining = math.floor(
                (time_remaining * 1000.0) / average_lap_time_ms
            )
            laps_remaining_source = (
                "ACC_Graphics.session_time_left_ms / "
                "mean_of_latest_five_valid_completed_laps"
            )
            blockers.append(
                "Timed-race finish-line and extra-lap behaviour is not yet live-qualified; "
                "the lap count is an estimate, not a guaranteed finish distance."
            )
    elif session_mode == "lap_based":
        if not qualified_lap_limit:
            blockers.append(
                "Lap-based remaining distance is unavailable until ACC Graphics "
                "number_of_laps is live-qualified (issue #22)."
            )
        elif completed_laps is None:
            blockers.append(
                "Lap-based remaining distance requires a valid completed-lap count."
            )
        elif completed_laps > lap_limit:
            blockers.append(
                "ACC completed-lap count exceeds the qualified race lap limit; "
                "remaining distance is contradictory."
            )
        else:
            laps_remaining = lap_limit - completed_laps
            laps_remaining_source = (
                "ACC_Graphics.number_of_laps - ACC_Graphics.completed_laps"
            )
            laps_remaining_qualified = True

    if session_mode != "lap_based" or not qualified_lap_limit:
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
        average_lap_time_ms=average_lap_time_ms,
        lap_time_sample_count=len(lap_times),
        lap_limit_candidate=lap_limit if lap_limit and lap_limit > 0 else None,
        lap_limit_qualified=qualified_lap_limit,
        laps_remaining=laps_remaining,
        estimated_race_laps_remaining=laps_remaining,
        estimated_race_laps_source=laps_remaining_source,
        estimated_race_laps_qualified=laps_remaining_qualified,
        projected_fuel_required_l=None,
        blockers=tuple(blockers),
    )


def race_progress_payload(assessment: RaceProgressAssessment) -> dict[str, Any]:
    """Return a JSON-serializable service payload."""
    return asdict(assessment)
