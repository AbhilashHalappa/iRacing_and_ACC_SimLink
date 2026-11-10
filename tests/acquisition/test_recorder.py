import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE
from race_engineer_acquisition.inspection import inspect_recording
from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.fanout import FanOutDispatcher
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
    def test_default_writer_uses_current_800_byte_physics_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "current.accraw"
            item = PhysicsSnapshot(1, 101, 10, 11, 11, bytes(PHYSICS_SIZE))
            with RawPhysicsRecordingWriter(path) as writer:
                self.assertEqual(writer.payload_size, 800)
                writer.write_batch([item])
            self.assertEqual(recover_recording(path).recovered_snapshot_count, 1)
            report = inspect_recording(path)
            self.assertEqual(report["layout"], "current-800-byte")

    def test_default_worker_records_800_byte_acquisition_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.accraw"
            queue = AcquisitionRingBuffer[PhysicsSnapshot](4)
            for sequence in range(1, 4):
                item = PhysicsSnapshot(
                    sequence, 100 + sequence, sequence * 10, sequence * 10 + 1,
                    sequence * 10 + 1, bytes([sequence]) * PHYSICS_SIZE,
                )
                self.assertEqual(len(item.payload), 800)
                self.assertTrue(queue.try_put(item))

            worker = PhysicsRecorderWorker(queue, path, batch_size=2)
            stop = Event()
            stop.set()
            worker.run(stop)

            self.assertIsNone(worker.error)
            self.assertEqual(worker.payload_size, 800)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 3)
            self.assertEqual(queue.size, 0)
            recovered = recover_recording(path)
            self.assertEqual(recovered.recovered_snapshot_count, 3)
            report = inspect_recording(path)
            self.assertEqual(report["layout"], "current-800-byte")

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

    def test_recovery_after_interrupted_second_block_keeps_first_complete_block(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=8) as writer:
                writer.write_batch([snapshot(1)])
                writer.write_batch([snapshot(2)])
            complete_size = path.stat().st_size
            # Simulate process/power loss while the second block is being appended.
            with path.open("r+b") as stream:
                stream.truncate(complete_size - 5)
            report = recover_recording(path)
            self.assertEqual(report.valid_block_count, 1)
            self.assertEqual(report.recovered_snapshot_count, 1)
            self.assertEqual(report.last_capture_sequence, 1)
            self.assertEqual(report.truncated_bytes, complete_size - 5 - report.valid_bytes)
            self.assertEqual(path.stat().st_size, report.valid_bytes)

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

    def test_slow_storage_worker_still_drains_all_queued_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 6):
                self.assertTrue(queue.try_put(snapshot(sequence)))
            worker = PhysicsRecorderWorker(queue, Path(directory) / "slow.accraw",
                                           payload_size=8, batch_size=2)
            original_write_batch = RawPhysicsRecordingWriter.write_batch

            def delayed_write(writer, batch):
                time.sleep(0.02)
                return original_write_batch(writer, batch)

            stop = Event()
            stop.set()
            started = time.perf_counter()
            with patch.object(RawPhysicsRecordingWriter, "write_batch", delayed_write):
                worker.run(stop)
            elapsed = time.perf_counter() - started

            self.assertGreaterEqual(elapsed, 0.05)
            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 5)
            self.assertEqual(queue.size, 0)
            self.assertEqual(recover_recording(worker.path).recovered_snapshot_count, 5)

    def test_disk_write_failure_accounts_failed_batch_and_leaves_remaining_queue_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "disk_failure.accraw"
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 4):
                self.assertTrue(queue.try_put(snapshot(sequence)))
            worker = PhysicsRecorderWorker(queue, path, payload_size=8, batch_size=2)

            def fail_during_block_write(writer, batch):
                # Leave a deliberately incomplete block, as a full disk or abrupt
                # storage error can do after the append has started.
                writer._stream.write(b"PHBK" + bytes((1, 2)))
                writer._stream.flush()
                raise OSError("simulated disk full")

            stop = Event()
            stop.set()
            with patch.object(RawPhysicsRecordingWriter, "write_batch", fail_during_block_write):
                worker.run(stop)

            self.assertIn("simulated disk full", worker.error)
            self.assertEqual(worker.metrics.write_failure_count, 1)
            self.assertEqual(worker.metrics.failed_snapshot_count, 2)
            self.assertEqual(worker.metrics.first_failed_sequence, 1)
            self.assertEqual(worker.metrics.last_failed_sequence, 2)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 0)
            self.assertEqual(queue.size, 1)
            recovery = recover_recording(path)
            self.assertEqual(recovery.recovered_snapshot_count, 0)
            self.assertGreater(recovery.truncated_bytes, 0)
            self.assertEqual(path.stat().st_size, recovery.valid_bytes)



    def test_simulated_enospc_preserves_complete_blocks_and_accounts_failed_and_queued_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "simulated_enospc.accraw"
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 6):
                self.assertTrue(queue.try_put(snapshot(sequence)))
            worker = PhysicsRecorderWorker(
                queue, path, payload_size=8, batch_size=2,
                simulated_disk_full_after_batches=1,
            )
            stop = Event()
            stop.set()
            worker.run(stop)

            self.assertTrue(worker.metrics.simulated_disk_full_triggered)
            self.assertIn("No space left on device (simulated)", worker.error)
            self.assertEqual(worker.metrics.write_failure_count, 1)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 2)
            self.assertEqual(worker.metrics.failed_snapshot_count, 2)
            self.assertEqual(worker.metrics.first_failed_sequence, 3)
            self.assertEqual(worker.metrics.last_failed_sequence, 4)
            self.assertEqual(queue.size, 1)

            recovery = recover_recording(path, truncate_invalid_tail=False)
            self.assertEqual(recovery.valid_block_count, 1)
            self.assertEqual(recovery.recovered_snapshot_count, 2)
            self.assertEqual(recovery.last_capture_sequence, 2)
            self.assertGreater(recovery.truncated_bytes, 0)

            repaired = recover_recording(path, truncate_invalid_tail=True)
            self.assertEqual(repaired.recovered_snapshot_count, 2)
            self.assertGreater(repaired.truncated_bytes, 0)
            clean = recover_recording(path, truncate_invalid_tail=False)
            self.assertEqual(clean.truncated_bytes, 0)
            self.assertEqual(clean.recovered_snapshot_count, 2)

    def test_simulated_enospc_batch_threshold_must_be_positive(self):
        queue = AcquisitionRingBuffer[PhysicsSnapshot](1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                PhysicsRecorderWorker(
                    queue, Path(directory) / "invalid.accraw",
                    simulated_disk_full_after_batches=0,
                )

    def test_worker_publishes_in_flight_batch_until_fsync_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer[PhysicsSnapshot](4)
            self.assertTrue(queue.try_put(snapshot(1)))
            worker = PhysicsRecorderWorker(
                queue, Path(directory) / "in_flight.accraw",
                payload_size=8, batch_size=1,
            )
            write_entered = Event()
            release_write = Event()
            original_write_batch = RawPhysicsRecordingWriter.write_batch

            def blocked_write(writer, batch):
                write_entered.set()
                if not release_write.wait(timeout=3):
                    raise TimeoutError("test did not release the simulated disk write")
                return original_write_batch(writer, batch)

            stop = Event()
            thread = Thread(target=worker.run, args=(stop,))
            with patch.object(RawPhysicsRecordingWriter, "write_batch", blocked_write):
                thread.start()
                self.assertTrue(write_entered.wait(timeout=2))
                self.assertEqual(worker.metrics.in_flight_snapshot_count, 1)
                self.assertEqual(worker.metrics.in_flight_first_sequence, 1)
                self.assertEqual(worker.metrics.in_flight_last_sequence, 1)
                self.assertEqual(worker.metrics.persisted_snapshot_count, 0)
                release_write.set()
                stop.set()
                thread.join(timeout=3)

            self.assertFalse(thread.is_alive())
            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.in_flight_snapshot_count, 0)
            self.assertEqual(worker.metrics.last_persisted_capture_sequence, 1)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 1)

    def test_one_time_initial_recorder_stall_is_measured_and_then_drains(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = AcquisitionRingBuffer[PhysicsSnapshot](8)
            for sequence in range(1, 5):
                self.assertTrue(queue.try_put(snapshot(sequence)))
            worker = PhysicsRecorderWorker(
                queue, Path(directory) / "initial_stall.accraw",
                payload_size=8, batch_size=2,
                simulated_initial_stall_seconds=0.05,
            )
            stop = Event()
            stop.set()
            worker.run(stop)

            self.assertIsNone(worker.error)
            self.assertEqual(worker.metrics.persisted_snapshot_count, 4)
            self.assertGreaterEqual(worker.metrics.simulated_initial_stall_ns, 50_000_000)
            self.assertIsNotNone(worker.metrics.simulated_initial_stall_started_ns)
            self.assertIsNotNone(worker.metrics.simulated_initial_stall_finished_ns)
            self.assertEqual(queue.size, 0)
            self.assertEqual(recover_recording(worker.path).recovered_snapshot_count, 4)

    def test_initial_recorder_stall_must_be_non_negative(self):
        queue = AcquisitionRingBuffer[PhysicsSnapshot](1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                PhysicsRecorderWorker(
                    queue, Path(directory) / "invalid_initial_stall.accraw",
                    simulated_initial_stall_seconds=-0.01,
                )

    def test_fanout_recorder_acknowledges_only_successfully_persisted_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            source = AcquisitionRingBuffer[PhysicsSnapshot](4)
            dispatcher = FanOutDispatcher(source)
            recorder_queue = dispatcher.register("recorder", 4, required=True)
            for sequence in range(1, 4):
                self.assertTrue(source.try_put(snapshot(sequence)))
            dispatch_stop = Event()
            dispatch_stop.set()
            dispatcher.run(dispatch_stop)

            worker = PhysicsRecorderWorker(
                recorder_queue, Path(directory) / "fanout.accraw",
                payload_size=8, batch_size=2,
            )
            recorder_stop = Event()
            recorder_stop.set()
            worker.run(recorder_stop)

            metrics = recorder_queue.metrics
            self.assertIsNone(worker.error)
            self.assertEqual(metrics.offered_count, 3)
            self.assertEqual(metrics.dispatched_count, 3)
            self.assertEqual(metrics.processed_count, 3)
            self.assertEqual(metrics.failed_count, 0)
            self.assertEqual(metrics.pending_count, 0)
            self.assertEqual(recover_recording(worker.path).recovered_snapshot_count, 3)

    def test_fanout_recorder_write_failure_marks_batch_failed_and_drains_queue_accountably(self):
        with tempfile.TemporaryDirectory() as directory:
            source = AcquisitionRingBuffer[PhysicsSnapshot](4)
            dispatcher = FanOutDispatcher(source)
            recorder_queue = dispatcher.register("recorder", 4, required=True)
            for sequence in range(1, 4):
                self.assertTrue(source.try_put(snapshot(sequence)))
            dispatch_stop = Event()
            dispatch_stop.set()
            dispatcher.run(dispatch_stop)

            worker = PhysicsRecorderWorker(
                recorder_queue, Path(directory) / "fanout_failure.accraw",
                payload_size=8, batch_size=2, simulated_disk_full_after_batches=1,
            )
            recorder_stop = Event()
            recorder_stop.set()
            worker.run(recorder_stop)

            metrics = recorder_queue.metrics
            self.assertIn("No space left on device (simulated)", worker.error)
            self.assertEqual(metrics.offered_count, 3)
            self.assertEqual(metrics.dispatched_count, 3)
            self.assertEqual(metrics.processed_count, 2)
            self.assertEqual(metrics.failed_count, 1)
            self.assertEqual(metrics.pending_count, 0)
            self.assertEqual(metrics.dispatched_count, metrics.processed_count + metrics.failed_count + metrics.pending_count)
            self.assertEqual(recover_recording(worker.path).recovered_snapshot_count, 2)


if __name__ == "__main__":
    unittest.main()
