"""Measured fuel-consumption strategy from compact completed-lap history.

This layer deliberately estimates consumption from successive ACC lap-boundary
fuel readings. It does not trust the unvalidated Graphics fuel-per-lap estimate
and does not infer remaining race distance or issue pit/refuelling advice.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class FuelConsumptionAssessment:
    status: str
    current_fuel_l: float | None
    current_fuel_fresh: bool
    measured_fuel_per_lap_l: float | None
    consumption_sample_count: int
    estimated_laps_available: float | None
    reserve_laps: float
    estimated_laps_after_reserve: float | None
    reserve_fuel_l: float | None
    recommendation: None
    blockers: tuple[str, ...]


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def assess_measured_fuel(
    current_fuel_l: Any,
    *,
    current_fuel_fresh: bool,
    lap_records: Iterable[Any],
    reserve_laps: float = 3.0,
    max_samples: int = 5,
    min_samples: int = 2,
) -> FuelConsumptionAssessment:
    """Estimate fuel/lap from consecutive valid timed-lap boundary readings.

    Out-laps, invalid laps, unclassified records, lap-number gaps, refuelling
    increases and implausibly large deltas are excluded. At least two measured
    intervals are required before publishing an actionable availability
    estimate. The result is observational only: race distance is not inferred.
    """
    reserve = _finite_nonnegative(reserve_laps)
    if reserve is None or reserve <= 0:
        raise ValueError("reserve_laps must be finite and positive")
    if max_samples < 1 or min_samples < 1 or min_samples > max_samples:
        raise ValueError("sample limits must be positive and min_samples <= max_samples")

    fuel = _finite_nonnegative(current_fuel_l) if current_fuel_fresh else None
    eligible = []
    for record in lap_records:
        valid = getattr(record, "lap_valid", None) is True
        timed = getattr(record, "out_lap", None) is False
        classified = getattr(record, "classification", None) == "classified"
        lap = getattr(record, "lap_number", None)
        remaining = _finite_nonnegative(getattr(record, "fuel_remaining_l", None))
        if valid and timed and classified and isinstance(lap, int) and not isinstance(lap, bool) and remaining is not None:
            eligible.append((lap, remaining))

    eligible.sort(key=lambda item: item[0])
    deltas: list[float] = []
    for previous, current in zip(eligible, eligible[1:]):
        if current[0] != previous[0] + 1:
            continue
        used = previous[1] - current[1]
        # Fuel increases indicate refuelling/reset; very large deltas are
        # rejected rather than poisoning the estimate.
        if 0.0 < used <= 20.0:
            deltas.append(used)
    samples = deltas[-max_samples:]
    measured = sum(samples) / len(samples) if samples else None
    blockers: list[str] = []
    if fuel is None:
        blockers.append("Fresh current fuel in litres is unavailable.")
    if len(samples) < min_samples:
        blockers.append(
            f"Need at least {min_samples} consecutive valid timed-lap fuel-consumption samples; "
            f"currently have {len(samples)}."
        )

    ready = not blockers
    available = fuel / measured if ready and measured and fuel is not None else None
    after_reserve = max(0.0, available - reserve) if available is not None else None
    reserve_fuel = measured * reserve if measured is not None else None
    return FuelConsumptionAssessment(
        status="ready" if ready else "insufficient_data",
        current_fuel_l=fuel,
        current_fuel_fresh=fuel is not None,
        measured_fuel_per_lap_l=measured,
        consumption_sample_count=len(samples),
        estimated_laps_available=available,
        reserve_laps=reserve,
        estimated_laps_after_reserve=after_reserve,
        reserve_fuel_l=reserve_fuel,
        recommendation=None,
        blockers=tuple(blockers),
    )


def fuel_consumption_payload(assessment: FuelConsumptionAssessment) -> dict[str, Any]:
    """Return a JSON-serializable service payload."""
    return asdict(assessment)
