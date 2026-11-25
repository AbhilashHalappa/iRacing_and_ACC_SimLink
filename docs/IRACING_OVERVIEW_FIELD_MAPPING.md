# iRacing mapping for every Overview field

Branch audited: `feature/iracing-game-support`  
Audited revision: `1729bb1b83cdaefae665a34655e33e41ca466927`  
UI source: `frontend/src/App.tsx` (`TileContentBody`, `definitions`, `tileStreamDependencies`)  
Adapter source: `src/iracing/reader.py`

This is a UI-field-by-UI-field mapping, not a claim that every ACC concept exists in iRacing. The statuses below distinguish data already emitted by the adapter from data that has a plausible SDK source but is not yet mapped, and data for which there is no safe equivalent. A field marked unavailable must remain null/unknown; do not synthesize a value.

## Status legend

- **Mapped** — the iRacing source is already read and normalized by the current adapter.
- **Partial** — some subfields are mapped, but others are not; details are listed.
- **Derivable** — can be calculated from mapped iRacing values or session metadata.
- **Not mapped** — an iRacing source may exist, but the current adapter does not expose it.
- **No safe equivalent** — no general, documented live SDK field equivalent is available for the Overview meaning.
- **External** — not simulator telemetry; requires the app's hardware/device layer.

## 1. Driver trace

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Brake trace | `Brake` | Mapped; 0..1 input |
| Throttle trace | `Throttle` | Mapped; 0..1 input |
| Gear trace | `Gear` | Mapped; -1 reverse, 0 neutral, positive forward |
| Speed trace | `Speed` | Mapped; m/s converted to km/h |
| RPM trace | `RPM` | Mapped; rev/min |

## 2. Speed, gear and engine RPM

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Vehicle speed | `Speed` | Mapped; m/s → km/h |
| Selected gear | `Gear` | Mapped; normalized for UI |
| Engine RPM | `RPM` | Mapped |
| Shift/RPM threshold | DriverInfo `DriverCarSLShiftRPM`, fallback `PlayerCarSLBlinkRPM`, DriverInfo `DriverCarSLBlinkRPM` | Mapped; configured shift RPM preferred |

## 3. Driver inputs / pedals

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Steering angle | `SteeringWheelAngle` | Mapped; radians, UI converts to degrees |
| Throttle | `Throttle` | Mapped; normalized 0..1 |
| Brake | `Brake` | Mapped; normalized 0..1 |
| Clutch | `Clutch` | Mapped; normalized 0..1 |
| Handbrake (not currently shown in this tile) | `HandBrake` if exposed by car/SDK | Partial; verify actual variable header on the active car |

## 4. Lap times and lap history

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Current lap time | `LapCurrentLapTime` | Mapped; seconds → ms/string |
| Last lap time | `LapLastLapTime` | Mapped |
| Best lap time | `LapBestLapTime` | Mapped |
| Completed lap count / current lap number | `LapCompleted` | Mapped |
| Lap validity | No universal direct equivalent confirmed in the current adapter | No safe equivalent yet; `LapDeltaToBestLap_OK` is delta-reference validity, not lap legality |
| Recent lap history | `LapCompleted`, `LapLastLapTime` plus app-side capture | Derivable; current app captures completed lap times |
| Sector 1/2/3 | iRacing session split timing / session metadata if exposed | Partial / not mapped; current reader returns `sector=None` and no split string |
| Best sector history | Completed lap sector boundaries | Not available until reliable sector boundaries are decoded |

## 5. Weather

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Road/track temperature | `TrackTempCrew` | Mapped; °C |
| Air temperature | `AirTemp` | Mapped; °C |
| Track grip | No direct ACC-style grip-state equivalent | No safe equivalent |
| Rain now | `Precipitation` only if present in the active SDK header; `TrackWetness` is a different measure | Not mapped / verify per SDK build; do not substitute wetness for rain intensity |
| Rain +10 min / +30 min | No forecast variables in current adapter | No safe equivalent |
| Wind speed | `WindVel` | Mapped; m/s → km/h |
| Wind direction | `WindDir` | Mapped; radians → compass display |
| Humidity / air density / air pressure / fog / sky | `RelativeHumidity`, `AirDensity`, `AirPressure`, `FogLevel`, `Skies` where present | Some already read (humidity/density/pressure); fog/sky not exposed to Overview currently |

## 6. Track map

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Track name | `WeekendInfo.TrackName` | Mapped |
| Track configuration | `WeekendInfo.TrackConfigName` | Mapped |
| Progress around lap | `LapDistPct` | Mapped as normalized progress |
| Distance around lap | `LapDist` | Mapped |
| Player world X/Y position | No world-coordinate pair in the current adapter | No safe equivalent in current mapping; `LapDistPct` is not a world coordinate |
| Map geometry | App-learned/captured track map | App data, not an iRacing telemetry variable |

