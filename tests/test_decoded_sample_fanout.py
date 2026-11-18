from __future__ import annotations

import unittest

from src.race_engineer_acquisition.decoded_sample_fanout import (
    DecodedSampleFanOut,
)


class DecodedSampleFanOutTests(unittest.TestCase):
    def test_subscribers_receive_independent_ordered_samples(self) -> None:
        fanout = DecodedSampleFanOut()
        fast = fanout.subscribe("fast", capacity=4)
        slow = fanout.subscribe("slow", capacity=4)

        for sequence in range(1, 4):
            accepted = fanout.publish(
                stream="physics",
                capture_sequence=sequence,
                capture_timestamp_ns=sequence * 10,
                data={"speed": sequence},
            )
            self.assertEqual(accepted, {"fast": True, "slow": True})

        self.assertEqual(
            [sample.capture_sequence for sample in fast.read_batch(4)],
            [1, 2, 3],
        )
        self.assertEqual(
            [sample.capture_sequence for sample in slow.read_batch(4)],
            [1, 2, 3],
        )
        self.assertEqual(fast.metrics.rejected_count, 0)
        self.assertEqual(slow.metrics.rejected_count, 0)

    def test_full_subscriber_drops_newest_and_reports_sequence(self) -> None:
        fanout = DecodedSampleFanOut()
        slow = fanout.subscribe("slow", capacity=2)

        for sequence in range(1, 4):
            fanout.publish(
                stream="graphics",
                capture_sequence=sequence,
                capture_timestamp_ns=sequence * 100,
                data={"progress": sequence / 3},
            )

        metrics = slow.metrics
        self.assertEqual(metrics.offered_count, 3)
        self.assertEqual(metrics.accepted_count, 2)
        self.assertEqual(metrics.rejected_count, 1)
        self.assertEqual(metrics.first_rejected_sequence, 3)
        self.assertEqual(metrics.last_rejected_sequence, 3)
        self.assertEqual(metrics.high_water_mark, 2)
        self.assertEqual(
            [sample.capture_sequence for sample in slow.read_batch(4)],
            [1, 2],
        )

    def test_slow_subscriber_does_not_reject_fast_subscriber(self) -> None:
        fanout = DecodedSampleFanOut()
        fast = fanout.subscribe("fast", capacity=2)
        slow = fanout.subscribe("slow", capacity=1)

        for sequence in range(1, 4):
            result = fanout.publish(
                stream="physics",
                capture_sequence=sequence,
                capture_timestamp_ns=sequence,
                data=sequence,
            )
            self.assertEqual(result["fast"], True)
            self.assertEqual(fast.read_nowait().capture_sequence, sequence)

        self.assertEqual(result["slow"], False)
        self.assertEqual(slow.metrics.rejected_count, 2)
        self.assertEqual(fast.metrics.rejected_count, 0)

    def test_unsubscribe_closes_only_the_selected_subscriber(self) -> None:
        fanout = DecodedSampleFanOut()
        removed = fanout.subscribe("removed", capacity=2)
        retained = fanout.subscribe("retained", capacity=2)
        fanout.unsubscribe("removed")
        result = fanout.publish(
            stream="graphics", capture_sequence=7, capture_timestamp_ns=70, data={}
        )
        self.assertEqual(result, {"retained": True})
        self.assertTrue(removed.metrics.closed)
        self.assertEqual(retained.metrics.accepted_count, 1)

    def test_close_rejects_future_subscriptions_and_publications(self) -> None:
        fanout = DecodedSampleFanOut()
        fanout.subscribe("consumer", capacity=2)
        fanout.close()
        self.assertEqual(fanout.publish(
            stream="physics", capture_sequence=1, capture_timestamp_ns=1, data={}
        ), {})
        with self.assertRaises(RuntimeError):
            fanout.subscribe("late", capacity=1)


if __name__ == "__main__":
    unittest.main()
