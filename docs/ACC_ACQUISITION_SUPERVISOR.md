# ACC Acquisition Lifecycle Supervisor

**Status:** Implemented in the acquisition foundation; automated lifecycle tests added.
**Scope:** Physics, Graphics and Static worker lifecycle only.

## Entry point

The default Windows runtime is built and started through one entry point:

```python
from race_engineer_acquisition.supervisor import create_acc_acquisition_runtime

runtime = create_acc_acquisition_runtime()
runtime.supervisor.start()

# The streams run concurrently. Read each stream only from its own buffer:
physics_buffer = runtime.buffers["physics"]
graphics_buffer = runtime.buffers["graphics"]
static_buffer = runtime.buffers["static"]

# On application shutdown:
still_running = runtime.supervisor.stop(timeout=5.0)
if still_running:
    # Report the names; do not unmap a source while its worker may still read.
    print("Acquisition workers did not stop:", still_running)
```

The runtime creates independent Windows source adapters, acquirers and bounded
SPSC buffers. Mapping handles are opened lazily on the corresponding worker
thread. Default cadence is Physics 480 Hz, Graphics 100 Hz and Static 1 Hz;
each can be configured independently. On Windows, the supervisor requests a
balanced 1 ms WinMM timer resolution before starting workers and holds that
request until every worker has exited. If shutdown times out, the request stays
active until the final worker exits; it is never released while acquisition is
still running. Set `timer_resolution_ms=0` only for a controlled diagnostic
comparison, not normal operation. Timer resolution improves wait granularity
but cannot guarantee scheduler wake-up timing. The returned buffers are not a
multi-consumer broadcast mechanism and are not connected to persistence.

## Lifecycle contract

- Each stream has its own thread and stop event; no stream performs another
  stream's read or waits for another stream's source.
- Existing Physics, Graphics and Static acquisition loops are called unchanged.
  Their packet IDs, timestamps, snapshot models, buffer behavior and Static
  initial/change-detection rules remain independent.
- A worker exception marks only that stream `failed`, records its exception
  text and closes its source. Other workers continue until explicitly stopped.
- If a thread cannot be started part-way through startup, the supervisor sets
  every stop event, joins workers that did start, and closes sources for workers
  that never started. Startup raises `AcquisitionStartupError`.
- Each source close callback is guarded and invoked at most once.
- `stop(timeout)` uses one shared timeout budget and returns names of workers
  that remain alive. A timed-out worker retains ownership of its source; the
  supervisor does not unmap shared memory while a read may still be in flight.
- Repeated stop calls are safe.
- The supervisor does not decode, serialize, persist, update UI/dashboard,
  coach, reconstruct laps or merge/synchronize streams.

## Validation

Run from the repository root on Windows PowerShell or another supported Python
environment:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -p "test_supervisor.py" -v
python -m unittest discover -s tests/acquisition -v
```

The focused tests cover concurrent independent startup, normal and repeated
shutdown, exactly-once source close, worker failure isolation, partial startup
rollback and duplicate stream-name rejection.

A Windows ACC smoke test is still required to validate all three live mapping
opens and clean shutdown together. This lifecycle change does not require
repeating Physics or Graphics field recordings.


## Live Windows smoke test

With ACC running, execute:

```powershell
python scripts/validate_acc_acquisition_supervisor.py --seconds 30
```

The script opens all three independent mappings through their worker threads
and drains each SPSC queue on a separate validation thread. It requests a 1 ms
timer resolution by default, measures actual successful-read rates, reconciles
all captured records against drained/rejected/pending records, and checks clean
shutdown. Acceptance requires at least 99% of the configured 480 Hz Physics
and 100 Hz Graphics read rates, zero source read failures, zero buffer rejects,
zero reconciliation delta, empty queues and released timer resolution. It
performs no disk writes and does not repeat Physics/Graphics field recordings.

Run the full 120-second validation (matching the original benchmark duration)
with:

```powershell
python scripts/validate_acc_acquisition_supervisor.py --seconds 120 --minimum-rate-ratio 0.99
```

A `PASSED` result is now performance-gated; merely observing one or more reads
is insufficient. Compare the Physics read rate with the original measured
479.672 Hz benchmark. Compare Physics unique capture rate separately: ACC does
not publish a new packet on every poll, so the historical 388.50 unique
snapshots/s is not the polling-rate acceptance target. The validator also reports total process CPU as a percentage of one core;
compare it with the original Physics-only benchmark cautiously because this
runtime additionally polls Graphics and Static and drains three queues.


## Common per-stream health

Every Physics, Graphics and Static acquirer exposes `acquirer.health.snapshot`,
an immutable `AcquisitionHealthSnapshot`. The supervisor also includes that
same snapshot in `supervisor.status[name]["health"]`.

Common fields:

- `lifecycle_state`: `idle`, `starting`, `running`, `stopped` or `failed`.
- `successful_reads` and `source_read_failures`.
- `consecutive_failures`, reset after the next successful source read.
- `last_successful_read_ns`: local monotonic completion timestamp, not an ACC
  source timestamp.
- `last_read_duration_ns` and `max_read_duration_ns`.
- `buffer_rejections` and `last_error`.

Source exceptions are counted at the source-read boundary and re-raised. The
supervisor records the fatal worker state and error; it does not silently retry
or change the existing fail-fast worker policy. A caller using `capture_once()`
directly can catch an exception and retry; the next successful read resets the
consecutive-failure count.

Health ownership is split by field: the supervisor alone writes lifecycle
state, while the corresponding acquisition worker alone writes read and buffer
counters. These fields are stored independently so concurrent updates cannot
overwrite each other. Readers obtain a frozen snapshot without acquiring a
lock. Health reads are therefore detached and non-blocking. Existing
stream-specific metrics remain on `acquirer.metrics` (Physics packet gaps,
consistency retries and timing; Graphics packet observations and consistency;
Static unchanged-read counts). Common health does not replace those metrics.

The common health test suite is:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests/acquisition -p "test_health.py" -v
python -m unittest discover -s tests/acquisition -v
```