## 7. Session tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Track | `WeekendInfo.TrackName` | Mapped |
| Session type | `SessionInfo.Sessions[SessionNum].SessionType` | Mapped where known |
| Session status | `IsReplayPlaying`, `IsOnTrack`, `IsInGarage` | Mapped into Overview status; not raw `SessionState` |
| Time left | `SessionTimeRemain` | Mapped |
| Completed laps | `LapCompleted` | Mapped |
| Overall position | `PlayerCarPosition` | Mapped |
| Active car count | DriverInfo `Drivers[]` excluding pace cars/spectators | Mapped |
| Tyre compound | `PlayerTireCompound` | Mapped as supplied by SDK |

## 8. Brake temperatures tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| FL/FR/RL/RR brake disc temperature | No general live brake-temperature channel confirmed in the shared-memory variable set | No safe equivalent; current `brake_temp_c=None` |
| FL/FR/RL/RR brake line pressure | `LF/RF/LR/RRbrakeLinePress` | Mapped; bar |
| Brake pad life | No general live pad-life field | No safe equivalent |
| Brake disc life | No general live disc-life field | No safe equivalent |

## 9. Tyre condition tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Per-corner carcass temperature | `LF/RF/LR/RRtempCL/CM/CR` | Mapped; current adapter averages available zones |
| Per-corner pressure | `LF/RF/LR/RRcoldPressure` | Partial; mapped as cold setup pressure (kPa → PSI), not live hot pressure |
| Slip ratio | No general matching per-wheel slip-ratio channel in current reader | No safe equivalent currently |
| Slip angle | No general matching per-wheel slip-angle channel in current reader | No safe equivalent currently |
| Per-corner tread remaining | `LF/RF/LR/RRwearL/M/R` | Mapped in payload as average tread-remaining percentage; **not currently displayed in the Tyre Condition tile** |
| Individual inner/middle/outer tread remaining | `wearL`, `wearM`, `wearR` for each tyre | Source is available; current adapter only emits the average |

## 10. Fuel tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Fuel remaining | `FuelLevel` | Mapped; litres |
| Estimated laps remaining | `FuelLevel` / smoothed app-derived fuel-per-lap | Derivable; requires completed lap data |
| Fuel per lap | Difference in `FuelLevel` across completed laps | Derivable |
| Tank capacity | DriverInfo `DriverCarFuelMaxLtr` | Mapped; litres |
| Fuel percentage (not currently shown) | `FuelLevelPct` | Mapped |
| Fuel used | Session-start fuel minus current `FuelLevel` | Derivable; current reader emits `used_fuel_l` |

## 11. Penalties & warnings tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Lap validity | No confirmed universal direct field | No safe equivalent yet |
| Penalty type | `SessionFlags` / race-control state are not ACC penalty codes | No safe equivalent for ACC penalty enum |
| Penalty time | No equivalent exposed by current live reader | No safe equivalent |
| Missing mandatory pits | Session rules / results metadata, not a universal live variable in current reader | Not mapped |
| Mandatory pit completed | No universal direct variable confirmed | No safe equivalent |
| Incident count | `PlayerCarMyIncidentCount`, `PlayerCarDriverIncidentCount`, `PlayerCarTeamIncidentCount` | Mapped as separate incident counts; do not convert to ACC penalty codes |

## 12. Hardware tile

| Overview field | Source | Status / notes |
|---|---|---|
| Wheel USB link / wheel device | Operating-system device discovery / hardware subsystem | External; not an iRacing SDK field |
| Pedals device | Hardware subsystem | External |
| Handbrake device | Hardware subsystem | External |
| RPM LED controller | Hardware subsystem | External |

## 13. Delta tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Live delta to best | `LapDeltaToBestLap` | Mapped; seconds → ms/string |
| Delta direction | Sign of `LapDeltaToBestLap` | Mapped |
| Estimated lap time | `LapBestLapTime + LapDeltaToBestLap` | Derivable; current reader calculates |
| Best lap time | `LapBestLapTime` | Mapped |

## 14. Sector performance tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Current sector number | iRacing split/session sector metadata | Not mapped; current reader emits `sector=None` |
| Live sector/split time | iRacing split timing data | Not mapped; current reader emits empty string |
| Last completed sector | Reconstructed from reliable split boundaries | Not mapped |
| Best S1/S2/S3 | Completed valid lap sector splits | Not mapped; cannot calculate until sector splits are available |
| Sector delta | Current sector vs best sector | Derivable only after reliable split mapping |

