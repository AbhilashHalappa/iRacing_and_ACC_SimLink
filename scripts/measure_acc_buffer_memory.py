"""Measure default ACC queue storage and snapshot-object overhead on Windows.

This is an offline sizing diagnostic: it does not open ACC shared memory,
start acquisition threads, or write recordings. Payload bytes are shared
between synthetic snapshots so tracemalloc isolates queue/reference and
snapshot metadata overhead; the full distinct-payload bound is reported
separately.
"""
from __future__ import annotations

import ctypes
import json
import struct
import sys
import tracemalloc

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE
from race_engineer_acquisition.fanout import BoundedConsumerQueue
from race_engineer_acquisition.graphics import GraphicsSnapshot
from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import StaticSnapshot


PHYSICS_CAPACITY = 100_000
GRAPHICS_CAPACITY = 10_000
STATIC_CAPACITY = 64
GRAPHICS_PAGE_SIZE = 4_096
STATIC_PAGE_SIZE = 4_096


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def process_memory() -> dict[str, int] | None:
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_ProcessMemoryCountersEx),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        counters = _ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "working_set_bytes": counters.WorkingSetSize,
            "private_usage_bytes": counters.PrivateUsage,
            "peak_working_set_bytes": counters.PeakWorkingSetSize,
        }
    except (AttributeError, OSError):
        return None


def mib(value: int) -> float:
    return round(value / (1024 * 1024), 3)


def main() -> int:
    rss_before = process_memory()
    tracemalloc.start()
    before_queues, _ = tracemalloc.get_traced_memory()

    physics_acquisition = AcquisitionRingBuffer[PhysicsSnapshot](PHYSICS_CAPACITY)
    physics_recorder = BoundedConsumerQueue[PhysicsSnapshot](
        "recorder", PHYSICS_CAPACITY, required=True
    )
    graphics_acquisition = AcquisitionRingBuffer[GraphicsSnapshot](GRAPHICS_CAPACITY)
    graphics_recorder = AcquisitionRingBuffer[GraphicsSnapshot](GRAPHICS_CAPACITY)
    static_acquisition = AcquisitionRingBuffer[StaticSnapshot](STATIC_CAPACITY)
    static_recorder = AcquisitionRingBuffer[StaticSnapshot](STATIC_CAPACITY)

    after_queues, _ = tracemalloc.get_traced_memory()
    rss_queues = process_memory()

    physics_payload = bytes(PHYSICS_SIZE)
    graphics_payload = bytes(GRAPHICS_PAGE_SIZE)
    static_payload = bytes(STATIC_PAGE_SIZE)

    for sequence in range(1, PHYSICS_CAPACITY + 1):
        tick = sequence * 2_083_333
        first = PhysicsSnapshot(sequence, sequence, tick, tick + 1, tick + 1, physics_payload)
        second_sequence = sequence + PHYSICS_CAPACITY
        second_tick = second_sequence * 2_083_333
        second = PhysicsSnapshot(
            second_sequence, second_sequence, second_tick, second_tick + 1,
            second_tick + 1, physics_payload,
        )
        if not physics_acquisition.try_put(first) or not physics_recorder.offer(second):
            raise RuntimeError("Physics queue unexpectedly rejected a sizing sample")

    for sequence in range(1, GRAPHICS_CAPACITY + 1):
        tick = sequence * 10_000_000
        first = GraphicsSnapshot(sequence, sequence, tick, tick + 1, tick + 1, graphics_payload)
        second_sequence = sequence + GRAPHICS_CAPACITY
        second_tick = second_sequence * 10_000_000
        second = GraphicsSnapshot(
            second_sequence, second_sequence, second_tick, second_tick + 1,
            second_tick + 1, graphics_payload,
        )
        if not graphics_acquisition.try_put(first) or not graphics_recorder.try_put(second):
            raise RuntimeError("Graphics queue unexpectedly rejected a sizing sample")

    for sequence in range(1, STATIC_CAPACITY + 1):
        tick = sequence * 1_000_000_000
        first = StaticSnapshot(sequence, None, None, tick, tick + 1, tick + 1, static_payload)
        second_sequence = sequence + STATIC_CAPACITY
        second_tick = second_sequence * 1_000_000_000
        second = StaticSnapshot(
            second_sequence, None, None, second_tick, second_tick + 1,
            second_tick + 1, static_payload,
        )
        if not static_acquisition.try_put(first) or not static_recorder.try_put(second):
            raise RuntimeError("Static queue unexpectedly rejected a sizing sample")

    after_population, peak_traced = tracemalloc.get_traced_memory()
    rss_populated = process_memory()

    queue_count = 2 * PHYSICS_CAPACITY + 2 * GRAPHICS_CAPACITY + 2 * STATIC_CAPACITY
    slot_bytes = queue_count * struct.calcsize("P")
    snapshot_metadata_bytes = after_population - after_queues
    queue_storage_bytes = after_queues - before_queues

    physics_payload_bound = 2 * PHYSICS_CAPACITY * PHYSICS_SIZE
    graphics_payload_bound = 2 * GRAPHICS_CAPACITY * GRAPHICS_PAGE_SIZE
    static_payload_bound = 2 * STATIC_CAPACITY * STATIC_PAGE_SIZE
    total_payload_bound = (
        physics_payload_bound + graphics_payload_bound + static_payload_bound
    )

    report = {
        "measurement": "default-capacity synthetic queue population; no ACC access",
        "pointer_size_bytes": struct.calcsize("P"),
        "queue_count": 6,
        "queue_slots": queue_count,
        "slot_reference_array_bytes_theoretical": slot_bytes,
        "traced_queue_storage_increment_bytes": queue_storage_bytes,
        "traced_snapshot_population_increment_bytes": snapshot_metadata_bytes,
        "traced_current_bytes": after_population,
        "traced_peak_bytes": peak_traced,
        "traced_snapshot_overhead_per_item_bytes": round(
            snapshot_metadata_bytes / queue_count, 2
        ),
        "payload_bound_bytes": {
            "physics": physics_payload_bound,
            "graphics": graphics_payload_bound,
            "static": static_payload_bound,
            "total": total_payload_bound,
        },
        "combined_payload_plus_traced_queue_and_snapshot_bytes": (
            total_payload_bound + queue_storage_bytes + snapshot_metadata_bytes
        ),
        "combined_payload_plus_traced_queue_and_snapshot_mib": mib(
            total_payload_bound + queue_storage_bytes + snapshot_metadata_bytes
        ),
        "process_memory_before": rss_before,
        "process_memory_after_empty_queues": rss_queues,
        "process_memory_after_population": rss_populated,
        "note": (
            "Synthetic snapshots share one payload object per stream to isolate "
            "metadata/reference overhead. Payload budget assumes a distinct full "
            "payload per retained snapshot. RSS includes interpreter/runtime and "
            "allocator effects and is a process-level observation, not a queue-only "
            "measurement."
        ),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
