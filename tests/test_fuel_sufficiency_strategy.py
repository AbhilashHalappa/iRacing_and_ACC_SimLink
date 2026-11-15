import pytest

from src.race_engineer_acquisition.fuel_sufficiency_strategy import assess_fuel_sufficiency


def test_compares_acc_fuel_laps_directly_with_estimated_race_laps():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=15.7,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=12,
        current_fuel_l=42.5,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=2.7,
        fuel_per_lap_fresh=True,
    )

    assert result.status == "estimated_sufficient"
    assert result.acc_fuel_laps_remaining == 15.7
    assert result.estimated_race_laps_remaining == 12
    assert result.fuel_margin_laps == pytest.approx(3.7)
    assert result.estimated_fuel_required_l == pytest.approx(32.4)
    assert result.fuel_margin_l == pytest.approx(10.1)


def test_reports_estimated_shortfall_without_recalculating_acc_fuel_laps():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=8.5,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=10,
        current_fuel_l=25.0,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=2.8,
        fuel_per_lap_fresh=True,
    )

    assert result.status == "estimated_shortfall"
    assert result.acc_fuel_laps_remaining == 8.5
    assert result.fuel_margin_laps == -1.5


def test_does_not_compare_when_either_source_is_unavailable():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=8.5,
        fuel_laps_fresh=False,
        estimated_race_laps_remaining=10,
        current_fuel_l=25.0,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=2.8,
        fuel_per_lap_fresh=True,
    )

    assert result.status == "unavailable"
    assert result.acc_fuel_laps_remaining is None
    assert result.fuel_margin_laps is None
    assert any("ACC fuel-laps-remaining" in item for item in result.blockers)
