"""Freshness-aware direct ACC fuel observations for the Race Engineer."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class FuelEngineerSnapshot:
    """ACC fuel values, exposed only while their source stream is fresh."""

    current_fuel_l: float | None
    current_fuel_fresh: bool
    acc_fuel_per_lap_l: float | None
    fuel_per_lap_fresh: bool
    acc_fuel_laps_remaining: float | None
    fuel_laps_fresh: bool
    mfd_fuel_to_add_l: float | None
    fuel_used_l: float | None
    graphics_fresh: bool
    strategy_calculations_enabled: bool
    blockers: tuple[str, ...]

    @property
    def fuel_per_lap_candidate_l(self) -> float | None:
        return self.acc_fuel_per_lap_l

    @property
    def estimated_laps_candidate(self) -> float | None:
        return self.acc_fuel_laps_remaining


def _nonnegative_finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def build_fuel_engineer_snapshot(
    telemetry: Any,
    *,
    fuel_per_lap_validated: bool = True,
    estimated_laps_validated: bool = True,
    safety_reserve_l: float | None = None,
) -> FuelEngineerSnapshot:
    """Read ACC fuel and endurance fields directly; no local fuel-lap estimate.

    safety_reserve_l is retained for call compatibility only. ACC's own
    endurance estimate does not require a locally configured reserve.
    """
    del safety_reserve_l
    physics = telemetry.physics
    graphics = telemetry.graphics
    physics_data = physics.data if physics.is_fresh else None
    graphics_data = graphics.data if graphics.is_fresh else None

    current_fuel = (
        _nonnegative_finite(getattr(physics_data, "fuel_kg", None))
        if physics_data is not None else None
    )
    per_lap = (
        _nonnegative_finite(getattr(graphics_data, "fuel_per_lap_l", None))
        if graphics_data is not None and fuel_per_lap_validated else None
    )
    estimated_laps = (
        _nonnegative_finite(getattr(graphics_data, "fuel_estimated_laps", None))
        if graphics_data is not None and estimated_laps_validated else None
    )
    mfd_to_add = (
        _nonnegative_finite(getattr(graphics_data, "mfd_fuel_to_add", None))
        if graphics_data is not None else None
    )
    fuel_used = (
        _nonnegative_finite(getattr(graphics_data, "used_fuel_l", None))
        if graphics_data is not None else None
    )

    blockers: list[str] = []
    if current_fuel is None:
        blockers.append("Current fuel is unavailable, invalid, or stale.")
    if estimated_laps is None:
        blockers.append("ACC fuel-laps-remaining data is unavailable, invalid, or stale.")
    ready = not blockers
    return FuelEngineerSnapshot(
        current_fuel_l=current_fuel,
        current_fuel_fresh=current_fuel is not None,
        acc_fuel_per_lap_l=per_lap,
        fuel_per_lap_fresh=per_lap is not None,
        acc_fuel_laps_remaining=estimated_laps,
        fuel_laps_fresh=estimated_laps is not None,
        mfd_fuel_to_add_l=mfd_to_add,
        fuel_used_l=fuel_used,
        graphics_fresh=graphics.is_fresh,
        strategy_calculations_enabled=ready,
        blockers=tuple(blockers),
    )
