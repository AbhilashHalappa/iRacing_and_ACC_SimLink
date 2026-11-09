"""Supervise the independent ACC Physics, Graphics and Static readers.

The supervisor owns worker threads, stop events and source closure. It does not
merge streams, consume their buffers, decode payloads or perform persistence.
A worker failure is isolated to that stream and remains visible in status.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, Thread, current_thread
from typing import Callable, Iterable

from .health import AcquisitionHealth


RunWorker = Callable[[Event], None]
CloseSource = Callable[[], None]


@dataclass(frozen=True, slots=True)
class AcquisitionStream:
    """One independently scheduled acquisition worker and its source cleanup."""

    name: str
    run: RunWorker
    close: CloseSource
    health: AcquisitionHealth | None = None


@dataclass(slots=True)
class _StreamRuntime:
    spec: AcquisitionStream
    stop_event: Event
    state: str = "pending"
    error: str | None = None
    close_error: str | None = None
    thread: Thread | None = None
    close_lock: Lock | None = None
    closed: bool = False


class AcquisitionStartupError(RuntimeError):
    """Raised when a worker thread cannot be started; started workers roll back."""


class AcquisitionSupervisor:
    """Own the start/stop lifecycle of independent acquisition streams.

    A source is closed exactly once, by its worker on exit where possible. A
    source whose worker never started is closed by the startup rollback/stop
    caller. Timed-out live workers retain ownership of their source; the
    supervisor never unmaps memory concurrently with an active read.
    """

    def __init__(
        self,
        streams: Iterable[AcquisitionStream],
        *,
        thread_factory=Thread,
        startup_rollback_timeout_seconds: float = 5.0,
        timer_resolution=None,
    ) -> None:
        specs = tuple(streams)
        if not specs:
            raise ValueError("at least one acquisition stream is required")
        names = [item.name for item in specs]
        if any(not name.strip() for name in names):
            raise ValueError("stream names must be non-empty")
        if len(set(names)) != len(names):
            raise ValueError("stream names must be unique")
        if startup_rollback_timeout_seconds <= 0:
            raise ValueError("startup rollback timeout must be positive")
        self._thread_factory = thread_factory
        self._startup_rollback_timeout_seconds = startup_rollback_timeout_seconds
        self._timer_resolution = timer_resolution
        self._timer_entered = False
        self._timer_released = False
        self._timer_error: str | None = None
        self._timer_lock = Lock()
        self._runtimes = {
            spec.name: _StreamRuntime(spec, Event(), close_lock=Lock())
            for spec in specs
        }
        self._lock = Lock()
        self._lifecycle_lock = Lock()
        self._started = False
        self._stop_requested = False

    @property
    def status(self) -> dict[str, dict[str, object | None]]:
        """Return detached lifecycle status and the latest common health snapshots."""
        with self._lock:
            return {
                name: {
                    "state": runtime.state,
                    "error": runtime.error,
                    "close_error": runtime.close_error,
                    "health": (runtime.spec.health.snapshot if runtime.spec.health is not None else None),
                    "timer_resolution_error": self._timer_error,
                    "timer_resolution_active": bool(getattr(self._timer_resolution, "active", False)),
                }
                for name, runtime in self._runtimes.items()
            }

    def start(self) -> None:
        """Start every stream on its own thread or roll back partial startup."""
        with self._lifecycle_lock:
            with self._lock:
                if self._started:
                    raise RuntimeError("acquisition supervisor has already been started")
                if self._stop_requested:
                    raise RuntimeError("a stopped acquisition supervisor cannot be restarted")
                self._started = True

            if self._timer_resolution is not None:
                try:
                    self._timer_resolution.__enter__()
                    self._timer_entered = True
                except Exception as exc:
                    self._timer_error = f"{type(exc).__name__}: {exc}"
                    raise

            for name, runtime in self._runtimes.items():
                with self._lock:
                    runtime.state = "starting"
                if runtime.spec.health is not None:
                    runtime.spec.health.set_lifecycle("starting")
                try:
                    thread = self._thread_factory(
                        target=self._run_stream,
                        args=(name,),
                        name=f"ACC-{name}-Acquisition",
                        daemon=True,
                    )
                    runtime.thread = thread
                    thread.start()
                except BaseException as exc:
                    with self._lock:
                        runtime.state = "failed"
                        runtime.error = f"{type(exc).__name__}: {exc}"
                    if runtime.spec.health is not None:
                        runtime.spec.health.set_lifecycle("failed")
                    alive = self._rollback_startup()
                    suffix = f" Workers still running: {', '.join(alive)}." if alive else " All started workers stopped."
                    raise AcquisitionStartupError(
                        f"Could not start acquisition stream {name!r};"
                        f"{suffix}"
                    ) from exc

    def _run_stream(self, name: str) -> None:
        runtime = self._runtimes[name]
        with self._lock:
            if runtime.state == "starting":
                runtime.state = "running"
            if runtime.spec.health is not None:
                runtime.spec.health.set_lifecycle("running")
        failed = False
        try:
            runtime.spec.run(runtime.stop_event)
        except Exception as exc:
            failed = True
            with self._lock:
                runtime.state = "failed"
                runtime.error = f"{type(exc).__name__}: {exc}"
            if runtime.spec.health is not None:
                runtime.spec.health.set_lifecycle("failed")
        finally:
            self._close_once(runtime)
            with self._lock:
                if runtime.close_error:
                    runtime.state = "failed"
                    if runtime.spec.health is not None:
                        runtime.spec.health.set_lifecycle("failed")
                elif not failed and runtime.state != "failed":
                    runtime.state = "stopped"
                    if runtime.spec.health is not None:
                        runtime.spec.health.set_lifecycle("stopped")
            self._release_timer_if_stopped()

    def _release_timer_if_stopped(self) -> None:
        if self._timer_resolution is None or not self._timer_entered:
            return
        with self._timer_lock:
            if self._timer_released:
                return
            current = current_thread()
            for runtime in self._runtimes.values():
                thread = runtime.thread
                if runtime.state not in ("stopped", "failed"):
                    return
                if thread is not None and thread is not current and thread.ident is not None and thread.is_alive():
                    return
            try:
                self._timer_resolution.__exit__(None, None, None)
            except Exception as exc:
                self._timer_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._timer_released = True

    def _close_once(self, runtime: _StreamRuntime) -> None:
        assert runtime.close_lock is not None
        with runtime.close_lock:
            if runtime.closed:
                return
            runtime.closed = True
            try:
                runtime.spec.close()
            except Exception as exc:
                with self._lock:
                    runtime.close_error = f"{type(exc).__name__}: {exc}"

    def _rollback_startup(self) -> tuple[str, ...]:
        with self._lock:
            self._stop_requested = True
        for runtime in self._runtimes.values():
            runtime.stop_event.set()
        import time

        deadline = time.monotonic() + self._startup_rollback_timeout_seconds
        alive: list[str] = []
        for name, runtime in self._runtimes.items():
            thread = runtime.thread
            if thread is not None and thread.ident is not None:
                thread.join(max(0.0, deadline - time.monotonic()))
                if thread.is_alive():
                    alive.append(name)
            else:
                self._close_once(runtime)
                with self._lock:
                    if runtime.state != "failed":
                        runtime.state = "stopped"
                        if runtime.spec.health is not None:
                            runtime.spec.health.set_lifecycle("stopped")
        if not alive:
            self._release_timer_if_stopped()
        return tuple(alive)

    def join(self, timeout: float | None = None) -> tuple[str, ...]:
        """Wait for workers without requesting stop; return names still alive."""
        alive: list[str] = []
        for name, runtime in self._runtimes.items():
            thread = runtime.thread
            if thread is not None:
                thread.join(timeout)
                if thread.is_alive():
                    alive.append(name)
        return tuple(alive)

    def stop(self, timeout: float | None = 5.0) -> tuple[str, ...]:
        """Request all workers to stop and wait up to a shared timeout budget.

        Returns names of workers still alive. Their sources remain owned by
        those workers and are closed by their finally blocks when they exit.
        Repeated calls are safe and do not close a source twice.
        """
        with self._lifecycle_lock:
            with self._lock:
                self._stop_requested = True
            for runtime in self._runtimes.values():
                runtime.stop_event.set()

            import time

            deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
            alive: list[str] = []
            for name, runtime in self._runtimes.items():
                thread = runtime.thread
                if thread is None or thread.ident is None:
                    self._close_once(runtime)
                    with self._lock:
                        if runtime.state != "failed":
                            runtime.state = "stopped"
                            if runtime.spec.health is not None:
                                runtime.spec.health.set_lifecycle("stopped")
                    continue
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                thread.join(remaining)
                if thread.is_alive():
                    alive.append(name)
            if not alive:
                self._release_timer_if_stopped()
            return tuple(alive)


@dataclass(frozen=True, slots=True)
class ACCAcquisitionRuntime:
    """Default Windows ACC supervisor plus independent per-stream buffers."""

    supervisor: AcquisitionSupervisor
    buffers: dict[str, object]
    acquirers: dict[str, object]


def create_acc_acquisition_runtime(
    *,
    physics_poll_hz: float = 480.0,
    graphics_poll_hz: float = 100.0,
    static_refresh_seconds: float = 1.0,
    physics_buffer_capacity: int = 100_000,
    graphics_buffer_capacity: int = 10_000,
    static_buffer_capacity: int = 64,
    timer_resolution_ms: int = 1,
) -> ACCAcquisitionRuntime:
    """Build the three independent Windows ACC acquisition workers.

    Shared-memory handles are opened lazily by each worker. The returned
    buffers are separate SPSC queues; this function does not add consumers.
    """
    if min(physics_poll_hz, graphics_poll_hz, static_refresh_seconds) <= 0:
        raise ValueError("poll rates and Static refresh interval must be positive")

    from .acc_windows import WindowsACCPhysicsSource
    from .acquirer import PhysicsAcquirer
    from .graphics import GraphicsAcquirer, WindowsACCGraphicsSource
    from .ring_buffer import AcquisitionRingBuffer
    from .static import StaticAcquirer, WindowsACCStaticSource
    from .timing_windows import WindowsTimerResolution

    physics_source = WindowsACCPhysicsSource()
    graphics_source = WindowsACCGraphicsSource()
    static_source = WindowsACCStaticSource()

    buffers = {
        "physics": AcquisitionRingBuffer(physics_buffer_capacity),
        "graphics": AcquisitionRingBuffer(graphics_buffer_capacity),
        "static": AcquisitionRingBuffer(static_buffer_capacity),
    }
    acquirers = {
        "physics": PhysicsAcquirer(physics_source, buffers["physics"]),
        "graphics": GraphicsAcquirer(graphics_source, buffers["graphics"]),
        "static": StaticAcquirer(static_source, buffers["static"]),
    }
    streams = (
        AcquisitionStream(
            "physics",
            lambda stop: acquirers["physics"].run(
                stop, poll_interval_ns=max(1, round(1_000_000_000 / physics_poll_hz))
            ),
            physics_source.close,
            acquirers["physics"].health,
        ),
        AcquisitionStream(
            "graphics",
            lambda stop: acquirers["graphics"].run(
                stop, poll_interval_ns=max(1, round(1_000_000_000 / graphics_poll_hz))
            ),
            graphics_source.close,
            acquirers["graphics"].health,
        ),
        AcquisitionStream(
            "static",
            lambda stop: acquirers["static"].run(
                stop, refresh_interval_ns=max(1, round(static_refresh_seconds * 1_000_000_000))
            ),
            static_source.close,
            acquirers["static"].health,
        ),
    )
    return ACCAcquisitionRuntime(
        AcquisitionSupervisor(
            streams, timer_resolution=WindowsTimerResolution(timer_resolution_ms)
        ), buffers, acquirers
    )
