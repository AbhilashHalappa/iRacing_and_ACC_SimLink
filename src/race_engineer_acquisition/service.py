"""Read-only Race Engineer service over Stage 2 decoded data."""
from __future__ import annotations

from dataclasses import asdict
from threading import Event, Lock, Thread
import time
from pathlib import Path
from typing import Any

from .decoded_distribution import DecodedTelemetryBroker
from .fuel_engineer import SessionFuelUsedAccumulator, build_fuel_engineer_snapshot
from .fuel_sufficiency_strategy import assess_fuel_sufficiency, fuel_sufficiency_payload
from .race_progress_strategy import assess_race_progress, race_progress_payload
from .strategy_lap_history import StrategyLapHistory, StrategyLapRecord


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

    def __init__(self, runtime: Any, *, history_path: str | Path | None = None) -> None:
        self._broker = DecodedTelemetryBroker(runtime)
        self._live_subscription = self._broker.subscribe("race-engineer-live-state")
        self._lap_events = self._broker.subscribe_events(
            "strategy-lap-history-events", capacity=256
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

    def start(self) -> None:
        self._broker.start()
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
        self._live_subscription.close()
        self._lap_events.close()
        stopped = self._broker.close()
        self._lap_history.close()
        return stopped and (worker is None or not worker.is_alive())

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
        return {
            "fuel_engineer": fuel_payload,
            "race_progress": race_progress_payload_value,
            "fuel_sufficiency_strategy": fuel_sufficiency_payload_value,
            "race_rules_observation": _race_rules_observation(telemetry),
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