## 15. Race position & gaps tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Overall position | `PlayerCarPosition` / `CarIdxPosition` | Mapped |
| Active cars | DriverInfo `Drivers[]` | Mapped |
| Gap ahead | `CarIdxPosition` + `CarIdxF2Time` | Mapped for Race sessions |
| Gap behind | `CarIdxPosition` + `CarIdxF2Time` | Mapped for Race sessions |
| Class position | `PlayerCarClassPosition` | Mapped in payload; Overview position tile currently displays overall position |

## 16. Electronics tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| TC level | `dcTractionControl` if the car exposes it | Partial; vehicle-dependent |
| ABS level | `dcABS` if the car exposes it | Partial; vehicle-dependent |
| Brake bias | `dcBrakeBias` if exposed | Partial; unit/scale is car-specific and needs per-car verification |
| TC cut | No universal ACC-equivalent field | No safe equivalent |
| Engine map | No universal generic engine-map field | No safe equivalent |
| Auto shifter | No universal generic auto-shifter state | No safe equivalent |
| Turbo boost | `ManifoldPress` is manifold pressure, **not** turbo boost | Do not map manifold pressure to turbo boost |
| Manifold pressure (not currently displayed) | `ManifoldPress` | Mapped separately in physics payload |

## 17. Pit stop & stint tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Pit box | `PlayerCarInPitStall` | Mapped |
| Pit lane | `OnPitRoad` | Mapped |
| Mandatory stop | No universal direct equivalent confirmed | No safe equivalent |
| Total stint time left | No universal direct equivalent in current reader | No safe equivalent |
| Stint time left | No universal direct equivalent in current reader | No safe equivalent |
| Fuel used | Session-start `FuelLevel` minus current `FuelLevel` | Derivable / mapped |
| MFD fuel to add | `PitSvFuel` | Mapped; litres or kWh depending on vehicle, so UI must not assume litres for EVs |
| MFD tyre set | `PitSvTireCompound` / `PitSvFlags` and setup/service metadata | Not mapped as a tyre-set index |
| Current tyre set | No universal current-set index confirmed | No safe equivalent |
| Strategy tyre set | App strategy state | Not an iRacing telemetry field |
| Tyre change requested | `PitSvFlags` / `PitSvTireCompound` or per-wheel pit service flags | Not mapped |
| Tyre compound | `PlayerTireCompound` and pending `PitSvTireCompound` | Current compound mapped; pending compound not mapped |
| Requested tyre pressures | `PitSvLFP/RFP/LRP/RRP` | Mapped; kPa → PSI |

## 18. Vehicle damage tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Car damage front / rear / left / right / centre | No general live damage percentage fields confirmed | No safe equivalent; current `car_damage=None` |
| Per-corner suspension damage | No general damage percentage field | No safe equivalent; current `suspension_damage=None` |
| Suspension movement / deflection (not the same as damage) | `LF/RF/LR/RRshockDefl`, `LF/RF/LR/RRshockVel` | SDK channels exist; **not mapped yet**; must not be displayed as damage |
| Ride height (not the same as damage) | Car-specific ride-height variables when present in active SDK header | Not mapped; availability varies by car |
| Repair state / time | `PitRepairLeft`, `PitOptRepairLeft`, `PitstopActive`, `PlayerCarPitSvStatus` where available | Repair status/time, not a damage amount; some fields already mapped |

## 19. Tyre pressure targets tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Actual pressure per corner | `LF/RF/LR/RRcoldPressure` | Partial; cold setup pressure only, not live actual pressure |
| Target pressure per corner | User-configured app setting | External/manual target; no iRacing target assumed |
| Actual minus target | App calculation | Derivable, but currently compares cold setup pressure to manual target; label must make this limitation clear |

## 20. Race control tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Main flag | `SessionFlags` bitfield | Mapped for known checkered/white/green/yellow/red/blue/debris/black flags |
| Global flags | `SessionFlags` | Partial; known global states mapped |
| Track status | `OnPitRoad`, `IsOnTrack`, `IsInGarage` | Mapped as vehicle state, not a full track-condition state |
| Sector yellow flags | `SessionFlags` global yellow/caution bits | No per-sector mapping; current adapter leaves sector 2/3 unknown |
| Global green/checkered/red | `SessionFlags` | Mapped |
| Race-control message | No text message field in current live telemetry mapping | No safe equivalent |

## 21. Car lights & status tile

