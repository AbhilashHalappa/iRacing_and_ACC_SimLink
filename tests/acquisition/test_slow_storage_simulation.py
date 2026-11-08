"""Tests for opt-in slow-storage simulation on the recorder thread."""
import tempfile
import unittest
from pathlib import Path
from threading import Event

from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.recorder import PhysicsRecorderWorker, recover_recording
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class SlowStorageSimulationTests(unittest.TestCase):
    def test_simulated_delay_is_applied_only_to_recorder_and_queue_drains(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 5):
                sample = PhysicsSnapshot(
                    sequence, sequence + 100, sequence * 10, sequence * 10 + 1,
                    sequence * 10 + 1, b"12345678",
                )
                self.assertTrue(queue.try_put(sample))

            worker = PhysicsRecorderWorker(
                queue, Path(directory) / "slow.accraw", payload_size=8,
                batch_size=2, simulated_write_delay_seconds=0.01,
            )
            stop = Event()
            stop.set()
            worker.run(stop)

            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 4)
            self.assertEqual(worker.metrics.simulated_write_delay_ns, 20_000_000)
            self.assertGreaterEqual(worker.metrics.max_persist_duration_ns, 10_000_000)
            self.assertEqual(queue.size, 0)
            self.assertEqual(recover_recording(worker.path).recovered_snapshot_count, 4)

    def test_negative_simulated_delay_is_rejected(self):
        queue = AcquisitionRingBuffer[PhysicsSnapshot](1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                PhysicsRecorderWorker(
                    queue, Path(directory) / "invalid.accraw",
                    simulated_write_delay_seconds=-0.001,
                )


if __name__ == "__main__":
    unittest.main()
