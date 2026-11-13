"""Small Race Engineer service boundary for fresh ACC observations.

This service reuses the existing acquisition consumers through the snapshot
aggregator. It never reads shared memory, writes to ACC, or controls the MFD.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .decoded_distribution import DecodedTelemetryBroker
from .fuel_engineer import build_fuel_engineer_snapshot


class RaceEngineerService:
    """Build detached, freshness-gated observations for the desktop bridge."""

    def __init__(self, runtime: Any) -> None:
        self._broker = DecodedTelemetryBroker(runtime)
        self._fuel_subscription = self._broker.subscribe("fuel-engineer-observation")

    def start(self) -> None:
        """Start the independent decoded-data distribution worker."""
        self._broker.start()

    def close(self) -> bool:
        """Stop distribution cleanly during desktop shutdown."""
        self._fuel_subscription.close()
        return self._broker.close()

    @staticmethod
    def _fuel_radio_preview(fuel: Any) -> str:
        if not fuel.current_fuel_fresh:
            return "Fuel telemetry unavailable or stale. No fuel recommendation."
        parts = [f"{fuel.current_fuel_l:.1f} litres remaining"]
        if fuel.fuel_per_lap_fresh and fuel.fuel_per_lap_candidate_l is not None:
            parts.append(f"{fuel.fuel_per_lap_candidate_l:.2f} litres per lap")
        if fuel.estimated_laps_fresh and fuel.estimated_laps_candidate is not None:
            parts.append(f"{fuel.estimated_laps_candidate:.1f} laps estimated")
        if fuel.fuel_used_l is not None:
            parts.append(f"{fuel.fuel_used_l:.1f} litres used")
        if fuel.mfd_fuel_to_add_l is not None:
            parts.append(f"MFD fuel-to-add {fuel.mfd_fuel_to_add_l:.1f} litres")
        return "Fuel status: " + "; ".join(parts) + "."

    def snapshot(self) -> dict[str, Any]:
        envelope = self._fuel_subscription.read_latest()
        if envelope is None:
            raise RuntimeError("decoded telemetry broker has not published its initial snapshot")
        telemetry = envelope.telemetry
        fuel = build_fuel_engineer_snapshot(telemetry)
        return {
            "fuel_engineer": asdict(fuel),
            "fuel_radio_preview": {
                "text": self._fuel_radio_preview(fuel),
                "kind": "observation_only",
                "speech_enabled": False,
                "strategy_recommendations_enabled": fuel.strategy_calculations_enabled,
            },
        }
