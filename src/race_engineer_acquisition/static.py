"""Raw-only ACC Static shared-memory acquisition.

Static has no documented packetId or source timestamp member. This adapter
therefore preserves the complete mapping bytes and explicitly records those
source fields as absent; local monotonic read timestamps are acquisition
metadata, not fabricated ACC timestamps. A new snapshot is emitted at startup
and only when the raw page changes.
"""
from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from .ring_buffer import AcquisitionRingBuffer
from .health import AcquisitionHealth

STATIC_MAP = r"Local\acpmf_static"
MIN_STATIC_MAPPING_SIZE = 1


@dataclass(frozen=True, slots=True)
class RawStaticRead:
    payload: bytes


@dataclass(frozen=True, slots=True)
class StaticSnapshot:
    capture_sequence: int
    source_packet_id: int | None
    source_timestamp_ns: int | None
    read_start_ns: int
    read_complete_ns: int
    capture_timestamp_ns: int
    payload: bytes

    @property
    def acquisition_duration_ns(self) -> int:
        return self.read_complete_ns - self.read_start_ns


@dataclass(slots=True)
class StaticAcquisitionMetrics:
    read_count: int = 0
    capture_count: int = 0
    unchanged_read_count: int = 0
    buffer_rejection_count: int = 0
    last_capture_sequence: int = 0
    last_acquisition_duration_ns: int = 0
    max_acquisition_duration_ns: int = 0


class StaticSource(Protocol):
    @property
    def page_size(self) -> int: ...
    def read_static(self) -> RawStaticRead: ...
    def close(self) -> None: ...


class StaticAcquirer:
    """Emit an initial Static page and later snapshots only when bytes change."""

    def __init__(
        self,
        source: StaticSource,
        buffer: AcquisitionRingBuffer[StaticSnapshot],
        *,
        clock_ns=time.perf_counter_ns,
    ) -> None:
        self._source = source
        self._buffer = buffer
        self._clock_ns = clock_ns
        self._previous_payload: bytes | None = None
        self._next_sequence = 1
        self.metrics = StaticAcquisitionMetrics()
        self.health = AcquisitionHealth()

    def capture_once(self) -> StaticSnapshot | None:
        started = self._clock_ns()
        try:
            raw = self._source.read_static()
        except Exception as exc:
            self.health.record_read_failure(exc)
            raise
        completed = self._clock_ns()
        self.health.record_read_success(completed, completed - started)
        self.metrics.read_count += 1
        payload = bytes(raw.payload)
        if not payload:
            raise ValueError("ACC Static mapping returned an empty page")
        if self._previous_payload is not None and payload == self._previous_payload:
            self.metrics.unchanged_read_count += 1
            return None

        sequence = self._next_sequence
        self._next_sequence += 1
        # ACC's documented SPageFileStatic has no packet ID or source timestamp.
        # Do not borrow either value from Physics/Graphics or synthesize one.
        snapshot = StaticSnapshot(
            capture_sequence=sequence,
            source_packet_id=None,
            source_timestamp_ns=None,
            read_start_ns=started,
            read_complete_ns=completed,
            capture_timestamp_ns=completed,
            payload=payload,
        )
        self.metrics.capture_count += 1
        self.metrics.last_capture_sequence = sequence
        duration = snapshot.acquisition_duration_ns
        self.metrics.last_acquisition_duration_ns = duration
        self.metrics.max_acquisition_duration_ns = max(
            self.metrics.max_acquisition_duration_ns, duration
        )
        if not self._buffer.try_put(snapshot):
            self.metrics.buffer_rejection_count += 1
            self.health.record_buffer_rejection()
        else:
            # Only suppress this payload after it has entered the queue. If the
            # bounded buffer rejects it, the next poll must retry the same page.
            self._previous_payload = payload
        return snapshot

    def run(self, stop_event: Event, *, refresh_interval_ns: int = 1_000_000_000) -> None:
        if refresh_interval_ns <= 0:
            raise ValueError("refresh_interval_ns must be positive")
        next_deadline = self._clock_ns()
        while not stop_event.is_set():
            wait_ns = next_deadline - self._clock_ns()
            if wait_ns > 0 and stop_event.wait(wait_ns / 1_000_000_000):
                break
            if stop_event.is_set():
                break
            self.capture_once()
            next_deadline += refresh_interval_ns
            now = self._clock_ns()
            if next_deadline <= now:
                missed = ((now - next_deadline) // refresh_interval_ns) + 1
                next_deadline += missed * refresh_interval_ns


class _SectionBasicInformation(ctypes.Structure):
    _fields_ = [
        ("base_address", ctypes.c_void_p),
        ("allocation_attributes", ctypes.c_ulong),
        ("maximum_size", ctypes.c_longlong),
    ]


class _WindowsStaticMapping:
    """Read-only mapping that discovers and copies the complete allocation."""

    def __init__(self, name: str = STATIC_MAP) -> None:
        if os.name != "nt":
            raise OSError("ACC Static shared memory requires Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ntdll = ctypes.WinDLL("ntdll")
        self._kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
        ]
        self._kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        self._kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_size_t
        ]
        self._kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self._kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._ntdll.NtQuerySection.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
        ]
        self._ntdll.NtQuerySection.restype = ctypes.c_long
        # SECTION_QUERY | SECTION_MAP_READ only.
        self._handle = self._kernel32.OpenFileMappingW(0x0001 | 0x0004, 0, name)
        if not self._handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"Cannot open {name}. Is ACC running?")
        self._view = None
        self.size = 0
        try:
            info = _SectionBasicInformation()
            returned = ctypes.c_ulong()
            status = self._ntdll.NtQuerySection(
                self._handle, 0, ctypes.byref(info),
                ctypes.sizeof(info), ctypes.byref(returned)
            )
            if status < 0:
                raise OSError(
                    f"NtQuerySection failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}"
                )
            self.size = int(info.maximum_size)
            if self.size < MIN_STATIC_MAPPING_SIZE:
                raise ValueError(f"Invalid ACC Static mapping size: {self.size}")
            self._view = self._kernel32.MapViewOfFile(
                self._handle, 0x0004, 0, 0, 0
            )
            if not self._view:
                error = ctypes.get_last_error()
                raise OSError(error, f"Cannot map {name}")
        except Exception:
            self.close()
            raise

    def copy_page(self) -> bytes:
        if not self._view:
            raise OSError("ACC Static shared-memory view is closed")
        return ctypes.string_at(self._view, self.size)

    def close(self) -> None:
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class WindowsACCStaticSource:
    """Read-only ACC Static source; no guessed layout or field decoding."""

    def __init__(self, mapping_factory=_WindowsStaticMapping) -> None:
        self._mapping_factory = mapping_factory
        self._mapping = None

    def _ensure_mapping(self):
        if self._mapping is None:
            self._mapping = self._mapping_factory()
        return self._mapping

    @property
    def page_size(self) -> int:
        return int(self._ensure_mapping().size)

    def read_static(self) -> RawStaticRead:
        mapping = self._ensure_mapping()
        payload = mapping.copy_page()
        if len(payload) != mapping.size or not payload:
            raise ValueError(
                f"ACC Static copy size mismatch: {len(payload)} != {mapping.size}"
            )
        return RawStaticRead(payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
