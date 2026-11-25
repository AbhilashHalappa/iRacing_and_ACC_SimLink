# iRacing telemetry audit and Overview mapping

This document records the iRacing SDK mapping into the simulator-neutral Overview payload.
The SDK is polled through pyirsdk; values are only populated when the current session exposes
a valid value. Unsupported ACC-only concepts must remain null rather than being guessed.

## Mapped

| Overview area | iRacing source | Normalization / notes |
|---|---|---|
| Speed | `Speed` | m/s to km/h |
| Gear | `Gear` | -1 reverse, 0 neutral, positive forward; UI raw gear offset retained |
| RPM / shift threshold | `RPM`, `PlayerCarSLBlinkRPM`, DriverInfo `DriverCarSLBlinkRPM` fallback | RPM |
| Driver inputs | `Throttle`, `Brake`, `Clutch`, `SteeringWheelAngle`, `HandBrake` | Pedals 0..1; steering radians |
| Tyre temperature | `LF/RF/LR/RRtempCL/CM/CR` | Average available carcass zones |
| Tyre cold pressure | `LF/RF/LR/RRcoldPressure` | kPa to PSI; explicitly cold setup pressure, not live hot pressure |
| Tyre wear | `LF/RF/LR/RRwearL/M/R` | Average available tread-remaining percentages |
| Brake line pressure | `LF/RF/LR/RRbrakeLinePress` | bar |
| Fuel | `FuelLevel`, `FuelLevelPct`, `FuelUsePerHour` | litres, percent and kg/hour; legacy `fuel_kg` key retained for current UI compatibility |
| Fuel capacity | DriverInfo `DriverCarFuelMaxLtr` | litres |
| Fuel use / lap | Difference in `FuelLevel` at completed-lap boundaries | Smoothed estimate; requires at least one completed lap |
| Engine / fluids | `WaterTemp`, `OilTemp`, `OilPress`, `FuelPress`, `OilLevel`, `WaterLevel`, `Voltage` | Native units retained in explicit field names |
| Vehicle dynamics | `LongAccel`, `LatAccel`, `VertAccel`, `YawRate`, `Pitch`, `Roll` | m/s² and radians |
| Environment | `AirTemp`, `TrackTempCrew`, `WindVel`, `WindDir`, `AirDensity`, `AirPressure`, `RelativeHumidity`, `TrackWetness`, `Precipitation`, `WeatherDeclaredWet` | Wind converted to km/h; direction remains radians for existing UI conversion |
| Lap timing | `LapCurrentLapTime`, `LapLastLapTime`, `LapBestLapTime`, `LapDeltaToBestLap` | Seconds converted to ms and formatted strings |
| Session | `SessionInfo.Sessions[].SessionType`, `SessionNum`, `SessionTimeRemain`, `SessionTime`, `SessionTimeTotal`, `SessionLapsRemainEx`, `SessionUniqueID` | Session type normalized to Overview index where known |
| Race position | `PlayerCarPosition`, `PlayerCarClassPosition`, `PlayerCarClass` | Overall and class position |
| Race gaps | `CarIdxPosition`, `CarIdxF2Time` | Only during Race; F2 time differences yield nearest car ahead/behind |
| Race control | `SessionFlags` | Known bit flags mapped to Overview flag enum and global green/yellow/red/checkered states |
| Incidents | `PlayerCarMyIncidentCount`, `PlayerCarDriverIncidentCount`, `PlayerCarTeamIncidentCount` | Counts exposed separately; not misrepresented as ACC penalty enums |
| Pit / service | `OnPitRoad`, `PlayerCarInPitStall`, `PitstopActive`, `PitRepairLeft`, `PitOptRepairLeft`, `PitSvFuel`, `PitSvLF/RF/LR/RR`, fast-repair variables | Pit lane vs pit box separated; requested tyre pressures converted kPa to PSI |
| Car identity | `WeekendInfo`, `DriverInfo.Drivers` | Track, configuration and player car model |
| Car status | `IsOnTrack`, `IsInGarage`, `IsReplayPlaying`, `dcPitSpeedLimiterToggle`, `BrakeABSactive`, `EngineWarnings`, `ManifoldPress`, `PushToPass` | Explicit status fields; manifold pressure is not called turbo boost |

## Not safely available as a general live iRacing telemetry field

- Live hot tyre pressure: SDK exposes cold setup pressure, not live hot pressure.
- Brake disc temperature, brake pad/disc life, suspension damage and per-corner brake temperature.
- Standard car-damage percentages equivalent to ACC's damage channels.
- A universal valid/invalid lap boolean or ACC-style penalty code. `LapDeltaToBestLap_OK` validates the delta reference, not lap legality.
- Universal three-sector split timing / sector boundaries.
- World X/Y position for a track map. `LapDistPct` is a scalar progress value and is not a world coordinate.
- ACC-style TC cut, engine map, automatic-shifter state, rain lights, wipers and indicators.
- Mandatory-pit completion and stint clock fields equivalent to ACC's.
- A universal tyre-set identifier. `TireSetsUsed` is a usage count, not the currently fitted set.
- Weather forecast at +10/+30 minutes and ACC track-grip state.
- Text race-control messages.

## Verification notes

The SDK exposes live telemetry, session YAML and IBT data as distinct sources. This adapter currently consumes live shared-memory telemetry and selected YAML/session metadata. Some channels vary by car, series, session type, and whether the car is on track.

The fake-SDK regression tests verify unit conversions and mapping logic. They do not replace a live test in iRacing. Before enabling any additional optional field, verify that it exists in the actual session's SDK variable header and inspect its unit/meaning.
