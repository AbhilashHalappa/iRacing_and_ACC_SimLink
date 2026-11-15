"""Compare ACC fuel endurance and capacity with estimated remaining race distance."""
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
    tank_capacity_l: float | None = None
    tank_capacity_status: str = "unavailable"
    tank_capacity_blockers: tuple[str, ...] = ()


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def _finite_positive(value: Any) -> float | None:
    """Fuel consumption and tank capacity must be finite and strictly positive."""
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
    max_fuel_capacity_l: Any = None,
    fuel_capacity_fresh: bool = False,
    safety_reserve_laps: int = 3,
) -> FuelSufficiencyAssessment:
    """Compare ACC endurance and only recommend a pit addition when tank capacity is known.

    ACC Static max_fuel is a litre-valued tank-capacity field. It is accepted
    only from a fresh decoded Static snapshot; no generic capacity is assumed.
    """
    fuel_laps = _finite_nonnegative(acc_fuel_laps_remaining) if fuel_laps_fresh else None
    race_laps = (
        estimated_race_laps_remaining
        if isinstance(estimated_race_laps_remaining, int)
        and not isinstance(estimated_race_laps_remaining, bool)
        and estimated_race_laps_remaining >= 0 else None
    )
    fuel = _finite_nonnegative(current_fuel_l) if current_fuel_fresh else None
    per_lap = _finite_positive(acc_fuel_per_lap_l) if fuel_per_lap_fresh else None
    capacity = _finite_positive(max_fuel_capacity_l) if fuel_capacity_fresh else None
    blockers: list[str] = []
    capacity_blockers: list[str] = []
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
    if capacity is None:
        capacity_status = "unavailable"
        capacity_blockers.append(
            "Fresh ACC Static max_fuel capacity is unavailable or invalid; tank capacity is unknown."
        )
    else:
        capacity_status = "within_capacity"

    required_l = per_lap * race_laps if per_lap is not None and race_laps is not None else None
    reserve_l = per_lap * reserve_laps if per_lap is not None else None
    safety_target_l = (
        required_l + reserve_l
        if required_l is not None and reserve_l is not None else None
    )

    fuel_to_add_l = None
    fuel_to_add_status = "unavailable"
    if capacity is None:
        fuel_to_add_status = "capacity_unavailable"
    elif fuel is not None and fuel > capacity:
        capacity_status = "current_fuel_exceeds_capacity"
        capacity_blockers.append(
            "Current fuel exceeds the validated ACC tank capacity; pit-add recommendation suppressed."
        )
        fuel_to_add_status = "capacity_exceeded"
    elif safety_target_l is not None and safety_target_l > capacity:
        capacity_status = "target_exceeds_capacity"
        capacity_blockers.append(
            "Finish fuel plus safety reserve exceeds the validated ACC tank capacity; the target is physically impossible."
        )
        fuel_to_add_status = "target_exceeds_capacity"
    elif fuel is not None and per_lap is not None and safety_target_l is not None:
        # Existing recommendation assumes the stop occurs at the end of this
        # lap. Both target and fuel-at-arrival reduce by one lap of consumption.
        # Validate the post-stop target against tank capacity and calculate
        # the maximum addition from the projected pit-arrival fuel level.
        arrival_fuel = max(0.0, fuel - per_lap)
        post_stop_target = max(0.0, safety_target_l - per_lap)
        available_space = max(0.0, capacity - arrival_fuel)
        requested_add = max(0.0, post_stop_target - arrival_fuel)
        fuel_to_add_l = min(requested_add, available_space)
        fuel_to_add_status = "estimate_available"

    if blockers:
        return FuelSufficiencyAssessment(
            "unavailable", fuel_laps, race_laps, None, fuel, per_lap,
            required_l, None, reserve_laps, reserve_l, None, safety_target_l,
            None, "unavailable", fuel_to_add_l, fuel_to_add_status,
            tuple(blockers), capacity, capacity_status, tuple(capacity_blockers),
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
        safety_margin_l, safety_status, fuel_to_add_l, fuel_to_add_status,
        (), capacity, capacity_status, tuple(capacity_blockers),
    )


def fuel_sufficiency_payload(assessment: FuelSufficiencyAssessment) -> dict[str, Any]:
    return asdict(assessment)