| Overview field | iRacing source | Status / notes |
|---|---|---|
| Pit limiter | `dcPitSpeedLimiterToggle` | Mapped |
| Engine running | `RPM > 0` | Mapped as a derived state |
| Ignition | No universal generic ignition state confirmed | No safe equivalent |
| Starter | `dcStarter` may represent starter control/request | Not mapped; not necessarily engine-started state |
| AI control | DriverInfo player-driver metadata (if AI flag is exposed) | Not mapped; verify exact metadata field |
| Water temperature | `WaterTemp` | Mapped |
| Rain light | No universal generic field confirmed | No safe equivalent |
| Flashing lights | No universal generic field confirmed | No safe equivalent |
| Lights stage | No universal generic field confirmed | No safe equivalent |
| Wiper level | Car-specific control variable if present | Not mapped; verify active header |
| Left/right indicators | No universal generic field confirmed | No safe equivalent |
| Exhaust temperature | No general shared-memory field confirmed | No safe equivalent |
| Rain tyres | `PlayerTireCompound` may identify compound text, but is not a boolean rain-tyre flag | Do not infer a boolean without a verified compound mapping |

## 22. Additional iRacing channels worth adding (not currently represented by Overview tiles)

These are useful telemetry candidates, but must be added as separate normalized fields and must not be mislabeled as damage or ACC-only concepts:

| iRacing source | Meaning / unit | Recommended normalized field |
|---|---|---|
| `LF/RF/LR/RRshockDefl` | Shock deflection, m | `wheels[corner].suspension_deflection_m` |
| `LF/RF/LR/RRshockVel` | Shock velocity, m/s | `wheels[corner].suspension_velocity_mps` |
| `SteeringWheelTorque` | Steering shaft torque, N·m | `steering_torque_nm` |
| `SteeringWheelPctTorqueSign` | Signed FFB torque percentage | `steering_torque_pct` |
| `Yaw`, `Pitch`, `Roll` | Vehicle orientation, rad | `yaw_rad`, `pitch_rad`, `roll_rad` |
| `YawRate`, `PitchRate`, `RollRate` | Angular rates, rad/s | `yaw_rate_rad_s`, `pitch_rate_rad_s`, `roll_rate_rad_s` |
| `VelocityX/Y/Z` | World velocity, m/s | `velocity_world_mps` |
| `LongAccel_ST`, `LatAccel_ST`, `VertAccel_ST` | High-rate accelerations, m/s² | High-rate channels for analysis only |
| `LF/RF/LR/RRodometer` | Tyre distance travelled, m | `wheels[corner].odometer_m` |
| `TireSetsAvailable/Used`, `FrontTireSetsAvailable/Used`, `RearTireSetsAvailable/Used` | Tyre-set counts | Separate total/front/rear set counters |
| `DRS_Status`, `DRS_Count` where present | DRS state/count | `drs_active`, `drs_count` |
| `EnergyERSBattery`, `EnergyERSBatteryPct`, `PowerMGU_K`, `TorqueMGU_K`, `PowerMGU_H` where present | Hybrid/ERS data | Explicit energy/power/torque fields |
| `FogLevel`, `Skies`, `SolarAltitude`, `SolarAzimuth` where present | Environment / sky | Explicit weather fields |

## Implementation guardrails

1. Keep the ACC UI contract intact; add iRacing values in the existing normalized payload or add clearly named optional fields.
2. Do not map iRacing incident counts to ACC penalty enums.
3. Do not map suspension deflection/velocity to suspension damage.
4. Do not map cold setup pressure to live hot pressure.
5. Do not map `ManifoldPress` to turbo boost.
6. Do not map `LapDeltaToBestLap_OK` to lap validity.
7. Do not treat `TireSetsUsed` as the currently fitted tyre set.
8. Enumerate the active shared-memory variable header at runtime (or validate against it) because optional variables differ by car and SDK build.
9. A missing variable must remain unavailable/null, not zero or false.
10. Add per-field regression tests and then validate in a live iRacing session; fake-SDK tests alone cannot prove that a car/series exposes a variable.

## Key references

- iRacing SDK variable catalogue mirror: https://irsdk-node.bengsfort.dev/API-Reference/irsdk-node-types/interfaces/TelemetryVarList/
- Community-exported iRacing variable list with descriptions/units: https://github.com/MartijnStraatman/iracing-exporter/blob/main/iracing-vars.txt
- iRacing telemetry SDK documentation overview: https://github.com/ irsdk-node (see linked generated variable catalogue above)

The SDK's live telemetry, session YAML, and IBT/logged telemetry are separate sources. This mapping is scoped to the live shared-memory adapter plus selected session/driver metadata.
