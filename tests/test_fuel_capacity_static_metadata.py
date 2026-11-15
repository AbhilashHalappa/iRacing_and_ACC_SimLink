from types import SimpleNamespace

from src.race_engineer_acquisition.service import _fresh_acc_max_fuel_capacity_l


def test_extracts_max_fuel_from_fresh_static_metadata():
    telemetry = SimpleNamespace(
        static_decoded=SimpleNamespace(
            is_fresh=True,
            data=SimpleNamespace(max_fuel=120.0),
        )
    )

    assert _fresh_acc_max_fuel_capacity_l(telemetry) == (120.0, True)


def test_stale_static_metadata_does_not_supply_tank_capacity():
    telemetry = SimpleNamespace(
        static_decoded=SimpleNamespace(
            is_fresh=False,
            data=SimpleNamespace(max_fuel=120.0),
        )
    )

    assert _fresh_acc_max_fuel_capacity_l(telemetry) == (None, False)


def test_missing_static_data_does_not_supply_tank_capacity():
    telemetry = SimpleNamespace(
        static_decoded=SimpleNamespace(is_fresh=True, data=None)
    )

    assert _fresh_acc_max_fuel_capacity_l(telemetry) == (None, False)


def test_missing_max_fuel_field_is_reported_as_unavailable_input():
    telemetry = SimpleNamespace(
        static_decoded=SimpleNamespace(
            is_fresh=True,
            data=SimpleNamespace(car_model=42),
        )
    )

    assert _fresh_acc_max_fuel_capacity_l(telemetry) == (None, True)
