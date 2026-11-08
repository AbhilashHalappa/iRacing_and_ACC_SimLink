import unittest

from race_engineer_acquisition.acquirer import PhysicsAcquirer
from race_engineer_acquisition.models import RawPhysicsRead
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class FakeSource:
    def __init__(self, reads):
        self.reads = iter(reads)

    def read_physics(self):
        return next(self.reads)


class FakeClock:
    def __init__(self):
        self.value = 100

    def __call__(self):
        value = self.value
        self.value += 10
        return value


class AcquirerTests(unittest.TestCase):
    def test_capture_assigns_sequence_and_timestamps(self) -> None:
        buffer = AcquisitionRingBuffer(4)
        acquirer = PhysicsAcquirer(
            FakeSource([RawPhysicsRead(42, 42, b"physics")]),
            buffer,
            clock_ns=FakeClock(),
        )
        snapshot = acquirer.capture_once()
        self.assertEqual(snapshot.capture_sequence, 1)
        self.assertEqual(snapshot.acc_physics_packet_id, 42)
        self.assertEqual(snapshot.read_start_ns, 110)
        self.assertEqual(snapshot.read_complete_ns, 120)
        self.assertEqual(snapshot.payload, b"physics")
        self.assertEqual(acquirer.metrics.capture_count, 1)
        self.assertEqual(buffer.try_get(), snapshot)

    def test_inconsistent_snapshot_retries_then_succeeds(self) -> None:
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(10, 11, b"torn"),
            RawPhysicsRead(11, 11, b"good"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, clock_ns=FakeClock())
        snapshot = acquirer.capture_once()
        self.assertEqual(snapshot.payload, b"good")
        self.assertEqual(acquirer.metrics.inconsistent_snapshot_count, 1)
        self.assertEqual(acquirer.metrics.consistency_retry_count, 1)
        self.assertEqual(acquirer.metrics.read_attempt_count, 2)
        self.assertEqual(acquirer.metrics.total_read_attempt_duration_ns, 20)
        self.assertEqual(acquirer.metrics.max_read_attempt_duration_ns, 10)

    def test_packet_id_gaps_are_counted_separately(self) -> None:
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(100, 100, b"a"),
            RawPhysicsRead(104, 104, b"b"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, clock_ns=FakeClock())
        acquirer.capture_once()
        acquirer.capture_once()
        self.assertEqual(acquirer.metrics.source_packet_gap_count, 3)
        self.assertEqual(acquirer.metrics.buffer_rejection_count, 0)

    def test_failed_consistency_attempts_do_not_publish_snapshot(self) -> None:
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(1, 2, b"bad-1"),
            RawPhysicsRead(2, 3, b"bad-2"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, max_consistency_attempts=2)
        self.assertIsNone(acquirer.capture_once())
        self.assertEqual(buffer.size, 0)
        self.assertEqual(acquirer.metrics.capture_count, 0)
        self.assertEqual(acquirer.metrics.inconsistent_snapshot_count, 2)

    def test_duplicate_packet_id_is_not_published_twice(self):
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(7, 7, b"first"),
            RawPhysicsRead(7, 7, b"duplicate"),
            RawPhysicsRead(8, 8, b"next"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, clock_ns=FakeClock())
        first = acquirer.capture_once()
        duplicate = acquirer.capture_once()
        next_packet = acquirer.capture_once()
        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertEqual(next_packet.capture_sequence, 2)
        self.assertEqual(acquirer.metrics.capture_count, 2)
        self.assertEqual(acquirer.metrics.duplicate_packet_observation_count, 1)
        self.assertEqual(buffer.try_get().payload, b"first")
        self.assertEqual(buffer.try_get().payload, b"next")

    def test_packet_id_regression_is_flagged_not_guessed_as_wrap(self):
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(100, 100, b"before"),
            RawPhysicsRead(2, 2, b"after"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, clock_ns=FakeClock())
        acquirer.capture_once()
        snapshot = acquirer.capture_once()
        self.assertEqual(snapshot.acc_physics_packet_id, 2)
        self.assertEqual(acquirer.metrics.packet_id_regression_count, 1)
        self.assertEqual(acquirer.metrics.source_packet_gap_count, 0)

    def test_poll_interval_is_measured_between_capture_cycles(self) -> None:
        buffer = AcquisitionRingBuffer(4)
        source = FakeSource([
            RawPhysicsRead(20, 20, b"first"),
            RawPhysicsRead(21, 21, b"second"),
        ])
        acquirer = PhysicsAcquirer(source, buffer, clock_ns=FakeClock())
        acquirer.capture_once()
        acquirer.capture_once()
        self.assertEqual(acquirer.metrics.poll_interval_count, 1)
        self.assertEqual(acquirer.metrics.last_poll_interval_ns, 30)
        self.assertEqual(acquirer.metrics.total_poll_interval_ns, 30)
        self.assertEqual(acquirer.metrics.min_poll_interval_ns, 30)
        self.assertEqual(acquirer.metrics.max_poll_interval_ns, 30)

    def test_run_rejects_negative_poll_interval(self) -> None:
        from threading import Event
        acquirer = PhysicsAcquirer(FakeSource([]), AcquisitionRingBuffer(1))
        with self.assertRaises(ValueError):
            acquirer.run(Event(), poll_interval_ns=-1)


if __name__ == "__main__":
    unittest.main()
