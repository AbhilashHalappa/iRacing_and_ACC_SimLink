import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread

from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.recorder import (
    PhysicsRecorderWorker,
    RawPhysicsRecordingWriter,
    recover_recording,
)
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def snapshot(sequence: int, payload_size: int = 8) -> PhysicsSnapshot:
    return PhysicsSnapshot(sequence, sequence + 100, sequence * 10, sequence * 10 + 1,
                           sequence * 10 + 1, bytes([sequence % 256]) * payload_size)


class RecorderTests(unittest.TestCase):
    def test_writer_persists_multiple_checksummed_blocks_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8, created_utc_ns=123) as writer:
                writer.write_batch([snapshot(1), snapshot(2)])
                writer.write_batch([snapshot(3)])
            report = recover_recording(path, truncate_invalid_tail=False)
            self.assertEqual(report.valid_block_count, 2)
            self.assertEqual(report.recovered_snapshot_count, 3)
            self.assertEqual(report.last_capture_sequence, 3)
            self.assertEqual(report.truncated_bytes, 0)

    def test_recovery_truncates_incomplete_tail_and_keeps_complete_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8) as writer:
                writer.write_batch([snapshot(1), snapshot(2)])
            valid_size = path.stat().st_size
            with path.open("ab") as stream:
                stream.write(b"PHBK" + bytes((1, 2)))
            report = recover_recording(path)
            self.assertEqual(report.recovered_snapshot_count, 2)
            self.assertEqual(report.truncated_bytes, 6)
            self.assertEqual(path.stat().st_size, valid_size)

    def test_recovery_discards_block_with_corrupt_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8) as writer:
                writer.write_batch([snapshot(1)])
            original = path.read_bytes()
            damaged = bytearray(original)
            damaged[-1] ^= 0xFF
            path.write_bytes(damaged)
            report = recover_recording(path)
            self.assertEqual(report.valid_block_count, 0)
            self.assertEqual(report.recovered_snapshot_count, 0)
            self.assertEqual(report.truncated_bytes, len(original) - 28)
            self.assertEqual(path.stat().st_size, 28)

    def test_writer_rejects_non_increasing_capture_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8) as writer:
                writer.write_batch([snapshot(2)])
                with self.assertRaises(ValueError):
                    writer.write_batch([snapshot(2)])

    def test_writer_rejects_wrong_payload_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8) as writer:
                with self.assertRaises(ValueError):
                    writer.write_batch([snapshot(1, payload_size=7)])

    def test_worker_drains_queue_in_batches_and_persists_every_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 6):
                self.assertTrue(queue.try_put(snapshot(sequence)))
            worker = PhysicsRecorderWorker(queue, Path(directory) / "worker.accraw",
                                           payload_size=8, batch_size=2)
            stop = Event()
            thread = Thread(target=worker.run, args=(stop,))
            thread.start()
            stop.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 5)
            self.assertEqual(worker.metrics.persisted_block_count, 3)
            report = recover_recording(worker.path)
            self.assertEqual(report.recovered_snapshot_count, 5)
            self.assertEqual(queue.size, 0)


if __name__ == "__main__":
    unittest.main()
