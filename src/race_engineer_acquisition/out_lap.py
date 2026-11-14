"""Session-scoped ACC initial out-lap detection shared by Overview and strategies.

This observer is downstream of decoded Physics and Graphics. It preserves the
existing Overview indication while exposing the classification at lap boundary.
"""
from __future__ import annotations

from typing import Any


class ACCOutLapObserver:
    """Identify the initial garage-to-track lap and stop at start/finish."""

    MIN_MOVING_SPEED_KPH = 3.0
    START_FINISH_HIGH = 0.85
    START_FINISH_LOW = 0.15

    def __init__(self) -> None:
        self._session_key: tuple[Any, ...] | None = None
        self._garage_candidate = False
        self._active = False
        self._out_lap_completed = False
        self._pending_completed_lap_out_lap: bool | None = None
        self._last_completed_lap_out_lap: bool | None = None
        self._last_position: float | None = None
        self._last_completed_laps: int | None = None
        self._seen_live_frame = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def out_lap_completed(self) -> bool:
        return self._out_lap_completed

    @property
    def last_completed_lap_out_lap(self) -> bool | None:
        """Classification for the lap whose ACC completed-lap counter advanced."""
        return self._last_completed_lap_out_lap

    def reset(self, session_key: tuple[Any, ...] | None = None) -> None:
        self._session_key = session_key
        self._garage_candidate = False
        self._active = False
        self._out_lap_completed = False
        self._pending_completed_lap_out_lap = None
        self._last_completed_lap_out_lap = None
        self._last_position = None
        self._last_completed_laps = None
        self._seen_live_frame = False

    def observe(
        self,
        graphics: Any,
        speed_kph: float | None,
        session_key: tuple[Any, ...],
    ) -> bool:
        """Return True while the session's initial out-lap is in progress.

        The classification output is tri-state: True/False only when the
        existing observer has enough evidence; otherwise it remains unknown.
        """
        if self._session_key != session_key:
            self.reset(session_key)

        self._last_completed_lap_out_lap = None
        status = getattr(graphics, "status", None)
        completed_raw = getattr(graphics, "completed_laps", None)
        position = getattr(graphics, "normalized_car_position", None)
        completed = (
            int(completed_raw)
            if isinstance(completed_raw, (int, float)) and completed_raw >= 0
            else None
        )
        try:
            speed = float(speed_kph) if speed_kph is not None else 0.0
        except (TypeError, ValueError, OverflowError):
            speed = 0.0
        if speed != speed or abs(speed) == float("inf"):
            speed = 0.0

        in_pit = bool(getattr(graphics, "is_in_pit", False))
        in_pit_lane = bool(getattr(graphics, "is_in_pit_lane", False))
        setup_visible = bool(getattr(graphics, "setup_menu_visible", False))
        garage_evidence = in_pit or in_pit_lane or setup_visible

        if status == 1:
            self.reset(session_key)
            return False

        if status != 2:
            if status in (0, 3) and completed == 0 and garage_evidence:
                self._garage_candidate = True
            return False

        if completed is None:
            return self._active

        if (
            self._last_completed_laps is not None
            and completed < self._last_completed_laps
        ):
            self.reset(session_key)

        previous_completed = self._last_completed_laps
        self._last_completed_laps = completed
        if completed > 0:
            if previous_completed == 0:
                if self._active or self._pending_completed_lap_out_lap is True:
                    self._last_completed_lap_out_lap = True
                elif self._pending_completed_lap_out_lap is False or self._out_lap_completed:
                    self._last_completed_lap_out_lap = False
                self._pending_completed_lap_out_lap = None
            elif previous_completed is not None and completed > previous_completed:
                self._last_completed_lap_out_lap = False
            self._active = False
            self._garage_candidate = False
            self._out_lap_completed = True
            self._last_position = position
            self._seen_live_frame = True
            return False

        if self._out_lap_completed:
            return False

        if garage_evidence:
            self._garage_candidate = True
            self._last_position = position
            self._seen_live_frame = True
            return False

        moving = speed >= self.MIN_MOVING_SPEED_KPH
        if not self._active and moving:
            if self._garage_candidate:
                self._active = True
                self._garage_candidate = False
            elif not self._seen_live_frame:
                if position is None or position > self.START_FINISH_LOW:
                    self._active = True
                else:
                    self._out_lap_completed = True
                    self._pending_completed_lap_out_lap = False

        if self._active:
            wrapped = (
                self._last_position is not None
                and position is not None
                and self._last_position > self.START_FINISH_HIGH
                and position < self.START_FINISH_LOW
            )
            if wrapped:
                self._active = False
                self._out_lap_completed = True
                self._pending_completed_lap_out_lap = True
                self._last_position = position
                self._seen_live_frame = True
                return False

            if speed < self.MIN_MOVING_SPEED_KPH and (in_pit or setup_visible):
                self._active = False
                self._garage_candidate = True
                self._last_position = position
                self._seen_live_frame = True
                return False

        self._last_position = position
        self._seen_live_frame = True
        return self._active
