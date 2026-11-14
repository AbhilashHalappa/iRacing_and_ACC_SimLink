"""Stage 2 distribution for immutable, decoded ACC telemetry snapshots.

This broker is deliberately downstream of the existing Physics and Graphics
decoders. It never reads acquisition rings, raw payloads or ACC shared memory.
Decoder notifications only set a waitable dirty flag; aggregation and subscriber
publication happen on this broker's own worker thread.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Event, Lock, Thread
import time
from uuid import uuid4
from typing import Any, Mapping

from .decoded_events import (
    DecodedDomainEvent,
    DecodedEventPublisher,
    DecodedEventSubscription,
)

from .engineering_snapshot import RaceEngineerSnapshotAggregator, RaceEngineerTelemetrySnapshot
from .out_lap import ACCOutLapObserver
from .lap_events import (
    CompletedLapEventObserver,
    LapProgressReconciliation,
    reconcile_lap_progress,
)


@dataclass(frozen=True, slots=True)
class DecodedSnapshotEnvelope:
    """One broker publication with a monotonic revision and publication time."""

    revision: int
    published_at_ns: int
    telemetry: RaceEngineerTelemetrySnapshot


class LatestSnapshotSubscription:
    """Independent coalescing latest-value mailbox for one downstream consumer."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = Lock()
        self._latest: DecodedSnapshotEnvelope | None = None
        self._last_read_revision = 0
        self._coalesced_updates = 0
        self._closed = False

    @property
    def latest(self) -> DecodedSnapshotEnvelope | None:
        with self._lock:
            return self._latest

    @property
    def coalesced_updates(self) -> int:
        with self._lock:
            return self._coalesced_updates

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def read_latest(self) -> DecodedSnapshotEnvelope | None:
        """Read the newest publication and mark all older revisions observed."""
        with self._lock:
            result = self._latest
            if result is not None:
                self._last_read_revision = result.revision
            return result

    def _publish(self, envelope: DecodedSnapshotEnvelope) -> None:
        with self._lock:
            if self._closed:
                return
            if (
                self._latest is not None
                and self._latest.revision > self._last_read_revision
            ):
                self._coalesced_updates += 1
            self._latest = envelope

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._latest = None


