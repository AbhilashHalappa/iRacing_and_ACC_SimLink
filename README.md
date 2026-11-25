# iRacing & ACC SimLink — Overview-only

This branch adds iRacing telemetry to the tested Overview-only desktop application while retaining the ACC implementation. The React Overview dashboard, tile library, tile arrangement, settings, theme, and bridge contract are shared.

## Supported game modes

### ACC (unchanged)
Uses the existing ACC Shared Memory Physics, Graphics and Static acquisition/decoding path.

```powershell
python -m src.main --game acc
```

### iRacing (new)
Uses the iRacing SDK shared-memory interface through `pyirsdk`. The SDK reader runs on a background thread, reconnects when iRacing starts or restarts, and publishes detached snapshots through the same HTTP/SSE bridge and normalized tile data contract.

```powershell
python -m src.main --game iracing
```

The default game remains ACC to preserve the tested startup behaviour. Start the selected simulator before expecting live values.

## Overview tile coverage and source limitations

The same Overview tiles are retained. iRacing fields are mapped where the SDK provides them; unavailable values are deliberately left blank rather than inferred or fabricated.

- Live: speed, gear, RPM, throttle, brake, clutch, steering, lap timer, last/best lap, lap count, session/track/car identity, position, fuel level, air/track temperature, wind, and available tyre carcass temperatures.
- Derived: fuel-per-lap and estimated laps remaining are calculated from observed fuel changes across completed laps.
- Not exposed by the standard iRacing SDK contract used here: live hot tyre pressure, brake-disc temperature, suspension/car damage, reliable lap-validity/out-lap status, sector timing, and circuit world coordinates. The relevant tiles remain present but show unavailable values. The Track Map tile explains the world-coordinate limitation.
- Hardware connections remain reported by the existing hardware tile; no firmware or hardware protocol changes are made.

## Windows setup

From the repository root:

```powershell
python -m pip install -r requirements-desktop.txt

cd frontend
npm.cmd install
npm.cmd run build

cd ..
python -m src.main --game iracing
```

For ACC, use `python -m src.main --game acc`.

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m compileall -q src
python -m unittest discover -s tests/acquisition -v
python -m unittest discover -s tests/iracing -v
```

Frontend utility tests:

```powershell
cd frontend
npm.cmd run test:track-map
npm.cmd run test:time-units
```

This feature branch is based on `feature/overview-only`. The `main` and `feature/overview-only` branches are not modified by the iRacing work.
