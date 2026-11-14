"""Conservative, read-only Fuel Strategy calculations.

This module consumes the existing decoded FuelEngineerSnapshot. It does not
read ACC memory, infer race distance, issue pit commands, or speak to TTS.
A finish-fuel calculation is enabled only when actual remaining race laps are
explicitly supplied by a validated race-progress provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Literal


FuelStrategyStatus = Literal["insufficient_data", "no_stop_required", "fuel_shortfall"]


@dataclass(frozen=True, slots=True)
class FuelStrategyAssessment:
    """One explainable fuel feasibility assessment."""

    status: FuelStrategyStatus
    calculation_enabled: bool
    reserve_laps: float
    reserve_fuel_l: float | None
    estimated_laps_available: float | None
    estimated_laps_after_reserve: float | None
    reserve_laps_shortfall: float | None
    remaining_race_laps: float | None
    target_fuel_l: float | None
    projected_finish_margin_l: float | None
    recommendation: None
    blockers: tuple[str, ...]


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def assess_fuel_strategy(
    fuel: Any,
    *,
    remaining_race_laps: float | None = None,
    remaining_race_laps_validated: bool = False,
    reserve_laps: float = 3.0,
) -> FuelStrategyAssessment:
    """Assess finish-fuel feasibility using only fresh, validated inputs.

    remaining_race_laps must mean laps remaining until the actual ACC finish,
    not a raw race-lap-limit field or a timer-derived guess. Its provider must
    explicitly mark the value validated. This function deliberately does not
    turn a shortfall into a pit recommendation: saving feasibility, pit timing,
    tank capacity, pit loss and refuelling constraints are separate release
    gates owned by later strategy layers.
    """
    reserve = _finite_nonnegative(reserve_laps)
    if reserve is None or reserve <= 0.0:
        raise ValueError("reserve_laps must be a finite positive number")

    current_fuel = (
        _finite_nonnegative(getattr(fuel, "current_fuel_l", None))
        if getattr(fuel, "current_fuel_fresh", False) else None
    )
    fuel_per_lap = (
        _finite_nonnegative(getattr(fuel, "fuel_per_lap_candidate_l", None))
        if getattr(fuel, "fuel_per_lap_fresh", False) else None
    )
    estimated_laps = (
        _finite_nonnegative(getattr(fuel, "estimated_laps_candidate", None))
        if getattr(fuel, "estimated_laps_fresh", False) else None
    )

    blockers: list[str] = []
    if current_fuel is None:
        blockers.append("Fresh current fuel in litres is unavailable.")
    if fuel_per_lap is None or fuel_per_lap <= 0.0:
        blockers.append("Fresh, positive fuel-per-lap data is unavailable.")
    race_laps = _finite_nonnegative(remaining_race_laps)
    if not remaining_race_laps_validated or race_laps is None:
        blockers.append("Laps remaining to the actual race finish are not validated.")

    reserve_fuel = reserve * fuel_per_lap if fuel_per_lap is not None else None
    laps_after_reserve = (
        max(0.0, estimated_laps - reserve) if estimated_laps is not None else None
    )
    reserve_laps_shortfall = (
        max(0.0, reserve - estimated_laps) if estimated_laps is not None else None
    )

    if blockers:
        return FuelStrategyAssessment(
            status="insufficient_data",
            calculation_enabled=False,
            reserve_laps=reserve,
            reserve_fuel_l=reserve_fuel,
            estimated_laps_available=estimated_laps,
            estimated_laps_after_reserve=laps_after_reserve,
            reserve_laps_shortfall=reserve_laps_shortfall,
            remaining_race_laps=race_laps,
            target_fuel_l=None,
            projected_finish_margin_l=None,
            recommendation=None,
            blockers=tuple(blockers),
        )

    target_fuel = (race_laps + reserve) * fuel_per_lap
    margin = current_fuel - target_fuel
    status: FuelStrategyStatus = "no_stop_required" if margin >= 0.0 else "fuel_shortfall"
    return FuelStrategyAssessment(
        status=status,
        calculation_enabled=True,
        reserve_laps=reserve,
        reserve_fuel_l=reserve_fuel,
        estimated_laps_available=estimated_laps,
        estimated_laps_after_reserve=laps_after_reserve,
        reserve_laps_shortfall=reserve_laps_shortfall,
        remaining_race_laps=race_laps,
        target_fuel_l=target_fuel,
        projected_finish_margin_l=margin,
        recommendation=None,
        blockers=(),
    )
