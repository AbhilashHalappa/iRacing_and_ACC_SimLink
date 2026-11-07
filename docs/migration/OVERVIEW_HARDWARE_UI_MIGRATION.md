# Overview and Hardware UI Migration

## Source and destination

- Source repository: `AbhilashHalappa/Race-Engineer-ACC`
- Source branch: `feature/lite-app`
- Source commit inspected: `2c5bc1b19404607c2fba80c83554b52db3907044`
- Destination repository: `AbhilashHalappa/Race-Engineer-ACC-New`
- Destination base: `main` at `f0c70db8949eb800270576ea9ae60ac17d421a08`
- Migration branch: `feature/overview-hardware-migration`

## Scope

Migrate exactly two workspaces, with deliberately separate data boundaries.

1. **Overview — UI only.** Migrate the complete Overview page presentation and visual behaviour: tile layout/editor, tile selection, ordering, pinning, resizing/configuration, theme styling, and the page's visual states. Use static/mock placeholder values where the UI needs content. Do not connect ACC Shared Memory, telemetry, the old dashboard API, a backend, or session/history storage. Do not migrate the old dashboard data pipeline just to populate the page. The Overview data contract can be introduced later.
2. **Hardware — complete hardware workspace.** Migrate the complete Hardware-related UI and the hardware-specific configuration, service, and protocol logic required to make its hardware workflows function. This includes device/hardware status, pedal setup and live physical pedal readings, pedal response curves, calibration, pedal sensor setup, C3 handbrake configuration, HID gamepad input testing, and serial receiver/device management. Retain the necessary shared hardware service, models, settings, serial bridge, HID polling, and protocol implementation; do not reduce this to handbrake-only functionality.

**Critical separation:** the Hardware workspace must not receive, depend on, or consume ACC game telemetry. Its data comes only from its own hardware devices and hardware service. It must remain independently connectable to the new application later. The Overview is also disconnected from live data for this migration; its placeholders are visual-only.

## Source UI inventory

- `frontend/src/LiteApp.tsx` — reference for the two-workspace shell and theme toggle.
- `frontend/src/App.tsx` — source of the Overview and Hardware page implementations. It also contains unrelated full-app navigation and other pages; do not copy it wholesale.
- `frontend/src/PedalCurveEditor.tsx` — pedal curves, calibration and sensor configuration UI.
- `frontend/src/InputTester.tsx` — live game-controller buttons/axes and rescan.
- `frontend/src/DeviceManagement.tsx` — serial-port inventory and receiver selection.
- `frontend/src/hardwareApi.ts` — hardware API contracts and commands.
- `frontend/src/dashboardApi.ts` — contains the old live dashboard transport/data contract. Do not carry its ACC/dashboard data connection into the new Overview. Extract only any genuinely hardware-specific contract if needed, without retaining the dashboard dependency.
- `frontend/src/styles.css` — shared visual tokens and page styling; retain the styling required by both migrated workspaces.
- `frontend/lite.html`, `frontend/src/lite-main.tsx`, and Vite/TypeScript configuration — reference for the isolated frontend entry point.

## Hardware backend dependency inventory

The Hardware UI depends on local hardware services and is not a React-only page. Port the minimum complete hardware-specific runtime required by the retained workflows, keeping it independent of ACC telemetry and the old full application runtime.

Relevant source modules include:

- `src/hardware_companion/dashboard_api.py` — inspect and extract only hardware endpoints/handlers; do not bring over ACC dashboard or telemetry routes.
- `src/hardware_companion/pedal_curves.py` — authoritative pedal curve model, normalization and wire encoding.
- `src/hardware_companion/pedal_auto_calibration.py` — calibration capture logic.
- `src/hardware_companion/pedal_sensor.py` — pedal sensor configuration/status protocol.
- `src/hardware_companion/handbrake_sensor.py` — C3 handbrake sensor protocol.
- `src/hardware_companion/protocol.py` — serial receiver bridge, status readback, command queue and port reconnection.
- `src/hardware_companion/input_tester.py` — shared Windows gamepad/HID polling service.
- `src/hardware_companion/models.py` — receiver and hardware state models.
- `src/hardware_companion/settings.py` — hardware receiver settings persistence.

Review imports and runtime ownership before porting. Do not create duplicate serial ownership or duplicate curve normalization, calibration, HID polling, or firmware-protocol logic.

## Greenfield integration rules

- Keep the new ACC acquisition/recording pipeline independent and highest priority.
- The Hardware workspace and hardware service must not accept or consume ACC game telemetry. Hardware state is sourced only from hardware devices and the hardware service.
- Hardware polling, serial I/O, HID polling, hardware command handling and UI updates must remain outside the ACC acquisition loop.
- Expose hardware state and commands through a separate hardware-service/interface. This interface can be integrated into the new application later without coupling it to ACC telemetry.
- Preserve command/readback semantics: queued commands are pending until a newer authoritative receiver status confirms them.
- Preserve unknown/not-reported states; do not render them as disconnected or as zero.
- Keep device management local-only unless a future security review explicitly authorizes remote access.
- Overview is visual-only in this migration: use mock/static values and local UI state; no ACC telemetry, dashboard API, backend, or session/history dependency.
- Do not import the old full dashboard server, full application runtime, coaching, strategy, replay, settings, session persistence, or old ACC telemetry/lap-processing runtime merely to make the migrated pages compile.
- Do not copy firmware projects as part of this UI migration. Maintain compatibility with the existing hardware firmware/protocol.

## Migration sequence

1. Create an isolated two-workspace frontend shell for Overview and Hardware; exclude all unrelated pages and navigation.
2. Extract the complete Overview UI and visual interactions, replacing data reads with static/mock placeholders and local UI state.
3. Extract the complete Hardware UI, including pedal setup/curves/calibration, handbrake configuration, HID input testing, device management and all associated hardware status views.
4. Port the hardware service and its protocol/model dependencies behind an isolated hardware-service boundary, retaining one owner for the serial receiver and one shared HID polling service. Do not connect this service to ACC telemetry.
5. Keep Overview and Hardware data paths independent: Overview placeholders only; Hardware device/service data only.
6. Add focused tests for UI state/interaction behaviour and hardware curve normalization/serialization, sensor protocol encoding/decoding, calibration state transitions, readback confirmation, port selection and HID snapshots.
7. Build and type-check the frontend and run backend tests. Live hardware validation must be performed on the target Windows machine; ACC telemetry integration is explicitly out of scope.

## Explicit exclusions

Do not migrate Race Engineer, Performance Coach, Corner Coach, Race Strategy, Replay & Analysis, Settings, the full application shell, unrelated dashboard/server routes, session/history persistence, coaching services, or the old ACC telemetry/lap-processing runtime. Do not connect ACC telemetry to either page in this migration.

This document records the corrected migration boundary. It does not claim that the code migration or live hardware validation has been completed.
