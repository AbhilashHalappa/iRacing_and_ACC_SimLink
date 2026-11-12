"""Session-scoped ACC initial out-lap detection for the desktop telemetry publisher.

This observer is downstream of the decoded Graphics and Physics consumers. It
never changes ACC lap timing, lap validity, or the acquisition pipeline.
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
        self._last_position: float | None = None
        self._last_completed_laps: int | None = None
        self._seen_live_frame = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def out_lap_completed(self) -> bool:
        return self._out_lap_completed

    def reset(self, session_key: tuple[Any, ...] | None = None) -> None:
        self._session_key = session_key
        self._garage_candidate = False
        self._active = False
        self._out_lap_completed = False
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

        Garage/pit evidence is preferred. If the app attaches after the car has
        already left the garage, the first moving LIVE frame can seed detection
        while completed_laps is zero. A first sample already near the
        start/finish line is treated as a timed lap rather than an out-lap.
        """
        if self._session_key != session_key:
            self.reset(session_key)

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

        # Replay must never create an out-lap candidate.
        if status == 1:
            self.reset(session_key)
            return False

        # ACC can expose the parked garage before Graphics becomes LIVE.
        if status != 2:
            if status in (0, 3) and completed == 0 and garage_evidence:
                self._garage_candidate = True
            return False

        if completed is None:
            return self._active

        # A decreasing lap counter is a fresh session even when ACC reuses the
        # same session type/index and the app remained open.
        if (
            self._last_completed_laps is not None
            and completed < self._last_completed_laps
        ):
            self.reset(session_key)

        self._last_completed_laps = completed
        if completed > 0:
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
                # Attach-after-departure fallback: do not require a garage
                # frame that may have occurred before this app was launched.
                if position is None or position > self.START_FINISH_LOW:
                    self._active = True
                else:
                    # The first observed frame is already just beyond S/F.
                    self._out_lap_completed = True

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
                self._last_position = position
                self._seen_live_frame = True
                return False

            # Returning to the actual pit box before completing the initial
            # lap ends the indicator and rearms the initial garage departure.
            if speed < self.MIN_MOVING_SPEED_KPH and (in_pit or setup_visible):
                self._active = False
                self._garage_candidate = True
                self._last_position = position
                self._seen_live_frame = True
                return False

        self._last_position = position
        self._seen_live_frame = True
        return self._active
