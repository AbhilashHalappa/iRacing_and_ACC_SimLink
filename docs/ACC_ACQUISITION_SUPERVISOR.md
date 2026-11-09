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
each can be configured independently. The returned buffers are not a
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

The script opens all three independent mappings through their worker threads,
then requests shutdown. It reports each stream's state, capture count, pending
buffer entries, buffer rejections and source-close errors. It performs no disk
writes and does not repeat Physics/Graphics field recordings.
