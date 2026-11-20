"""Read-only Race Engineer service over Stage 2 decoded data."""
from __future__ import annotations

from dataclasses import asdict
from threading import Event, Lock, Thread
import time
import math
from pathlib import Path
from typing import Any

from .decoded_distribution import DecodedTelemetryBroker
from .decoded_sample_fanout import DecodedSampleSubscription
from .fuel_engineer import SessionFuelUsedAccumulator, build_fuel_engineer_snapshot
from .fuel_sufficiency_strategy import assess_fuel_sufficiency, fuel_sufficiency_payload
from .race_progress_strategy import assess_race_progress, race_progress_payload
from .strategy_lap_history import StrategyLapHistory, StrategyLapRecord
from .performance_lap_capture import PerformanceLapCaptureWorker
from .performance_analysis_service import analyze_archived_laps
from .session_analysis import build_session_summary
from .racing_line_analysis import build_track_trajectory
from .track_model import build_track_model
from .track_model_archive import CanonicalTrackModelStore
from .live_coach_adapter import build_acc_live_coach_source
from .performance_lap_archive import (
    LapArchiveContext,
    PerformanceArchiveConfig,
    PerformanceLapArchive,
    PerformanceLapPersistenceWorker,
)


def _fresh_acc_max_fuel_capacity_l(telemetry: Any) -> tuple[Any, bool]:
    """Return ACC Static max_fuel only while the decoded Static page is fresh."""
    static_view = getattr(telemetry, "static_decoded", None)
    if static_view is None or not getattr(static_view, "is_fresh", False):
        return None, False
    static_data = getattr(static_view, "data", None)
    if static_data is None:
        return None, False
    return getattr(static_data, "max_fuel", None), True


def _race_rules_observation(telemetry: Any) -> dict[str, Any]:
    """Expose decoded Graphics race-rule candidates without assigning unvalidated semantics."""
    graphics_view = getattr(telemetry, "graphics", None)
    if graphics_view is None or not getattr(graphics_view, "is_fresh", False):
        return {
            "status": "unavailable",
            "capture_sequence": None,
            "capture_timestamp_ns": None,
            "semantics": "unqualified_candidates",
            "mandatory_pit_done_candidate": None,
            "missing_mandatory_pits_candidate": None,
            "driver_stint_total_ms_candidate": None,
            "driver_stint_left_ms_candidate": None,
            "is_in_pit_candidate": None,
            "is_in_pit_lane_candidate": None,
        }
    graphics = getattr(graphics_view, "data", None)
    if graphics is None:
        return {
            "status": "unavailable",
            "capture_sequence": getattr(graphics_view, "capture_sequence", None),
            "capture_timestamp_ns": getattr(graphics_view, "capture_timestamp_ns", None),
            "semantics": "unqualified_candidates",
            "mandatory_pit_done_candidate": None,
            "missing_mandatory_pits_candidate": None,
            "driver_stint_total_ms_candidate": None,
            "driver_stint_left_ms_candidate": None,
            "is_in_pit_candidate": None,
            "is_in_pit_lane_candidate": None,
        }
    return {
        "status": "fresh",
        "capture_sequence": getattr(graphics_view, "capture_sequence", None),
        "capture_timestamp_ns": getattr(graphics_view, "capture_timestamp_ns", None),
        "semantics": "unqualified_candidates",
        "mandatory_pit_done_candidate": getattr(graphics, "mandatory_pit_done", None),
        "missing_mandatory_pits_candidate": getattr(graphics, "missing_mandatory_pits", None),
        "driver_stint_total_ms_candidate": getattr(graphics, "driver_stint_total_ms", None),
        "driver_stint_left_ms_candidate": getattr(graphics, "driver_stint_left_ms", None),
        "is_in_pit_candidate": getattr(graphics, "is_in_pit", None),
        "is_in_pit_lane_candidate": getattr(graphics, "is_in_pit_lane", None),
    }


def _is_next_assessable_lap_event(
    event: Any,
    *,
    session_id: str | None,
    last_session_id: str | None,
    last_lap_number: int | None,
) -> bool:
    """Accept one classified, non-out completed lap in the active session."""
    if getattr(event, "event_type", None) != "lap.completed":
        return False
    if not session_id or getattr(event, "session_id", None) != session_id:
        return False
    payload = getattr(event, "payload", {})
    if not isinstance(payload, dict) and not hasattr(payload, "get"):
        return False
    lap_number = payload.get("lap_number")
    if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
        return False
    if not isinstance(payload.get("lap_valid"), bool):
        return False
    if payload.get("out_lap") is not False:
        return False
    if last_session_id == session_id and last_lap_number is not None:
        # A repeated lap number is a duplicate; a jump means an event was
        # skipped. Neither is allowed to advance strategy assessment state.
        return lap_number == last_lap_number + 1
    return True


