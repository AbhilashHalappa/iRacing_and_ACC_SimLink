from __future__ import annotations

import unittest

from iracing.reader import IRacingTelemetryReader


class FakeSDK:
    def __init__(self):
        self.values = {
            "Speed": 50.0, "Gear": 3, "RPM": 7200, "PlayerCarSLBlinkRPM": 8500,
            "FuelLevel": 42.5, "LapCompleted": 4, "SessionNum": 0,
            "LapDistPct": 0.42, "LapCurrentLapTime": 81.234,
            "LapLastLapTime": 80.5, "LapBestLapTime": 79.75,
            "LapDeltaToBestLap": 1.2, "SessionTimeRemain": 900.0,
            "WeekendInfo": {"TrackName": "Okayama", "TrackConfigName": "Full"},
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
            "WindVel": 2.0, "WindDir": 1.0, "OnPitRoad": False,
            "PlayerCarPosition": 7, "PlayerCarClassPosition": 2, "PlayerCarClass": 1,
            "CarIdxPosition": [7, 6, 8], "CarIdxF2Time": [13.0, 12.0, 14.0],
            "IsOnTrack": True, "IsInGarage": False, "IsReplayPlaying": False,
            "SessionFlags": 8, "PlayerCarMyIncidentCount": 2,
            "LFcoldPressure": 200.0, "LFwearL": 80.0, "LFwearM": 75.0, "LFwearR": 70.0,
            "PitSvFuel": 15.0, "PitSvLFP": 200.0, "PitSvRFP": 201.0, "PitSvLRP": 202.0, "PitSvRRP": 203.0,
            "TireSetsUsed": 1, "FuelLevelPct": 0.5, "OilTemp": 100.0, "OilPress": 4.0,
            "LFtempCL": 70.0, "LFtempCM": 75.0,
            "LFtempCR": 80.0, "WaterTemp": 90.0,
        }

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
        self.assertEqual(snapshot["physics"]["data"]["wheels"]["FL"]["tyre_wear_pct"], 75.0)
        self.assertEqual(snapshot["physics"]["data"]["oil_temp_c"], 100.0)
        self.assertEqual(snapshot["graphics"]["data"]["gap_ahead_ms"], 1000)
        self.assertEqual(snapshot["graphics"]["data"]["gap_behind_ms"], 1000)
        self.assertEqual(snapshot["graphics"]["data"]["flag"], 2)
        self.assertEqual(snapshot["graphics"]["data"]["incident_count"], 2)
        self.assertEqual(snapshot["graphics"]["data"]["mfd_fuel_to_add"], 15.0)
        self.assertEqual(snapshot["graphics"]["data"]["tyre_sets_used"], 1)
        self.assertEqual(snapshot["graphics"]["data"]["status"], 2)

    def test_practice_session_without_time_limit_does_not_publish_stale_countdown(self):
        sdk = FakeSDK()
        sdk.values["SessionInfo"] = {"Sessions": [{"SessionType": "Practice"}]}
        sdk.values["SessionTimeTotal"] = 0.0
        sdk.values["SessionTimeRemain"] = 604.0

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["session_name"], "Practice")
        self.assertEqual(graphics["session_time_total_s"], 0.0)
        self.assertIsNone(graphics["session_time_left_s"])

    def test_timed_practice_session_keeps_real_countdown(self):
        sdk = FakeSDK()
        sdk.values["SessionInfo"] = {"Sessions": [{"SessionType": "Practice"}]}
        sdk.values["SessionTimeTotal"] = 1800.0
        sdk.values["SessionTimeRemain"] = 604.0

        graphics = IRacingTelemetryReader(sdk_factory=FakeSDK)._build_snapshot(sdk)["graphics"]["data"]
        self.assertEqual(graphics["session_time_total_s"], 1800.0)
        self.assertEqual(graphics["session_time_left_s"], 604.0)

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
