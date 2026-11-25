# iRacing & ACC SimLink — Overview-only branch

This branch is a lightweight, live-telemetry desktop application. It retains the Overview dashboard, its configurable tiles, and the ACC telemetry acquisition/decoding path required to feed them.

## Included

- ACC Shared Memory Physics, Graphics and Static acquisition.
- Existing decoded telemetry consumers and stream-health reporting.
- Live Overview dashboard and its tiles, including the track map.
- Overview tile layout, glow thresholds and tyre-pressure target settings.
- Out-lap observation used to mark the current lap tile.
- Local WebEngine profile/cache for the desktop shell.

## Deliberately excluded

This branch does not start or include the Race Strategy service, Performance Hub lap archive/capture/persistence workers, canonical track-model analysis, coaching/analysis workspaces, fuel-assessment background workers, standalone acquisition/recording tools, or the Hardware workspace.

The Overview UI reads the live Physics, Graphics and Static consumer snapshots directly. No lap archive or strategy-history database is created by this branch. User settings remain in browser local storage.

## Windows setup

From the repository root:

```powershell
python -m pip install -r requirements-desktop.txt

cd frontend
npm.cmd install
npm.cmd run build

cd ..
python -m src.main
```

Start ACC before expecting live values. The desktop app can open without ACC, but its telemetry tiles will show their waiting/unavailable states until the shared-memory streams become available.

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -v
```

Frontend utility tests:

```powershell
cd frontend
npm.cmd run test:track-map
npm.cmd run test:time-units
```

This branch is intentionally separate from `main`. It is a reduced Overview runtime, not a replacement for the full development branch.
