from __future__ import annotations

import unittest

from iracing.reader import IRacingTelemetryReader


class FakeVarHeader:
    def __init__(self, name, desc, unit=""):
        self.name = name
        self.desc = desc
        self.unit = unit


class FakeSDK:
    def __init__(self):
        self.values = {
            "Speed": 50.0, "Gear": 3, "RPM": 7200, "PlayerCarSLBlinkRPM": 8500,
            "FuelLevel": 42.5, "LapCompleted": 4, "SessionNum": 0,
            "LapDistPct": 0.42, "LapCurrentLapTime": 81.234,
            "LapLastLapTime": 80.5, "LapBestLapTime": 79.75,
            "LapDeltaToBestLap": 1.2, "SessionTimeRemain": 900.0,
            "WeekendInfo": {"TrackName": "Okayama", "TrackConfigName": "Full", "TrackRelativeHumidity": 0.99, "TrackWindDir": "0.240855 rad"},
            "DriverInfo": {"DriverCarFuelMaxLtr": 40.0, "Drivers": [{"CarIdx": 0, "CarScreenName": "Formula Vee"}]},
            "SessionInfo": {"Sessions": [{"SessionType": "Race"}]},
            "SplitTimeInfo": {"Sectors": [
                {"SectorNum": 0, "SectorStartPct": 0.0},
                {"SectorNum": 1, "SectorStartPct": 0.2},
                {"SectorNum": 2, "SectorStartPct": 0.4},
                {"SectorNum": 3, "SectorStartPct": 0.7},
            ]},
            "PlayerCarIdx": 0, "Throttle": 0.8, "Brake": 0.1, "Clutch": 0.0,
            "SteeringWheelAngle": 0.15, "AirTemp": 21.0, "TrackTempCrew": 28.0,
            "WindVel": 2.0, "WindDir": 1.0, "TrackWetness": 5, "Precipitation": 0.25, "Skies": 2, "OnPitRoad": False,
            "PlayerCarPosition": 7, "PlayerCarClassPosition": 2, "PlayerCarClass": 1,
            "CarIdxPosition": [7, 6, 8], "CarIdxLap": [10, 10, 10], "CarIdxLapDistPct": [0.42, 0.45, 0.40], "CarIdxEstTime": [100.0, 107.2, 102.6],
            "IsOnTrack": True, "IsInGarage": False, "IsReplayPlaying": False,
            "SessionFlags": 8, "PlayerCarMyIncidentCount": 2,
            "LFcoldPressure": 200.0, "LFpressure": 163.0, "LFwearL": 80.0, "LFwearM": 75.0, "LFwearR": 70.0,
            "PitSvFuel": 15.0, "PitSvLFP": 200.0, "PitSvRFP": 201.0, "PitSvLRP": 202.0, "PitSvRRP": 203.0,
            "PitSvFlags": 0x0005, "PitSvTireCompound": 2, "PlayerCarInPitStall": True,
            "EngineWarnings": 5, "PitRepairLeft": 125.0, "PitOptRepairLeft": 45.0,
            "PlayerCarTowTime": 0.0, "FastRepairAvailable": 1, "FastRepairUsed": 0,
            "TireSetsUsed": 1, "FuelLevelPct": 0.5, "OilTemp": 100.0, "OilPress": 4.0,
            "LFtempCL": 70.0, "LFtempCM": 75.0,
            "LFtempCR": 80.0, "WaterTemp": 90.0,
        }
        self._var_headers = [FakeVarHeader("PitSvFuel", "Pit service fuel add amount", "l")]

    def __getitem__(self, key):
        return self.values.get(key)

    @property
    def is_connected(self):
        return True


