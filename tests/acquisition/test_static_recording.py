from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Event

from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import StaticSnapshot
from race_engineer_acquisition.static_recording import (
    RawStaticRecordingWriter, StaticRecorderWorker, _decode_static_block,
    recover_static_recording, _FILE_HEADER, _BLOCK_HEADER,
)


def sample(sequence: int, payload: bytes) -> StaticSnapshot:
    return StaticSnapshot(
        sequence, None, None, sequence * 10, sequence * 10 + 1,
        sequence * 10 + 1, payload,
    )


class StaticRecordingTests(unittest.TestCase):
    def test_writer_preserves_complete_page_and_timestamp_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.accraw"
            ticks = iter((100, 200))
            with RawStaticRecordingWriter(
                path, page_size=8, created_utc_ns=1, clock_ns=lambda: next(ticks)
            ) as writer:
                writer.write_batch([sample(1, b"12345678")])
                writer.write_batch([sample(2, b"abcdefgh")])
            data = path.read_bytes()
            offset = _FILE_HEADER.size
            decoded = []
            for expected_timestamp in (100, 200):
                _, _, count, length, _ = _BLOCK_HEADER.unpack_from(data, offset)
                block_start = offset + _BLOCK_HEADER.size
                records = _decode_static_block(data[block_start:block_start + length], count)
                self.assertEqual([r.persistence_timestamp_ns for r in records], [expected_timestamp])
                decoded.extend(records)
                offset = block_start + length
            self.assertEqual([r.capture_sequence for r in decoded], [1, 2])
            self.assertEqual([r.payload for r in decoded], [b"12345678", b"abcdefgh"])
            self.assertEqual([r.read_start_ns for r in decoded], [10, 20])
            self.assertEqual(recover_static_recording(path).recovered_snapshot_count, 2)

    def test_worker_drains_queue_and_accounts_persisted_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.accraw"
            queue = AcquisitionRingBuffer[StaticSnapshot](4)
            queue.try_put(sample(1, b"12345678"))
            queue.try_put(sample(2, b"abcdefgh"))
            worker = StaticRecorderWorker(queue, path, page_size=8, batch_size=2)
            worker.run(Event())
            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 2)
            self.assertEqual(queue.size, 0)
            self.assertEqual(recover_static_recording(path).recovered_snapshot_count, 2)

    def test_bounded_recorder_queue_rejects_without_overwriting_and_persists_accepted_page(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.accraw"
            queue = AcquisitionRingBuffer[StaticSnapshot](1)
            self.assertTrue(queue.try_put(sample(1, b"12345678")))
            self.assertFalse(queue.try_put(sample(2, b"abcdefgh")))
            self.assertEqual(queue.total_rejection_count, 1)
            worker = StaticRecorderWorker(queue, path, page_size=8)
            worker.run(Event())
            self.assertEqual(worker.metrics.persisted_snapshot_count, 1)
            self.assertEqual(recover_static_recording(path).recovered_snapshot_count, 1)

    def test_worker_reports_write_failure_and_recovery_keeps_valid_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.accraw"
            queue = AcquisitionRingBuffer[StaticSnapshot](4)
            for i in range(1, 4):
                queue.try_put(sample(i, bytes([i]) * 8))
            worker = StaticRecorderWorker(
                queue, path, page_size=8, batch_size=1,
                simulated_write_failure_after_batches=1,
            )
            worker.run(Event())
            self.assertIsNotNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 1)
            self.assertEqual(worker.metrics.failed_snapshot_count, 1)
            self.assertEqual(worker.metrics.write_failure_count, 1)
            recovered = recover_static_recording(path)
            self.assertEqual(recovered.recovered_snapshot_count, 1)
            self.assertGreater(recovered.truncated_bytes, 0)

    def test_writer_rejects_fabricated_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.accraw"
            bad = StaticSnapshot(1, 7, None, 10, 11, 11, b"12345678")
            with RawStaticRecordingWriter(path, page_size=8, created_utc_ns=1) as writer:
                with self.assertRaises(ValueError):
                    writer.write_batch([bad])


if __name__ == "__main__":
    unittest.main()
