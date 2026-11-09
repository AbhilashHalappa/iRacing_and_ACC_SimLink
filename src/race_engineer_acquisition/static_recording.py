"""Versioned, checksummed raw ACC Static recording and off-thread worker.

Static has no ACC source packet ID or source timestamp. The file stores only
its application-local capture sequence, local read/capture times, a downstream
persistence timestamp, and the complete raw mapping page.
"""
from __future__ import annotations

import os
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Iterable

from .ring_buffer import AcquisitionRingBuffer
from .static import StaticSnapshot

_FILE_MAGIC = b"ACCSTA01"
_FILE_VERSION = 2
_FILE_HEADER = struct.Struct("<8sIIQI")
_BLOCK_MAGIC = b"STBK"
_BLOCK_HEADER = struct.Struct("<4sQIII")
_RECORD_HEADER = struct.Struct("<QQQQQI")


@dataclass(frozen=True, slots=True)
class StaticRecordingSample:
    capture_sequence: int
    read_start_ns: int
    read_complete_ns: int
    capture_timestamp_ns: int
    persistence_timestamp_ns: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class StaticRecordingRecovery:
    valid_block_count: int
    recovered_snapshot_count: int
    valid_bytes: int
    truncated_bytes: int
    last_block_sequence: int
    last_capture_sequence: int | None
    page_size: int


@dataclass(slots=True)
class StaticRecorderMetrics:
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
    last_block_write_duration_ns: int = 0
    max_block_write_duration_ns: int = 0


def _decode_static_block(payload: bytes, record_count: int) -> list[StaticRecordingSample]:
    records: list[StaticRecordingSample] = []
    offset = 0
    for _ in range(record_count):
        if len(payload) - offset < _RECORD_HEADER.size:
            raise ValueError("Truncated Static record header")
        seq, started, completed, captured, persisted, size = _RECORD_HEADER.unpack_from(payload, offset)
        offset += _RECORD_HEADER.size
        end = offset + size
        if end > len(payload):
            raise ValueError("Truncated Static raw page")
        records.append(StaticRecordingSample(
            seq, started, completed, captured, persisted, payload[offset:end]
        ))
        offset = end
    if offset != len(payload):
        raise ValueError("Unexpected bytes after Static block records")
    return records


