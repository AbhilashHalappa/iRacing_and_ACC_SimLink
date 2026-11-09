import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE
from race_engineer_acquisition.graphics import (
    GraphicsSnapshot,
    RawGraphicsRecordingWriter,
    _decode_graphics_block,
    recover_graphics_recording,
)
from race_engineer_acquisition.inspection import inspect_recording, read_raw_payloads
from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.recorder import (
    RawPhysicsRecordingWriter,
    _decode_block_payload,
    recover_recording,
)


_FILE_HEADER = struct.Struct("<8sIIQI")
_BLOCK_HEADER = struct.Struct("<4sQIII")
_PHYSICS_V1_RECORD = struct.Struct("<QQQQQI")
_GRAPHICS_V1_RECORD = struct.Struct("<QQQQQI")
_PHYSICS_V2_RECORD = struct.Struct("<QQQQQQI")
_GRAPHICS_V2_RECORD = struct.Struct("<QQQQQQI")


def _write_v1_recording(path: Path, *, magic: bytes, block_magic: bytes,
                        page: bytes, packet_id: int) -> None:
    prefix = struct.pack("<8sIIQ", magic, 1, len(page), 123456)
    file_header = prefix + struct.pack("<I", zlib.crc32(prefix))
    record_header = _PHYSICS_V1_RECORD.pack(1, packet_id, 100, 110, 110, len(page))
    record = record_header + page
    block_header = _BLOCK_HEADER.pack(
        block_magic, 1, 1, len(record), zlib.crc32(record)
    )
    path.write_bytes(file_header + block_header + record)


class PersistenceTimestampTests(unittest.TestCase):
    def test_physics_writer_assigns_one_monotonic_timestamp_per_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "physics.accraw"
            ticks = iter((100, 200))
            snapshots = [
                PhysicsSnapshot(i, 100 + i, i * 10, i * 10 + 1,
                                i * 10 + 1, bytes([i]) * PHYSICS_SIZE)
                for i in (1, 2, 3)
            ]
            self.assertIsNone(snapshots[0].persistence_timestamp_ns)
            with RawPhysicsRecordingWriter(
                path, payload_size=PHYSICS_SIZE, created_utc_ns=1, clock_ns=lambda: next(ticks)
            ) as writer:
                writer.write_batch(snapshots[:2])
                writer.write_batch(snapshots[2:])

            data = path.read_bytes()
            offset = _FILE_HEADER.size
            decoded = []
            for block_index, (expected_timestamp, expected_count) in enumerate(((100, 2), (200, 1)), start=1):
                block_magic, block_seq, count, payload_size, crc = _BLOCK_HEADER.unpack_from(data, offset)
                self.assertEqual(block_magic, b"PHBK")
                self.assertEqual(block_seq, block_index)
                self.assertEqual(count, expected_count)
                start = offset + _BLOCK_HEADER.size
                payload = data[start:start + payload_size]
                self.assertEqual(zlib.crc32(payload), crc)
                records = _decode_block_payload(payload, count, format_version=2)
                self.assertEqual(
                    [item.persistence_timestamp_ns for item in records],
                    [expected_timestamp] * expected_count,
                )
                decoded.extend(records)
                offset = start + payload_size
            self.assertEqual([item.capture_sequence for item in decoded], [1, 2, 3])
            self.assertEqual([item.capture_timestamp_ns for item in decoded], [11, 21, 31])
            self.assertEqual(recover_recording(path).recovered_snapshot_count, 3)
            size, samples = read_raw_payloads(path)
            self.assertEqual(size, PHYSICS_SIZE)
            self.assertEqual([sequence for sequence, _ in samples], [1, 2, 3])
            self.assertEqual(inspect_recording(path)["format_version"], 2)

    def test_graphics_writer_assigns_one_monotonic_timestamp_per_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graphics.accraw"
            ticks = iter((300, 400))
            snapshots = [
                GraphicsSnapshot(i, 200 + i, i * 10, i * 10 + 1,
                                 i * 10 + 1, bytes([i]) * 8)
                for i in (1, 2, 3)
            ]
            self.assertIsNone(snapshots[0].persistence_timestamp_ns)
            with RawGraphicsRecordingWriter(
                path, page_size=8, created_utc_ns=1, clock_ns=lambda: next(ticks)
            ) as writer:
                writer.write_batch(snapshots[:2])
                writer.write_batch(snapshots[2:])

            data = path.read_bytes()
            offset = _FILE_HEADER.size
            decoded = []
            for block_index, (expected_timestamp, expected_count) in enumerate(((300, 2), (400, 1)), start=1):
                block_magic, block_seq, count, payload_size, crc = _BLOCK_HEADER.unpack_from(data, offset)
                self.assertEqual(block_magic, b"GFXB")
                self.assertEqual(block_seq, block_index)
                self.assertEqual(count, expected_count)
                start = offset + _BLOCK_HEADER.size
                payload = data[start:start + payload_size]
                self.assertEqual(zlib.crc32(payload), crc)
                records = _decode_graphics_block(payload, count, format_version=2)
                self.assertEqual(
                    [item.persistence_timestamp_ns for item in records],
                    [expected_timestamp] * expected_count,
                )
                decoded.extend(records)
                offset = start + payload_size
            self.assertEqual([item.capture_sequence for item in decoded], [1, 2, 3])
            self.assertEqual(recover_graphics_recording(path).recovered_snapshot_count, 3)

    def test_legacy_physics_v1_recording_remains_readable_without_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy_physics.accraw"
            _write_v1_recording(
                path, magic=b"ACCPHY01", block_magic=b"PHBK",
                page=bytes(PHYSICS_SIZE), packet_id=77,
            )
            recovered = recover_recording(path)
            self.assertEqual(recovered.recovered_snapshot_count, 1)
            raw = path.read_bytes()
            payload = raw[_FILE_HEADER.size + _BLOCK_HEADER.size:]
            decoded = _decode_block_payload(payload, 1, format_version=1)
            self.assertIsNone(decoded[0].persistence_timestamp_ns)
            size, samples = read_raw_payloads(path)
            self.assertEqual(size, PHYSICS_SIZE)
            self.assertEqual(samples, [(1, bytes(PHYSICS_SIZE))])

    def test_legacy_graphics_v1_recording_remains_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy_graphics.accraw"
            _write_v1_recording(
                path, magic=b"ACCGFX01", block_magic=b"GFXB",
                page=b"abcdefgh", packet_id=88,
            )
            recovered = recover_graphics_recording(path)
            self.assertEqual(recovered.recovered_snapshot_count, 1)
            raw = path.read_bytes()
            payload = raw[_FILE_HEADER.size + _BLOCK_HEADER.size:]
            decoded = _decode_graphics_block(payload, 1, format_version=1)
            self.assertIsNone(decoded[0].persistence_timestamp_ns)


if __name__ == "__main__":
    unittest.main()
