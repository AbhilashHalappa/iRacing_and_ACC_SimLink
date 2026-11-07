# Overview and Hardware UI Migration

## Source and destination

- Source repository: `AbhilashHalappa/Race-Engineer-ACC`
- Source branch: `feature/lite-app`
- Source commit inspected: `2c5bc1b19404607c2fba80c83554b52db3907044`
- Destination repository: `AbhilashHalappa/Race-Engineer-ACC-New`
- Destination base: `main` at `f0c70db8949eb800270576ea9ae60ac17d421a08`
- Migration branch: `feature/overview-hardware-migration`

## Scope

Carry over only these two user-facing workspaces:

1. **Overview** — the live ACC overview, tile layout/editor, telemetry cards, map, weather, tyres, brakes, fuel, lap display/history tile, and hardware-status tile.
2. **Hardware** — device status, pedal response curves, live physical pedal readings, pedal calibration, pedal sensor setup, C3 handbrake configuration, HID Input Tester, and serial receiver port management.

The Lite shell may be used as a visual/reference starting point, but the page components must be isolated from the full application's navigation and unrelated page implementations.

## Source UI inventory

- `frontend/src/LiteApp.tsx` — two-page shell and theme toggle.
- `frontend/src/App.tsx` — source of the Overview and Hardware page implementations. It also contains unrelated full-app navigation and placeholder page wiring; do not copy it wholesale.
- `frontend/src/PedalCurveEditor.tsx` — pedal curves, calibration and sensor configuration UI.
- `frontend/src/InputTester.tsx` — live game-controller buttons/axes and rescan.
- `frontend/src/DeviceManagement.tsx` — serial-port inventory and receiver selection.
- `frontend/src/hardwareApi.ts` — hardware API contracts and commands.
- `frontend/src/dashboardApi.ts` — live dashboard transport and Overview data contract.
- `frontend/src/styles.css` — shared visual tokens and page styling; retain only styling required by the two migrated pages when practical.
- `frontend/lite.html`, `frontend/src/lite-main.tsx`, and Vite/TypeScript configuration — reference for the isolated frontend entry point.

## Hardware backend dependency inventory

The current Hardware UI is not a standalone React-only page. Its workflows use local HTTP endpoints backed by the shared receiver service.

Relevant source modules include:

- `src/hardware_companion/dashboard_api.py` — pedal curve, calibration, sensor, handbrake and device-management API operations.
- `src/hardware_companion/pedal_curves.py` — authoritative curve model, normalization and wire encoding.
- `src/hardware_companion/pedal_auto_calibration.py` — calibration capture logic.
- `src/hardware_companion/pedal_sensor.py` — pedal sensor configuration/status protocol.
- `src/hardware_companion/handbrake_sensor.py` — C3 handbrake sensor protocol.
- `src/hardware_companion/protocol.py` — serial receiver bridge, status readback, command queue and port reconnection.
- `src/hardware_companion/input_tester.py` — shared Windows gamepad/HID polling service.
- `src/hardware_companion/models.py` — receiver and hardware state models.
- `src/hardware_companion/settings.py` — receiver settings persistence.

These modules must be reviewed for imports and runtime ownership before being ported. In particular, do not create a second serial owner or duplicate receiver, calibration, curve-normalization or firmware-protocol logic.

## Greenfield integration rules

- Keep the new ACC acquisition/recording pipeline independent and highest priority.
- Hardware polling, serial I/O, UI updates and hardware command handling must not execute in the ACC acquisition loop.
- Expose hardware state through a separate service/interface consumed by the Hardware page.
- Preserve command/readback semantics: queued commands are pending until a newer authoritative receiver status confirms them.
- Preserve unknown/not-reported states; do not render them as disconnected or as zero.
- Keep device management local-only unless a future security review explicitly authorizes remote access.
- Do not import the old full dashboard server, full application runtime, coaching, strategy, replay, settings, session persistence or unrelated services merely to make these pages compile.
- Do not copy firmware projects as part of the page migration. Existing firmware/protocol compatibility must be maintained by the hardware service.

## Migration sequence

1. Extract Overview and Hardware page components into dedicated modules with a two-page navigation shell; exclude unrelated page code.
2. Bring across the minimum frontend components, types, theme tokens and static assets required by those pages.
3. Define the greenfield dashboard-state and hardware-service interfaces. Keep the Overview read-only with respect to acquisition.
4. Port the hardware service and its protocol/model dependencies behind an isolated service boundary; retain one owner for the serial receiver and one shared HID polling service.
5. Add focused tests for curve normalization/serialization, sensor protocol encoding/decoding, calibration state transitions, readback confirmation, port selection and HID snapshots.
6. Build and type-check the frontend; then perform live ACC and hardware validation on Windows.

## Explicit exclusions

Do not migrate Race Engineer, Performance Coach, Corner Coach, Race Strategy, Replay & Analysis, Settings, the full application shell, unrelated dashboard/server routes, session/history persistence, coaching services, or the old ACC telemetry/lap-processing runtime.

This document records the migration boundary. It does not claim that the code migration or live hardware validation has been completed.
