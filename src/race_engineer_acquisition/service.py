"""Read-only Race Engineer service over Stage 2 decoded data."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import math
from typing import Any

from .decoded_distribution import DecodedTelemetryBroker
from .fuel_engineer import build_fuel_engineer_snapshot
from .race_progress_strategy import assess_race_progress, race_progress_payload
from .strategy_lap_history import StrategyLapHistory, StrategyLapRecord


def _fuel_sufficiency_payload(fuel: Any, race_progress: Any) -> dict[str, Any]:
    """Compare ACC's own fuel-laps estimate with estimated race distance."""
    fuel_laps = (
        fuel.acc_fuel_laps_remaining
        if fuel.fuel_laps_fresh else None
    )
    race_laps = race_progress.laps_remaining
    current_fuel = fuel.current_fuel_l if fuel.current_fuel_fresh else None
    per_lap = fuel.acc_fuel_per_lap_l if fuel.fuel_per_lap_fresh else None
    blockers = []
    if fuel_laps is None:
        blockers.append("Fresh ACC fuel-laps-remaining value is unavailable.")
    if race_laps is None:
        blockers.append("Estimated remaining race laps are unavailable.")
    required_l = per_lap * race_laps if per_lap is not None and race_laps is not None else None
    margin_l = current_fuel - required_l if current_fuel is not None and required_l is not None else None
    margin_laps = fuel_laps - race_laps if fuel_laps is not None and race_laps is not None else None
    return {
        "status": (
            "unavailable" if blockers
            else "estimated_shortfall" if margin_laps is not None and margin_laps < 0
            else "estimated_sufficient"
        ),
        "acc_fuel_laps_remaining": fuel_laps,
        "estimated_race_laps_remaining": race_laps,
        "fuel_margin_laps": margin_laps,
        "current_fuel_l": current_fuel,
        "acc_fuel_per_lap_l": per_lap,
        "estimated_fuel_required_l": required_l,
        "fuel_margin_l": margin_l,
        "blockers": blockers,
    }


class RaceEngineerService:
    """Expose fresh live state and shared compact lap history to consumers."""

    def __init__(self, runtime: Any, *, history_path: str | Path | None = None) -> None:
        self._broker = DecodedTelemetryBroker(runtime)
        self._live_subscription = self._broker.subscribe("race-engineer-live-state")
        self._lap_events = self._broker.subscribe_events(
            "strategy-lap-history-events", capacity=256
        )
        self._lap_history = StrategyLapHistory(history_path)

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
            parts.append(f"{fuel.fuel_used_l:.1f} litres used")
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
        history = self._update_lap_history(telemetry, track=track, car=car)
        lap_records = self._lap_history.read_records()
        race_progress = assess_race_progress(
            telemetry,
            lap_records=lap_records,
        )
        return {
            "fuel_engineer": asdict(fuel),
            "race_progress": race_progress_payload(race_progress),
            "fuel_sufficiency_strategy": _fuel_sufficiency_payload(fuel, race_progress),
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
