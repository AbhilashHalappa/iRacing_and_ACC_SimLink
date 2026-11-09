import unittest
from threading import Event

from race_engineer_acquisition.fanout import BoundedConsumerQueue, FanOutDispatcher
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class Item:
    def __init__(self, capture_sequence: int) -> None:
        self.capture_sequence = capture_sequence


def source_with(*sequences: int) -> AcquisitionRingBuffer[Item]:
    source = AcquisitionRingBuffer[Item](max(1, len(sequences)))
    for sequence in sequences:
        if not source.try_put(Item(sequence)):
            raise AssertionError("test source unexpectedly rejected an item")
    return source


class FanOutTests(unittest.TestCase):
    def test_independent_consumers_receive_every_sample_and_cannot_steal(self):
        dispatcher = FanOutDispatcher(source_with(1, 2, 3))
        recorder = dispatcher.register("recorder", 3, required=True)
        decoder = dispatcher.register("decoder-test", 3)
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        first_recorder_item = recorder.try_get()
        self.assertEqual(first_recorder_item.capture_sequence, 1)
        self.assertEqual(decoder.size, 3)
        self.assertEqual([decoder.try_get().capture_sequence for _ in range(3)], [1, 2, 3])
        recorder.acknowledge(first_recorder_item, success=True)
        for sequence in (2, 3):
            item = recorder.try_get()
            self.assertEqual(item.capture_sequence, sequence)
            recorder.acknowledge(item, success=True)
        for sequence in (1, 2, 3):
            decoder.acknowledge(sequence, success=True)

        for consumer in (recorder, decoder):
            metrics = consumer.metrics
            self.assertEqual(metrics.offered_count, 3)
            self.assertEqual(metrics.dispatched_count, 3)
            self.assertEqual(metrics.processed_count, 3)
            self.assertEqual(metrics.failed_count, 0)
            self.assertEqual(metrics.rejected_count, 0)
            self.assertEqual(metrics.pending_count, 0)
            self.assertEqual(metrics.dispatched_count, metrics.processed_count + metrics.failed_count + metrics.pending_count)
        self.assertEqual(dispatcher.metrics.source_dequeued_count, 3)
        self.assertEqual(dispatcher.metrics.dispatched_item_count, 3)

    def test_slow_full_consumer_does_not_block_fast_consumer(self):
        dispatcher = FanOutDispatcher(source_with(10, 11, 12))
        slow_required = dispatcher.register("slow-recorder", 1, required=True)
        fast = dispatcher.register("fast-decoder", 3)
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        self.assertEqual(slow_required.size, 1)
        self.assertEqual(fast.size, 3)
        slow_metrics = slow_required.metrics
        self.assertEqual(slow_metrics.dispatched_count, 1)
        self.assertEqual(slow_metrics.rejected_count, 2)
        self.assertEqual(slow_metrics.first_lost_sequence, 11)
        self.assertEqual(slow_metrics.last_lost_sequence, 12)
        self.assertEqual(dispatcher.metrics.required_delivery_rejection_count, 2)
        self.assertEqual([fast.try_get().capture_sequence for _ in range(3)], [10, 11, 12])

    def test_failed_consumer_isolated_from_other_consumers(self):
        dispatcher = FanOutDispatcher(source_with(20, 21))
        failed = dispatcher.register("failed-decoder", 2)
        healthy = dispatcher.register("healthy-recorder", 2, required=True)
        failed.mark_failed("decoder worker crashed")
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        self.assertTrue(failed.metrics.failed)
        self.assertEqual(failed.metrics.rejected_count, 2)
        self.assertEqual(failed.metrics.error, "decoder worker crashed")
        self.assertEqual(healthy.metrics.dispatched_count, 2)
        self.assertEqual([healthy.try_get().capture_sequence for _ in range(2)], [20, 21])

    def test_processing_failure_is_not_counted_as_success(self):
        dispatcher = FanOutDispatcher(source_with(30))
        consumer = dispatcher.register("recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        item = consumer.try_get()
        consumer.acknowledge(item, success=False)
        metrics = consumer.metrics
        self.assertEqual(metrics.processed_count, 0)
        self.assertEqual(metrics.failed_count, 1)
        self.assertEqual(metrics.first_failed_sequence, 30)
        self.assertEqual(metrics.last_failed_sequence, 30)
        self.assertEqual(metrics.pending_count, 0)

    def test_shutdown_drains_source_then_closes_dispatch_but_allows_consumer_drain(self):
        dispatcher = FanOutDispatcher(source_with(40, 41, 42))
        consumer = dispatcher.register("recorder", 3, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        self.assertTrue(consumer.metrics.closed)
        self.assertEqual(consumer.metrics.pending_count, 3)
        self.assertFalse(consumer.offer(Item(43)))
        self.assertEqual(consumer.metrics.rejected_count, 1)
        for sequence in (40, 41, 42):
            item = consumer.try_get()
            self.assertEqual(item.capture_sequence, sequence)
            consumer.acknowledge(item)
        self.assertEqual(consumer.metrics.pending_count, 0)
        self.assertEqual(consumer.metrics.processed_count, 3)

    def test_capacity_must_be_positive_and_registration_is_closed_after_start(self):
        dispatcher = FanOutDispatcher(source_with(1))
        with self.assertRaises(ValueError):
            dispatcher.register("invalid", 0)
        dispatcher.register("consumer", 1)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        with self.assertRaises(RuntimeError):
            dispatcher.register("late", 1)

    def test_capacity_includes_unacknowledged_in_flight_items(self):
        consumer = BoundedConsumerQueue("bounded", 1)
        self.assertTrue(consumer.offer(Item(70)))
        item = consumer.try_get()
        self.assertEqual(item.capture_sequence, 70)
        self.assertFalse(consumer.offer(Item(71)))
        metrics = consumer.metrics
        self.assertEqual(metrics.pending_count, 1)
        self.assertEqual(metrics.in_flight_count, 1)
        self.assertEqual(metrics.queued_count, 0)
        self.assertEqual(metrics.high_water_mark, 1)
        self.assertEqual(metrics.rejected_count, 1)
        consumer.acknowledge(item)
        self.assertEqual(consumer.metrics.pending_count, 0)

    def test_failed_consumer_accounts_queued_and_in_flight_items(self):
        dispatcher = FanOutDispatcher(source_with(60, 61, 62))
        consumer = dispatcher.register("decoder", 3)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        in_flight = consumer.try_get()
        self.assertEqual(in_flight.capture_sequence, 60)

        failed_count = consumer.mark_failed("decoder worker stopped unexpectedly")
        metrics = consumer.metrics
        self.assertEqual(failed_count, 3)
        self.assertEqual(metrics.dispatched_count, 3)
        self.assertEqual(metrics.processed_count, 0)
        self.assertEqual(metrics.failed_count, 3)
        self.assertEqual(metrics.pending_count, 0)
        self.assertEqual(metrics.first_failed_sequence, 60)
        self.assertEqual(metrics.last_failed_sequence, 62)
        self.assertEqual(metrics.dispatched_count, metrics.processed_count + metrics.failed_count + metrics.pending_count)

    def test_required_consumer_loss_is_explicit(self):
        dispatcher = FanOutDispatcher(source_with(50, 51))
        recorder = dispatcher.register("required-recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        self.assertEqual(dispatcher.metrics.required_delivery_rejection_count, 1)
        self.assertEqual(recorder.metrics.offered_count, 2)
        self.assertEqual(recorder.metrics.dispatched_count, 1)
        self.assertEqual(recorder.metrics.rejected_count, 1)
        self.assertNotEqual(recorder.metrics.offered_count, recorder.metrics.dispatched_count)


if __name__ == "__main__":
    unittest.main()
