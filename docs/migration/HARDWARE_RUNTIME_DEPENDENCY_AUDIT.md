# Hardware Runtime Dependency Audit

**Target branch:** `feature/overview-hardware-migration`  
**Source inspected:** `AbhilashHalappa/Race-Engineer-ACC` at `2c5bc1b19404607c2fba80c83554b52db3907044`  
**Status:** Source dependency audit complete; destination application runtime not implemented.

## Why this audit exists

The destination branch currently contains architecture and migration documentation only. It does not yet contain a Python application entry point, hardware service host, frontend package, or build workflow. Therefore, this audit separates dependencies required by the hardware workflows from dependencies belonging to the old full application. It does not claim that the new application has been built or run.

## Hardware dependency findings

The source Hardware workspace contains these workflows:

- Serial receiver discovery, connection, reconnect, status readback, and command dispatch.
- Pedal curves and pedal enable/configuration.
- Pedal sensor setup and calibration.
- C3 handbrake sensor setup and calibration.
- Windows game-controller button/axis input testing.
- Serial receiver port selection and device management.

The audited hardware modules use Python standard-library facilities for their models, curve calculations, calibration capture, settings serialization, and hardware API payloads. The two third-party runtime libraries needed for the complete retained hardware workflows are:

| Package | Version | Why it is needed |
|---|---:|---|
| `pyserial` | `3.5` | `hardware_companion/protocol.py` imports `serial` and `serial.tools.list_ports` for the receiver serial link and port inventory. |
| `pygame` | `2.6.1` | `hardware_companion/input_tester.py` uses pygame's joystick/game-controller subsystem for live buttons and axes. |

These versions match the source repository's existing pinned `requirements.txt`.

## Deliberately excluded packages

| Package | Reason it is not part of the Hardware workspace runtime manifest |
|---|---|
| `piper-tts` | Voice/TTS feature, excluded from the Overview + Hardware migration. |
| `sounddevice` | Audio capture/playback feature, not used by the retained hardware workflows. |
| `faster-whisper` | Speech recognition, not used by the retained hardware workflows. |
| `av` | Audio/video processing dependency for speech/media paths, not used by the retained hardware workflows. |
| `hidapi` | The migrated Input Tester implementation uses pygame; the audited hardware Input Tester does not import hidapi. |
| `qrcode` | Offline LAN setup/QR feature, not part of the hardware workspace. |
| `PySide6` | Used by the old standalone Qt hardware UI (`hardware_companion/gui_qt.py`), not by the React Hardware workspace being migrated. Revisit only if the new application explicitly chooses a Qt-native shell. |

## Runtime boundary

- **Overview:** static/mock values and local UI state only. No Python dependency, ACC telemetry connection, dashboard API, backend, or session/history dependency is required for this page.
- **Hardware:** its service reads hardware devices only. It must not accept or consume ACC game telemetry.
- **Application host:** the new Python host/server and desktop shell have not been implemented. Their dependencies must be added only after their actual imports and selected architecture are present. Do not copy the old monolithic `dashboard_server.py` or `src/main.py` dependency graph into this project.
- **Frontend:** React/TypeScript dependencies belong in the future frontend `package.json`; they are not Python requirements.

## Manifest

The companion file `requirements-hardware.txt` contains only the two audited third-party dependencies for the complete Hardware workspace.

This is intentionally not named `requirements.txt`: it is a scoped hardware dependency set, not a complete install manifest for an application that does not yet exist.

## Validation status and next gate

- Source imports were inspected at the source commit recorded above.
- Dependency selection is source-audited, not yet validated by installing and running the destination application.
- The destination currently has no runtime code or CI workflow to exercise these packages.
- When the hardware service is ported, add a focused CI job that installs `requirements-hardware.txt`, compiles the hardware modules, and runs isolated tests for serial protocol parsing/encoding, curve normalization, calibration transitions, and gamepad snapshot handling.
- Live serial receiver and gamepad validation must still be performed on the target Windows machine.

Do not add the old application's audio, coaching, telemetry, session, or dashboard dependencies to this manifest.
