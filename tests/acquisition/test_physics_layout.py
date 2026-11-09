"""Regression tests for the complete ACC Physics shared-memory layout.

These assertions lock the audited 800-byte ABI transcription. They do not
replace verification against Kunos' authoritative shared-memory specification
or live validation against a running ACC build.
"""
import ctypes
import unittest

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE, _Physics


# (field name, ctypes scalar type, array length, byte offset, byte size)
EXPECTED_FIELDS = (
    ("packet_id", ctypes.c_int32, 1, 0, 4),
    ("throttle", ctypes.c_float, 1, 4, 4),
    ("brake", ctypes.c_float, 1, 8, 4),
    ("fuel_kg", ctypes.c_float, 1, 12, 4),
    ("gear_raw", ctypes.c_int32, 1, 16, 4),
    ("rpm", ctypes.c_int32, 1, 20, 4),
    ("steering", ctypes.c_float, 1, 24, 4),
    ("speed_kph", ctypes.c_float, 1, 28, 4),
    ("velocity", ctypes.c_float, 3, 32, 12),
    ("acc_g", ctypes.c_float, 3, 44, 12),
    ("wheel_slip", ctypes.c_float, 4, 56, 16),
    ("wheel_load", ctypes.c_float, 4, 72, 16),
    ("tyre_pressure_psi", ctypes.c_float, 4, 88, 16),
    ("wheel_angular_speed", ctypes.c_float, 4, 104, 16),
    ("tyre_wear_unused", ctypes.c_float, 4, 120, 16),
    ("tyre_dirty", ctypes.c_float, 4, 136, 16),
    ("tyre_core_temp_c", ctypes.c_float, 4, 152, 16),
    ("camber_unused", ctypes.c_float, 4, 168, 16),
    ("suspension_travel", ctypes.c_float, 4, 184, 16),
    ("drs_unused", ctypes.c_float, 1, 200, 4),
    ("tc", ctypes.c_float, 1, 204, 4),
    ("heading", ctypes.c_float, 1, 208, 4),
    ("pitch", ctypes.c_float, 1, 212, 4),
    ("roll", ctypes.c_float, 1, 216, 4),
    ("cg_height_unused", ctypes.c_float, 1, 220, 4),
    ("car_damage", ctypes.c_float, 5, 224, 20),
    ("tyres_out_unused", ctypes.c_int32, 1, 244, 4),
    ("pit_limiter_on", ctypes.c_int32, 1, 248, 4),
    ("abs", ctypes.c_float, 1, 252, 4),
    ("kers_charge_unused", ctypes.c_float, 1, 256, 4),
    ("kers_input_unused", ctypes.c_float, 1, 260, 4),
    ("autoshifter_on", ctypes.c_int32, 1, 264, 4),
    ("ride_height_unused", ctypes.c_float, 2, 268, 8),
    ("turbo_boost", ctypes.c_float, 1, 276, 4),
    ("ballast_unused", ctypes.c_float, 1, 280, 4),
    ("air_density_unused", ctypes.c_float, 1, 284, 4),
    ("air_temp_c", ctypes.c_float, 1, 288, 4),
    ("road_temp_c", ctypes.c_float, 1, 292, 4),
    ("local_angular_velocity", ctypes.c_float, 3, 296, 12),
    ("final_ff", ctypes.c_float, 1, 308, 4),
    ("performance_meter_unused", ctypes.c_float, 1, 312, 4),
    ("engine_brake_unused", ctypes.c_int32, 1, 316, 4),
    ("ers_recovery_unused", ctypes.c_int32, 1, 320, 4),
    ("ers_power_unused", ctypes.c_int32, 1, 324, 4),
    ("ers_heat_unused", ctypes.c_int32, 1, 328, 4),
    ("ers_charging_unused", ctypes.c_int32, 1, 332, 4),
    ("kers_current_unused", ctypes.c_float, 1, 336, 4),
    ("drs_available_unused", ctypes.c_int32, 1, 340, 4),
    ("drs_enabled_unused", ctypes.c_int32, 1, 344, 4),
    ("brake_temp_c", ctypes.c_float, 4, 348, 16),
    ("clutch", ctypes.c_float, 1, 364, 4),
    ("tyre_temp_i_unused", ctypes.c_float, 4, 368, 16),
    ("tyre_temp_m_unused", ctypes.c_float, 4, 384, 16),
    ("tyre_temp_o_unused", ctypes.c_float, 4, 400, 16),
    ("is_ai_controlled", ctypes.c_int32, 1, 416, 4),
    ("tyre_contact_point", ctypes.c_float, 12, 420, 48),
    ("tyre_contact_normal", ctypes.c_float, 12, 468, 48),
    ("tyre_contact_heading", ctypes.c_float, 12, 516, 48),
    ("brake_bias", ctypes.c_float, 1, 564, 4),
    ("local_velocity", ctypes.c_float, 3, 568, 12),
    ("p2p_activation_unused", ctypes.c_int32, 1, 580, 4),
    ("p2p_status_unused", ctypes.c_int32, 1, 584, 4),
    ("current_max_rpm", ctypes.c_int32, 1, 588, 4),
    ("mz_unused", ctypes.c_float, 4, 592, 16),
    ("fx_unused", ctypes.c_float, 4, 608, 16),
    ("fy_unused", ctypes.c_float, 4, 624, 16),
    ("slip_ratio", ctypes.c_float, 4, 640, 16),
    ("slip_angle", ctypes.c_float, 4, 656, 16),
    ("tc_in_action_unused", ctypes.c_int32, 1, 672, 4),
    ("abs_in_action_unused", ctypes.c_int32, 1, 676, 4),
    ("suspension_damage_unused", ctypes.c_float, 4, 680, 16),
    ("tyre_temp_unused", ctypes.c_float, 4, 696, 16),
    ("water_temp_c", ctypes.c_float, 1, 712, 4),
    ("brake_pressure", ctypes.c_float, 4, 716, 16),
    ("front_brake_compound", ctypes.c_int32, 1, 732, 4),
    ("rear_brake_compound", ctypes.c_int32, 1, 736, 4),
    ("pad_life", ctypes.c_float, 4, 740, 16),
    ("disc_life", ctypes.c_float, 4, 756, 16),
    ("ignition_on", ctypes.c_int32, 1, 772, 4),
    ("starter_engine_on", ctypes.c_int32, 1, 776, 4),
    ("engine_running", ctypes.c_int32, 1, 780, 4),
    ("tail_reserved", ctypes.c_ubyte, 16, 784, 16),
)


