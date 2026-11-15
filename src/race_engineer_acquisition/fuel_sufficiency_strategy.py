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
    safety_reserve_laps: int
    safety_reserve_fuel_l: float | None
    safety_margin_laps: float | None
    safety_target_fuel_l: float | None
    safety_fuel_margin_l: float | None
    safety_status: str
    estimated_fuel_to_add_next_pit_l: float | None
    fuel_to_add_estimate_status: str
    blockers: tuple[str, ...]


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def _finite_positive(value: Any) -> float | None:
    """Fuel consumption must be finite and strictly greater than zero."""
    result = _finite_nonnegative(value)
    return result if result is not None and result > 0.0 else None


def assess_fuel_sufficiency(
    *,
    acc_fuel_laps_remaining: Any,
    fuel_laps_fresh: bool,
    estimated_race_laps_remaining: Any,
    current_fuel_l: Any,
    current_fuel_fresh: bool,
    acc_fuel_per_lap_l: Any,
    fuel_per_lap_fresh: bool,
    safety_reserve_laps: int = 3,
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
    per_lap = _finite_positive(acc_fuel_per_lap_l) if fuel_per_lap_fresh else None
    blockers: list[str] = []
    reserve_laps = (
        safety_reserve_laps
        if isinstance(safety_reserve_laps, int)
        and not isinstance(safety_reserve_laps, bool)
        and safety_reserve_laps >= 0
        else 3
    )
    if fuel_laps is None:
        blockers.append("Fresh ACC fuel-laps-remaining value is unavailable.")
    if race_laps is None:
        blockers.append("Estimated remaining race laps are unavailable.")
    if per_lap is None:
        blockers.append(
            "Fresh ACC fuel-per-lap data must be finite and greater than zero."
        )
    required_l = per_lap * race_laps if per_lap is not None and race_laps is not None else None
    reserve_l = per_lap * reserve_laps if per_lap is not None else None
    safety_target_l = (
        required_l + reserve_l
        if required_l is not None and reserve_l is not None else None
    )
    # Estimate the amount to enter in the MFD at the next stop. This assumes
    # the car pits at the end of the current lap: projected fuel at pit arrival
    # and remaining race fuel both decrease by one lap, so the net addition is
    # the safety-adjusted target minus current fuel. Do not publish a number
    # unless all inputs needed for that estimate are fresh and available.
    fuel_to_add_l = (
        max(0.0, safety_target_l - fuel)
        if fuel is not None and safety_target_l is not None else None
    )
    fuel_to_add_status = "estimate_available" if fuel_to_add_l is not None else "unavailable"
    if blockers:
        return FuelSufficiencyAssessment(
            "unavailable", fuel_laps, race_laps, None, fuel, per_lap,
            required_l, None, reserve_laps, reserve_l, None, safety_target_l,
            None, "unavailable", fuel_to_add_l, fuel_to_add_status, tuple(blockers),
        )
    margin_laps = fuel_laps - race_laps
    margin_l = fuel - required_l if fuel is not None and required_l is not None else None
    safety_margin_laps = margin_laps - reserve_laps
    safety_margin_l = (
        fuel - safety_target_l
        if fuel is not None and safety_target_l is not None else None
    )
    safety_status = (
        "unavailable" if safety_margin_laps is None
        else "reserve_shortfall" if safety_margin_laps < 0
        else "reserve_satisfied"
    )
    return FuelSufficiencyAssessment(
        "estimated_shortfall" if margin_laps < 0 else "estimated_sufficient",
        fuel_laps, race_laps, margin_laps, fuel, per_lap, required_l, margin_l,
        reserve_laps, reserve_l, safety_margin_laps, safety_target_l,
        safety_margin_l, safety_status, fuel_to_add_l, fuel_to_add_status, (),
    )


def fuel_sufficiency_payload(assessment: FuelSufficiencyAssessment) -> dict[str, Any]:
    return asdict(assessment)
