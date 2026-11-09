"""Raw-only ACC Graphics acquisition and recording.

No SPageFileGraphic decoder is defined here. The complete Windows mapping
allocation is copied and persisted so unknown/future fields are retained.
The 1,588-byte candidate struct is not used to limit the raw payload.
"""
from __future__ import annotations

import ctypes
import os
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Iterable, Protocol

from .ring_buffer import AcquisitionRingBuffer
from .health import AcquisitionHealth

GRAPHICS_MAP = r"Local\acpmf_graphics"
MIN_GRAPHICS_MAPPING_SIZE = 4
_FILE_MAGIC = b"ACCGFX01"
_FILE_VERSION = 2
_FILE_HEADER = struct.Struct("<8sIIQI")
_BLOCK_MAGIC = b"GFXB"
_BLOCK_HEADER = struct.Struct("<4sQIII")
_RECORD_HEADER_V1 = struct.Struct("<QQQQQI")
_RECORD_HEADER_V2 = struct.Struct("<QQQQQQI")


@dataclass(frozen=True, slots=True)
class RawGraphicsRead:
    packet_id_before: int
    packet_id_in_payload: int
    packet_id_after: int
    payload: bytes

    @property
    def is_consistent(self) -> bool:
        return self.packet_id_before == self.packet_id_in_payload == self.packet_id_after


@dataclass(frozen=True, slots=True)
class GraphicsSnapshot:
    capture_sequence: int
    acc_graphics_packet_id: int
    read_start_ns: int
    read_complete_ns: int
    capture_timestamp_ns: int
    payload: bytes
    # Set only by the downstream recorder; acquisition snapshots leave this None.
    persistence_timestamp_ns: int | None = None

    @property
    def acquisition_duration_ns(self) -> int:
        return self.read_complete_ns - self.read_start_ns


@dataclass(slots=True)
class GraphicsAcquisitionMetrics:
    capture_count: int = 0
    read_attempt_count: int = 0
    inconsistent_snapshot_count: int = 0
    consistency_retry_count: int = 0
    duplicate_packet_observation_count: int = 0
    source_packet_gap_count: int = 0
    packet_id_regression_count: int = 0
    buffer_rejection_count: int = 0
    last_packet_id: int | None = None
    last_capture_sequence: int = 0
    last_acquisition_duration_ns: int = 0
    max_acquisition_duration_ns: int = 0
    poll_interval_count: int = 0
    total_poll_interval_ns: int = 0
    min_poll_interval_ns: int = 0
    max_poll_interval_ns: int = 0
    _previous_poll_start_ns: int | None = None


class GraphicsSource(Protocol):
    @property
    def page_size(self) -> int: ...
    def read_graphics(self) -> RawGraphicsRead: ...
    def close(self) -> None: ...


