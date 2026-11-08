import unittest

from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class Item:
    def __init__(self, capture_sequence: int) -> None:
        self.capture_sequence = capture_sequence


class RingBufferTests(unittest.TestCase):
    def test_fifo_and_wraparound(self) -> None:
        buffer = AcquisitionRingBuffer[Item](2)
        self.assertTrue(buffer.try_put(Item(1)))
        self.assertTrue(buffer.try_put(Item(2)))
        self.assertEqual(buffer.try_get().capture_sequence, 1)
        self.assertTrue(buffer.try_put(Item(3)))
        self.assertEqual(buffer.try_get().capture_sequence, 2)
        self.assertEqual(buffer.try_get().capture_sequence, 3)
        self.assertIsNone(buffer.try_get())

    def test_full_buffer_rejects_without_overwrite_and_accounts_loss(self) -> None:
        buffer = AcquisitionRingBuffer[Item](1)
        first = Item(10)
        rejected = Item(11)
        self.assertTrue(buffer.try_put(first))
        self.assertFalse(buffer.try_put(rejected))
        self.assertEqual(buffer.try_get().capture_sequence, 10)
        self.assertEqual(buffer.overflow_count, 1)
        self.assertEqual(buffer.full_buffer_rejection_count, 1)
        self.assertEqual(buffer.total_rejection_count, 1)
        self.assertEqual(buffer.lock_contention_count, 0)
        self.assertEqual(buffer.first_lost_sequence, 11)
        self.assertEqual(buffer.last_lost_sequence, 11)
        self.assertEqual(buffer.high_water_mark, 1)

    def test_capacity_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            AcquisitionRingBuffer(0)


if __name__ == "__main__":
    unittest.main()
