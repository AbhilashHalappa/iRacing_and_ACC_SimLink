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



def test_keeps_acc_margin_and_adds_separate_three_lap_safety_reserve():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=15.7,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=12,
        current_fuel_l=42.5,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=2.7,
        fuel_per_lap_fresh=True,
    )

    # The ACC comparison remains unchanged.
    assert result.fuel_margin_laps == pytest.approx(3.7)
    assert result.fuel_margin_l == pytest.approx(10.1)
    # The strategy margin separately subtracts the approved three-lap reserve.
    assert result.safety_reserve_laps == 3
    assert result.safety_reserve_fuel_l == pytest.approx(8.1)
    assert result.safety_margin_laps == pytest.approx(0.7)
    assert result.safety_target_fuel_l == pytest.approx(40.5)
    assert result.safety_fuel_margin_l == pytest.approx(2.0)
    assert result.safety_status == "reserve_satisfied"


def test_reports_reserve_shortfall_even_when_acc_margin_is_positive():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=14.0,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=12,
        current_fuel_l=35.0,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=2.5,
        fuel_per_lap_fresh=True,
    )

    assert result.status == "estimated_sufficient"
    assert result.fuel_margin_laps == pytest.approx(2.0)
    assert result.safety_margin_laps == pytest.approx(-1.0)
    assert result.safety_fuel_margin_l == pytest.approx(-2.5)
    assert result.safety_status == "reserve_shortfall"


def test_estimates_fuel_to_add_at_next_pit_with_three_lap_reserve():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=2.3,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=14,
        current_fuel_l=7.1,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=3.01,
        fuel_per_lap_fresh=True,
    )

    assert result.estimated_fuel_to_add_next_pit_l == pytest.approx(44.07)
    assert result.fuel_to_add_estimate_status == "estimate_available"


def test_next_pit_fuel_add_is_zero_when_current_fuel_covers_target_and_reserve():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=20.0,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=10,
        current_fuel_l=40.0,
        current_fuel_fresh=True,
        acc_fuel_per_lap_l=3.0,
        fuel_per_lap_fresh=True,
    )

    assert result.estimated_fuel_to_add_next_pit_l == 0.0


def test_next_pit_fuel_add_is_unavailable_without_fresh_fuel_inputs():
    result = assess_fuel_sufficiency(
        acc_fuel_laps_remaining=8.0,
        fuel_laps_fresh=True,
        estimated_race_laps_remaining=10,
        current_fuel_l=25.0,
        current_fuel_fresh=False,
        acc_fuel_per_lap_l=2.8,
        fuel_per_lap_fresh=True,
    )

    assert result.estimated_fuel_to_add_next_pit_l is None
    assert result.fuel_to_add_estimate_status == "unavailable"
