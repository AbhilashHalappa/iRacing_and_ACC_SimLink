# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current scope

The initial source-independent core is in src/race_engineer_acquisition/:

- Immutable raw Physics observation models.
- A bounded, preallocated SPSC ring buffer that never overwrites unread samples.
- Non-blocking producer insertion with explicit loss accounting.
- An injectable Physics acquisition loop with monotonic read timestamps.
- Packet-ID gap accounting and snapshot consistency retry accounting.

**Important:** the ACC Windows Shared Memory adapter is not implemented yet. This package currently uses an injected source interface and deterministic fake sources in tests. It is not a runnable live ACC recorder yet.

## Run the current tests

From the repository root on Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -v
```

## Next gate

Implement the ACC Physics Shared Memory adapter only after confirming the actual page structure, packet-ID field semantics and copy consistency behaviour. Then measure it in live ACC before adding the independent binary recorder.

See [the acquisition and data-integrity decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md).
