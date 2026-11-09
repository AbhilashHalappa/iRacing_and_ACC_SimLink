import struct
import unittest

from race_engineer_acquisition.graphics import GRAPHICS_MAP, GraphicsAcquirer, RawGraphicsRead
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class FakeSource:
    def __init__(self, reads):
        self.reads = iter(reads)

    def read_graphics(self):
        return next(self.reads)


class FakeClock:
    def __init__(self):
        self.value = 100

    def __call__(self):
        value = self.value
        self.value += 10
        return value


def read(before, copied, after, suffix=b"page"):
    return RawGraphicsRead(before, copied, after, struct.pack("<i", copied) + suffix)


class GraphicsAcquirerTests(unittest.TestCase):
    def test_windows_graphics_mapping_name_uses_single_namespace_separator(self):
        self.assertEqual(GRAPHICS_MAP, r"Local\acpmf_graphics")

    def test_capture_preserves_complete_payload_and_timestamps(self):
        buffer = AcquisitionRingBuffer(4)
        acquirer = GraphicsAcquirer(
            FakeSource([read(42, 42, 42, b"full-mapping")]),
            buffer, clock_ns=FakeClock(),
        )
        snapshot = acquirer.capture_once()
        self.assertEqual(snapshot.capture_sequence, 1)
        self.assertEqual(snapshot.acc_graphics_packet_id, 42)
        self.assertEqual(snapshot.read_start_ns, 100)
        self.assertEqual(snapshot.read_complete_ns, 110)
        self.assertEqual(snapshot.payload, struct.pack("<i", 42) + b"full-mapping")
        self.assertEqual(buffer.try_get(), snapshot)

    def test_inconsistent_bracket_retries_then_accepts(self):
        buffer = AcquisitionRingBuffer(4)
        acquirer = GraphicsAcquirer(
            FakeSource([read(10, 11, 11, b"torn"), read(11, 11, 11, b"good")]),
            buffer, clock_ns=FakeClock(),
        )
        snapshot = acquirer.capture_once()
        self.assertEqual(snapshot.acc_graphics_packet_id, 11)
        self.assertTrue(snapshot.payload.endswith(b"good"))
        self.assertEqual(acquirer.metrics.inconsistent_snapshot_count, 1)
        self.assertEqual(acquirer.metrics.consistency_retry_count, 1)
        self.assertEqual(acquirer.metrics.read_attempt_count, 2)

    def test_duplicate_packet_id_observations_are_preserved(self):
        buffer = AcquisitionRingBuffer(4)
        acquirer = GraphicsAcquirer(
            FakeSource([
                read(7, 7, 7, b"first"),
                read(7, 7, 7, b"changed-with-same-id"),
                read(8, 8, 8, b"next"),
            ]),
            buffer, clock_ns=FakeClock(),
        )
        first = acquirer.capture_once()
        same_id = acquirer.capture_once()
        next_page = acquirer.capture_once()
        self.assertEqual(first.capture_sequence, 1)
        self.assertEqual(same_id.capture_sequence, 2)
        self.assertEqual(same_id.payload.endswith(b"changed-with-same-id"), True)
        self.assertEqual(next_page.capture_sequence, 3)
        self.assertEqual(acquirer.metrics.duplicate_packet_observation_count, 1)
        self.assertEqual(buffer.try_get().acc_graphics_packet_id, 7)
        self.assertEqual(buffer.try_get().payload.endswith(b"changed-with-same-id"), True)
        self.assertEqual(buffer.try_get().acc_graphics_packet_id, 8)

    def test_packet_gaps_and_regressions_are_accounted_separately(self):
        buffer = AcquisitionRingBuffer(8)
        acquirer = GraphicsAcquirer(
            FakeSource([read(10, 10, 10), read(14, 14, 14), read(2, 2, 2)]),
            buffer, clock_ns=FakeClock(),
        )
        acquirer.capture_once()
        acquirer.capture_once()
        acquirer.capture_once()
        self.assertEqual(acquirer.metrics.source_packet_gap_count, 3)
        self.assertEqual(acquirer.metrics.packet_id_regression_count, 1)

    def test_all_inconsistent_attempts_publish_nothing(self):
        buffer = AcquisitionRingBuffer(4)
        acquirer = GraphicsAcquirer(
            FakeSource([read(1, 2, 2), read(2, 3, 3)]),
            buffer, max_consistency_attempts=2, clock_ns=FakeClock(),
        )
        self.assertIsNone(acquirer.capture_once())
        self.assertEqual(buffer.size, 0)
        self.assertEqual(acquirer.metrics.capture_count, 0)
        self.assertEqual(acquirer.metrics.inconsistent_snapshot_count, 2)

    def test_buffer_rejection_is_reported_without_overwrite(self):
        buffer = AcquisitionRingBuffer(1)
        acquirer = GraphicsAcquirer(
            FakeSource([read(1, 1, 1), read(2, 2, 2)]),
            buffer, clock_ns=FakeClock(),
        )
        acquirer.capture_once()
        acquirer.capture_once()
        self.assertEqual(acquirer.metrics.buffer_rejection_count, 1)
        self.assertEqual(buffer.total_rejection_count, 1)
        self.assertEqual(buffer.try_get().acc_graphics_packet_id, 1)


    def test_windows_source_uses_reported_mapping_size_and_copies_every_byte(self):
        class FakeMapping:
            size = 4096

            def __init__(self):
                self.closed = False

            def read_packet_id(self):
                return 123

            def copy_page(self):
                return struct.pack("<i", 123) + bytes((i % 251 for i in range(4092)))

            def close(self):
                self.closed = True

        from race_engineer_acquisition.graphics import WindowsACCGraphicsSource

        mapping = FakeMapping()
        source = WindowsACCGraphicsSource(mapping_factory=lambda: mapping)
        self.assertEqual(source.page_size, 4096)
        raw = source.read_graphics()
        self.assertTrue(raw.is_consistent)
        self.assertEqual(len(raw.payload), 4096)
        self.assertEqual(raw.payload[0:4], struct.pack("<i", 123))
        self.assertEqual(raw.payload[4:], bytes((i % 251 for i in range(4092))))
        source.close()
        self.assertTrue(mapping.closed)


if __name__ == "__main__":
    unittest.main()
