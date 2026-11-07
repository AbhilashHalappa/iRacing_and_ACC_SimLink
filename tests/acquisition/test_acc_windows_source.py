import unittest

from race_engineer_acquisition.acc_windows import (
    PHYSICS_MAP,
    PHYSICS_SIZE,
    WindowsACCPhysicsSource,
)


class FakeMapping:
    def __init__(self, packet_ids, payload):
        self.packet_ids = iter(packet_ids)
        self.payload = payload
        self.closed = False

    def read_packet_id(self):
        return next(self.packet_ids)

    def copy_page(self):
        return self.payload

    def close(self):
        self.closed = True


class WindowsSourceAdapterTests(unittest.TestCase):
    def test_uses_acc_physics_named_mapping(self):
        self.assertEqual(PHYSICS_MAP, r"Local\acpmf_physics")

    def test_copies_page_bracketed_by_packet_ids(self):
        payload = bytes(PHYSICS_SIZE)
        mapping = FakeMapping([1234, 1234], payload)
        source = WindowsACCPhysicsSource(mapping_factory=lambda: mapping)
        read = source.read_physics()
        self.assertEqual(read.packet_id_before, 1234)
        self.assertEqual(read.packet_id_after, 1234)
        self.assertTrue(read.is_consistent)
        self.assertEqual(read.payload, payload)
        source.close()
        self.assertTrue(mapping.closed)

    def test_inconsistent_packet_ids_are_returned_for_acquirer_retry(self):
        mapping = FakeMapping([50, 51], bytes(PHYSICS_SIZE))
        source = WindowsACCPhysicsSource(mapping_factory=lambda: mapping)
        read = source.read_physics()
        self.assertFalse(read.is_consistent)

    def test_rejects_wrong_page_size(self):
        mapping = FakeMapping([1, 1], b"short")
        source = WindowsACCPhysicsSource(mapping_factory=lambda: mapping)
        with self.assertRaises(ValueError):
            source.read_physics()


if __name__ == "__main__":
    unittest.main()