class RawStaticRecordingWriter:
    """Append-only Static recording writer; one persistence timestamp per batch."""

    def __init__(
        self, path: str | Path, *, page_size: int,
        created_utc_ns: int | None = None, clock_ns=time.perf_counter_ns,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
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

    def write_batch(self, snapshots: Iterable[StaticSnapshot]) -> int:
        if self._closed:
            raise RuntimeError("Static recording writer is closed")
        items = list(snapshots)
        if not items:
            return 0
        previous = self._last_capture_sequence
        for item in items:
            if previous is not None and item.capture_sequence <= previous:
                raise ValueError("Static capture sequences must increase strictly")
            if len(item.payload) != self.page_size:
                raise ValueError(
                    f"Static payload must be {self.page_size} bytes; got {len(item.payload)}"
                )
            if item.source_packet_id is not None or item.source_timestamp_ns is not None:
                raise ValueError("Static source packet ID and source timestamp must remain absent")
            previous = item.capture_sequence

        persistence_timestamp_ns = self._clock_ns()
        if (
            self._last_persistence_timestamp_ns is not None
            and persistence_timestamp_ns < self._last_persistence_timestamp_ns
        ):
            raise RuntimeError("Monotonic persistence clock moved backwards")
        encoded = bytearray()
        for item in items:
            encoded.extend(_RECORD_HEADER.pack(
                item.capture_sequence, item.read_start_ns, item.read_complete_ns,
                item.capture_timestamp_ns, persistence_timestamp_ns, len(item.payload),
            ))
            encoded.extend(item.payload)
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

    def __enter__(self) -> "RawStaticRecordingWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def recover_static_recording(
    path: str | Path, *, truncate_invalid_tail: bool = True
) -> StaticRecordingRecovery:
    recording = Path(path)
    data_size = recording.stat().st_size
    with recording.open("rb") as stream:
        header = stream.read(_FILE_HEADER.size)
        if len(header) != _FILE_HEADER.size:
            raise ValueError("Static recording header is incomplete")
        magic, version, page_size, _created, checksum = _FILE_HEADER.unpack(header)
        if magic != _FILE_MAGIC or version != _FILE_VERSION:
            raise ValueError("Unsupported raw Static recording format")
        if zlib.crc32(header[:-4]) != checksum:
            raise ValueError("Static recording header checksum mismatch")
        if page_size <= 0:
            raise ValueError("Invalid Static page size")

        valid_end = _FILE_HEADER.size
        block_count = snapshot_count = last_block = 0
        last_sequence = None
        last_persistence_timestamp = None
        while True:
            raw_header = stream.read(_BLOCK_HEADER.size)
            if not raw_header:
                break
            if len(raw_header) != _BLOCK_HEADER.size:
                break
            block_magic, block_seq, count, payload_len, crc = _BLOCK_HEADER.unpack(raw_header)
            if block_magic != _BLOCK_MAGIC or block_seq != last_block + 1 or count <= 0:
                break
            block = stream.read(payload_len)
            if len(block) != payload_len or zlib.crc32(block) != crc:
                break
            try:
                records = _decode_static_block(block, count)
            except ValueError:
                break
            if any(len(item.payload) != page_size for item in records):
                break
            if records and last_sequence is not None and records[0].capture_sequence <= last_sequence:
                break
            if any(records[i].capture_sequence <= records[i - 1].capture_sequence
                   for i in range(1, len(records))):
                break
            timestamps = [item.persistence_timestamp_ns for item in records]
            if any(value <= 0 for value in timestamps):
                break
            if timestamps[0] < (last_persistence_timestamp or 0):
                break
            if any(timestamps[i] < timestamps[i - 1] for i in range(1, len(timestamps))):
                break
            last_persistence_timestamp = timestamps[-1]
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
    return StaticRecordingRecovery(
        block_count, snapshot_count, valid_end, truncated, last_block,
        last_sequence, page_size,
    )


class StaticRecorderWorker:
    """Drain a bounded recorder queue and persist Static pages off acquisition."""

    def __init__(
        self, buffer: AcquisitionRingBuffer[StaticSnapshot], path: str | Path,
        *, page_size: int, batch_size: int = 16,
        simulated_write_failure_after_batches: int | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if simulated_write_failure_after_batches is not None and simulated_write_failure_after_batches <= 0:
            raise ValueError("simulated failure batch count must be positive")
        self.buffer = buffer
        self.path = Path(path)
        self.page_size = page_size
        self.batch_size = batch_size
        self.simulated_write_failure_after_batches = simulated_write_failure_after_batches
        self.metrics = StaticRecorderMetrics()
        self.error: str | None = None

    def run(self, stop_event: Event) -> None:
        batch: list[StaticSnapshot] = []
        try:
            with RawStaticRecordingWriter(self.path, page_size=self.page_size) as writer:
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

    def _persist(self, writer: RawStaticRecordingWriter, batch: list[StaticSnapshot]) -> None:
        self.metrics.in_flight_snapshot_count = len(batch)
        self.metrics.in_flight_first_sequence = batch[0].capture_sequence
        self.metrics.in_flight_last_sequence = batch[-1].capture_sequence
        try:
            if (
                self.simulated_write_failure_after_batches is not None
                and self.metrics.persisted_block_count >= self.simulated_write_failure_after_batches
            ):
                writer._stream.write(b"STBK" + struct.pack("<Q", self.metrics.persisted_block_count + 1))
                writer._stream.flush()
                raise OSError("Simulated Static recording write failure")
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
            self.metrics.last_block_write_duration_ns = duration
            self.metrics.max_block_write_duration_ns = max(
                self.metrics.max_block_write_duration_ns, duration
            )
        finally:
            self.metrics.in_flight_snapshot_count = 0
            self.metrics.in_flight_first_sequence = None
            self.metrics.in_flight_last_sequence = None
