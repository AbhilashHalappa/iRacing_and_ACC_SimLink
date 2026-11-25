"""Lightweight decoded-state monitor used by the live Overview and out-lap tile."""

from __future__ import annotations

from threading import Event, Lock, Thread
import time
from typing import Any

from .engineering_snapshot import RaceEngineerSnapshotAggregator
from .out_lap import ACCOutLapObserver


class DecodedTelemetryBroker:
    """Watch decoded snapshots and expose only the Overview out-lap state.

    This reduced runtime intentionally has no sample fan-out, lap-event stream,
    strategy session history, or persistence subscribers.
    """

    def __init__(self, runtime: Any, *, clock_ns=time.perf_counter_ns) -> None:
        self._aggregator = RaceEngineerSnapshotAggregator(runtime, clock_ns=clock_ns)
        self._out_lap_observer = ACCOutLapObserver()
        self._out_lap_active = False
        self._out_lap_fresh = False
        self._last_completed_lap_out_lap: bool | None = None
        self._clock_ns = clock_ns
        self._dirty = Event()
        self._stop = Event()
        self._lock = Lock()
        self._revision = 0
        self._published_count = 0
        self._wake_count = 0
        self._error_count = 0
        self._last_error: str | None = None
        self._thread: Thread | None = None
        self._started = False
        self._closed = False

        # Decoder callbacks only signal the broker-owned worker.
        runtime.physics_consumer.set_update_notifier(self.notify_dirty)
        runtime.graphics_consumer.set_update_notifier(self.notify_dirty)
        runtime.static_consumer.set_update_notifier(self.notify_dirty)

    def notify_dirty(self) -> None:
        """Constant-time decoder hook; safe to call after releasing decoder locks."""
        if not self._closed:
            self._dirty.set()

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded telemetry monitor is closed")
            if self._started:
                return
            self._started = True
        try:
            self._publish_once()
        except Exception:
            with self._lock:
                self._started = False
            raise
        with self._lock:
            self._thread = Thread(
                target=self._run,
                name="ACC-Overview-Telemetry-Monitor",
                daemon=True,
            )
            self._thread.start()
        self.notify_dirty()

    def _publish_once(self) -> None:
        telemetry = self._aggregator.snapshot()
        graphics_view = telemetry.graphics
        physics_view = telemetry.physics
        graphics = graphics_view.data if graphics_view.is_fresh else None
        physics = physics_view.data if physics_view.is_fresh else None
        graphics_status = getattr(graphics, "status", None)

        if graphics is not None and graphics_status not in (2, 3):
            # OFF/REPLAY are session boundaries; PAUSE is transient.
            session_key = (
                getattr(graphics, "session_index", None),
                getattr(graphics, "session", None),
            )
            self._out_lap_observer.reset(session_key)

        out_lap_fresh = graphics_view.is_fresh and physics_view.is_fresh
        if out_lap_fresh and graphics is not None and physics is not None:
            session_key = (
                getattr(graphics, "session_index", None),
                getattr(graphics, "session", None),
            )
            active = self._out_lap_observer.observe(
                graphics, getattr(physics, "speed_kph", None), session_key
            )
        else:
            active = False

        completed_out_lap = self._out_lap_observer.last_completed_lap_out_lap
        with self._lock:
            self._out_lap_active = bool(active)
            self._out_lap_fresh = out_lap_fresh
            if completed_out_lap is not None:
                self._last_completed_lap_out_lap = completed_out_lap
            self._revision += 1
            self._published_count += 1
            self._last_error = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._dirty.wait()
            self._dirty.clear()
            if self._stop.is_set():
                break
            with self._lock:
                self._wake_count += 1
            try:
                self._publish_once()
            except Exception as exc:
                with self._lock:
                    self._error_count += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"

    @property
    def out_lap_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._out_lap_active if self._out_lap_fresh else False,
                "fresh": self._out_lap_fresh,
                "last_completed_lap_out_lap": self._last_completed_lap_out_lap,
                "source": "ACCOutLapObserver",
            }

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started": self._started,
                "closed": self._closed,
                "revision": self._revision,
                "published_count": self._published_count,
                "wake_count": self._wake_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
            }

    def close(self, *, timeout: float = 2.0) -> bool:
        """Stop the Overview monitor; return False if its worker exceeds timeout."""
        with self._lock:
            if self._closed:
                thread = self._thread
            else:
                self._closed = True
                self._stop.set()
                thread = self._thread
        self._dirty.set()
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True
