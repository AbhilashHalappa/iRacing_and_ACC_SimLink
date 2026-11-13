"""Tests for conservative Race Engineer fuel observations."""
from types import SimpleNamespace
import math
import unittest

from race_engineer_acquisition.fuel_engineer import build_fuel_engineer_snapshot


def telemetry(*, physics_fresh=True, graphics_fresh=True, fuel=42.5, per_lap=2.7, laps=15.7, mfd=20.0, used=8.4):
    physics_data = SimpleNamespace(fuel_kg=fuel) if physics_fresh else None
    graphics_data = SimpleNamespace(
        fuel_per_lap_l=per_lap,
        fuel_estimated_laps=laps,
        mfd_fuel_to_add=mfd,
        used_fuel_l=used,
    ) if graphics_fresh else None
    return SimpleNamespace(
        physics=SimpleNamespace(is_fresh=physics_fresh, data=physics_data),
        graphics=SimpleNamespace(is_fresh=graphics_fresh, data=graphics_data),
    )


class FuelEngineerTests(unittest.TestCase):
    def test_current_fuel_is_exposed_as_litres_without_conversion(self):
        result = build_fuel_engineer_snapshot(telemetry(fuel=42.5))
        self.assertEqual(result.current_fuel_l, 42.5)
        self.assertTrue(result.current_fuel_fresh)

    def test_graphics_candidates_do_not_enable_strategy_by_default(self):
        result = build_fuel_engineer_snapshot(telemetry())
        self.assertEqual(result.fuel_per_lap_candidate_l, 2.7)
        self.assertEqual(result.estimated_laps_candidate, 15.7)
        self.assertEqual(result.mfd_fuel_to_add_l, 20.0)
        self.assertEqual(result.fuel_used_l, 8.4)
        self.assertFalse(result.strategy_calculations_enabled)
        self.assertEqual(result.blockers, ("A safety-fuel reserve has not been configured.",))

    def test_strategy_requires_both_validations_and_reserve(self):
        result = build_fuel_engineer_snapshot(
            telemetry(), fuel_per_lap_validated=True,
            estimated_laps_validated=True, safety_reserve_l=2.0,
        )
        self.assertTrue(result.strategy_calculations_enabled)
        self.assertEqual(result.blockers, ())

    def test_stale_stream_values_are_not_exposed(self):
        result = build_fuel_engineer_snapshot(
            telemetry(physics_fresh=False, graphics_fresh=False),
            fuel_per_lap_validated=True, estimated_laps_validated=True,
            safety_reserve_l=2.0,
        )
        self.assertIsNone(result.current_fuel_l)
        self.assertIsNone(result.fuel_per_lap_candidate_l)
        self.assertIsNone(result.estimated_laps_candidate)
        self.assertFalse(result.strategy_calculations_enabled)

    def test_invalid_or_negative_values_fail_closed(self):
        result = build_fuel_engineer_snapshot(
            telemetry(fuel=-1.0, per_lap=math.nan, laps=-2.0, mfd=-4.0),
        )
        self.assertIsNone(result.current_fuel_l)
        self.assertIsNone(result.fuel_per_lap_candidate_l)
        self.assertIsNone(result.estimated_laps_candidate)
        self.assertIsNone(result.mfd_fuel_to_add_l)
        self.assertIsNone(result.fuel_used_l)


if __name__ == "__main__":
    unittest.main()