class PhysicsLayoutRegressionTests(unittest.TestCase):
    def test_total_structure_size_is_784_bytes(self):
        self.assertEqual(ctypes.sizeof(_Physics), 800)
        self.assertEqual(PHYSICS_SIZE, 800)

    def test_every_field_name_type_count_offset_and_size(self):
        actual_fields = _Physics._fields_
        self.assertEqual(len(actual_fields), len(EXPECTED_FIELDS))

        for actual, expected in zip(actual_fields, EXPECTED_FIELDS):
            name, scalar_type, count, offset, size = expected
            with self.subTest(field=name):
                actual_name, actual_type = actual
                self.assertEqual(actual_name, name)
                if count == 1:
                    self.assertIs(actual_type, scalar_type)
                else:
                    self.assertEqual(actual_type._type_, scalar_type)
                    self.assertEqual(actual_type._length_, count)

                descriptor = getattr(_Physics, name)
                self.assertEqual(descriptor.offset, offset)
                self.assertEqual(ctypes.sizeof(actual_type), size)

    def test_fields_are_contiguous_without_implicit_gaps(self):
        expected_offset = 0
        for name, scalar_type, count, offset, size in EXPECTED_FIELDS:
            with self.subTest(field=name):
                self.assertEqual(offset, expected_offset)
                expected_offset += size
        self.assertEqual(expected_offset, 800)


if __name__ == "__main__":
    unittest.main()
