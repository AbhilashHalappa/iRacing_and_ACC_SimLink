"""Completed-lap event production from validated decoded Graphics state.

This module consumes only the freshness-gated Stage 2 aggregate. It treats
Graphics completed_laps as the authoritative lap counter and preserves ACC's
completed-lap timing and validity observations. It never reads raw telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LapProgressReconciliation:
    """Fresh authoritative lap cursor for recovery after a detected event gap."""

    session_id: str
    completed_laps: int
    latest_lap_time_ms: int | None
    latest_lap_valid: bool | None
    source_capture_sequence: int | None
    source_timestamp_ns: int | None
    historical_laps_recovered: bool = False


@dataclass(frozen=True, slots=True)
class LapEventCandidate:
    event_type: str
    session_id: str
    source_capture_sequence: int | None
    source_timestamp_ns: int | None
    payload: dict[str, Any]


class CompletedLapEventObserver:
    """Convert decoded completed-lap counter transitions into domain events.

    The first fresh LIVE observation seeds the cursor and emits no historical
    event. A one-lap increment produces one completed-lap event. A jump greater
    than one produces an explicit gap event; missing lap records are never
    fabricated from the latest ACC fields. Session changes and counter resets
    re-seed the observer.
    """

    LIVE_STATUS = 2

    def __init__(self) -> None:
        self._session_key: tuple[int | None, int | None] | None = None
        self._completed_laps: int | None = None

    def reset(self) -> None:
        self._session_key = None
        self._completed_laps = None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    def observe(self, telemetry: Any) -> tuple[LapEventCandidate, ...]:
        graphics_view = telemetry.graphics
        if not graphics_view.is_fresh or graphics_view.data is None:
            return ()

        graphics = graphics_view.data
        if getattr(graphics, "status", None) != self.LIVE_STATUS:
            return ()

        completed = self._integer(getattr(graphics, "completed_laps", None))
        if completed is None:
            return ()

        session_index = self._integer(getattr(graphics, "session_index", None))
        session_type = self._integer(getattr(graphics, "session", None))
        session_key = (session_index, session_type)
        session_id = f"acc-session:{session_index}:{session_type}"

        if self._session_key != session_key or self._completed_laps is None:
            self._session_key = session_key
            self._completed_laps = completed
            return ()

        previous = self._completed_laps
        if completed < previous:
            # ACC reset/restarted its lap counter without a usable session key
            # transition. Re-seed instead of interpreting this as a lap.
            self._completed_laps = completed
            return ()

        if completed == previous:
            return ()

        self._completed_laps = completed
        delta = completed - previous
        source_sequence = graphics_view.capture_sequence
        source_timestamp = graphics_view.capture_timestamp_ns

        if delta > 1:
            return (
                LapEventCandidate(
                    event_type="lap.completion_gap",
                    session_id=session_id,
                    source_capture_sequence=source_sequence,
                    source_timestamp_ns=source_timestamp,
                    payload={
                        "previous_completed_laps": previous,
                        "current_completed_laps": completed,
                        "missing_lap_count": delta - 1,
                        "latest_lap_number": completed,
                        "reconciliation_required": True,
                        "reason": "completed_lap_counter_advanced_by_multiple_laps",
                    },
                ),
            )

        lap_time_ms = self._integer(getattr(graphics, "last_time_ms", None))
        lap_time_str = getattr(graphics, "last_time_str", None)
        lap_valid = getattr(graphics, "is_valid_lap", None)
        validity_known = isinstance(lap_valid, bool)

        return (
            LapEventCandidate(
                event_type="lap.completed",
                session_id=session_id,
                source_capture_sequence=source_sequence,
                source_timestamp_ns=source_timestamp,
                payload={
                    "lap_number": completed,
                    "lap_time_ms": lap_time_ms if lap_time_ms and lap_time_ms > 0 else None,
                    "lap_time_str": lap_time_str if isinstance(lap_time_str, str) else None,
                    "lap_valid": lap_valid if validity_known else None,
                    "validity_known": validity_known,
                    "validity_source": "ACC_Graphics.is_valid_lap" if validity_known else None,
                    "timing_source": "ACC_Graphics.last_time_ms",
                    "timing_available": bool(lap_time_ms and lap_time_ms > 0),
                    "out_lap": False,
                    "session_index": session_index,
                    "session_type": session_type,
                },
            ),
        )



def reconcile_lap_progress(
    telemetry: Any, *, now_ns: int | None = None
) -> LapProgressReconciliation | None:
    """Return the latest fresh ACC lap cursor after a consumer detects a gap.

    This repairs the consumer's current progress cursor, not missing historical
    lap records. Historical laps remain unrecovered until a durable lap-history
    source is connected; callers must not fill the gap with fabricated laps.
    """
    view = telemetry.graphics
    if view.data is None or view.capture_timestamp_ns is None:
        return None
    if now_ns is None:
        import time
        now_ns = time.perf_counter_ns()
    age_ns = now_ns - view.capture_timestamp_ns
    if (
        not view.is_fresh
        or age_ns < 0
        or age_ns > view.max_age_ns
        or view.consumer_lifecycle != "running"
        or view.acquisition_lifecycle != "running"
    ):
        return None
    graphics = view.data
    if getattr(graphics, "status", None) != CompletedLapEventObserver.LIVE_STATUS:
        return None
    completed = CompletedLapEventObserver._integer(
        getattr(graphics, "completed_laps", None)
    )
    if completed is None:
        return None
    session_index = CompletedLapEventObserver._integer(
        getattr(graphics, "session_index", None)
    )
    session_type = CompletedLapEventObserver._integer(
        getattr(graphics, "session", None)
    )
    lap_time = CompletedLapEventObserver._integer(
        getattr(graphics, "last_time_ms", None)
    )
    lap_valid = getattr(graphics, "is_valid_lap", None)
    return LapProgressReconciliation(
        session_id=f"acc-session:{session_index}:{session_type}",
        completed_laps=completed,
        latest_lap_time_ms=lap_time if lap_time and lap_time > 0 else None,
        latest_lap_valid=lap_valid if isinstance(lap_valid, bool) else None,
        source_capture_sequence=view.capture_sequence,
        source_timestamp_ns=view.capture_timestamp_ns,
    )
