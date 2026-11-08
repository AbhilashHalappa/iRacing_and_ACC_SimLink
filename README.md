# Race Engineer ACC New — Acquisition Foundation

This branch is dedicated to building and validating the ACC telemetry acquisition and raw-recording foundation before adding the desktop UI, Hardware workspace, coaching or lap analysis.

## Current project status

**As of 8 November 2026:** the source-independent Physics acquisition core and Windows ACC Physics shared-memory adapter are implemented. Automated acquisition tests passed locally (13/13), and a short live ACC smoke test successfully copied 100 Physics pages of the expected 784-byte size while observing 100 unique, advancing packet IDs.

This is not yet a complete acquisition pipeline. Sustained acquisition through the acquirer and buffer, cadence/CPU measurement, Graphics and Static page acquisition, raw recording, recovery and end-of-session reconciliation remain outstanding.

The project-level stage tracker, evidence, limitations and next-stage acceptance gates are maintained in [docs/PROJECT_COMPLETION_STATUS.md](docs/PROJECT_COMPLETION_STATUS.md). Update that document whenever a stage reaches a new evidence-backed state.

## Current scope

The initial source-independent core is in `src/race_engineer_acquisition/`:

- Immutable raw Physics observation models.
- A bounded, preallocated SPSC ring buffer that never overwrites unread samples.
- Non-blocking producer insertion with explicit loss accounting.
- An injectable Physics acquisition loop with monotonic read timestamps.
- Packet-ID gap, duplicate, regression and consistency-retry accounting.
- A Windows read-only adapter for the audited `Local\\acpmf_physics` mapping/layout.

**Important:** ACC Shared Memory exposes latest-state pages, not a guaranteed delivery queue. The project distinguishes source packet progression from application-level buffer loss and does not claim zero source-level packet loss. The current implementation reads Physics only; Graphics and Static are not implemented. The package is not yet a complete raw recorder.

## Run the current tests

From the repository root on Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -v
```

## Next gate

Implement a controlled live benchmark that exercises the actual `PhysicsAcquirer` and SPSC buffer together. Define a deliberate polling/cadence policy, measure read intervals/duration, packet gaps, consistency retries, buffer rejects, occupancy/high-water and CPU impact during sustained ACC driving. Do not begin the raw recorder until the acquisition measurement baseline and loss accounting are trustworthy.

See:
- [Project Completion Status](docs/PROJECT_COMPLETION_STATUS.md)
- [Acquisition and Data Integrity Decision](docs/decisions/ACC_HIGH_PRIORITY_ACQUISITION_AND_DATA_INTEGRITY.md)