class DecodedTelemetryBroker:
    """Publish decoded latest-state snapshots to independent subscribers.

    The broker has no callback execution on decoder threads. Decoder workers
    invoke only `notify_dirty()`, which sets a threading.Event. This worker
    coalesces bursts, reads the existing freshness-aware decoded aggregator,
    and replaces each subscriber's latest-value mailbox.

    History-critical events use a separate bounded, identified event channel.
    Snapshot coalescing and event delivery have independent subscriber mailboxes.
    """

    def __init__(self, runtime: Any, *, clock_ns=time.perf_counter_ns) -> None:
        self._aggregator = RaceEngineerSnapshotAggregator(runtime, clock_ns=clock_ns)
        self._events = DecodedEventPublisher(clock_ns=clock_ns)
        self._lap_event_observer = CompletedLapEventObserver()
        # A run-scoped identity prevents ACC's reusable session_index/session
        # pair from merging separate sessions or app launches in lap history.
        self._session_generation: str | None = None
        self._strategy_session_id: str | None = None
        self._out_lap_observer = ACCOutLapObserver()
        self._out_lap_active = False
        self._out_lap_fresh = False
        self._last_completed_lap_out_lap: bool | None = None
        self._clock_ns = clock_ns
        self._dirty = Event()
        self._stop = Event()
        self._lock = Lock()
        self._subscribers: dict[str, LatestSnapshotSubscription] = {}
        self._revision = 0
        self._latest: DecodedSnapshotEnvelope | None = None
        self._published_count = 0
        self._wake_count = 0
        self._error_count = 0
        self._last_error: str | None = None
        self._thread: Thread | None = None
        self._started = False
        self._closed = False

        # The callback performs no aggregation, queue operation or consumer
        # work. It only signals this broker-owned worker.
        runtime.physics_consumer.set_update_notifier(self.notify_dirty)
        runtime.graphics_consumer.set_update_notifier(self.notify_dirty)

    def subscribe(self, name: str) -> LatestSnapshotSubscription:
        if not name or not name.strip():
            raise ValueError("subscriber name must be non-empty")
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded telemetry broker is closed")
            if name in self._subscribers:
                raise ValueError(f"subscriber already registered: {name}")
            subscription = LatestSnapshotSubscription(name)
            if self._latest is not None:
                subscription._publish(self._latest)
            self._subscribers[name] = subscription
            return subscription

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            subscription = self._subscribers.pop(name, None)
        if subscription is not None:
            subscription.close()

    def subscribe_events(
        self, name: str, *, capacity: int = 128
    ) -> DecodedEventSubscription:
        """Register an independent bounded mailbox for important domain events."""
        return self._events.subscribe(name, capacity=capacity)

    def publish_event(
        self,
        event_type: str,
        *,
        session_id: str | None,
        source_stream: str,
        source_capture_sequence: int | None,
        source_timestamp_ns: int | None,
        payload: Mapping[str, Any],
        schema_version: int = 1,
    ) -> DecodedDomainEvent:
        """Publish an event already derived from validated decoded state.

        Producers must not call this with raw ACC payloads or unvalidated
        candidate semantics. Event consumers detect overflow and reconcile
        against authoritative decoded state/history before acting.
        """
        return self._events.publish(
            event_type,
            session_id=session_id,
            source_stream=source_stream,
            source_capture_sequence=source_capture_sequence,
            source_timestamp_ns=source_timestamp_ns,
            payload=payload,
            schema_version=schema_version,
        )

    def notify_dirty(self) -> None:
        """Constant-time decoder hook; safe to call after releasing decoder lock."""
        if not self._closed:
            self._dirty.set()

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("decoded telemetry broker is closed")
            if self._started:
                return
            self._started = True
        try:
            # Seed the first immutable view before any service can subscribe.
            self._publish_once()
        except Exception:
            with self._lock:
                self._started = False
            raise
        with self._lock:
            self._thread = Thread(
                target=self._run,
                name="ACC-Decoded-Telemetry-Broker",
                daemon=True,
            )
            self._thread.start()
        self.notify_dirty()

    def _publish_once(self) -> None:
        telemetry = self._aggregator.snapshot()
        graphics_view = telemetry.graphics
        physics_view = telemetry.physics
        completed_lap_out_lap = None
        out_lap_fresh = graphics_view.is_fresh and physics_view.is_fresh
        graphics_data = graphics_view.data if graphics_view.is_fresh else None
        graphics_status = (
            getattr(graphics_data, "status", None)
            if graphics_data is not None else None
        )
        if (
            graphics_data is not None
            and graphics_status != CompletedLapEventObserver.LIVE_STATUS
            and graphics_status != CompletedLapEventObserver.PAUSE_STATUS
        ):
            # OFF/REPLAY are treated as session boundaries. PAUSE is a
            # transient state inside the same ACC session: retain the run ID
            # and lap cursor so the next LIVE sample continues the same history.
            self._session_generation = None
            self._strategy_session_id = None
            self._lap_event_observer.reset()
            session_key = (
                getattr(graphics_data, "session_index", None),
                getattr(graphics_data, "session", None),
            )
            self._out_lap_observer.reset(session_key)
        elif (
            graphics_data is not None
            and graphics_status == CompletedLapEventObserver.LIVE_STATUS
        ):
            if self._session_generation is None:
                self._session_generation = uuid4().hex
            self._strategy_session_id = (
                f"acc-run:{self._session_generation}:"
                f"{getattr(graphics_data, 'session_index', None)}:"
                f"{getattr(graphics_data, 'session', None)}"
            )
        if out_lap_fresh and graphics_data is not None and physics_view.data is not None:
            session_key = (
                getattr(graphics_data, "session_index", None),
                getattr(graphics_data, "session", None),
            )
            active = self._out_lap_observer.observe(
                graphics_data, getattr(physics_view.data, "speed_kph", None), session_key
            )
            completed_lap_out_lap = self._out_lap_observer.last_completed_lap_out_lap
        else:
            active = False
        with self._lock:
            self._out_lap_active = bool(active)
            self._out_lap_fresh = out_lap_fresh
            if completed_lap_out_lap is not None:
                self._last_completed_lap_out_lap = completed_lap_out_lap
        lap_events = self._lap_event_observer.observe(
            telemetry, completed_lap_out_lap=completed_lap_out_lap
        )
        # Publish the lap event before exposing the matching snapshot revision.
        # The compact boundary sample travels with the event, so history never
        # has to correlate against a later/coalesced live snapshot.
        physics_sample = None
        if physics_view.is_fresh and physics_view.data is not None:
            physics_data = physics_view.data
            physics_sample = {
                "capture_sequence": physics_view.capture_sequence,
                "capture_timestamp_ns": physics_view.capture_timestamp_ns,
                "fuel_remaining_l": getattr(physics_data, "fuel_kg", None),
                "tyre_pressure_psi": tuple(getattr(physics_data, "tyre_pressure_psi", ())),
                "tyre_core_temp_c": tuple(getattr(physics_data, "tyre_core_temp_c", ())),
                "brake_temp_c": tuple(getattr(physics_data, "brake_temp_c", ())),
                "car_damage": tuple(getattr(physics_data, "car_damage", ())),
                "air_temp_c": getattr(physics_data, "air_temp_c", None),
                "road_temp_c": getattr(physics_data, "road_temp_c", None),
            }
        graphics_sample = None
        if graphics_view.is_fresh and graphics_view.data is not None:
            graphics_data = graphics_view.data
            graphics_sample = {
                "capture_sequence": graphics_view.capture_sequence,
                "capture_timestamp_ns": graphics_view.capture_timestamp_ns,
                "fuel_per_lap_l": getattr(graphics_data, "fuel_per_lap_l", None),
                "fuel_used_l": getattr(graphics_data, "used_fuel_l", None),
                "tyre_compound": getattr(graphics_data, "tyre_compound", None),
                "position": getattr(graphics_data, "position", None),
                "gap_ahead_ms": getattr(graphics_data, "gap_ahead_ms", None),
                "gap_behind_ms": getattr(graphics_data, "gap_behind_ms", None),
                "penalty_time_s": getattr(graphics_data, "penalty_time_s", None),
                "mandatory_pit_done": getattr(graphics_data, "mandatory_pit_done", None),
                "driver_stint_left_ms": getattr(graphics_data, "driver_stint_left_ms", None),
                "rain_intensity": getattr(graphics_data, "rain_intensity", None),
                "track_grip_status": getattr(graphics_data, "track_grip_status", None),
            }
        for candidate in lap_events:
            payload = dict(candidate.payload)
            if candidate.event_type == "lap.completed":
                payload["strategy_sample"] = {
                    "physics": physics_sample,
                    "graphics": graphics_sample,
                }
            self._events.publish(
                candidate.event_type,
                session_id=self._strategy_session_id or candidate.session_id,
                source_stream="graphics",
                source_capture_sequence=candidate.source_capture_sequence,
                source_timestamp_ns=candidate.source_timestamp_ns,
                payload=payload,
            )

        with self._lock:
            self._revision += 1
            envelope = DecodedSnapshotEnvelope(
                revision=self._revision,
                published_at_ns=self._clock_ns(),
                telemetry=telemetry,
            )
            self._latest = envelope
            self._published_count += 1
            self._last_error = None
            subscribers = tuple(self._subscribers.values())
        for subscriber in subscribers:
            subscriber._publish(envelope)

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

    def reconcile_lap_progress(self) -> LapProgressReconciliation | None:
        """Resync a consumer's lap cursor from the latest fresh ACC state.

        This does not replay or reconstruct missing historical lap records.
        A caller must retain that distinction after an event sequence gap.
        """
        envelope = self.latest
        if envelope is None:
            return None
        result = reconcile_lap_progress(envelope.telemetry, now_ns=self._clock_ns())
        session_id = self.strategy_session_id
        if result is not None and session_id is not None:
            return replace(result, session_id=session_id)
        return result

    @property
    def strategy_session_id(self) -> str | None:
        """Unique identity for the currently observed LIVE run/session."""
        with self._lock:
            return self._strategy_session_id

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
    def latest(self) -> DecodedSnapshotEnvelope | None:
        with self._lock:
            return self._latest

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started": self._started,
                "closed": self._closed,
                "subscriber_count": len(self._subscribers),
                "revision": self._revision,
                "published_count": self._published_count,
                "wake_count": self._wake_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "event_delivery": self._events.metrics,
            }

    def close(self, *, timeout: float = 2.0) -> bool:
        """Stop the broker worker; return False if it exceeded the timeout."""
        with self._lock:
            if self._closed:
                thread = self._thread
            else:
                self._closed = True
                self._stop.set()
                thread = self._thread
                subscribers = tuple(self._subscribers.values())
                self._subscribers.clear()
                for subscriber in subscribers:
                    subscriber.close()
        self._events.close()
        self._dirty.set()
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True
