from __future__ import annotations

import unittest

from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import (
    RawStaticRead, StaticAcquirer, WindowsACCStaticSource,
)


class FakeStaticSource:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def read_static(self):
        return RawStaticRead(next(self.payloads))

    @property
    def page_size(self):
        return 8

    def close(self):
        pass


class FakeMapping:
    size = 8

    def __init__(self):
        self.payload = b"12345678"
        self.closed = False

    def copy_page(self):
        return self.payload

    def close(self):
        self.closed = True


class StaticAcquisitionTests(unittest.TestCase):
    def test_initial_and_changed_pages_are_emitted_but_unchanged_are_not(self):
        source = FakeStaticSource([b"first001", b"first001", b"second02"])
        buffer = AcquisitionRingBuffer[object](capacity=8)
        acquirer = StaticAcquirer(source, buffer, clock_ns=iter([10, 12, 20, 22, 30, 33]).__next__)

        first = acquirer.capture_once()
        unchanged = acquirer.capture_once()
        changed = acquirer.capture_once()

        self.assertIsNotNone(first)
        self.assertIsNone(unchanged)
        self.assertIsNotNone(changed)
        self.assertEqual(first.capture_sequence, 1)
        self.assertEqual(changed.capture_sequence, 2)
        self.assertEqual(first.payload, b"first001")
        self.assertIsNone(first.source_packet_id)
        self.assertIsNone(first.source_timestamp_ns)
        self.assertEqual(first.read_start_ns, 10)
        self.assertEqual(first.read_complete_ns, 12)
        self.assertEqual(acquirer.metrics.unchanged_read_count, 1)
        self.assertEqual(buffer.size, 2)

    def test_windows_source_copies_full_mapping_without_decoding(self):
        mapping = FakeMapping()
        source = WindowsACCStaticSource(mapping_factory=lambda: mapping)
        self.assertEqual(source.page_size, 8)
        self.assertEqual(source.read_static().payload, b"12345678")
        source.close()
        self.assertTrue(mapping.closed)


if __name__ == "__main__":
    unittest.main()
