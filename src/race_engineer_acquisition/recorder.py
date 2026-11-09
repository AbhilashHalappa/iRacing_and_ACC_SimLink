"""Checksummed append-only raw Physics recording and independent writer worker.

The acquisition loop never calls this module. A dispatcher transfers snapshots
from the acquisition SPSC queue to a second bounded recorder queue; this module
owns only the recorder queue consumer and disk writes.
"""
from __future__ import annotations

import errno
import os
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Iterable

from .acc_windows import PHYSICS_SIZE
from .models import PhysicsSnapshot
from .ring_buffer import AcquisitionRingBuffer

_FILE_MAGIC = b"ACCPHY01"
_FILE_VERSION = 1
_FILE_HEADER = struct.Struct("<8sIIQI")
_BLOCK_MAGIC = b"PHBK"
_BLOCK_HEADER = struct.Struct("<4sQIII")
_RECORD_HEADER = struct.Struct("<QQQQQI")


@dataclass(frozen=True, slots=True)
class RecordingRecovery:
    valid_block_count: int
    recovered_snapshot_count: int
    valid_bytes: int
    truncated_bytes: int
    last_block_sequence: int
    last_capture_sequence: int | None


@dataclass(slots=True)
class RecorderMetrics:
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
    simulated_write_delay_ns: int = 0
    last_persist_duration_ns: int = 0
    max_persist_duration_ns: int = 0
    simulated_disk_full_triggered: bool = False


def _encode_snapshot(snapshot: PhysicsSnapshot) -> bytes:
    payload = bytes(snapshot.payload)
    header = _RECORD_HEADER.pack(
        snapshot.capture_sequence,
        snapshot.acc_physics_packet_id,
        snapshot.read_start_ns,
        snapshot.read_complete_ns,
        snapshot.capture_timestamp_ns,
        len(payload),
    )
    return header + payload


def _decode_block_payload(payload: bytes, record_count: int) -> list[PhysicsSnapshot]:
    snapshots: list[PhysicsSnapshot] = []
    offset = 0
    for _ in range(record_count):
        if len(payload) - offset < _RECORD_HEADER.size:
            raise ValueError("Truncated snapshot record header")
        seq, packet, started, completed, captured, size = _RECORD_HEADER.unpack_from(payload, offset)
        offset += _RECORD_HEADER.size
        end = offset + size
        if end > len(payload):
            raise ValueError("Truncated snapshot payload")
        snapshots.append(PhysicsSnapshot(seq, packet, started, completed, captured, payload[offset:end]))
        offset = end
    if offset != len(payload):
        raise ValueError("Unexpected bytes after block records")
    return snapshots