class IRacingReaderTests(unittest.TestCase):
    def test_normalizes_core_telemetry_to_overview_contract(self):
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)
        snapshot = reader._build_snapshot(FakeSDK())
        self.assertTrue(snapshot["connected"])
        self.assertEqual(snapshot["source"], "iRacing SDK / Shared Memory")
        self.assertEqual(snapshot["physics"]["data"]["speed_kph"], 180.0)
        self.assertEqual(snapshot["physics"]["data"]["gear_raw"], 4)
        self.assertEqual(snapshot["physics"]["data"]["gear_display"], "3")
        self.assertEqual(snapshot["physics"]["data"]["fuel_kg"], 42.5)
        self.assertEqual(snapshot["graphics"]["data"]["current_time_ms"], 81234)
        self.assertEqual(snapshot["graphics"]["data"]["current_time_str"], "01:21.234")
        self.assertEqual(snapshot["graphics"]["data"]["last_time_ms"], 80500)
        self.assertEqual(snapshot["graphics"]["data"]["last_time_str"], "01:20.500")
        self.assertEqual(snapshot["graphics"]["data"]["best_time_ms"], 79750)
        self.assertEqual(snapshot["graphics"]["data"]["best_time_str"], "01:19.750")
        self.assertIsNone(snapshot["graphics"]["data"]["is_valid_lap"])
        self.assertIsNone(snapshot["graphics"]["lap_status"])
        self.assertEqual(snapshot["vehicle"]["track"], "Okayama")
        self.assertEqual(snapshot["vehicle"]["car_model"], "Formula Vee")
        self.assertEqual(snapshot["static_metadata"]["data"]["max_fuel"], 40.0)
        self.assertAlmostEqual(snapshot["physics"]["data"]["wheels"]["FL"]["tyre_pressure_psi"], 29.0075, places=3)
        self.assertEqual(snapshot["physics"]["data"]["wheels"]["FL"]["tyre_pressure_kpa"], 200.0)
        self.assertEqual(snapshot["physics"]["data"]["wheels"]["FL"]["tyre_wear_pct"], 75.0)
        self.assertEqual(snapshot["physics"]["data"]["oil_temp_c"], 100.0)
        self.assertEqual(snapshot["graphics"]["data"]["gap_ahead_ms"], 7200)
        self.assertEqual(snapshot["graphics"]["data"]["gap_behind_ms"], -2600)
        self.assertEqual(snapshot["graphics"]["data"]["flag"], 2)
        self.assertTrue(snapshot["graphics"]["data"]["global_yellow"])
        self.assertIsNone(snapshot["graphics"]["data"]["global_yellow_1"])
        self.assertEqual(snapshot["graphics"]["data"]["track_status"], "Pit stall")
        self.assertEqual(snapshot["graphics"]["data"]["incident_count"], 2)
        self.assertEqual(snapshot["graphics"]["data"]["mfd_fuel_to_add"], 15.0)
        self.assertEqual(snapshot["graphics"]["data"]["mfd_fuel_to_add_unit"], "L")
        self.assertTrue(snapshot["graphics"]["data"]["mfd_tyre_change"])
        self.assertEqual(snapshot["graphics"]["data"]["mfd_tyre_compound"], 2)
        self.assertFalse(snapshot["graphics"]["data"]["mfd_fuel_fill"])
        self.assertFalse(snapshot["graphics"]["data"]["mfd_windshield_tearoff"])
        self.assertFalse(snapshot["graphics"]["data"]["mfd_fast_repair"])
        self.assertTrue(snapshot["graphics"]["data"]["is_in_pit"])
        self.assertFalse(snapshot["graphics"]["data"]["is_in_pit_lane"])
        self.assertEqual(snapshot["graphics"]["data"]["tyre_sets_used"], 1)
        self.assertEqual(snapshot["graphics"]["data"]["status"], 2)

    def test_iracing_flag_state_preserves_black_flag_identity_and_colour(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        cases = (
            (0x00010000, "Black Flag", "black"),
            (0x00020000, "Disqualified", "black"),
            (0x00000008, "Yellow Flag", "yellow"),
            (0x00000020, "Blue Flag", "blue"),
            (0x00000004, "Green Flag", "green"),
            (0x00000001, "Chequered Flag", "checkered"),
            (0, "No Flag", "unknown"),
        )
        for flags, expected_name, expected_colour in cases:
            sdk.values["SessionFlags"] = flags
            graphics = reader._build_snapshot(sdk)["graphics"]["data"]
            self.assertEqual(graphics["iracing_flag_name"], expected_name)
            self.assertEqual(graphics["iracing_flag_color"], expected_colour)

        # An individual black flag remains visible alongside a global green flag.
        sdk.values["SessionFlags"] = 0x00010000 | 0x00000004
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["iracing_flag_name"], "Black Flag")
        self.assertTrue(graphics["global_green"])

    def test_race_control_preserves_missing_session_flags_and_maps_track_surface(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)
        sdk.values["SessionFlags"] = None
        sdk.values["PlayerTrackSurface"] = 3
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertIsNone(graphics["flag"])
        self.assertIsNone(graphics["global_yellow"])
        self.assertIsNone(graphics["global_green"])
        self.assertEqual(graphics["track_status"], "On track")

        sdk.values["SessionFlags"] = 0
        sdk.values["PlayerTrackSurface"] = 0
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["flag"], 0)
        self.assertFalse(graphics["global_yellow"])
        self.assertEqual(graphics["track_status"], "Off track")

    def test_mfd_tyre_change_uses_any_of_four_pit_service_flags(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        for flags in (0x0001, 0x0002, 0x0004, 0x0008, 0x000F):
            sdk.values["PitSvFlags"] = flags
            graphics = reader._build_snapshot(sdk)["graphics"]["data"]
            self.assertTrue(graphics["mfd_tyre_change"])

        # Each non-tyre MFD service request is decoded independently.
        for flag, field in (
            (0x0010, "mfd_fuel_fill"),
            (0x0020, "mfd_windshield_tearoff"),
            (0x0040, "mfd_fast_repair"),
        ):
            sdk.values["PitSvFlags"] = flag
            graphics = reader._build_snapshot(sdk)["graphics"]["data"]
            self.assertFalse(graphics["mfd_tyre_change"])
            self.assertTrue(graphics[field])
            for other in ("mfd_fuel_fill", "mfd_windshield_tearoff", "mfd_fast_repair"):
                if other != field:
                    self.assertFalse(graphics[other])

        sdk.values["PitSvFlags"] = None
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertIsNone(graphics["mfd_tyre_change"])
        self.assertIsNone(graphics["mfd_fuel_fill"])
        self.assertIsNone(graphics["mfd_windshield_tearoff"])
        self.assertIsNone(graphics["mfd_fast_repair"])

    def test_mfd_fuel_unit_comes_from_live_sdk_metadata(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        sdk._var_headers = [FakeVarHeader("PitSvFuel", "Pit service fuel add amount", "kWh")]
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["mfd_fuel_to_add"], 15.0)
        self.assertEqual(graphics["mfd_fuel_to_add_unit"], "kWh")

        sdk._var_headers = [FakeVarHeader("PitSvFuel", "Pit service fuel add amount", "")]
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["mfd_fuel_to_add"], 15.0)
        self.assertIsNone(graphics["mfd_fuel_to_add_unit"])

        sdk._var_headers = []
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertIsNone(graphics["mfd_fuel_to_add_unit"])

    def test_race_gaps_ignore_inactive_car_positions(self):
        sdk = FakeSDK()
        sdk.values["CarIdxPosition"] = [7, 6, 8, 0]
        sdk.values["CarIdxLap"] = [10, 10, 10, None]
        sdk.values["CarIdxLapDistPct"] = [0.42, 0.45, 0.40, None]
        sdk.values["CarIdxEstTime"] = [100.0, 107.2, 102.6, 0.0]

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["gap_ahead_ms"], 7200)
        self.assertEqual(graphics["gap_behind_ms"], -2600)

    def test_race_leader_has_zero_gap_ahead(self):
        sdk = FakeSDK()
        sdk.values["CarIdxPosition"] = [1, 2, 3]
        sdk.values["CarIdxLap"] = [10, 10, 10]
        sdk.values["CarIdxLapDistPct"] = [0.90, 0.80, 0.70]
        sdk.values["CarIdxEstTime"] = [100.0, 101.0, 105.0]

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["gap_ahead_ms"], 0)
        self.assertEqual(graphics["gap_behind_ms"], -1000)

    def test_race_gaps_follow_live_track_order_during_overtake_before_position_updates(self):
        sdk = FakeSDK()
        # Classification still says player P7 and opponent P6, but live track
        # progress shows that opponent has fallen behind after an overtake.
        sdk.values["PlayerCarPosition"] = 7
        sdk.values["CarIdxPosition"] = [7, 6, 8]
        sdk.values["CarIdxLap"] = [10, 10, 10]
        sdk.values["CarIdxLapDistPct"] = [0.50, 0.49, 0.53]
        sdk.values["CarIdxEstTime"] = [100.0, 102.6, 107.2]

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["gap_ahead_ms"], 7200)
        self.assertEqual(graphics["gap_behind_ms"], -2600)

    def test_race_gaps_unavailable_without_live_track_progress(self):
        sdk = FakeSDK()
        sdk.values["CarIdxLap"] = None
        sdk.values["CarIdxLapDistPct"] = None

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertIsNone(graphics["gap_ahead_ms"])
        self.assertIsNone(graphics["gap_behind_ms"])

    def test_maps_only_supported_iracing_damage_and_repair_telemetry(self):
        sdk = FakeSDK()
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertEqual(physics["engine_warning_flags"], 5)
        self.assertEqual(physics["mandatory_repair_left_s"], 125.0)
        self.assertEqual(physics["optional_repair_left_s"], 45.0)
        self.assertEqual(physics["tow_time_left_s"], 0.0)
        self.assertEqual(physics["fast_repairs_available"], 1)
        self.assertEqual(physics["fast_repairs_used"], 0)
        self.assertIsNone(physics["car_damage"])
        self.assertIsNone(physics["wheels"]["FL"]["suspension_damage"])

    def test_discovers_damage_fields_from_current_sdk_variable_metadata(self):
        sdk = FakeSDK()
        sdk._var_headers = [
            FakeVarHeader("FrontBodyDamage", "Front body damage", "%"),
            FakeVarHeader("LFWheelDamage", "Left-front wheel damage", "level"),
            FakeVarHeader("OilTemp", "Oil temperature", "C"),
        ]
        sdk.values["FrontBodyDamage"] = 25.0
        sdk.values["LFWheelDamage"] = [0, 1, 2]
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertEqual(
            physics["damage_telemetry"],
            [
                {"name": "FrontBodyDamage", "description": "Front body damage", "unit": "%", "value": 25.0},
                {"name": "LFWheelDamage", "description": "Left-front wheel damage", "unit": "level", "value": [0.0, 1.0, 2.0]},
            ],
        )

    def test_engine_warning_flags_are_decoded_to_text_and_unknown_bits_preserved(self):
        sdk = FakeSDK()
        sdk.values["EngineWarnings"] = 0x0180
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertEqual(
            physics["engine_warning_text"],
            ["Mandatory repair required", "Optional repair required"],
        )
        sdk.values["EngineWarnings"] = 0x8000
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertEqual(physics["engine_warning_text"], ["Unmapped warning flags (0x8000)"])

    def test_missing_iracing_damage_fields_remain_unavailable(self):
        sdk = FakeSDK()
        for variable in ("EngineWarnings", "PitRepairLeft", "PitOptRepairLeft",
                         "PlayerCarTowTime", "FastRepairAvailable", "FastRepairUsed"):
            sdk.values.pop(variable, None)
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertIsNone(physics["engine_warning_flags"])
        self.assertIsNone(physics["mandatory_repair_left_s"])
        self.assertIsNone(physics["optional_repair_left_s"])
        self.assertIsNone(physics["tow_time_left_s"])
        self.assertIsNone(physics["fast_repairs_available"])
        self.assertIsNone(physics["fast_repairs_used"])

    def test_maps_native_iracing_weather_fields_and_units(self):
        sdk = FakeSDK()
        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["track_wetness"], 5)
        self.assertEqual(graphics["skies"], 2)
        self.assertEqual(graphics["precipitation_pct"], 25.0)
        physics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]
        self.assertEqual(physics["relative_humidity_pct"], 99.0)
        self.assertAlmostEqual(graphics["wind_speed"], 7.2)
        self.assertEqual(graphics["rain_10min"], None)
        self.assertEqual(graphics["rain_30min"], None)

    def test_wind_direction_falls_back_to_session_weather_when_live_value_missing(self):
        sdk = FakeSDK()
        sdk.values["WindDir"] = None
        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertAlmostEqual(graphics["wind_direction"], 0.240855)

    def test_missing_iracing_weather_fields_remain_unavailable(self):
        sdk = FakeSDK()
        for variable in ("TrackWetness", "Precipitation", "Skies"):
            sdk.values.pop(variable, None)
        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertIsNone(graphics["track_wetness"])
        self.assertIsNone(graphics["precipitation_pct"])
        self.assertIsNone(graphics["skies"])

    def test_fuel_per_lap_uses_running_pairwise_average(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        # Establish the starting fuel/lap anchor without publishing an estimate.
        reader._build_snapshot(sdk)
        self.assertIsNone(reader._fuel_per_lap)

        # First completed lap consumed 4.0 L.
        sdk.values["LapCompleted"] = 5
        sdk.values["FuelLevel"] = 38.5
        first = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(first["fuel_per_lap_l"], 4.0)
        self.assertAlmostEqual(first["fuel_estimated_laps"], 38.5 / 4.0)

        # Next lap consumed 5.0 L: average previous 4.0 and latest 5.0.
        sdk.values["LapCompleted"] = 6
        sdk.values["FuelLevel"] = 33.5
        second = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(second["fuel_per_lap_l"], 4.5)
        self.assertAlmostEqual(second["fuel_estimated_laps"], 33.5 / 4.5)

    def test_normalizes_fractional_iracing_tyre_wear_to_percent(self):
        sdk = FakeSDK()
        for variable in ("LFwearL", "LFwearM", "LFwearR"):
            sdk.values[variable] = 1.0

        wheels = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["physics"]["data"]["wheels"]
        self.assertEqual(wheels["FL"]["tyre_wear_pct"], 100.0)

    def test_practice_session_without_time_limit_does_not_publish_stale_countdown(self):
        sdk = FakeSDK()
        sdk.values["SessionInfo"] = {"Sessions": [{"SessionType": "Practice"}]}
        sdk.values["SessionTimeTotal"] = 0.0
        sdk.values["SessionTimeRemain"] = 604.0

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["session_name"], "Practice")
        self.assertEqual(graphics["session_time_total_s"], 0.0)
        self.assertIsNone(graphics["session_time_left_s"])
        self.assertEqual(graphics["session_time_left_display"], "NO TIME LIMIT")

    def test_practice_session_seven_day_sentinel_is_unlimited(self):
        sdk = FakeSDK()
        sdk.values["SessionInfo"] = {"Sessions": [{"SessionType": "Practice"}]}
        sdk.values["SessionTimeTotal"] = 604800.0
        sdk.values["SessionTimeRemain"] = 604800.0

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["session_time_total_s"], 604800.0)
        self.assertIsNone(graphics["session_time_left_s"])
        self.assertEqual(graphics["session_time_left_display"], "NO TIME LIMIT")

    def test_timed_practice_session_keeps_real_countdown(self):
        sdk = FakeSDK()
        sdk.values["SessionInfo"] = {"Sessions": [{"SessionType": "Practice"}]}
        sdk.values["SessionTimeTotal"] = 1800.0
        sdk.values["SessionTimeRemain"] = 604.0

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["session_time_total_s"], 1800.0)
        self.assertEqual(graphics["session_time_left_s"], 604.0)
        self.assertEqual(graphics["session_time_left_display"], "10:04")

    def test_lap_times_reject_zero_and_missing_sdk_values(self):
        sdk = FakeSDK()
        sdk.values["LapCurrentLapTime"] = 0.0
        sdk.values["LapLastLapTime"] = None
        sdk.values["LapBestLapTime"] = 0.0
        snapshot = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)
        graphics = snapshot["graphics"]["data"]
        self.assertIsNone(graphics["current_time_ms"])
        self.assertEqual(graphics["current_time_str"], "")
        self.assertIsNone(graphics["last_time_ms"])
        self.assertEqual(graphics["last_time_str"], "")
        self.assertIsNone(graphics["best_time_ms"])
        self.assertEqual(graphics["best_time_str"], "")
        self.assertIsNone(graphics["is_valid_lap"])

    def test_track_sector_count_and_timing_are_dynamic(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        first = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(first["sector_count"], 4)
        self.assertEqual(first["sector"], 2)
        self.assertEqual(first["sector_boundaries_pct"], [0.0, 0.2, 0.4, 0.7])
        self.assertEqual(len(first["sector_times_ms"]), 4)
        # Attaching mid-lap must not invent a sector duration from lap start.
        self.assertIsNone(first["live_sector_time_ms"])

        sdk.values["LapDistPct"] = 0.72
        sdk.values["LapCurrentLapTime"] = 85.234
        crossed = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(crossed["sector"], 3)
        self.assertIsNone(crossed["sector_times_ms"][2])

        sdk.values["LapCurrentLapTime"] = 87.234
        live = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(live["live_sector_time_ms"], 2000)

    def test_completed_lap_preserves_dynamic_sector_durations(self):
        sdk = FakeSDK()
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)

        sdk.values["LapDistPct"] = 0.10
        sdk.values["LapCurrentLapTime"] = 10.0
        reader._build_snapshot(sdk)
        sdk.values["LapDistPct"] = 0.30
        sdk.values["LapCurrentLapTime"] = 25.0
        reader._build_snapshot(sdk)
        sdk.values["LapDistPct"] = 0.50
        sdk.values["LapCurrentLapTime"] = 50.0
        reader._build_snapshot(sdk)
        sdk.values["LapDistPct"] = 0.80
        sdk.values["LapCurrentLapTime"] = 80.0
        reader._build_snapshot(sdk)

        sdk.values["LapCompleted"] = 5
        sdk.values["LapDistPct"] = 0.01
        sdk.values["LapCurrentLapTime"] = 0.5
        sdk.values["LapLastLapTime"] = 100.0
        graphics = reader._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["last_lap_sector_times_ms"], [25000, 25000, 30000, 20000])
        self.assertEqual(graphics["sector_times_ms"], [None, None, None, None])

    def test_does_not_misrepresent_unavailable_iRacing_channels(self):
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)
        sdk = FakeSDK()
        # This test models a session where iRacing has not supplied sector metadata.
        sdk.values.pop("SplitTimeInfo")
        snapshot = reader._build_snapshot(sdk)
        physics = snapshot["physics"]["data"]
        graphics = snapshot["graphics"]["data"]
        self.assertAlmostEqual(physics["wheels"]["FL"]["tyre_pressure_psi"], 29.0075, places=3)
        self.assertEqual(physics["wheels"]["FL"]["tyre_pressure_kpa"], 200.0)
        self.assertIsNone(physics["wheels"]["FL"]["brake_temp_c"])
        self.assertIsNone(graphics["is_valid_lap"])
        self.assertIsNone(graphics["player_world_position"])
        self.assertIsNone(graphics["sector"])

    def test_waiting_snapshot_is_disconnected_and_has_same_stream_shape(self):
        reader = IRacingTelemetryReader(sdk_factory=FakeSDK)
        snapshot = reader.snapshot()
        self.assertFalse(snapshot["connected"])
        self.assertEqual(set(snapshot["streams"]), {"physics", "graphics", "static"})
        self.assertIsNone(snapshot["physics"]["data"])


if __name__ == "__main__":
    unittest.main()