class RaceEngineerService:
    """Expose fresh live state and shared compact lap history to consumers."""

    def __init__(
        self, runtime: Any, *, history_path: str | Path | None = None,
        performance_archive_path: str | Path | None = None,
        performance_archive_config: PerformanceArchiveConfig | None = None,
    ) -> None:
        self._broker = DecodedTelemetryBroker(runtime)
        self._live_subscription = self._broker.subscribe("race-engineer-live-state")
        self._lap_events = self._broker.subscribe_events(
            "strategy-lap-history-events", capacity=256
        )
        # Performance Hub owns independent bounded subscriptions. These do not
        # consume or alter the Race Strategy event mailbox or live snapshot.
        self._performance_samples = self._broker.subscribe_samples(
            "performance-hub-lap-capture", capacity=100_000
        )
        self._performance_events = self._broker.subscribe_events(
            "performance-hub-lap-events", capacity=256
        )
        self._performance_capture = PerformanceLapCaptureWorker(
            self._performance_samples, self._performance_events,
            sample_capacity=100_000, result_capacity=4,
        )
        self._performance_archive = PerformanceLapArchive(
            performance_archive_path or None,
            config=performance_archive_config,
        )
        self._canonical_track_models = CanonicalTrackModelStore()
        self._performance_persistence = PerformanceLapPersistenceWorker(
            self._performance_capture,
            self._performance_archive,
            self._performance_archive_context,
        )
        self._lap_history = StrategyLapHistory(history_path)
        self._session_fuel_used = SessionFuelUsedAccumulator()
        self._assessment_stop = Event()
        self._assessment_thread: Thread | None = None
        self._assessment_lock = Lock()
        self._latest_race_progress: dict[str, Any] | None = None
        self._latest_fuel_sufficiency: dict[str, Any] | None = None
        self._assessment_count = 0
        self._last_assessment_event_id: str | None = None
        self._last_assessment_lap_number: int | None = None
        self._last_assessment_session_id: str | None = None
        self._last_seen_lap_session_id: str | None = None
        self._last_seen_lap_number: int | None = None
        self._processed_assessment_event_ids: set[str] = set()
        self._assessment_session_id: str | None = None
        self._last_broker_revision = 0
        self._track: str | None = None
        self._car: str | None = None
        self._last_race_rules_diagnostic: tuple[Any, ...] | None = None

    def start(self) -> None:
        self._broker.start()
        self._performance_capture.start()
        self._performance_persistence.start()
        if self._assessment_thread is None or not self._assessment_thread.is_alive():
            self._assessment_stop.clear()
            self._assessment_thread = Thread(
                target=self._run_background_assessments,
                name="ACC-Fuel-Strategy-Assessment",
                daemon=True,
            )
            self._assessment_thread.start()

    def close(self) -> bool:
        self._assessment_stop.set()
        worker = self._assessment_thread
        if worker is not None:
            worker.join(timeout=2.0)
        performance_stopped = self._performance_capture.close(timeout=5.0)
        persistence_stopped = False
        if performance_stopped:
            persistence_stopped = self._performance_persistence.close(timeout=10.0)
            if persistence_stopped:
                self._performance_archive.close()
        self._live_subscription.close()
        self._lap_events.close()
        self._broker.unsubscribe_samples(
            "performance-hub-lap-capture", discard_pending=True
        )
        self._broker.unsubscribe_events("performance-hub-lap-events")
        stopped = self._broker.close()
        self._lap_history.close()
        return (
            stopped and performance_stopped and persistence_stopped
            and (worker is None or not worker.is_alive())
        )

    def _performance_archive_context(self) -> LapArchiveContext:
        """Snapshot identity/weather metadata without touching acquisition feeds."""
        envelope = self._live_subscription.latest
        if envelope is None:
            return LapArchiveContext()
        telemetry = envelope.telemetry
        static_view = getattr(telemetry, "static_decoded", None)
        static_data = (
            getattr(static_view, "data", None)
            if static_view is not None and getattr(static_view, "is_fresh", False)
            else None
        )
        graphics_view = getattr(telemetry, "graphics", None)
        graphics = (
            getattr(graphics_view, "data", None)
            if graphics_view is not None and getattr(graphics_view, "is_fresh", False)
            else None
        )
        physics_view = getattr(telemetry, "physics", None)
        physics = (
            getattr(physics_view, "data", None)
            if physics_view is not None and getattr(physics_view, "is_fresh", False)
            else None
        )
        weather = {
            "rain_intensity": getattr(graphics, "rain_intensity", None),
            "rain_10min": getattr(graphics, "rain_10min", None),
            "rain_30min": getattr(graphics, "rain_30min", None),
            "track_grip_status": getattr(graphics, "track_grip_status", None),
            "surface_grip": getattr(graphics, "surface_grip", None),
            "wind_speed": getattr(graphics, "wind_speed", None),
            "wind_direction": getattr(graphics, "wind_direction", None),
            "air_temp_c": getattr(physics, "air_temp_c", None),
            "road_temp_c": getattr(physics, "road_temp_c", None),
        }
        source_timestamps = {
            "static": getattr(static_view, "capture_timestamp_ns", None),
            "graphics": getattr(graphics_view, "capture_timestamp_ns", None),
            "physics": getattr(physics_view, "capture_timestamp_ns", None),
        }
        return LapArchiveContext(
            car_model=getattr(static_data, "car_model", None),
            track=getattr(static_data, "track", None),
            track_configuration=getattr(static_data, "track_configuration", None),
            session_index=getattr(graphics, "session_index", None),
            session_type=getattr(graphics, "session", None),
            weather=weather,
            metadata_source_timestamps_ns=source_timestamps,
        )

    @property
    def performance_archive_metrics(self) -> dict[str, Any]:
        """Expose durable archive and asynchronous writer health."""
        return {
            "capture": self._performance_capture.metrics,
            "persistence": self._performance_persistence.metrics,
            "archive": self._performance_archive.metrics,
        }

    def read_performance_archive_laps(
        self, *, session_id: str | None = None, car_model: str | None = None,
        track: str | None = None, track_configuration: str | None = None,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        """Read archive metadata through the service, never from the UI directly."""
        return self._performance_archive.read_laps(
            session_id=session_id, car_model=car_model, track=track,
            track_configuration=track_configuration, limit=limit,
        )

    def performance_session_summary(self, session_id: str) -> dict[str, Any]:
        """Return a compact session summary and lap history from the archive."""
        rows = self._performance_archive.read_laps(session_id=session_id, limit=5000)
        return build_session_summary(rows)

    def read_performance_lap_trace(
        self, session_id: str, lap_number: int
    ) -> dict[str, Any] | None:
        """Read one source-preserving retained trace for analysis consumers."""
        return self._performance_archive.read_trace(session_id, lap_number)

    def analyze_performance_laps(
        self, *, reference_session_id: str, reference_lap_number: int,
        comparison_session_id: str, comparison_lap_number: int,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Run offline Performance Hub analysis against retained archive traces.

        This is an explicit request-path operation. It does not run on the
        telemetry broker, capture worker, persistence worker, or UI hot path.
        """
        return analyze_archived_laps(
            self._performance_archive,
            reference_session_id=reference_session_id,
            reference_lap_number=reference_lap_number,
            comparison_session_id=comparison_session_id,
            comparison_lap_number=comparison_lap_number,
            policy=policy,
            canonical_track_model_store=self._canonical_track_models,
        )

    def save_canonical_track_model(
        self, *, session_id: str, lap_number: int, geometry_policy: dict[str, Any],
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Explicitly promote one retained valid lap to the track reference model."""
        required = (
            "minimum_point_spacing_m", "minimum_turn_angle_rad",
            "minimum_corner_length_m", "merge_gap_m",
        )
        missing = [key for key in required if key not in geometry_policy]
        if missing:
            raise ValueError("missing geometry policy values: " + ", ".join(missing))
        for key in required:
            value = geometry_policy[key]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{key} must be a finite number")
        if geometry_policy["minimum_point_spacing_m"] < 0:
            raise ValueError("minimum_point_spacing_m must be non-negative")
        if not 0 < geometry_policy["minimum_turn_angle_rad"] < 3.141592653589793:
            raise ValueError("minimum_turn_angle_rad must be between 0 and pi")
        if geometry_policy["minimum_corner_length_m"] <= 0 or geometry_policy["merge_gap_m"] < 0:
            raise ValueError("corner length must be positive and merge gap non-negative")
        metadata = self._performance_archive.read_lap_metadata(session_id, lap_number)
        if metadata is None:
            raise LookupError(f"lap not found in archive: {session_id}:{lap_number}")
        if metadata.get("lap_valid") != 1 or metadata.get("out_lap") != 0:
            raise ValueError("only a valid non-out lap can be selected as canonical reference")
        if metadata.get("trace_status") not in ("retained", "identity_incomplete"):
            raise ValueError("selected reference lap has no retained full trace")
        track = metadata.get("track")
        track_configuration = metadata.get("track_configuration")
        if not isinstance(track, str) or not track.strip():
            raise ValueError("selected lap has no track identity")
        if not isinstance(track_configuration, str) or not track_configuration.strip():
            raise ValueError("selected lap has no track configuration identity")
        trace = self._performance_archive.read_trace(session_id, lap_number)
        if not isinstance(trace, dict) or not isinstance(trace.get("graphics"), list):
            raise ValueError("selected reference lap trace is unavailable or corrupt")
        trajectory = build_track_trajectory(
            trace["graphics"],
            minimum_point_spacing_m=geometry_policy["minimum_point_spacing_m"],
        )
        model = build_track_model(
            trajectory,
            minimum_turn_angle_rad=geometry_policy["minimum_turn_angle_rad"],
            minimum_corner_length_m=geometry_policy["minimum_corner_length_m"],
            merge_gap_m=geometry_policy["merge_gap_m"],
        )
        if not model.get("available"):
            raise ValueError("selected lap cannot produce a canonical track model: " + str(model.get("reason")))
        return self._canonical_track_models.save_reference_model(
            track, track_configuration, model,
            reference_session_id=session_id,
            reference_lap_number=lap_number,
            reference_lap_time_ms=metadata.get("lap_time_ms"),
            replace_existing=replace_existing,
        )

    def list_canonical_track_models(self) -> tuple[dict[str, Any], ...]:
        """List explicitly saved canonical track models."""
        return self._canonical_track_models.list_models()

    def subscribe_performance_samples(
        self, name: str, *, capacity: int
    ) -> DecodedSampleSubscription:
        """Subscribe to decoded Physics/Graphics samples for offline lap capture.

        The subscription is bounded and loss-accounted. It is deliberately
        separate from the coalescing live-state subscription used by Overview
        and Race Strategy.
        """
        return self._broker.subscribe_samples(name, capacity=capacity)

    def unsubscribe_performance_samples(
        self, name: str, *, discard_pending: bool = False
    ) -> None:
        """Release a Performance Hub sample subscription."""
        self._broker.unsubscribe_samples(name, discard_pending=discard_pending)

    @property
    def performance_sample_delivery_metrics(self) -> dict[str, Any]:
        """Expose Stage 2 sample queue metrics for diagnostics."""
        return self._broker.metrics["sample_delivery"]

    @property
    def performance_lap_capture_metrics(self) -> dict[str, Any]:
        """Expose runtime assembly throughput, errors and bounded-handoff loss."""
        return self._performance_capture.metrics

    def read_strategy_laps(
        self, *, limit: int | None = None
    ) -> tuple[StrategyLapRecord, ...]:
        """Read compact shared lap records for internal strategy calculations."""
        return self._lap_history.read_records(limit=limit)

    def out_lap_status(self) -> dict[str, Any]:
        """Expose the same ACCOutLapObserver state used by lap classification."""
        return self._broker.out_lap_status

    def _update_lap_history(
        self, telemetry: Any, *, track: str | None, car: str | None,
        batch: Any | None = None,
    ) -> dict[str, Any]:
        graphics_view = telemetry.graphics
        graphics = graphics_view.data if graphics_view.is_fresh else None
        cursor = None
        session_id = None
        if (
            graphics is not None
            and getattr(graphics, "status", None) == 2
            and isinstance(getattr(graphics, "completed_laps", None), int)
            and not isinstance(getattr(graphics, "completed_laps", None), bool)
        ):
            cursor = graphics.completed_laps
            # Use the broker's run-scoped identity. ACC session_index and
            # session type are reusable labels, not unique session IDs.
            session_id = self._broker.strategy_session_id

        # Verify a persisted session against its first fresh ACC cursor before
        # appending new events. If the cursor moved while the app was closed,
        # the history remains incomplete rather than inventing missing laps.
        if self._lap_history.recovery_pending and cursor is not None and session_id is not None:
            self._lap_history.observe_live_cursor(
                session_id, cursor, track=track, car=car
            )

        if batch is None:
            batch = self._lap_events.read_batch()
        self._lap_history.consume(batch, telemetry)
        event_timestamps = [
            event.source_timestamp_ns for event in batch.events
            if event.source_timestamp_ns is not None
        ]
        latest_event_timestamp = max(event_timestamps) if event_timestamps else None
        graphics_timestamp = graphics_view.capture_timestamp_ns
        snapshot_covers_events = (
            latest_event_timestamp is None
            or graphics_timestamp is None
            or graphics_timestamp >= latest_event_timestamp
        )
        if cursor is not None and session_id is not None and snapshot_covers_events:
            self._lap_history.observe_live_cursor(
                session_id, cursor, track=track, car=car
            )
        return self._lap_history.snapshot()

    @staticmethod
    def _fuel_radio_preview(fuel: Any) -> str:
        if not fuel.current_fuel_fresh:
            return "Fuel telemetry unavailable or stale. No fuel recommendation."
        parts = [f"{fuel.current_fuel_l:.1f} litres remaining"]
        if fuel.fuel_per_lap_fresh and fuel.acc_fuel_per_lap_l is not None:
            parts.append(f"{fuel.acc_fuel_per_lap_l:.2f} litres per lap")
        if fuel.fuel_laps_fresh and fuel.acc_fuel_laps_remaining is not None:
            parts.append(f"{fuel.acc_fuel_laps_remaining:.1f} fuel laps remaining according to ACC")
        if fuel.fuel_used_l is not None:
            parts.append(f"{fuel.fuel_used_l:.1f} litres used in the current ACC stint")
        if fuel.mfd_fuel_to_add_l is not None:
            parts.append(f"MFD fuel-to-add {fuel.mfd_fuel_to_add_l:.1f} litres")
        return "Fuel status: " + "; ".join(parts) + "."


    def _calculate_fuel_assessment(self, telemetry: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Calculate one immutable strategy result from the supplied decoded snapshot."""
        fuel = build_fuel_engineer_snapshot(telemetry)
        current_session_id = self._broker.strategy_session_id
        lap_records = tuple(
            record for record in self._lap_history.read_records()
            if current_session_id is not None and record.session_id == current_session_id
        )
        race_progress = assess_race_progress(
            telemetry, lap_records=lap_records, lap_limit_qualified=True,
        )
        max_fuel_capacity_l, fuel_capacity_fresh = (
            _fresh_acc_max_fuel_capacity_l(telemetry)
        )
        fuel_sufficiency = assess_fuel_sufficiency(
            acc_fuel_laps_remaining=fuel.acc_fuel_laps_remaining,
            fuel_laps_fresh=fuel.fuel_laps_fresh,
            estimated_race_laps_remaining=race_progress.estimated_race_laps_remaining,
            current_fuel_l=fuel.current_fuel_l,
            current_fuel_fresh=fuel.current_fuel_fresh,
            acc_fuel_per_lap_l=fuel.acc_fuel_per_lap_l,
            fuel_per_lap_fresh=fuel.fuel_per_lap_fresh,
            max_fuel_capacity_l=max_fuel_capacity_l,
            fuel_capacity_fresh=fuel_capacity_fresh,
        )
        return race_progress_payload(race_progress), fuel_sufficiency_payload(fuel_sufficiency)

    def _store_background_assessment(
        self, telemetry: Any, *, event_id: str | None = None,
        lap_number: int | None = None,
    ) -> None:
        race_progress, fuel_sufficiency = self._calculate_fuel_assessment(telemetry)
        with self._assessment_lock:
            self._latest_race_progress = race_progress
            self._latest_fuel_sufficiency = fuel_sufficiency
            if event_id is not None:
                self._assessment_count += 1
                self._last_assessment_event_id = event_id
                self._last_assessment_lap_number = lap_number
                self._last_assessment_session_id = self._broker.strategy_session_id
                assessment_count = self._assessment_count
                assessment_session_id = self._last_assessment_session_id

        # Diagnostic only: emitted once after each completed-lap assessment,
        # never for the startup/session seed or ordinary UI snapshot updates.
        if event_id is not None:
            print(
                "[Fuel Assessment] "
                f"trigger=completed_lap session={assessment_session_id} "
                f"lap={lap_number} assessment_count={assessment_count} "
                f"event_id={event_id}",
                flush=True,
            )

    def _run_background_assessments(self) -> None:
        """Assess at startup/session changes and once per unique completed-lap event."""
        empty_batch = type("EmptyBatch", (), {"events": (), "gap_detected": False})()
        seeded = False
        while not self._assessment_stop.is_set():
            batch = self._lap_events.read_batch(max_events=1)
            envelope = self._broker.latest
            if envelope is None:
                self._assessment_stop.wait(0.05)
                continue
            telemetry = envelope.telemetry
            session_id = self._broker.strategy_session_id
            session_changed = not seeded or session_id != self._assessment_session_id
            if session_changed:
                # Reconcile persisted history against the first fresh cursor
                # for each run. Never attach the previous run's laps.
                self._update_lap_history(
                    telemetry, track=self._track, car=self._car, batch=empty_batch
                )
                self._store_background_assessment(telemetry)
                self._assessment_session_id = session_id
                self._last_seen_lap_session_id = session_id
                self._last_seen_lap_number = None
                seeded = True
                if batch.events or batch.gap_detected:
                    self._update_lap_history(
                        telemetry, track=self._track, car=self._car, batch=batch
                    )
            elif batch.events or batch.gap_detected:
                self._update_lap_history(
                    telemetry, track=self._track, car=self._car, batch=batch
                )
            elif envelope.revision != self._last_broker_revision:
                # Keep the lap cursor reconciled even when a completion event
                # was lost; history marks the gap rather than fabricating laps.
                self._update_lap_history(
                    telemetry, track=self._track, car=self._car, batch=empty_batch
                )
            self._last_broker_revision = envelope.revision

            if not batch.events and not batch.gap_detected:
                self._assessment_stop.wait(0.05)
                continue
            if batch.gap_detected:
                continue

            for event in batch.events:
                if event.event_id in self._processed_assessment_event_ids:
                    continue
                if event.event_type == "lap.completion_gap":
                    gap_cursor = event.payload.get("current_completed_laps")
                    if isinstance(gap_cursor, int) and not isinstance(gap_cursor, bool):
                        self._last_seen_lap_session_id = event.session_id
                        self._last_seen_lap_number = gap_cursor
                    continue
                if event.event_type != "lap.completed":
                    continue
                if not event.session_id or event.session_id != session_id:
                    continue
                lap_number = event.payload.get("lap_number")
                if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
                    continue
                if not _is_next_assessable_lap_event(
                    event,
                    session_id=session_id,
                    last_session_id=self._last_seen_lap_session_id,
                    last_lap_number=self._last_seen_lap_number,
                ):
                    # Advance the observation cursor for a new but unclassified,
                    # invalidly classified, or out-lap boundary so it cannot
                    # make the following legitimate lap look like a skipped lap.
                    if (
                        self._last_seen_lap_session_id != session_id
                        or self._last_seen_lap_number is None
                        or lap_number > self._last_seen_lap_number
                    ):
                        self._last_seen_lap_session_id = session_id
                        self._last_seen_lap_number = lap_number
                    continue
                self._last_seen_lap_session_id = session_id
                self._last_seen_lap_number = lap_number
                self._processed_assessment_event_ids.add(event.event_id)
                if len(self._processed_assessment_event_ids) > 512:
                    self._processed_assessment_event_ids = {event.event_id}

                # The broker emits the lap event immediately before publishing
                # the matching snapshot. Wait briefly for that boundary view.
                deadline = time.monotonic() + 0.5
                assessment_telemetry = None
                while not self._assessment_stop.is_set():
                    latest = self._broker.latest
                    graphics_view = latest.telemetry.graphics if latest is not None else None
                    capture_ns = graphics_view.capture_timestamp_ns if graphics_view is not None else None
                    if event.source_timestamp_ns is None:
                        assessment_telemetry = latest.telemetry if latest is not None else None
                        break
                    if capture_ns is not None and capture_ns >= event.source_timestamp_ns:
                        assessment_telemetry = latest.telemetry
                        break
                    if time.monotonic() >= deadline:
                        break
                    self._assessment_stop.wait(0.01)
                if assessment_telemetry is not None and not self._assessment_stop.is_set():
                    # Reconcile the cursor against the boundary snapshot after
                    # consuming the event, then publish exactly one assessment.
                    self._update_lap_history(
                        assessment_telemetry, track=self._track, car=self._car,
                        batch=empty_batch,
                    )
                    self._store_background_assessment(
                        assessment_telemetry, event_id=event.event_id,
                        lap_number=lap_number,
                    )

    def snapshot(
        self, *, track: str | None = None, car: str | None = None
    ) -> dict[str, Any]:
        envelope = self._live_subscription.read_latest()
        if envelope is None:
            raise RuntimeError("decoded telemetry broker has not published its initial snapshot")
        telemetry = envelope.telemetry
        if track is not None:
            self._track = track
        if car is not None:
            self._car = car
        fuel = build_fuel_engineer_snapshot(telemetry)
        session_fuel_used_l = self._session_fuel_used.observe(
            session_id=self._broker.strategy_session_id,
            acc_used_fuel_l=fuel.fuel_used_l,
        )
        history = self._lap_history.snapshot()
        # Keep every UI calculation live on every decoded snapshot. The
        # completed-lap worker is an independent cadence for background
        # strategy/radio consumers and must never gate or cache UI values.
        race_progress_payload_value, fuel_sufficiency_payload_value = (
            self._calculate_fuel_assessment(telemetry)
        )
        race_rules_observation = _race_rules_observation(telemetry)
        if race_rules_observation["status"] == "fresh":
            diagnostic = (
                race_rules_observation["mandatory_pit_done_candidate"],
                race_rules_observation["missing_mandatory_pits_candidate"],
                race_rules_observation["driver_stint_total_ms_candidate"],
                race_rules_observation["driver_stint_left_ms_candidate"],
                race_rules_observation["is_in_pit_candidate"],
                race_rules_observation["is_in_pit_lane_candidate"],
            )
            if diagnostic != self._last_race_rules_diagnostic:
                self._last_race_rules_diagnostic = diagnostic
                print(
                    "[Race Rules Candidate] "
                    f"mandatory_pit_done={diagnostic[0]} "
                    f"missing_mandatory_pits={diagnostic[1]} "
                    f"driver_stint_total_ms={diagnostic[2]} "
                    f"driver_stint_left_ms={diagnostic[3]} "
                    f"is_in_pit={diagnostic[4]} "
                    f"is_in_pit_lane={diagnostic[5]}",
                    flush=True,
                )
        with self._assessment_lock:
            assessment_meta = {
                "trigger": "completed_lap",
                "assessment_count": self._assessment_count,
                "last_event_id": self._last_assessment_event_id,
                "last_lap_number": self._last_assessment_lap_number,
            }
        fuel_payload = asdict(fuel)
        fuel_payload["session_fuel_used_l"] = session_fuel_used_l
        fuel_payload["session_fuel_used_scope"] = "since_race_engineer_connected"
        live_coach_source = build_acc_live_coach_source(
            telemetry,
            session_id=self._broker.strategy_session_id,
            out_lap_status=self._broker.out_lap_status,
        )
        return {
            "live_coach_source": live_coach_source.to_payload(),
            "fuel_engineer": fuel_payload,
            "race_progress": race_progress_payload_value,
            "fuel_sufficiency_strategy": fuel_sufficiency_payload_value,
            "race_rules_observation": race_rules_observation,
            "background_assessment": assessment_meta,
            "static_metadata": {
                "status": "fresh" if telemetry.static_decoded.is_fresh else "unavailable",
                "capture_sequence": telemetry.static_decoded.capture_sequence,
                "capture_timestamp_ns": telemetry.static_decoded.capture_timestamp_ns,
                "last_error": telemetry.static_decoded.last_error,
                "data": (
                    asdict(telemetry.static_decoded.data)
                    if telemetry.static_decoded.is_fresh and telemetry.static_decoded.data is not None
                    else None
                ),
            },
            "strategy_lap_history": history,
            # Compatibility alias for clients that already read the Fuel slice.
            "fuel_lap_history": history,
            "out_lap_status": self._broker.out_lap_status,
            "fuel_radio_preview": {
                "text": self._fuel_radio_preview(fuel),
                "kind": "observation_only",
                "speech_enabled": False,
                "strategy_recommendations_enabled": False,
            },
        }