class GraphicsAcquirer:
    """Copy complete Graphics pages and publish immutable snapshots."""

    def __init__(
        self, source: GraphicsSource, buffer: AcquisitionRingBuffer[GraphicsSnapshot],
        *, max_consistency_attempts: int = 3, clock_ns=time.perf_counter_ns,
    ) -> None:
        if max_consistency_attempts < 1:
            raise ValueError("max_consistency_attempts must be at least one")
        self._source = source
        self._buffer = buffer
        self._max_attempts = max_consistency_attempts
        self._clock_ns = clock_ns
        self.metrics = GraphicsAcquisitionMetrics()
        self.health = AcquisitionHealth()
        self._next_sequence = 1

    def capture_once(self) -> GraphicsSnapshot | None:
        poll_start_ns = self._clock_ns()
        previous_start = self.metrics._previous_poll_start_ns
        if previous_start is not None:
            interval = poll_start_ns - previous_start
            self.metrics.poll_interval_count += 1
            self.metrics.total_poll_interval_ns += interval
            self.metrics.min_poll_interval_ns = (
                interval if self.metrics.min_poll_interval_ns == 0
                else min(self.metrics.min_poll_interval_ns, interval)
            )
            self.metrics.max_poll_interval_ns = max(
                self.metrics.max_poll_interval_ns, interval
            )
        self.metrics._previous_poll_start_ns = poll_start_ns

        for attempt in range(self._max_attempts):
            read_start_ns = self._clock_ns()
            try:
                raw = self._source.read_graphics()
            except Exception as exc:
                self.health.record_read_failure(exc)
                raise
            read_complete_ns = self._clock_ns()
            self.health.record_read_success(
                read_complete_ns, read_complete_ns - read_start_ns
            )
            self.metrics.read_attempt_count += 1
            if raw.is_consistent:
                break
            self.metrics.inconsistent_snapshot_count += 1
            if attempt + 1 < self._max_attempts:
                self.metrics.consistency_retry_count += 1
        else:
            return None

        packet_id = raw.packet_id_in_payload
        previous = self.metrics.last_packet_id
        if previous is not None and packet_id == previous:
            # Keep the sample: the raw page may still contain changes even when
            # the packet ID is unchanged. This is a raw capture, not a deduper.
            self.metrics.duplicate_packet_observation_count += 1
        sequence = self._next_sequence
        self._next_sequence += 1
        if previous is not None and packet_id > previous + 1:
            self.metrics.source_packet_gap_count += packet_id - previous - 1
        elif previous is not None and packet_id < previous:
            self.metrics.packet_id_regression_count += 1

        snapshot = GraphicsSnapshot(
            sequence, packet_id, read_start_ns, read_complete_ns,
            read_complete_ns, bytes(raw.payload),
        )
        self.metrics.capture_count += 1
        self.metrics.last_capture_sequence = sequence
        self.metrics.last_packet_id = packet_id
        duration = snapshot.acquisition_duration_ns
        self.metrics.last_acquisition_duration_ns = duration
        self.metrics.max_acquisition_duration_ns = max(
            self.metrics.max_acquisition_duration_ns, duration
        )
        if not self._buffer.try_put(snapshot):
            self.metrics.buffer_rejection_count += 1
            self.health.record_buffer_rejection()
        return snapshot

    def run(self, stop_event: Event, *, poll_interval_ns: int = 10_000_000) -> None:
        if poll_interval_ns <= 0:
            raise ValueError("poll_interval_ns must be positive")
        next_deadline_ns = self._clock_ns()
        while not stop_event.is_set():
            wait_ns = next_deadline_ns - self._clock_ns()
            if wait_ns > 0 and stop_event.wait(wait_ns / 1_000_000_000):
                break
            if stop_event.is_set():
                break
            self.capture_once()
            next_deadline_ns += poll_interval_ns
            finished_ns = self._clock_ns()
            if next_deadline_ns <= finished_ns:
                missed = ((finished_ns - next_deadline_ns) // poll_interval_ns) + 1
                next_deadline_ns += missed * poll_interval_ns


class _SectionBasicInformation(ctypes.Structure):
    _fields_ = [
        ("base_address", ctypes.c_void_p),
        ("allocation_attributes", ctypes.c_ulong),
        ("maximum_size", ctypes.c_longlong),
    ]


class _WindowsGraphicsMapping:
    def __init__(self, name: str = GRAPHICS_MAP) -> None:
        if os.name != "nt":
            raise OSError("ACC Graphics shared memory requires Windows")
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
        self._kernel32.UnmapViewOfFile.restype = ctypes.c_int
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_int
        self._ntdll.NtQuerySection.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
        ]
        self._ntdll.NtQuerySection.restype = ctypes.c_long
        # SECTION_QUERY | SECTION_MAP_READ. Never request write access.
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
            if self.size < MIN_GRAPHICS_MAPPING_SIZE:
                raise ValueError(f"Invalid Graphics mapping size: {self.size}")
            self._view = self._kernel32.MapViewOfFile(
                self._handle, 0x0004, 0, 0, 0
            )
            if not self._view:
                error = ctypes.get_last_error()
                raise OSError(error, f"Cannot map {name}")
        except Exception:
            self.close()
            raise

    def read_packet_id(self) -> int:
        if not self._view:
            raise OSError("ACC Graphics shared-memory view is closed")
        return int(ctypes.c_int32.from_address(self._view).value)

    def copy_page(self) -> bytes:
        if not self._view:
            raise OSError("ACC Graphics shared-memory view is closed")
        return ctypes.string_at(self._view, self.size)

    def close(self) -> None:
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class WindowsACCGraphicsSource:
    """Read-only source that copies the complete mapping allocation."""

    def __init__(self, mapping_factory=_WindowsGraphicsMapping) -> None:
        self._mapping_factory = mapping_factory
        self._mapping = None

    def _ensure_mapping(self):
        if self._mapping is None:
            self._mapping = self._mapping_factory()
        return self._mapping

    @property
    def page_size(self) -> int:
        return int(self._ensure_mapping().size)

    def read_graphics(self) -> RawGraphicsRead:
        mapping = self._ensure_mapping()
        before = mapping.read_packet_id()
        payload = mapping.copy_page()
        after = mapping.read_packet_id()
        if len(payload) != mapping.size or len(payload) < 4:
            raise ValueError(
                f"ACC Graphics copy size mismatch: {len(payload)} != {mapping.size}"
            )
        in_payload = struct.unpack_from("<i", payload, 0)[0]
        return RawGraphicsRead(before, in_payload, after, payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None


@dataclass(frozen=True, slots=True)
class GraphicsRecordingRecovery:
    valid_block_count: int
    recovered_snapshot_count: int
    valid_bytes: int
    truncated_bytes: int
    last_block_sequence: int
    last_capture_sequence: int | None
    page_size: int


@dataclass(slots=True)
class GraphicsRecorderMetrics:
    persisted_snapshot_count: int = 0
    persisted_block_count: int = 0
    persisted_bytes: int = 0
    write_failure_count: int = 0
    failed_snapshot_count: int = 0
    first_failed_sequence: int | None = None
    last_failed_sequence: int | None = None
    last_persisted_capture_sequence: int | None = None
    in_flight_snapshot_count: int = 0
    in_flight_first_sequence: int | None = None
    in_flight_last_sequence: int | None = None
    max_block_write_duration_ns: int = 0


def _encode_graphics_snapshot(
    snapshot: GraphicsSnapshot, persistence_timestamp_ns: int
) -> bytes:
    payload = bytes(snapshot.payload)
    return _RECORD_HEADER_V2.pack(
        snapshot.capture_sequence, snapshot.acc_graphics_packet_id,
        snapshot.read_start_ns, snapshot.read_complete_ns,
        snapshot.capture_timestamp_ns, persistence_timestamp_ns, len(payload),
    ) + payload


def _decode_graphics_block(
    payload: bytes, record_count: int, *, format_version: int = 2
) -> list[GraphicsSnapshot]:
    if format_version not in (1, 2):
        raise ValueError(f"Unsupported Graphics recording format version: {format_version}")
    record_header = _RECORD_HEADER_V1 if format_version == 1 else _RECORD_HEADER_V2
    records = []
    offset = 0
    for _ in range(record_count):
        if len(payload) - offset < record_header.size:
            raise ValueError("Truncated Graphics record header")
        values = record_header.unpack_from(payload, offset)
        if format_version == 1:
            seq, packet, started, completed, captured, size = values
            persisted_at = None
        else:
            seq, packet, started, completed, captured, persisted_at, size = values
        offset += record_header.size
        end = offset + size
        if end > len(payload):
            raise ValueError("Truncated Graphics record payload")
        records.append(GraphicsSnapshot(
            seq, packet, started, completed, captured, payload[offset:end], persisted_at
        ))
        offset = end
    if offset != len(payload):
        raise ValueError("Unexpected bytes after Graphics block records")
    return records


class RawGraphicsRecordingWriter:
    """Append-only CRC-protected recording of complete Graphics mapping pages."""

    def __init__(
        self, path: str | Path, *, page_size: int, created_utc_ns: int | None = None,
        clock_ns=time.perf_counter_ns,
    ) -> None:
        if page_size < MIN_GRAPHICS_MAPPING_SIZE:
            raise ValueError("page_size is too small")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.page_size = page_size
        self._clock_ns = clock_ns
        self._last_persistence_timestamp_ns: int | None = None
        created = time.time_ns() if created_utc_ns is None else created_utc_ns
        self._stream = self.path.open("xb")
        prefix = struct.pack("<8sIIQ", _FILE_MAGIC, _FILE_VERSION, page_size, created)
        self._stream.write(prefix + struct.pack("<I", zlib.crc32(prefix)))
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._next_block_sequence = 1
        self._last_capture_sequence: int | None = None
        self._closed = False

    def write_batch(self, snapshots: Iterable[GraphicsSnapshot]) -> int:
        if self._closed:
            raise RuntimeError("Graphics writer is closed")
        items = list(snapshots)
        if not items:
            return 0
        previous = self._last_capture_sequence
        for item in items:
            if previous is not None and item.capture_sequence <= previous:
                raise ValueError("Graphics capture sequences must increase strictly")
            if len(item.payload) != self.page_size:
                raise ValueError(
                    f"Graphics payload must be {self.page_size} bytes; got {len(item.payload)}"
                )
            previous = item.capture_sequence

        # One recorder-boundary timestamp is shared by every sample in this
        # batch. It is sampled after batch assembly and before block I/O.
        persistence_timestamp_ns = self._clock_ns()
        if (
            self._last_persistence_timestamp_ns is not None
            and persistence_timestamp_ns < self._last_persistence_timestamp_ns
        ):
            raise RuntimeError("Monotonic persistence clock moved backwards")
        encoded = bytearray()
        for item in items:
            encoded.extend(_encode_graphics_snapshot(item, persistence_timestamp_ns))
        block = bytes(encoded)
        header = _BLOCK_HEADER.pack(
            _BLOCK_MAGIC, self._next_block_sequence, len(items),
            len(block), zlib.crc32(block),
        )
        started = time.perf_counter_ns()
        self._stream.write(header)
        self._stream.write(block)
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._next_block_sequence += 1
        self._last_capture_sequence = previous
        self._last_persistence_timestamp_ns = persistence_timestamp_ns
        return time.perf_counter_ns() - started

    def close(self) -> None:
        if not self._closed:
            try:
                self._stream.flush()
                os.fsync(self._stream.fileno())
            finally:
                self._stream.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def recover_graphics_recording(
    path: str | Path, *, truncate_invalid_tail: bool = True
) -> GraphicsRecordingRecovery:
    recording = Path(path)
    data_size = recording.stat().st_size
    with recording.open("rb") as stream:
        header = stream.read(_FILE_HEADER.size)
        if len(header) != _FILE_HEADER.size:
            raise ValueError("Graphics recording header is incomplete")
        magic, version, page_size, _created, checksum = _FILE_HEADER.unpack(header)
        if magic != _FILE_MAGIC or version not in (1, 2):
            raise ValueError("Unsupported raw Graphics recording format")
        if zlib.crc32(header[:-4]) != checksum:
            raise ValueError("Graphics recording header checksum mismatch")
        if page_size < MIN_GRAPHICS_MAPPING_SIZE:
            raise ValueError("Invalid Graphics page size")
        valid_end = _FILE_HEADER.size
        block_count = snapshot_count = last_block = 0
        last_sequence = None
        last_persistence_timestamp_ns = None
        while True:
            raw_header = stream.read(_BLOCK_HEADER.size)
            if not raw_header:
                break
            if len(raw_header) != _BLOCK_HEADER.size:
                break
            magic_b, block_seq, count, payload_len, crc = _BLOCK_HEADER.unpack(raw_header)
            if magic_b != _BLOCK_MAGIC or block_seq != last_block + 1 or count <= 0:
                break
            block = stream.read(payload_len)
            if len(block) != payload_len or zlib.crc32(block) != crc:
                break
            try:
                records = _decode_graphics_block(
                    block, count, format_version=version
                )
            except ValueError:
                break
            if any(len(item.payload) != page_size for item in records):
                break
            if records and last_sequence is not None and records[0].capture_sequence <= last_sequence:
                break
            if any(records[i].capture_sequence <= records[i - 1].capture_sequence
                   for i in range(1, len(records))):
                break
            if version == 2:
                timestamps = [item.persistence_timestamp_ns for item in records]
                if any(value is None for value in timestamps):
                    break
                if timestamps[0] < (last_persistence_timestamp_ns or 0):
                    break
                if any(timestamps[i] < timestamps[i - 1] for i in range(1, len(timestamps))):
                    break
                last_persistence_timestamp_ns = timestamps[-1]
            last_sequence = records[-1].capture_sequence
            snapshot_count += count
            block_count += 1
            last_block = block_seq
            valid_end = stream.tell()

    truncated = data_size - valid_end
    if truncated and truncate_invalid_tail:
        with recording.open("r+b") as stream:
            stream.truncate(valid_end)
            stream.flush()
            os.fsync(stream.fileno())
    return GraphicsRecordingRecovery(
        block_count, snapshot_count, valid_end, truncated, last_block,
        last_sequence, page_size,
    )


class GraphicsRecorderWorker:
    """Drain the Graphics recorder queue and persist batches off-thread."""

    def __init__(
        self, buffer: AcquisitionRingBuffer[GraphicsSnapshot], path: str | Path,
        *, page_size: int, batch_size: int = 64,
        simulated_write_delay_seconds: float = 0.0,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if simulated_write_delay_seconds < 0:
            raise ValueError("simulated_write_delay_seconds cannot be negative")
        self.buffer = buffer
        self.path = Path(path)
        self.page_size = page_size
        self.batch_size = batch_size
        self.simulated_write_delay_seconds = simulated_write_delay_seconds
        self.metrics = GraphicsRecorderMetrics()
        self.error: str | None = None

    def run(self, stop_event: Event) -> None:
        batch: list[GraphicsSnapshot] = []
        try:
            with RawGraphicsRecordingWriter(self.path, page_size=self.page_size) as writer:
                while not stop_event.is_set() or self.buffer.size > 0:
                    item = self.buffer.try_get()
                    if item is None:
                        if batch:
                            self._persist(writer, batch)
                            batch = []
                        else:
                            stop_event.wait(0.0005)
                        continue
                    batch.append(item)
                    self.metrics.in_flight_snapshot_count = len(batch)
                    self.metrics.in_flight_first_sequence = batch[0].capture_sequence
                    self.metrics.in_flight_last_sequence = batch[-1].capture_sequence
                    if len(batch) >= self.batch_size:
                        self._persist(writer, batch)
                        batch = []
                if batch:
                    self._persist(writer, batch)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.metrics.write_failure_count += 1

    def _persist(self, writer: RawGraphicsRecordingWriter, batch: list[GraphicsSnapshot]) -> None:
        self.metrics.in_flight_snapshot_count = len(batch)
        self.metrics.in_flight_first_sequence = batch[0].capture_sequence
        self.metrics.in_flight_last_sequence = batch[-1].capture_sequence
        try:
            if self.simulated_write_delay_seconds:
                time.sleep(self.simulated_write_delay_seconds)
            duration = writer.write_batch(batch)
        except Exception:
            self.metrics.failed_snapshot_count += len(batch)
            if self.metrics.first_failed_sequence is None:
                self.metrics.first_failed_sequence = batch[0].capture_sequence
            self.metrics.last_failed_sequence = batch[-1].capture_sequence
            raise
        else:
            self.metrics.persisted_snapshot_count += len(batch)
            self.metrics.persisted_block_count += 1
            self.metrics.persisted_bytes += sum(len(item.payload) for item in batch)
            self.metrics.last_persisted_capture_sequence = batch[-1].capture_sequence
            self.metrics.max_block_write_duration_ns = max(
                self.metrics.max_block_write_duration_ns, duration
            )
        finally:
            self.metrics.in_flight_snapshot_count = 0
            self.metrics.in_flight_first_sequence = None
            self.metrics.in_flight_last_sequence = None
