"""Compare ACC's fuel endurance with estimated remaining race distance."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class FuelSufficiencyAssessment:
    status: str
    acc_fuel_laps_remaining: float | None
    estimated_race_laps_remaining: int | None
    fuel_margin_laps: float | None
    current_fuel_l: float | None
    acc_fuel_per_lap_l: float | None
    estimated_fuel_required_l: float | None
    fuel_margin_l: float | None
    blockers: tuple[str, ...]


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def assess_fuel_sufficiency(
    *,
    acc_fuel_laps_remaining: Any,
    fuel_laps_fresh: bool,
    estimated_race_laps_remaining: Any,
    current_fuel_l: Any,
    current_fuel_fresh: bool,
    acc_fuel_per_lap_l: Any,
    fuel_per_lap_fresh: bool,
) -> FuelSufficiencyAssessment:
    """Compare ACC's own fuel-laps value; never recalculate fuel endurance."""
    fuel_laps = _finite_nonnegative(acc_fuel_laps_remaining) if fuel_laps_fresh else None
    race_laps = (
        estimated_race_laps_remaining
        if isinstance(estimated_race_laps_remaining, int)
        and not isinstance(estimated_race_laps_remaining, bool)
        and estimated_race_laps_remaining >= 0 else None
    )
    fuel = _finite_nonnegative(current_fuel_l) if current_fuel_fresh else None
    per_lap = _finite_nonnegative(acc_fuel_per_lap_l) if fuel_per_lap_fresh else None
    blockers: list[str] = []
    if fuel_laps is None:
        blockers.append("Fresh ACC fuel-laps-remaining value is unavailable.")
    if race_laps is None:
        blockers.append("Estimated remaining race laps are unavailable.")
    if blockers:
        return FuelSufficiencyAssessment(
            "unavailable", fuel_laps, race_laps, None, fuel, per_lap,
            None, None, tuple(blockers),
        )
    margin_laps = fuel_laps - race_laps
    required_l = per_lap * race_laps if per_lap is not None else None
    margin_l = fuel - required_l if fuel is not None and required_l is not None else None
    return FuelSufficiencyAssessment(
        "estimated_shortfall" if margin_laps < 0 else "estimated_sufficient",
        fuel_laps, race_laps, margin_laps, fuel, per_lap, required_l, margin_l, (),
    )


def fuel_sufficiency_payload(assessment: FuelSufficiencyAssessment) -> dict[str, Any]:
    return asdict(assessment)
