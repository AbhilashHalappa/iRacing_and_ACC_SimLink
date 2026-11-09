import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread

from race_engineer_acquisition.graphics import (
    GraphicsRecorderWorker, GraphicsSnapshot, RawGraphicsRecordingWriter,
    recover_graphics_recording,
)
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


def snapshot(sequence, page_size=4096):
    payload = bytes((sequence + i) % 256 for i in range(page_size))
    return GraphicsSnapshot(
        sequence, 1000 + sequence, sequence * 10, sequence * 10 + 5,
        sequence * 10 + 5, payload,
    )


class GraphicsRecorderTests(unittest.TestCase):
    def test_writer_and_recovery_preserve_full_mapping_page_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.gfxraw"
            with RawGraphicsRecordingWriter(path, page_size=4096, created_utc_ns=1) as writer:
                writer.write_batch([snapshot(1), snapshot(2)])
                writer.write_batch([snapshot(3)])
            report = recover_graphics_recording(path, truncate_invalid_tail=False)
            self.assertEqual(report.page_size, 4096)
            self.assertEqual(report.valid_block_count, 2)
            self.assertEqual(report.recovered_snapshot_count, 3)
            self.assertEqual(report.truncated_bytes, 0)

    def test_writer_rejects_payload_size_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.gfxraw"
            with RawGraphicsRecordingWriter(path, page_size=4096) as writer:
                with self.assertRaises(ValueError):
                    writer.write_batch([snapshot(1, page_size=1588)])

    def test_writer_rejects_non_increasing_capture_sequences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.gfxraw"
            with RawGraphicsRecordingWriter(path, page_size=32) as writer:
                writer.write_batch([snapshot(2, page_size=32)])
                with self.assertRaises(ValueError):
                    writer.write_batch([snapshot(2, page_size=32)])

    def test_recovery_detects_and_truncates_corrupt_block(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.gfxraw"
            with RawGraphicsRecordingWriter(path, page_size=32) as writer:
                writer.write_batch([snapshot(1, page_size=32)])
            damaged = bytearray(path.read_bytes())
            damaged[-1] ^= 0xFF
            path.write_bytes(damaged)
            report = recover_graphics_recording(path, truncate_invalid_tail=False)
            self.assertEqual(report.recovered_snapshot_count, 0)
            self.assertGreater(report.truncated_bytes, 0)
            repaired = recover_graphics_recording(path, truncate_invalid_tail=True)
            self.assertEqual(repaired.truncated_bytes, report.truncated_bytes)
            self.assertEqual(path.stat().st_size, repaired.valid_bytes)

    def test_worker_drains_queue_and_persists_all_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer(8)
            for sequence in range(1, 6):
                self.assertTrue(queue.try_put(snapshot(sequence, page_size=4096)))
            worker = GraphicsRecorderWorker(
                queue, Path(directory) / "worker.gfxraw",
                page_size=4096, batch_size=2,
            )
            stop = Event()
            thread = Thread(target=worker.run, args=(stop,))
            thread.start()
            stop.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 5)
            self.assertEqual(worker.metrics.persisted_block_count, 3)
            report = recover_graphics_recording(worker.path)
            self.assertEqual(report.recovered_snapshot_count, 5)
            self.assertEqual(report.page_size, 4096)
            self.assertEqual(queue.size, 0)


if __name__ == "__main__":
    unittest.main()
