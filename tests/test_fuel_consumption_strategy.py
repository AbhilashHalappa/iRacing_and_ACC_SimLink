from types import SimpleNamespace

import pytest

from src.race_engineer_acquisition.fuel_consumption_strategy import assess_measured_fuel


def _lap(number, fuel, *, valid=True, out_lap=False, classification="classified"):
    return SimpleNamespace(
        lap_number=number,
        fuel_remaining_l=fuel,
        lap_valid=valid,
        out_lap=out_lap,
        classification=classification,
    )


def test_measures_consumption_from_consecutive_valid_timed_laps():
    result = assess_measured_fuel(
        40.0,
        current_fuel_fresh=True,
        lap_records=[_lap(1, 55.0), _lap(2, 52.0), _lap(3, 48.8)],
    )

    assert result.status == "ready"
    assert result.measured_fuel_per_lap_l == pytest.approx(3.1)
    assert result.consumption_sample_count == 2
    assert result.estimated_laps_available == pytest.approx(40.0 / 3.1)
    assert result.estimated_laps_after_reserve == pytest.approx((40.0 / 3.1) - 3.0)
    assert result.reserve_fuel_l == pytest.approx(9.3)
    assert result.recommendation is None


def test_excludes_invalid_out_laps_and_unclassified_records():
    result = assess_measured_fuel(
        40.0,
        current_fuel_fresh=True,
        lap_records=[
            _lap(1, 60.0, out_lap=True),
            _lap(2, 57.0),
            _lap(3, 54.0, valid=False),
            _lap(4, 51.0, classification="pending_classification"),
            _lap(5, 48.0),
            _lap(6, 45.0),
        ],
    )

    # Only the consecutive valid timed-lap interval 5 -> 6 is usable.
    assert result.status == "insufficient_data"
    assert result.consumption_sample_count == 1
    assert result.measured_fuel_per_lap_l == pytest.approx(3.0)


def test_rejects_lap_gaps_and_refuelling_increases():
    result = assess_measured_fuel(
        40.0,
        current_fuel_fresh=True,
        lap_records=[
            _lap(1, 60.0),
            _lap(2, 57.0),  # valid interval before refuelling
            _lap(3, 60.0),  # refuel or reset; 2 -> 3 is rejected
            _lap(5, 54.0),  # missing lap 4; 3 -> 5 is rejected
            _lap(6, 51.0),  # valid interval after the gap
        ],
        min_samples=3,
    )

    # The two independent valid intervals remain measurable, but do not meet
    # the deliberately higher three-sample readiness threshold.
    assert result.status == "insufficient_data"
    assert result.consumption_sample_count == 2
    assert result.measured_fuel_per_lap_l == pytest.approx(3.0)
    assert result.estimated_laps_available is None


def test_stale_current_fuel_never_produces_laps_available():
    result = assess_measured_fuel(
        40.0,
        current_fuel_fresh=False,
        lap_records=[_lap(1, 60.0), _lap(2, 57.0), _lap(3, 54.0)],
    )

    assert result.status == "insufficient_data"
    assert result.current_fuel_l is None
    assert result.estimated_laps_available is None
    assert any("Fresh current fuel" in blocker for blocker in result.blockers)


def test_reserve_and_sample_configuration_are_validated():
    with pytest.raises(ValueError):
        assess_measured_fuel(40, current_fuel_fresh=True, lap_records=[], reserve_laps=0)
    with pytest.raises(ValueError):
        assess_measured_fuel(40, current_fuel_fresh=True, lap_records=[], min_samples=3, max_samples=2)
