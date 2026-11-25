"""iRacing SDK reader that publishes the Overview's normalized telemetry contract.

The SDK is polled on one background thread. UI/HTTP code only reads detached
snapshots; it never calls into pyirsdk or blocks on shared memory.
"""
from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right
from threading import Event, Lock, Thread
import math
import time
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        return result if math.isfinite(result) else None
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _time_ms(value: Any) -> int | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return round(number * 1000)


def _time_string(milliseconds: int | None) -> str:
    if milliseconds is None:
        return ""
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _read(sdk: Any, key: str, default: Any = None) -> Any:
    try:
        value = sdk[key]
        return default if value is None else value
    except (KeyError, IndexError, TypeError, AttributeError):
        return default


def _nested(mapping: Any, *keys: str) -> Any:
    value = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


class IRacingTelemetryReader:
    """Reconnectable pyirsdk reader exposing the Overview bridge payload."""

    def __init__(
        self,
        *,
        sdk_factory: Any | None = None,
        poll_interval_s: float = 0.02,
        reconnect_interval_s: float = 1.0,
        clock: Any = time.monotonic,
    ) -> None:
        if sdk_factory is None:
            from irsdk import IRSDK
            sdk_factory = IRSDK
        self._sdk_factory = sdk_factory
        self._poll_interval_s = max(0.005, poll_interval_s)
        self._reconnect_interval_s = max(0.1, reconnect_interval_s)
        self._clock = clock
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._snapshot: dict[str, Any] = self._waiting_snapshot()
        self._connected = False
        self._sample_count = 0
        self._decode_errors = 0
        self._last_error: str | None = None
        self._fuel_lap_anchor: tuple[int, float] | None = None
        self._fuel_per_lap: float | None = None
        self._fuel_start_level: float | None = None
        self._fuel_session_key: tuple[Any, ...] | None = None
        self._sector_session_key: tuple[Any, ...] | None = None
        self._sector_lap: int | None = None
        self._sector_index: int | None = None
        self._sector_boundary_time_ms: int | None = 0
        self._sector_times_ms: list[int | None] = []

    @staticmethod
    def _waiting_snapshot() -> dict[str, Any]:
        waiting = {"state": "waiting", "age_ms": None, "threshold_ms": 1000, "lifecycle_state": "waiting"}
        return {
            "connected": False,
            "source": "iRacing SDK / Shared Memory",
            "streams": {"physics": dict(waiting), "graphics": dict(waiting), "static": dict(waiting)},
            "physics": {"data": None, "processed_count": 0, "decode_error_count": 0},
            "graphics": {"data": None, "lap_status": None},
            "static_metadata": {"data": {}},
            "vehicle": {"car_model": None, "track": None, "track_configuration": None},
            "lap_history": [],
            "acquisition": {"physics": {"state": "waiting"}, "graphics": {"state": "waiting"}, "static": {"state": "waiting"}},
        }

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(target=self._run, name="iRacing-SDK-Reader", daemon=True)
            self._thread.start()

    def close(self, timeout: float = 3.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._snapshot)

    def _run(self) -> None:
        while not self._stop.is_set():
            sdk = None
            try:
                sdk = self._sdk_factory()
                started = bool(sdk.startup())
                if not started:
                    self._publish_disconnected("Waiting for iRacing shared memory")
                    self._stop.wait(self._reconnect_interval_s)
                    continue
                while not self._stop.is_set() and bool(sdk.is_connected):
                    try:
                        payload = self._build_snapshot(sdk)
                        self._publish(payload)
                    except Exception as exc:
                        self._decode_errors += 1
                        self._last_error = f"{type(exc).__name__}: {exc}"
                    self._stop.wait(self._poll_interval_s)
                self._publish_disconnected("iRacing disconnected")
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._publish_disconnected(self._last_error)
                self._stop.wait(self._reconnect_interval_s)
            finally:
                if sdk is not None:
                    try:
                        sdk.shutdown()
                    except Exception:
                        pass

    def _build_snapshot(self, sdk: Any) -> dict[str, Any]:
        now = self._clock()
        speed_mps = _number(_read(sdk, "Speed"))
        gear = _integer(_read(sdk, "Gear"))
        rpm = _number(_read(sdk, "RPM"))
        max_rpm = (
            _number(_nested(_read(sdk, "DriverInfo", {}), "DriverCarSLShiftRPM"))
            or _number(_read(sdk, "PlayerCarSLBlinkRPM"))
            or _number(_nested(_read(sdk, "DriverInfo", {}), "DriverCarSLBlinkRPM"))
        )
        fuel = _number(_read(sdk, "FuelLevel"))
        lap = _integer(_read(sdk, "LapCompleted"))
        session_num = _integer(_read(sdk, "SessionNum"))
        lap_pct = _number(_read(sdk, "LapDistPct"))
        current_ms = _time_ms(_read(sdk, "LapCurrentLapTime"))
        last_ms = _time_ms(_read(sdk, "LapLastLapTime"))

        # SplitTimeInfo is session YAML, not a fixed three-sector telemetry
        # channel. Read the active track's sector starts and derive the count.
        split_info = _read(sdk, "SplitTimeInfo", {})
        if not isinstance(split_info, dict) or not split_info:
            split_info = _nested(_read(sdk, "SessionInfo", {}), "SplitTimeInfo") or {}
        raw_sectors = _nested(split_info, "Sectors")
        sector_starts: list[float] = []
        if isinstance(raw_sectors, list):
            parsed = []
            for item in raw_sectors:
                if not isinstance(item, dict):
                    continue
                pct = _number(item.get("SectorStartPct"))
                if pct is not None and 0.0 <= pct < 1.0:
                    parsed.append((pct, _integer(item.get("SectorNum"))))
            sector_starts = sorted({pct for pct, _ in parsed})
        if sector_starts and sector_starts[0] > 0.0001:
            sector_starts.insert(0, 0.0)
        if not sector_starts:
            sector_starts = []
        sector_count = len(sector_starts)
        sector_index = (
            max(0, min(sector_count - 1, bisect_right(sector_starts, lap_pct) - 1))
            if sector_count and lap_pct is not None and 0.0 <= lap_pct <= 1.0 else None
        )
        sector_session_key = (track, configuration, session_num, tuple(sector_starts))
        if sector_session_key != self._sector_session_key:
            self._sector_session_key = sector_session_key
            self._sector_lap = lap
            self._sector_index = sector_index
            self._sector_boundary_time_ms = 0 if sector_index == 0 else None
            self._sector_times_ms = [None] * sector_count
        elif sector_count:
            if lap is not None and self._sector_lap is not None and lap != self._sector_lap:
                # LapLastLapTime is the completed lap duration. Use it to
                # close the final sector if the SDK has already reset current time.
                if self._sector_index is not None and self._sector_index < sector_count - 1:
                    pass
                elif self._sector_index is not None and last_ms is not None:
                    self._sector_times_ms[self._sector_index] = max(0, last_ms - self._sector_boundary_time_ms)
                self._sector_lap = lap
                self._sector_index = sector_index
                self._sector_boundary_time_ms = 0 if sector_index == 0 else None
                self._sector_times_ms = [None] * sector_count
            elif sector_index is not None and self._sector_index is not None and sector_index > self._sector_index:
                if current_ms is not None and self._sector_boundary_time_ms is not None and current_ms >= self._sector_boundary_time_ms:
                    self._sector_times_ms[self._sector_index] = current_ms - self._sector_boundary_time_ms
                if current_ms is not None:
                    self._sector_boundary_time_ms = current_ms
                self._sector_index = sector_index
            elif self._sector_index is None:
                self._sector_index = sector_index
        best_ms = _time_ms(_read(sdk, "LapBestLapTime"))
        delta_s = _number(_read(sdk, "LapDeltaToBestLap"))
        remain_s = _number(_read(sdk, "SessionTimeRemain"))
        session_info = _read(sdk, "WeekendInfo", {})
        driver_info = _read(sdk, "DriverInfo", {})
        session_data = _read(sdk, "SessionInfo", {})
        track = _nested(session_info, "TrackName")
        configuration = _nested(session_info, "TrackConfigName")
        player_idx = _integer(_read(sdk, "PlayerCarIdx"))
        drivers = _nested(driver_info, "Drivers")
        car_model = None
        active_cars = 0
        if isinstance(drivers, list):
            active_cars = len([driver for driver in drivers if isinstance(driver, dict) and driver.get("CarIsPaceCar") not in (True, 1) and driver.get("IsSpectator") not in (True, 1)])
            for driver in drivers:
                if isinstance(driver, dict) and _integer(driver.get("CarIdx")) == player_idx:
                    car_model = driver.get("CarScreenName") or driver.get("CarScreenNameShort") or driver.get("CarPath")
                    break
        session_type = None
        sessions = _nested(session_data, "Sessions")
        if isinstance(sessions, list) and session_num is not None and 0 <= session_num < len(sessions):
            session_type = _nested(sessions[session_num], "SessionType")
        session_type_index = {
            "practice": 0, "offline testing": 0, "warmup": 0, "qualify": 1, "qualification": 1,
            "race": 2, "hotlap": 3, "time trial": 4,
        }.get(str(session_type or "").strip().lower())
        if not car_model:
            car_model = "iRacing vehicle"

        throttle = _number(_read(sdk, "Throttle"))
        brake = _number(_read(sdk, "Brake"))
        clutch = _number(_read(sdk, "Clutch"))
        steering = _number(_read(sdk, "SteeringWheelAngle"))
        water_temp = _number(_read(sdk, "WaterTemp"))
        air_temp = _number(_read(sdk, "AirTemp"))
        track_temp = _number(_read(sdk, "TrackTempCrew"))
        wind_mps = _number(_read(sdk, "WindVel"))
        wind_direction = _number(_read(sdk, "WindDir"))
        oil_temp = _number(_read(sdk, "OilTemp"))
        oil_pressure = _number(_read(sdk, "OilPress"))
        fuel_pressure = _number(_read(sdk, "FuelPress"))
        fuel_use_kg_hour = _number(_read(sdk, "FuelUsePerHour"))
        fuel_pct = _number(_read(sdk, "FuelLevelPct"))
        air_density = _number(_read(sdk, "AirDensity"))
        air_pressure = _number(_read(sdk, "AirPressure"))
        humidity = _number(_read(sdk, "RelativeHumidity"))
        track_wetness = _number(_read(sdk, "TrackWetness"))
        on_track = bool(_read(sdk, "IsOnTrack", False))
        in_garage = bool(_read(sdk, "IsInGarage", False))
        is_replay = bool(_read(sdk, "IsReplayPlaying", False))
        on_track_surface = _integer(_read(sdk, "PlayerTrackSurface"))
        track_surface_material = _integer(_read(sdk, "PlayerTrackSurfaceMaterial"))
        abs_active = bool(_read(sdk, "BrakeABSactive", False))
        engine_warnings = _integer(_read(sdk, "EngineWarnings"))
        engine_running = rpm is not None and rpm > 0
        pit_limiter = bool(_read(sdk, "dcPitSpeedLimiterToggle", False))
        incidents = _integer(_read(sdk, "PlayerCarMyIncidentCount"))
        team_incidents = _integer(_read(sdk, "PlayerCarTeamIncidentCount"))
        driver_incidents = _integer(_read(sdk, "PlayerCarDriverIncidentCount"))
        session_flags = _integer(_read(sdk, "SessionFlags")) or 0
        on_pit_road = bool(_read(sdk, "OnPitRoad", False))
        in_pit_stall = bool(_read(sdk, "PlayerCarInPitStall", False))
        position = _integer(_read(sdk, "PlayerCarPosition"))
        class_position = _integer(_read(sdk, "PlayerCarClassPosition"))
        class_id = _integer(_read(sdk, "PlayerCarClass"))
        # CarIdxF2Time is the time to the car ahead/behind in the F2 relative
        # display. Pair it with CarIdxPosition so gaps are assigned by race order.
        car_positions = _read(sdk, "CarIdxPosition", [])
        car_f2_times = _read(sdk, "CarIdxF2Time", [])
        gap_ahead_ms = gap_behind_ms = None
        if str(session_type or "").strip().lower() == "race" and player_idx is not None and isinstance(car_positions, (list, tuple)) and isinstance(car_f2_times, (list, tuple)):
            if player_idx < len(car_positions) and player_idx < len(car_f2_times):
                player_position = _integer(car_positions[player_idx])
                player_gap = _number(car_f2_times[player_idx])
                if player_position is not None and player_gap is not None:
                    ahead_gaps = []
                    behind_gaps = []
                    for idx, other_position_raw in enumerate(car_positions):
                        other_position = _integer(other_position_raw)
                        other_gap = _number(car_f2_times[idx]) if idx < len(car_f2_times) else None
                        if other_position is None or other_gap is None or idx == player_idx:
                            continue
                        if other_position < player_position:
                            ahead_gaps.append(player_gap - other_gap)
                        elif other_position > player_position:
                            behind_gaps.append(other_gap - player_gap)
                    if ahead_gaps:
                        gap_ahead_ms = round(min(ahead_gaps, key=abs) * 1000)
                    if behind_gaps:
                        gap_behind_ms = round(min(behind_gaps, key=abs) * 1000)
        completed = lap if lap is not None else 0

        fuel_session_key = (track, configuration, session_num)
        if fuel_session_key != self._fuel_session_key:
            self._fuel_session_key = fuel_session_key
            self._fuel_lap_anchor = (lap, fuel) if fuel is not None and lap is not None else None
            self._fuel_start_level = fuel
            self._fuel_per_lap = None
        if fuel is not None and lap is not None:
            if self._fuel_lap_anchor is None:
                self._fuel_lap_anchor = (lap, fuel)
            elif lap > self._fuel_lap_anchor[0]:
                used = self._fuel_lap_anchor[1] - fuel
                if used > 0:
                    self._fuel_per_lap = used if self._fuel_per_lap is None else (self._fuel_per_lap * 0.65 + used * 0.35)
                self._fuel_lap_anchor = (lap, fuel)
            elif lap < self._fuel_lap_anchor[0]:
                self._fuel_lap_anchor = (lap, fuel)
        estimated_laps = fuel / self._fuel_per_lap if fuel is not None and self._fuel_per_lap and self._fuel_per_lap > 0 else None
        used_fuel = max(0.0, self._fuel_start_level - fuel) if fuel is not None and self._fuel_start_level is not None else None
        delta_ms = round(delta_s * 1000) if delta_s is not None else None
        estimated_ms = best_ms + delta_ms if best_ms is not None and delta_ms is not None else None

        wheel_data: dict[str, dict[str, Any]] = {}
        for corner, prefix in (("FL", "LF"), ("FR", "RF"), ("RL", "LR"), ("RR", "RR")):
            temps = [_number(_read(sdk, f"{prefix}temp{part}")) for part in ("CL", "CM", "CR")]
            valid_temps = [value for value in temps if value is not None]
            average_temp = sum(valid_temps) / len(valid_temps) if valid_temps else None
            wheel_data[corner] = {
                "tyre_core_temp_c": average_temp,
                "tyre_temp_c": average_temp,
                # iRacing exposes cold setup pressure (kPa), not live hot pressure.
                "tyre_pressure_psi": (
                    _number(_read(sdk, f"{prefix}coldPressure")) * 0.1450377377
                    if _number(_read(sdk, f"{prefix}coldPressure")) is not None else None
                ),
                "slip_ratio": None,
                "slip_angle": None,
                "brake_temp_c": None,
                "brake_pressure": _number(_read(sdk, f"{prefix}brakeLinePress")),
                "tyre_wear_pct": (
                    sum(v for v in (
                        _number(_read(sdk, f"{prefix}wearL")),
                        _number(_read(sdk, f"{prefix}wearM")),
                        _number(_read(sdk, f"{prefix}wearR")),
                    ) if v is not None) / len([v for v in (
                        _number(_read(sdk, f"{prefix}wearL")),
                        _number(_read(sdk, f"{prefix}wearM")),
                        _number(_read(sdk, f"{prefix}wearR")),
                    ) if v is not None])
                    if any(_number(_read(sdk, f"{prefix}wear{side}")) is not None for side in ("L", "M", "R")) else None
                ),
                "suspension_damage": None,
                "pad_life": None,
                "disc_life": None,
            }

        self._sample_count += 1
        physics_data = {
            "throttle": throttle, "brake": brake, "clutch": clutch,
            "steering_angle": steering, "speed_kph": speed_mps * 3.6 if speed_mps is not None else None,
            "gear_raw": gear + 1 if gear is not None else None,
            "gear_display": "R" if gear == -1 else "N" if gear == 0 else str(gear) if gear is not None else "—",
            "rpm": rpm, "current_max_rpm": max_rpm, "fuel_l": fuel, "fuel_kg": fuel,  # legacy Overview field name; value is litres
            "air_temp_c": air_temp, "road_temp_c": track_temp, "water_temp_c": water_temp,
            "oil_temp_c": oil_temp, "oil_pressure_bar": oil_pressure, "fuel_pressure_bar": fuel_pressure,
            "fuel_level_pct": fuel_pct, "fuel_use_kg_hour": fuel_use_kg_hour,
            "fuel_tank_capacity_l": _number(_nested(driver_info, "DriverCarFuelMaxLtr")),
            "air_density_kg_m3": air_density, "air_pressure_inhg": air_pressure,
            "oil_level_l": _number(_read(sdk, "OilLevel")), "water_level_l": _number(_read(sdk, "WaterLevel")),
            "battery_voltage_v": _number(_read(sdk, "Voltage")),
            "handbrake": _number(_read(sdk, "HandBrake")), "steering_wheel_angle_max_rad": _number(_read(sdk, "SteeringWheelAngleMax")),
            "relative_humidity_pct": humidity, "track_wetness": track_wetness,
            "longitudinal_accel_mps2": _number(_read(sdk, "LongAccel")),
            "lateral_accel_mps2": _number(_read(sdk, "LatAccel")),
            "vertical_accel_mps2": _number(_read(sdk, "VertAccel")),
            "yaw_rate_rad_s": _number(_read(sdk, "YawRate")),
            "pitch_rad": _number(_read(sdk, "Pitch")), "roll_rad": _number(_read(sdk, "Roll")),
            "autoshifter_on": None, "turbo_boost": None, "manifold_pressure_bar": _number(_read(sdk, "ManifoldPress")),
            "brake_bias": _number(_read(sdk, "dcBrakeBias")),
            "abs_active": abs_active, "engine_running": engine_running,
            "pit_limiter_on": pit_limiter, "ignition_on": None, "starter_engine_on": None,
            "is_ai_controlled": None, "engine_warnings": engine_warnings,
            "car_damage": None, "wheels": wheel_data,
        }
        # iRacing SessionFlags is a bitfield. Convert only known flags to the
        # Overview's display booleans; never pass the raw bitmask as an ACC enum.
        flag_map = ((0x00000001, 5), (0x00000002, 4), (0x00000004, 7),
                    (0x00000008, 2), (0x00000100, 2), (0x00004000, 2),
                    (0x00000010, 3), (0x00010000, 3), (0x00000020, 1),
                    (0x00000040, 8))
        mapped_flag = next((value for bit, value in flag_map if session_flags & bit), 0)
        # Overview status is not the iRacing SessionState enum.
        graphics_status = 1 if is_replay else 2 if on_track else 0
        track_status = "Pit road" if on_pit_road else "On track" if on_track else "In garage" if in_garage else "Off track"
        graphics_data = {
            "status": graphics_status, "session": session_type_index, "session_name": session_type, "session_index": session_num,
            "current_time_ms": current_ms, "current_time_str": _time_string(current_ms),
            "last_time_ms": last_ms, "last_time_str": _time_string(last_ms),
            "best_time_ms": best_ms, "best_time_str": _time_string(best_ms),
            "completed_laps": completed, "number_of_laps": _integer(_read(sdk, "RaceLaps")),
            "distance_traveled_m": _number(_read(sdk, "LapDist")),
            "position": position, "class_position": class_position, "class_id": class_id, "active_cars": active_cars,
            "gap_ahead_ms": gap_ahead_ms, "gap_behind_ms": gap_behind_ms,
            "session_time_left_s": remain_s, "is_in_pit": in_pit_stall, "is_in_pit_lane": on_pit_road,
            "normalized_car_position": lap_pct, "player_world_position": None, "is_on_track": on_track, "is_in_garage": in_garage, "is_replay": is_replay, "track_surface": on_track_surface, "track_surface_material": track_surface_material,
            "is_valid_lap": None,
            "sector": sector_index,
            "sector_count": sector_count or None,
            "sector_boundaries_pct": sector_starts,
            "sector_times_ms": list(self._sector_times_ms),
            "live_sector_time_ms": (
                max(0, current_ms - self._sector_boundary_time_ms)
                if sector_index is not None and current_ms is not None and self._sector_boundary_time_ms is not None and current_ms >= self._sector_boundary_time_ms else None
            ),
            "split_time_str": _time_string(
                max(0, current_ms - self._sector_boundary_time_ms)
                if sector_index is not None and current_ms is not None and current_ms >= self._sector_boundary_time_ms else None
            ),
            "last_sector_time_ms": (
                self._sector_times_ms[sector_index - 1]
                if sector_index is not None and sector_index > 0 and sector_index - 1 < len(self._sector_times_ms) else None
            ),
            "tyre_compound": _read(sdk, "PlayerTireCompound"),
            "fuel_per_lap_l": self._fuel_per_lap, "fuel_estimated_laps": estimated_laps, "used_fuel_l": used_fuel,
            "mfd_fuel_to_add": _number(_read(sdk, "PitSvFuel")),
            "mfd_tyre_pressures": [
                (_number(_read(sdk, "PitSvLFP")) * 0.1450377377) if _number(_read(sdk, "PitSvLFP")) is not None else None,
                (_number(_read(sdk, "PitSvRFP")) * 0.1450377377) if _number(_read(sdk, "PitSvRFP")) is not None else None,
                (_number(_read(sdk, "PitSvLRP")) * 0.1450377377) if _number(_read(sdk, "PitSvLRP")) is not None else None,
                (_number(_read(sdk, "PitSvRRP")) * 0.1450377377) if _number(_read(sdk, "PitSvRRP")) is not None else None,
            ],
            "pitstop_active": bool(_read(sdk, "PitstopActive", False)),
            "pit_repair_left_s": _number(_read(sdk, "PitRepairLeft")),
            "pit_optional_repair_left_s": _number(_read(sdk, "PitOptRepairLeft")),
            "fast_repairs_available": _integer(_read(sdk, "FastRepairAvailable")),
            "fast_repairs_used": _integer(_read(sdk, "PlayerFastRepairsUsed")),
            "session_laps_remaining": _integer(_read(sdk, "SessionLapsRemainEx")),
            "session_time_elapsed_s": _number(_read(sdk, "SessionTime")),
            "session_time_total_s": _number(_read(sdk, "SessionTimeTotal")),
            "session_id": _integer(_read(sdk, "SessionUniqueID")),
            "player_tow_time_s": _number(_read(sdk, "PlayerCarTowTime")),
            "player_weight_penalty_kg": _number(_read(sdk, "PlayerCarWeightPenalty")),
            "player_power_adjust_pct": _number(_read(sdk, "PlayerCarPowerAdjust")),
            "push_to_pass_active": bool(_read(sdk, "PushToPass", False)),
            "push_to_pass_count": _integer(_read(sdk, "P2P_Count")),
            "delta_lap_time_ms": delta_ms, "delta_lap_time_str": f"{delta_s:+.3f}" if delta_s is not None else "",
            "delta_positive": delta_s > 0 if delta_s is not None else None,
            "estimated_lap_time_ms": estimated_ms, "estimated_lap_time_str": _time_string(estimated_ms),
            "track_grip_status": None, "track_wetness": track_wetness, "rain_intensity": None, "rain_10min": None, "rain_30min": None,
            "wind_speed": wind_mps * 3.6 if wind_mps is not None else None, "wind_direction": wind_direction,
            "flag": mapped_flag, "track_status": track_status, "session_flags": session_flags,
            "global_yellow_1": bool(session_flags & (0x00000008 | 0x00000100 | 0x00004000)), "global_yellow_2": None, "global_yellow_3": None,
            "global_green": bool(session_flags & 0x00000004), "global_chequered": bool(session_flags & 0x00000001),
            "global_red": bool(session_flags & 0x00000010),
            "penalty": None, "penalty_time_s": None, "incident_count": incidents, "team_incident_count": team_incidents, "driver_incident_count": driver_incidents, "missing_mandatory_pits": None,
            "mandatory_pit_done": None, "mfd_tyre_set": None, "current_tyre_set": None, "strategy_tyre_set": None,
            "tyre_sets_used": _integer(_read(sdk, "TireSetsUsed")),
            "tc_level": _number(_read(sdk, "dcTractionControl")),
            "abs_level": _number(_read(sdk, "dcABS")), "tc_cut": None, "engine_map": None,
            "class_position": class_position,
        }
        fresh = {"state": "fresh", "age_ms": 0, "threshold_ms": 1000, "lifecycle_state": "running"}
        return {
            "connected": True, "source": "iRacing SDK / Shared Memory",
            "streams": {"physics": dict(fresh), "graphics": dict(fresh), "static": dict(fresh)},
            "physics": {"data": physics_data, "processed_count": self._sample_count, "decode_error_count": self._decode_errors},
            "graphics": {"data": graphics_data, "lap_status": None},
            "static_metadata": {"data": {"max_fuel": _number(_nested(driver_info, "DriverCarFuelMaxLtr"))}},
            "vehicle": {"car_model": str(car_model), "track": str(track) if track else None, "track_configuration": str(configuration) if configuration else None},
            "lap_history": [],
            "acquisition": {"physics": {"state": "running"}, "graphics": {"state": "running"}, "static": {"state": "running"}},
            "captured_at": now,
        }

    def _publish(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._connected = True
            self._snapshot = snapshot
            self._last_error = None

    def _publish_disconnected(self, reason: str) -> None:
        snapshot = self._waiting_snapshot()
        snapshot["error"] = reason
        snapshot["physics"]["processed_count"] = self._sample_count
        snapshot["physics"]["decode_error_count"] = self._decode_errors
        with self._lock:
            self._connected = False
            self._snapshot = snapshot
