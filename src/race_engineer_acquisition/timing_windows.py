"""Windows timer-resolution request used by the live acquisition benchmark.

This requests a 1 ms system timer resolution for the duration of a benchmark.
It improves the granularity available to Windows wait operations; it does not
guarantee a particular thread wake-up time or polling rate.
"""

from __future__ import annotations

import ctypes
import os
from types import TracebackType
from typing import Any


class WindowsTimerResolution:
    """Manage a balanced WinMM timeBeginPeriod/timeEndPeriod request.

    winmm is injectable so lifecycle and error handling can be tested on
    non-Windows CI. A period of zero disables the request.
    """

    def __init__(self, period_ms: int = 1, *, winmm: Any | None = None) -> None:
        if period_ms < 0:
            raise ValueError("period_ms cannot be negative")
        self.period_ms = period_ms
        self._winmm = winmm
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def __enter__(self) -> "WindowsTimerResolution":
        if self.period_ms == 0:
            return self
        if self._winmm is None:
            if os.name != "nt":
                raise OSError("Windows timer resolution is available only on Windows")
            self._winmm = ctypes.WinDLL("winmm")

        begin = self._winmm.timeBeginPeriod
        end = self._winmm.timeEndPeriod
        if hasattr(begin, "argtypes"):
            begin.argtypes = [ctypes.c_uint]
            begin.restype = ctypes.c_uint
        if hasattr(end, "argtypes"):
            end.argtypes = [ctypes.c_uint]
            end.restype = ctypes.c_uint

        result = int(begin(self.period_ms))
        if result != 0:
            raise OSError(result, "timeBeginPeriod failed")
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._active:
            result = int(self._winmm.timeEndPeriod(self.period_ms))
            self._active = False
            if result != 0 and exc is None:
                raise OSError(result, "timeEndPeriod failed")
        return False
