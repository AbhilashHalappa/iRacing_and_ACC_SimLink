"""Read-only Race Engineer service over Stage 2 decoded data."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .decoded_distribution import DecodedTelemetryBroker
from .fuel_engineer import SessionFuelUsedAccumulator, build_fuel_engineer_snapshot
from .fuel_sufficiency_strategy import assess_fuel_sufficiency, fuel_sufficiency_payload
from .race_progress_strategy import assess_race_progress, race_progress_payload
from .strategy_lap_history import StrategyLapHistory, StrategyLapRecord


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

    def start(self) -> None:
        self._broker.start()

    def close(self) -> bool:
        self._live_subscription.close()
        self._lap_events.close()
        stopped = self._broker.close()
        self._lap_history.close()
        return stopped

    def read_strategy_laps(
        self, *, limit: int | None = None
    ) -> tuple[StrategyLapRecord, ...]:
        """Read compact shared lap records for internal strategy calculations."""
        return self._lap_history.read_records(limit=limit)

    def out_lap_status(self) -> dict[str, Any]:
        """Expose the same ACCOutLapObserver state used by lap classification."""
        return self._broker.out_lap_status

    def _update_lap_history(
        self, telemetry: Any, *, track: str | None, car: str | None
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

    def snapshot(
        self, *, track: str | None = None, car: str | None = None
    ) -> dict[str, Any]:
        envelope = self._live_subscription.read_latest()
        if envelope is None:
            raise RuntimeError("decoded telemetry broker has not published its initial snapshot")
        telemetry = envelope.telemetry
        fuel = build_fuel_engineer_snapshot(telemetry)
        session_fuel_used_l = self._session_fuel_used.observe(
            session_id=self._broker.strategy_session_id,
            acc_used_fuel_l=fuel.fuel_used_l,
        )
        history = self._update_lap_history(telemetry, track=track, car=car)
        all_lap_records = self._lap_history.read_records()
        current_session_id = self._broker.strategy_session_id
        # Timed-race pace must never borrow valid laps from a previous ACC
        # session, even when track and car are unchanged.
        lap_records = tuple(
            record for record in all_lap_records
            if current_session_id is not None and record.session_id == current_session_id
        )
        race_progress = assess_race_progress(
            telemetry,
            lap_records=lap_records,
        )
        fuel_sufficiency = assess_fuel_sufficiency(
            acc_fuel_laps_remaining=fuel.acc_fuel_laps_remaining,
            fuel_laps_fresh=fuel.fuel_laps_fresh,
            estimated_race_laps_remaining=race_progress.laps_remaining,
            current_fuel_l=fuel.current_fuel_l,
            current_fuel_fresh=fuel.current_fuel_fresh,
            acc_fuel_per_lap_l=fuel.acc_fuel_per_lap_l,
            fuel_per_lap_fresh=fuel.fuel_per_lap_fresh,
        )
        fuel_payload = asdict(fuel)
        fuel_payload["session_fuel_used_l"] = session_fuel_used_l
        fuel_payload["session_fuel_used_scope"] = "since_race_engineer_connected"
        return {
            "fuel_engineer": fuel_payload,
            "race_progress": race_progress_payload(race_progress),
            "fuel_sufficiency_strategy": fuel_sufficiency_payload(fuel_sufficiency),
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
