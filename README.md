# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current scope

The initial source-independent core is in src/race_engineer_acquisition/:

- Immutable raw Physics observation models.
- A bounded, preallocated SPSC ring buffer that never overwrites unread samples.
- Non-blocking producer insertion with explicit loss accounting.
- An injectable Physics acquisition loop with monotonic read timestamps.
- Packet-ID gap accounting and snapshot consistency retry accounting.

**Important:** the Windows ACC Physics Shared Memory adapter now exists and targets the audited Local\acpmf_physics mapping/layout. It has not yet been validated against a live ACC process or tested on the target Windows machine. The package is not yet a complete raw recorder.

## Run the current tests

From the repository root on Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -v
```

## Next gate

Validate the adapter on the target Windows machine with ACC running. Confirm the page size, packet-ID behaviour, consistency retry rate and measured acquisition cadence before adding the independent binary recorder.

See [the acquisition and data-integrity decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md).
