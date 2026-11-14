from types import SimpleNamespace

import pytest

from src.race_engineer_acquisition.fuel_strategy import assess_fuel_strategy


def _fuel(*, current=80.0, per_lap=3.0, estimated=26.6, current_fresh=True, per_lap_fresh=True, estimated_fresh=True):
    return SimpleNamespace(
        current_fuel_l=current,
        current_fuel_fresh=current_fresh,
        fuel_per_lap_candidate_l=per_lap,
        fuel_per_lap_fresh=per_lap_fresh,
        estimated_laps_candidate=estimated,
        estimated_laps_fresh=estimated_fresh,
    )


def test_three_lap_reserve_is_calculated_without_converting_litres():
    result = assess_fuel_strategy(_fuel(per_lap=3.66))
    assert result.reserve_laps == 3.0
    assert result.reserve_fuel_l == pytest.approx(10.98)
    assert result.status == "insufficient_data"
    assert result.target_fuel_l is None


def test_actual_finish_distance_must_be_explicitly_validated():
    result = assess_fuel_strategy(
        _fuel(), remaining_race_laps=10, remaining_race_laps_validated=False
    )
    assert result.status == "insufficient_data"
    assert result.calculation_enabled is False
    assert result.projected_finish_margin_l is None
    assert "not validated" in result.blockers[0]


def test_sufficient_fuel_covers_race_and_three_lap_reserve():
    result = assess_fuel_strategy(
        _fuel(current=45.0, per_lap=3.0),
        remaining_race_laps=12,
        remaining_race_laps_validated=True,
    )
    assert result.status == "no_stop_required"
    assert result.calculation_enabled is True
    assert result.target_fuel_l == pytest.approx(45.0)
    assert result.projected_finish_margin_l == pytest.approx(0.0)
    assert result.recommendation is None


def test_fuel_shortfall_is_reported_without_inventing_pit_advice():
    result = assess_fuel_strategy(
        _fuel(current=40.0, per_lap=3.0),
        remaining_race_laps=12,
        remaining_race_laps_validated=True,
    )
    assert result.status == "fuel_shortfall"
    assert result.target_fuel_l == pytest.approx(45.0)
    assert result.projected_finish_margin_l == pytest.approx(-5.0)
    assert result.recommendation is None


def test_stale_or_invalid_fuel_inputs_fail_closed():
    result = assess_fuel_strategy(
        _fuel(current_fresh=False, per_lap=float("nan")),
        remaining_race_laps=10,
        remaining_race_laps_validated=True,
    )
    assert result.status == "insufficient_data"
    assert result.calculation_enabled is False
    assert result.target_fuel_l is None
    assert len(result.blockers) == 2


def test_invalid_reserve_is_rejected():
    with pytest.raises(ValueError):
        assess_fuel_strategy(_fuel(), reserve_laps=0)
