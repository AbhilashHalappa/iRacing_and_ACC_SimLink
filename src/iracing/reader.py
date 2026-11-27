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


def _session_number(value: Any) -> float | None:
    """Parse numeric YAML values that may include a trailing unit label."""
    number = _number(value)
    if number is not None:
        return number
    if isinstance(value, str):
        try:
            result = float(value.strip().split()[0])
            return result if math.isfinite(result) else None
        except (ValueError, IndexError):
            return None
    return None


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


def _session_time_display(seconds: float | None) -> str:
    """Format iRacing session time, whose SDK unit is seconds."""
    if seconds is None or seconds < 0:
        return "—"
    total_seconds = int(seconds)
    minutes, remainder = divmod(total_seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


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


def _variable_unit(sdk: Any, name: str) -> str | None:
    """Return a supported unit from the active iRacing telemetry schema."""
    try:
        headers = getattr(sdk, "_var_headers", None)
        if callable(headers):
            headers = headers()
        if not isinstance(headers, (list, tuple)):
            return None
        header = next((item for item in headers if getattr(item, "name", None) == name), None)
        raw_unit = getattr(header, "unit", None) if header is not None else None
        if not isinstance(raw_unit, str):
            return None
        unit = raw_unit.strip().lower()
        if unit in {"l", "liter", "liters", "litre", "litres"}:
            return "L"
        if unit == "kwh":
            return "kWh"
    except Exception:
        return None
    return None


def _discover_damage_telemetry(sdk: Any) -> list[dict[str, Any]]:
    """Read damage-related variables from this session's live SDK schema."""
    try:
        headers = getattr(sdk, "_var_headers", None)
        if callable(headers):
            headers = headers()
        if not isinstance(headers, (list, tuple)):
            return []
    except Exception:
        return []

    matches: list[dict[str, Any]] = []
    terms = ("damage", "deform", "bent", "broken", "puncture", "punctured", "detached", "cracked")
    for header in headers:
        name = getattr(header, "name", None)
        description = getattr(header, "desc", None) or ""
        unit = getattr(header, "unit", None) or ""
        if not isinstance(name, str) or not name:
            continue
        searchable = f"{name} {description}".lower()
        if not any(term in searchable for term in terms):
            continue
        value = _read(sdk, name)
        if isinstance(value, bool):
            normalized: Any = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized = _number(value)
        elif isinstance(value, (list, tuple)):
            normalized = [
                (bool(item) if isinstance(item, bool) else _number(item))
                for item in value
            ]
        else:
            continue
        if normalized is None or (isinstance(normalized, list) and not any(v is not None for v in normalized)):
            continue
        matches.append({
            "name": name,
            "description": str(description).strip() or name,
            "unit": str(unit).strip(),
            "value": normalized,
        })
    return matches


def _iracing_flag_state(flags: int | None) -> tuple[str | None, str | None]:
    """Return the active player flag and its display colour from SessionFlags."""
    if flags is None:
        return None, None
    # Individual black/disqualification flags take precedence over session-wide flags.
    states = (
        (0x00020000, "Disqualified", "black"),
        (0x00010000, "Black Flag", "black"),
        (0x00000001, "Chequered Flag", "checkered"),
        (0x00000010, "Red Flag", "red"),
        (0x00000008 | 0x00000100 | 0x00004000 | 0x00008000, "Yellow Flag", "yellow"),
        (0x00000020, "Blue Flag", "blue"),
        (0x00000002, "White Flag", "white"),
        (0x00000004, "Green Flag", "green"),
        (0x00000040, "Debris Flag", "orange"),
        (0x00000080, "Crossed Flag", "white"),
    )
    for bit, name, colour in states:
        if flags & bit:
            return name, colour
    return "No Flag", "unknown"


def _engine_warning_text(flags: int | None) -> list[str]:
    """Decode documented iRacing EngineWarnings bits; retain unknown bits."""
    if flags is None:
        return []
    known = (
        (0x0001, "Water temperature warning"),
        (0x0002, "Fuel pressure warning"),
        (0x0004, "Oil pressure warning"),
        (0x0008, "Engine stalled"),
        (0x0010, "Pit speed limiter active"),
        (0x0020, "Rev limiter active"),
        (0x0040, "Oil temperature warning"),
        (0x0080, "Mandatory repair required"),
        (0x0100, "Optional repair required"),
    )
    active = [label for bit, label in known if flags & bit]
    known_mask = sum(bit for bit, _ in known)
    unknown = flags & ~known_mask
    if unknown:
        active.append(f"Unmapped warning flags (0x{unknown:04X})")
    return active


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
        self._last_lap_sector_times_ms: list[int | None] = []

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

        # Track identity is part of the sector-state key, so resolve it before
        # sector bookkeeping (not later with the rest of the metadata).
        session_info = _read(sdk, "WeekendInfo", {})
        track = _nested(session_info, "TrackName")
        configuration = _nested(session_info, "TrackConfigName")

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
                elif self._sector_index is not None and last_ms is not None and self._sector_boundary_time_ms is not None:
                    self._sector_times_ms[self._sector_index] = max(0, last_ms - self._sector_boundary_time_ms)
                # Preserve completed per-sector durations before resetting the live accumulator.
                self._last_lap_sector_times_ms = list(self._sector_times_ms)
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
        session_total_s = _number(_read(sdk, "SessionTimeTotal"))
        remain_s_raw = _number(_read(sdk, "SessionTimeRemain"))
        # iRacing represents an unlimited session with a 7-day duration
        # sentinel (604800 seconds), not only zero. Do not show that sentinel
        # as a real countdown. Preserve unknown totals as unknown.
        unlimited_time_sentinel = session_total_s is not None and (
            session_total_s <= 0 or session_total_s >= 604800
        )
        remain_s = None if unlimited_time_sentinel else remain_s_raw
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
        # Fall back to the session weather direction when the live channel
        # is unavailable. Keep this after initializing wind_direction.
        if wind_direction is None:
            wind_direction = _session_number(_nested(session_info, "TrackWindDir"))
        oil_temp = _number(_read(sdk, "OilTemp"))
        oil_pressure = _number(_read(sdk, "OilPress"))
        fuel_pressure = _number(_read(sdk, "FuelPress"))
        fuel_use_kg_hour = _number(_read(sdk, "FuelUsePerHour"))
        fuel_pct = _number(_read(sdk, "FuelLevelPct"))
        air_density = _number(_read(sdk, "AirDensity"))
        air_pressure = _number(_read(sdk, "AirPressure"))
        # The session YAML's WeekendInfo.TrackRelativeHumidity is the weather
        # value used for the session/black-box display. Prefer it over the
        # live RelativeHumidity channel, which may report a different value.
        humidity = _number(_nested(session_info, "TrackRelativeHumidity"))
        if humidity is None:
            humidity = _number(_read(sdk, "RelativeHumidity"))
        # iRacing reports relative humidity as a 0.0-1.0 fraction.
        # The Overview contract and UI display humidity in percent.
        if humidity is not None and 0.0 <= humidity <= 1.0:
            humidity *= 100.0
        track_wetness = _number(_read(sdk, "TrackWetness"))
        precipitation = _number(_read(sdk, "Precipitation"))
        precipitation_pct = precipitation * 100.0 if precipitation is not None and 0.0 <= precipitation <= 1.0 else precipitation
        skies = _integer(_read(sdk, "Skies"))
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
        session_flags = _integer(_read(sdk, "SessionFlags"))
        on_pit_road = bool(_read(sdk, "OnPitRoad", False))
        in_pit_stall = bool(_read(sdk, "PlayerCarInPitStall", False))
        pit_service_flags = _integer(_read(sdk, "PitSvFlags"))
        mfd_tyre_change = (
            bool(pit_service_flags & 0x000F)
            if pit_service_flags is not None else None
        )
        mfd_tyre_compound = _integer(_read(sdk, "PitSvTireCompound"))
        # PitSvFlags mirrors the selected service checkboxes in the iRacing MFD.
        # Keep each request separate so fuel fill is not confused with tyre changes.
        mfd_fuel_fill = bool(pit_service_flags & 0x0010) if pit_service_flags is not None else None
        mfd_windshield_tearoff = bool(pit_service_flags & 0x0020) if pit_service_flags is not None else None
        mfd_fast_repair = bool(pit_service_flags & 0x0040) if pit_service_flags is not None else None
        position = _integer(_read(sdk, "PlayerCarPosition"))
        class_position = _integer(_read(sdk, "PlayerCarClassPosition"))
        class_id = _integer(_read(sdk, "PlayerCarClass"))
        # CarIdxPosition is classification order and can remain unchanged
        # until a car crosses the timing line. Use live lap progress to decide
        # which cars are physically ahead/behind during an overtake, then use
        # CarIdxEstTime for the time difference at the player's track location.
        car_positions = _read(sdk, "CarIdxPosition", [])
        car_laps = _read(sdk, "CarIdxLap", [])
        car_lap_dist = _read(sdk, "CarIdxLapDistPct", [])
        car_est_times = _read(sdk, "CarIdxEstTime", [])
        gap_ahead_ms = gap_behind_ms = None
        if (
            str(session_type or "").strip().lower() == "race"
            and player_idx is not None
            and isinstance(car_laps, (list, tuple))
            and isinstance(car_lap_dist, (list, tuple))
            and isinstance(car_est_times, (list, tuple))
            and player_idx < len(car_laps)
            and player_idx < len(car_lap_dist)
            and player_idx < len(car_est_times)
        ):
            player_lap = _integer(car_laps[player_idx])
            player_pct = _number(car_lap_dist[player_idx])
            player_est_time = _number(car_est_times[player_idx])
            if player_lap is not None and player_pct is not None and player_est_time is not None:
                player_progress = player_lap + player_pct
                ahead_gaps = []
                behind_gaps = []
                for idx in range(min(len(car_laps), len(car_lap_dist), len(car_est_times))):
                    if idx == player_idx:
                        continue
                    other_lap = _integer(car_laps[idx])
                    other_pct = _number(car_lap_dist[idx])
                    other_est_time = _number(car_est_times[idx])
                    if other_lap is None or other_pct is None or other_est_time is None:
                        continue
                    # Ignore cars with no valid live lap-progress sample.
                    progress_delta = (other_lap + other_pct) - player_progress
                    if progress_delta > 0:
                        ahead_gaps.append((progress_delta, other_est_time - player_est_time))
                    elif progress_delta < 0:
                        behind_gaps.append((-progress_delta, player_est_time - other_est_time))
                if ahead_gaps:
                    gap_ahead_ms = abs(round(min(ahead_gaps, key=lambda item: item[0])[1] * 1000))
                elif isinstance(car_positions, (list, tuple)) and player_idx < len(car_positions):
                    # Retain the known leader-zero convention only when the
                    # live progress array confirms no car is physically ahead.
                    player_position = _integer(car_positions[player_idx])
                    if player_position == 1:
                        gap_ahead_ms = 0
                if behind_gaps:
                    gap_behind_ms = -abs(round(min(behind_gaps, key=lambda item: item[0])[1] * 1000))
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
                    self._fuel_per_lap = used if self._fuel_per_lap is None else (self._fuel_per_lap + used) / 2.0
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
            wear_values = [
                _number(_read(sdk, f"{prefix}wear{side}"))
                for side in ("L", "M", "R")
            ]
            valid_wear = [value for value in wear_values if value is not None]
            average_wear = sum(valid_wear) / len(valid_wear) if valid_wear else None
            # iRacing normally reports tread remaining as a 0.0–1.0
            # fraction (1.0 = 100%). Some SDK/car combinations expose
            # percentage-point values instead; preserve those as-is.
            if average_wear is not None and 0.0 <= average_wear <= 1.0:
                average_wear *= 100.0
            wheel_data[corner] = {
                "tyre_core_temp_c": average_temp,
                "tyre_temp_c": average_temp,
                # iRacing live SDK exposes the cold setup pressure channel.
                # Keep it explicitly labelled as cold setup pressure in the Overview.
                "tyre_pressure_kpa": _number(_read(sdk, f"{prefix}coldPressure")),
                "tyre_pressure_psi": (
                    _number(_read(sdk, f"{prefix}coldPressure")) * 0.1450377377
                    if _number(_read(sdk, f"{prefix}coldPressure")) is not None else None
                ),
                "slip_ratio": None,
                "slip_angle": None,
                "brake_temp_c": None,
                "brake_pressure": _number(_read(sdk, f"{prefix}brakeLinePress")),
                "tyre_wear_pct": average_wear,
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
            "brake_bias_fine": _number(_read(sdk, "dcBrakeBiasFine")),
            "throttle_shape": _number(_read(sdk, "dcThrottleShape")),
            "display_page": _integer(_read(sdk, "dcDashPage")),
            "abs_active": abs_active, "engine_running": engine_running,
            "pit_limiter_on": pit_limiter, "ignition_on": None, "starter_engine_on": None,
            "is_ai_controlled": None, "engine_warnings": engine_warnings,
            "car_damage": None,
            # iRacing exposes repair/tow state and an engine-warning bitfield,
            # but no live body-panel or per-corner suspension damage values.
            "engine_warning_flags": engine_warnings,
            "engine_warning_text": _engine_warning_text(engine_warnings),
            "damage_telemetry": _discover_damage_telemetry(sdk),
            "mandatory_repair_left_s": _number(_read(sdk, "PitRepairLeft")),
            "optional_repair_left_s": _number(_read(sdk, "PitOptRepairLeft")),
            "tow_time_left_s": _number(_read(sdk, "PlayerCarTowTime")),
            "fast_repairs_available": _integer(_read(sdk, "FastRepairAvailable")),
            "fast_repairs_used": _integer(_read(sdk, "FastRepairUsed")),
            "wheels": wheel_data,
        }
        # iRacing SessionFlags is a bitfield. Convert only known flags to the
        # Overview's display booleans; never pass the raw bitmask as an ACC enum.
        # Map iRacing SessionFlags to the shared flag display only when the
        # SDK supplied the bitfield. A missing value must not become "No Flag".
        flag_map = ((0x00000001, 5), (0x00000002, 4), (0x00000004, 7),
                    (0x00000008, 2), (0x00000100, 2), (0x00004000, 2),
                    (0x00008000, 2), (0x00000010, 3), (0x00010000, 6),
                    (0x00020000, 6), (0x00000020, 1), (0x00000040, 8))
        mapped_flag = (
            next((value for bit, value in flag_map if session_flags & bit), 0)
            if session_flags is not None else None
        )
        iracing_flag_name, iracing_flag_color = _iracing_flag_state(session_flags)
        # Overview status is not the iRacing SessionState enum. Track surface
        # values: -1 not in world, 0 off track, 1 pit stall/pit road, 2 approaching
        # pits, 3 on track. OnPitRoad remains the authoritative pit-lane signal.
        graphics_status = 1 if is_replay else 2 if on_track else 0
        track_status = (
            "Pit road" if on_pit_road else
            "Pit stall" if in_pit_stall or on_track_surface == 1 else
            "Pit approach" if on_track_surface == 2 else
            "On track" if on_track_surface == 3 else
            "Off track" if on_track_surface == 0 else
            "Not in world" if on_track_surface == -1 else
            "In garage" if in_garage else "—"
        )
        graphics_data = {
            "status": graphics_status, "session": session_type_index, "session_name": session_type, "session_index": session_num,
            "current_time_ms": current_ms, "current_time_str": _time_string(current_ms),
            "last_time_ms": last_ms, "last_time_str": _time_string(last_ms),
            "best_time_ms": best_ms, "best_time_str": _time_string(best_ms),
            "completed_laps": completed, "number_of_laps": _integer(_read(sdk, "RaceLaps")),
            "distance_traveled_m": _number(_read(sdk, "LapDist")),
            "position": position, "class_position": class_position, "class_id": class_id, "active_cars": active_cars,
            "gap_ahead_ms": gap_ahead_ms, "gap_behind_ms": gap_behind_ms,
            "session_time_left_s": remain_s, "session_time_left_display": ("NO TIME LIMIT" if unlimited_time_sentinel else _session_time_display(remain_s)), "is_in_pit": in_pit_stall, "is_in_pit_lane": on_pit_road,
            "normalized_car_position": lap_pct, "player_world_position": None, "is_on_track": on_track, "is_in_garage": in_garage, "is_replay": is_replay, "track_surface": on_track_surface, "track_surface_material": track_surface_material,
            "is_valid_lap": None,
            "sector": sector_index,
            "sector_count": sector_count or None,
            "sector_boundaries_pct": sector_starts,
            "sector_times_ms": list(self._sector_times_ms),
            "last_lap_sector_times_ms": list(self._last_lap_sector_times_ms),
            "live_sector_time_ms": (
                max(0, current_ms - self._sector_boundary_time_ms)
                if sector_index is not None and current_ms is not None and self._sector_boundary_time_ms is not None and current_ms >= self._sector_boundary_time_ms else None
            ),
            "split_time_str": _time_string(
                max(0, current_ms - self._sector_boundary_time_ms)
                if sector_index is not None and current_ms is not None and self._sector_boundary_time_ms is not None and current_ms >= self._sector_boundary_time_ms else None
            ),
            "last_sector_time_ms": (
                self._sector_times_ms[sector_index - 1]
                if sector_index is not None and sector_index > 0 and sector_index - 1 < len(self._sector_times_ms) else None
            ),
            "tyre_compound": _read(sdk, "PlayerTireCompound"),
            "fuel_per_lap_l": self._fuel_per_lap, "fuel_estimated_laps": estimated_laps, "used_fuel_l": used_fuel,
            "mfd_fuel_to_add": _number(_read(sdk, "PitSvFuel")),
            "mfd_fuel_to_add_unit": "L",  # iRacing PitSvFuel is reported in litres for this MFD field.
            "mfd_tyre_change": mfd_tyre_change,
            "mfd_tyre_compound": mfd_tyre_compound,
            "mfd_fuel_fill": mfd_fuel_fill,
            "mfd_windshield_tearoff": mfd_windshield_tearoff,
            "mfd_fast_repair": mfd_fast_repair,
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
            "session_time_total_s": session_total_s,
            "session_id": _integer(_read(sdk, "SessionUniqueID")),
            "player_tow_time_s": _number(_read(sdk, "PlayerCarTowTime")),
            "player_weight_penalty_kg": _number(_read(sdk, "PlayerCarWeightPenalty")),
            "player_power_adjust_pct": _number(_read(sdk, "PlayerCarPowerAdjust")),
            "push_to_pass_active": bool(_read(sdk, "PushToPass", False)),
            "push_to_pass_count": _integer(_read(sdk, "P2P_Count")),
            "delta_lap_time_ms": delta_ms, "delta_lap_time_str": f"{delta_s:+.3f}" if delta_s is not None else "",
            "delta_positive": delta_s > 0 if delta_s is not None else None,
            "estimated_lap_time_ms": estimated_ms, "estimated_lap_time_str": _time_string(estimated_ms),
            "track_grip_status": None, "track_wetness": track_wetness, "precipitation_pct": precipitation_pct, "skies": skies,
            "rain_intensity": None, "rain_10min": None, "rain_30min": None,
            "wind_speed": wind_mps * 3.6 if wind_mps is not None else None, "wind_direction": wind_direction,
            "flag": mapped_flag, "iracing_flag_name": iracing_flag_name, "iracing_flag_color": iracing_flag_color, "track_status": track_status, "session_flags": session_flags,
            # SessionFlags does not identify individual sector yellows.
            "global_yellow_1": None, "global_yellow_2": None, "global_yellow_3": None,
            "global_yellow": bool(session_flags & (0x00000008 | 0x00000100 | 0x00004000 | 0x00008000)) if session_flags is not None else None,
            "global_green": bool(session_flags & 0x00000004) if session_flags is not None else None,
            "global_blue": bool(session_flags & 0x00000020) if session_flags is not None else None,
            "global_chequered": bool(session_flags & 0x00000001) if session_flags is not None else None,
            "global_red": bool(session_flags & 0x00000010) if session_flags is not None else None,
            "penalty": None, "penalty_time_s": None, "incident_count": incidents, "team_incident_count": team_incidents, "driver_incident_count": driver_incidents, "missing_mandatory_pits": None,
            "mandatory_pit_done": None, "mfd_tyre_set": None, "current_tyre_set": None, "strategy_tyre_set": None,
            "tyre_sets_used": _integer(_read(sdk, "TireSetsUsed")),
            "tc_level": _number(_read(sdk, "dcTractionControl")),
            "tc_level_2": _number(_read(sdk, "dcTractionControl2")),
            "tc_level_3": _number(_read(sdk, "dcTractionControl3")),
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