class RawPhysicsRecordingWriter:
    """Single-writer append-only file with CRC-protected blocks."""

    def __init__(self, path: str | Path, *, payload_size: int = PHYSICS_SIZE, created_utc_ns: int | None = None) -> None:
        if payload_size <= 0:
            raise ValueError("payload_size must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.payload_size = payload_size
        self.created_utc_ns = time.time_ns() if created_utc_ns is None else created_utc_ns
        self._stream = self.path.open("xb")
        prefix = struct.pack("<8sIIQ", _FILE_MAGIC, _FILE_VERSION, payload_size, self.created_utc_ns)
        self._stream.write(prefix + struct.pack("<I", zlib.crc32(prefix)))
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._next_block_sequence = 1
        self._last_capture_sequence: int | None = None
        self._closed = False

    def write_batch(self, snapshots: Iterable[PhysicsSnapshot]) -> int:
        if self._closed:
            raise RuntimeError("Recording writer is closed")
        items = list(snapshots)
        if not items:
            return 0
        encoded = bytearray()
        previous_sequence = self._last_capture_sequence
        for snapshot in items:
            if previous_sequence is not None and snapshot.capture_sequence <= previous_sequence:
                raise ValueError("Capture sequences must increase strictly across recording blocks")
            if len(snapshot.payload) != self.payload_size:
                raise ValueError(
                    f"Physics payload must be {self.payload_size} bytes; got {len(snapshot.payload)}"
                )
            encoded.extend(_encode_snapshot(snapshot))
            previous_sequence = snapshot.capture_sequence
        payload = bytes(encoded)
        header = _BLOCK_HEADER.pack(
            _BLOCK_MAGIC,
            self._next_block_sequence,
            len(items),
            len(payload),
            zlib.crc32(payload),
        )
        started = time.perf_counter_ns()
        self._stream.write(header)
        self._stream.write(payload)
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._next_block_sequence += 1
        self._last_capture_sequence = previous_sequence
        return time.perf_counter_ns() - started

    def close(self) -> None:
        if not self._closed:
            try:
                self._stream.flush()
                os.fsync(self._stream.fileno())
            finally:
                self._stream.close()
                self._closed = True

    def __enter__(self) -> "RawPhysicsRecordingWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def recover_recording(path: str | Path, *, truncate_invalid_tail: bool = True) -> RecordingRecovery:
    """Scan CRC-valid blocks and optionally truncate an incomplete/corrupt tail."""
    recording = Path(path)
    data_size = recording.stat().st_size
    with recording.open("rb") as stream:
        header = stream.read(_FILE_HEADER.size)
        if len(header) != _FILE_HEADER.size:
            raise ValueError("Recording file header is incomplete")
        magic, version, payload_size, _created_ns, checksum = _FILE_HEADER.unpack(header)
        if magic != _FILE_MAGIC or version != _FILE_VERSION:
            raise ValueError("Unsupported raw Physics recording format")
        if zlib.crc32(header[:-4]) != checksum:
            raise ValueError("Recording file header checksum mismatch")
        if payload_size <= 0:
            raise ValueError("Invalid Physics payload size")

        valid_end = _FILE_HEADER.size
        block_count = 0
        snapshot_count = 0
        last_block = 0
        last_sequence = None
        while True:
            block_header = stream.read(_BLOCK_HEADER.size)
            if not block_header:
                break
            if len(block_header) != _BLOCK_HEADER.size:
                break
            block_magic, block_seq, count, payload_len, checksum = _BLOCK_HEADER.unpack(block_header)
            if block_magic != _BLOCK_MAGIC or block_seq != last_block + 1 or count <= 0:
                break
            block_payload = stream.read(payload_len)
            if len(block_payload) != payload_len or zlib.crc32(block_payload) != checksum:
                break
            try:
                records = _decode_block_payload(block_payload, count)
            except ValueError:
                break
            if any(len(item.payload) != payload_size for item in records):
                break
            if records and last_sequence is not None and records[0].capture_sequence <= last_sequence:
                break
            if any(
                records[index].capture_sequence <= records[index - 1].capture_sequence
                for index in range(1, len(records))
            ):
                break
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
    return RecordingRecovery(block_count, snapshot_count, valid_end, truncated, last_block, last_sequence)


class PhysicsRecorderWorker:
    """Drain a dedicated bounded recorder queue and persist batches off-thread."""

    def __init__(
        self,
        buffer: AcquisitionRingBuffer[PhysicsSnapshot],
        path: str | Path,
        *,
        payload_size: int = 784,
        batch_size: int = 128,
        simulated_write_delay_seconds: float = 0.0,
        simulated_disk_full_after_batches: int | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if simulated_write_delay_seconds < 0:
            raise ValueError("simulated_write_delay_seconds cannot be negative")
        if simulated_disk_full_after_batches is not None and simulated_disk_full_after_batches <= 0:
            raise ValueError("simulated_disk_full_after_batches must be positive")
        self.buffer = buffer
        self.path = Path(path)
        self.payload_size = payload_size
        self.batch_size = batch_size
        self.simulated_write_delay_seconds = simulated_write_delay_seconds
        self.simulated_disk_full_after_batches = simulated_disk_full_after_batches
        self.metrics = RecorderMetrics()
        self.error: str | None = None

    def run(self, stop_event: Event) -> None:
        batch: list[PhysicsSnapshot] = []
        try:
            with RawPhysicsRecordingWriter(self.path, payload_size=self.payload_size) as writer:
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
                    # The batch has left the queue but is not yet on disk. Keep
                    # its sequence range visible to the checkpoint observer.
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

    def _persist(self, writer: RawPhysicsRecordingWriter, batch: list[PhysicsSnapshot]) -> None:
        # Publish the current batch to the checkpoint observer before disk I/O.
        self.metrics.in_flight_snapshot_count = len(batch)
        self.metrics.in_flight_first_sequence = batch[0].capture_sequence
        self.metrics.in_flight_last_sequence = batch[-1].capture_sequence
        persist_started_ns = time.perf_counter_ns()
        try:
            if self.simulated_write_delay_seconds:
                delay_ns = round(self.simulated_write_delay_seconds * 1_000_000_000)
                time.sleep(self.simulated_write_delay_seconds)
                self.metrics.simulated_write_delay_ns += delay_ns
            if (
                self.simulated_disk_full_after_batches is not None
                and self.metrics.persisted_block_count >= self.simulated_disk_full_after_batches
            ):
                # Test-only ENOSPC injection: leave an incomplete next-block
                # prefix, then raise the filesystem-full errno.
                writer._stream.write(b"PHBK" + struct.pack("<Q", self.metrics.persisted_block_count + 1))
                writer._stream.flush()
                self.metrics.simulated_disk_full_triggered = True
                raise OSError(errno.ENOSPC, "No space left on device (simulated)")
            duration = writer.write_batch(batch)
        except Exception:
            self.metrics.failed_snapshot_count += len(batch)
            if self.metrics.first_failed_sequence is None:
                self.metrics.first_failed_sequence = batch[0].capture_sequence
            self.metrics.last_failed_sequence = batch[-1].capture_sequence
            raise
        else:
            # write_batch returns only after flush/fsync has completed.
            self.metrics.persisted_snapshot_count += len(batch)
            self.metrics.persisted_block_count += 1
            self.metrics.persisted_bytes += sum(len(item.payload) for item in batch)
            self.metrics.last_persisted_capture_sequence = batch[-1].capture_sequence
            self.metrics.last_block_write_duration_ns = duration
            self.metrics.max_block_write_duration_ns = max(
                self.metrics.max_block_write_duration_ns, duration
            )
        finally:
            persist_duration = time.perf_counter_ns() - persist_started_ns
            self.metrics.last_persist_duration_ns = persist_duration
            self.metrics.max_persist_duration_ns = max(
                self.metrics.max_persist_duration_ns, persist_duration
            )
            self.metrics.in_flight_snapshot_count = 0
            self.metrics.in_flight_first_sequence = None
            self.metrics.in_flight_last_sequence = None
