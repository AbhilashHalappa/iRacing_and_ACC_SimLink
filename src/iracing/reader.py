"""iRacing SDK reader that publishes the Overview's normalized telemetry contract.

The SDK is polled on one background thread. UI/HTTP code only reads detached
snapshots; it never calls into pyirsdk or blocks on shared memory.
"""
from __future__ import annotations

from copy import deepcopy
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
        max_rpm = _number(_read(sdk, "PlayerCarSLBlinkRPM")) or 9000.0
        fuel = _number(_read(sdk, "FuelLevel"))
        lap = _integer(_read(sdk, "LapCompleted"))
        session_num = _integer(_read(sdk, "SessionNum"))
        lap_pct = _number(_read(sdk, "LapDistPct"))
        current_ms = _time_ms(_read(sdk, "LapCurrentLapTime"))
        last_ms = _time_ms(_read(sdk, "LapLastLapTime"))
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
            active_cars = len([driver for driver in drivers if isinstance(driver, dict) and driver.get("CarIsPaceCar") is not True])
            for driver in drivers:
                if isinstance(driver, dict) and _integer(driver.get("CarIdx")) == player_idx:
                    car_model = driver.get("CarScreenName") or driver.get("CarScreenNameShort") or driver.get("CarPath")
                    break
        session_type = None
        sessions = _nested(session_data, "Sessions")
        if isinstance(sessions, list) and session_num is not None and 0 <= session_num < len(sessions):
            session_type = _nested(sessions[session_num], "SessionType")
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
        on_pit_road = bool(_read(sdk, "OnPitRoad", False))
        position = _integer(_read(sdk, "PlayerCarPosition"))
        completed = lap if lap is not None else 0

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
                # iRacing exposes cold setup pressure, not a live hot pressure.
                "tyre_pressure_psi": None,
                "slip_ratio": None,
                "slip_angle": None,
                "brake_temp_c": None,
                "brake_pressure": _number(_read(sdk, f"{prefix}brakeLinePress")),
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
            "rpm": rpm, "current_max_rpm": max_rpm, "fuel_kg": fuel,
            "air_temp_c": air_temp, "road_temp_c": track_temp, "water_temp_c": water_temp,
            "autoshifter_on": None, "turbo_boost": None, "brake_bias": _number(_read(sdk, "dcBrakeBias")),
            "car_damage": None, "wheels": wheel_data,
        }
        graphics_data = {
            "status": 2, "session": session_type, "session_index": session_num,
            "current_time_ms": current_ms, "current_time_str": _time_string(current_ms),
            "last_time_ms": last_ms, "last_time_str": _time_string(last_ms),
            "best_time_ms": best_ms, "best_time_str": _time_string(best_ms),
            "completed_laps": completed, "number_of_laps": _integer(_read(sdk, "RaceLaps")),
            "position": position, "active_cars": active_cars,
            "session_time_left_s": remain_s, "is_in_pit": on_pit_road, "is_in_pit_lane": on_pit_road,
            "normalized_car_position": lap_pct, "player_world_position": None,
            "is_valid_lap": None, "sector": None, "split_time_str": "",
            "last_sector_time_ms": None, "tyre_compound": None,
            "fuel_per_lap_l": self._fuel_per_lap, "fuel_estimated_laps": estimated_laps,
            "delta_lap_time_ms": delta_ms, "delta_lap_time_str": f"{delta_s:+.3f}" if delta_s is not None else "",
            "delta_positive": delta_s > 0 if delta_s is not None else None,
            "estimated_lap_time_ms": estimated_ms, "estimated_lap_time_str": _time_string(estimated_ms),
            "track_grip_status": None, "rain_intensity": None, "rain_10min": None, "rain_30min": None,
            "wind_speed": wind_mps * 3.6 if wind_mps is not None else None, "wind_direction": wind_direction,
            "penalty": None, "penalty_time_s": None, "missing_mandatory_pits": None,
            "mandatory_pit_done": None, "used_fuel_l": None, "mfd_fuel_to_add": None,
            "mfd_tyre_set": None, "current_tyre_set": None, "strategy_tyre_set": None,
            "mfd_tyre_pressures": None, "tc_level": _number(_read(sdk, "dcTractionControl")),
            "abs_level": _number(_read(sdk, "dcABS")), "tc_cut": None, "engine_map": None,
            "is_valid_lap": None,
        }
        fresh = {"state": "fresh", "age_ms": 0, "threshold_ms": 1000, "lifecycle_state": "running"}
        return {
            "connected": True, "source": "iRacing SDK / Shared Memory",
            "streams": {"physics": dict(fresh), "graphics": dict(fresh), "static": dict(fresh)},
            "physics": {"data": physics_data, "processed_count": self._sample_count, "decode_error_count": self._decode_errors},
            "graphics": {"data": graphics_data, "lap_status": None},
            "static_metadata": {"data": {"max_fuel": None}},
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
