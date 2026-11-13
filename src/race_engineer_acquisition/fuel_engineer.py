"""Read-only ACC fuel observations for the Race Engineer.

This first slice exposes current fuel in litres and keeps Graphics fuel
strategy candidates explicitly untrusted until they are correlated with ACC.
It performs no finish-fuel, shortfall, saving, or pit-refuelling calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class FuelEngineerSnapshot:
    """Fuel observations with source freshness and validation state."""

    current_fuel_l: float | None
    current_fuel_fresh: bool
    fuel_per_lap_candidate_l: float | None
    fuel_per_lap_fresh: bool
    estimated_laps_candidate: float | None
    estimated_laps_fresh: bool
    mfd_fuel_to_add_candidate_l: float | None
    graphics_fresh: bool
    strategy_calculations_enabled: bool
    blockers: tuple[str, ...]


def _nonnegative_finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def build_fuel_engineer_snapshot(
    telemetry: Any,
    *,
    fuel_per_lap_validated: bool = False,
    estimated_laps_validated: bool = False,
    safety_reserve_l: float | None = None,
) -> FuelEngineerSnapshot:
    """Build a conservative fuel view from the existing aggregate snapshot.

    Physics and Graphics are independent streams. Each value is exposed only
    when its own stream is fresh. The Physics decoder legacy field name
    fuel_kg is deliberately interpreted as litres based on the user direct
    in-game confirmation; the numeric value is not converted.

    Strategy calculations remain disabled unless both Graphics semantics are
    explicitly validated and a non-negative safety reserve is supplied.
    """
    physics = telemetry.physics
    graphics = telemetry.graphics
    physics_data = physics.data if physics.is_fresh else None
    graphics_data = graphics.data if graphics.is_fresh else None

    # The legacy decoder member name is misleading: ACC fuel was directly
    # checked by the user and confirmed to be litres.
    current_fuel = (
        _nonnegative_finite(getattr(physics_data, "fuel_kg", None))
        if physics_data is not None else None
    )
    per_lap = (
        _nonnegative_finite(getattr(graphics_data, "fuel_per_lap_l", None))
        if graphics_data is not None else None
    )
    estimated_laps = (
        _nonnegative_finite(getattr(graphics_data, "fuel_estimated_laps", None))
        if graphics_data is not None else None
    )
    mfd_to_add = (
        _nonnegative_finite(getattr(graphics_data, "mfd_fuel_to_add", None))
        if graphics_data is not None else None
    )

    reserve = _nonnegative_finite(safety_reserve_l)
    blockers: list[str] = []
    if current_fuel is None:
        blockers.append("Current fuel is unavailable, invalid, or stale.")
    if not fuel_per_lap_validated or per_lap is None:
        blockers.append("Fuel-per-lap data has not been validated against ACC.")
    if not estimated_laps_validated or estimated_laps is None:
        blockers.append("Estimated-laps data has not been validated against ACC.")
    if reserve is None:
        blockers.append("A safety-fuel reserve has not been configured.")

    calculations_enabled = not blockers
    return FuelEngineerSnapshot(
        current_fuel_l=current_fuel,
        current_fuel_fresh=current_fuel is not None,
        fuel_per_lap_candidate_l=per_lap,
        fuel_per_lap_fresh=per_lap is not None,
        estimated_laps_candidate=estimated_laps,
        estimated_laps_fresh=estimated_laps is not None,
        mfd_fuel_to_add_candidate_l=mfd_to_add,
        graphics_fresh=graphics.is_fresh,
        strategy_calculations_enabled=calculations_enabled,
        blockers=tuple(blockers),
    )
