import unittest
from threading import Event

from race_engineer_acquisition.fanout import FanOutDispatcher
from race_engineer_acquisition.recording_policy import evaluate_recording_completion
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class Item:
    def __init__(self, capture_sequence):
        self.capture_sequence = capture_sequence


def source_with(*sequences):
    source = AcquisitionRingBuffer(max(1, len(sequences)))
    for sequence in sequences:
        assert source.try_put(Item(sequence))
    return source


def decide(*, acquired, persisted, consumer, required_rejections=0,
           acquisition_rejections=0, pending_acquisition=0,
           dispatcher_in_flight=0, dispatcher_error=None, producer_error=None,
           recorder_error=None, recovery_valid=True, checkpoint_valid=True,
           shutdown_timed_out=False):
    return evaluate_recording_completion(
        acquired=acquired,
        persisted=persisted,
        acquisition_rejections=acquisition_rejections,
        pending_acquisition=pending_acquisition,
        dispatcher_in_flight=dispatcher_in_flight,
        required_delivery_rejections=required_rejections,
        required_consumer=consumer.metrics,
        dispatcher_error=dispatcher_error,
        producer_error=producer_error,
        recorder_error=recorder_error,
        recovery_valid=recovery_valid,
        checkpoint_valid=checkpoint_valid,
        shutdown_timed_out=shutdown_timed_out,
    )


class RecordingPolicyTests(unittest.TestCase):
    def test_complete_required_recording_is_accepted(self):
        dispatcher = FanOutDispatcher(source_with(1, 2, 3))
        recorder = dispatcher.register("recorder", 3, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        for sequence in (1, 2, 3):
            item = recorder.try_get()
            self.assertEqual(item.capture_sequence, sequence)
            recorder.acknowledge(item)

        decision = decide(acquired=3, persisted=3, consumer=recorder)
        self.assertTrue(decision.completed)
        self.assertEqual(decision.reasons, ())

    def test_required_queue_full_never_completes(self):
        dispatcher = FanOutDispatcher(source_with(10, 11))
        recorder = dispatcher.register("recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        decision = decide(
            acquired=2, persisted=0, consumer=recorder,
            required_rejections=dispatcher.metrics.required_delivery_rejection_count,
        )
        self.assertFalse(decision.completed)
        self.assertIn("required_recorder_queue_rejected_samples", decision.reasons)
        self.assertIn("required_delivery_rejections", decision.reasons)

    def test_required_consumer_crash_accounts_pending_as_failed(self):
        dispatcher = FanOutDispatcher(source_with(20, 21))
        recorder = dispatcher.register("recorder", 2, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        recorder.mark_failed("recorder worker crashed")

        decision = decide(
            acquired=2, persisted=0, consumer=recorder,
            recorder_error="RuntimeError: recorder worker crashed",
        )
        self.assertFalse(decision.completed)
        self.assertIn("required_recorder_consumer_failed_samples_or_worker", decision.reasons)
        self.assertIn("recorder_writer_failed", decision.reasons)
        self.assertEqual(recorder.metrics.pending_count, 0)
        self.assertEqual(recorder.metrics.failed_count, 2)

    def test_disk_write_failure_cannot_be_mistaken_for_persistence(self):
        dispatcher = FanOutDispatcher(source_with(30))
        recorder = dispatcher.register("recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        item = recorder.try_get()
        recorder.acknowledge(item, success=False)

        decision = decide(
            acquired=1, persisted=0, consumer=recorder,
            recorder_error="OSError: simulated disk full",
        )
        self.assertFalse(decision.completed)
        self.assertIn("required_recorder_consumer_failed_samples_or_worker", decision.reasons)
        self.assertIn("recorder_writer_failed", decision.reasons)

    def test_shutdown_timeout_is_explicitly_incomplete(self):
        dispatcher = FanOutDispatcher(source_with(40))
        recorder = dispatcher.register("recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        item = recorder.try_get()
        recorder.acknowledge(item)

        decision = decide(
            acquired=1, persisted=1, consumer=recorder,
            shutdown_timed_out=True,
        )
        self.assertFalse(decision.completed)
        self.assertIn("shutdown_timeout_worker_still_running", decision.reasons)

    def test_optional_consumer_failure_does_not_invalidate_required_recorder(self):
        dispatcher = FanOutDispatcher(source_with(50, 51))
        optional = dispatcher.register("live-analysis", 2)
        recorder = dispatcher.register("recorder", 2, required=True)
        optional.mark_failed("analysis worker crashed")
        stop = Event()
        stop.set()
        dispatcher.run(stop)

        for sequence in (50, 51):
            item = recorder.try_get()
            self.assertEqual(item.capture_sequence, sequence)
            recorder.acknowledge(item)

        self.assertTrue(optional.metrics.failed)
        self.assertEqual(recorder.metrics.processed_count, 2)
        decision = decide(
            acquired=2, persisted=2, consumer=recorder,
            required_rejections=dispatcher.metrics.required_delivery_rejection_count,
        )
        self.assertTrue(decision.completed)
        self.assertEqual(decision.reasons, ())

    def test_recovery_or_checkpoint_failure_prevents_completion(self):
        dispatcher = FanOutDispatcher(source_with(60))
        recorder = dispatcher.register("recorder", 1, required=True)
        stop = Event()
        stop.set()
        dispatcher.run(stop)
        item = recorder.try_get()
        recorder.acknowledge(item)

        decision = decide(
            acquired=1, persisted=1, consumer=recorder,
            recovery_valid=False, checkpoint_valid=False,
        )
        self.assertFalse(decision.completed)
        self.assertIn("recording_recovery_or_crc_validation_failed", decision.reasons)
        self.assertIn("checkpoint_validation_failed", decision.reasons)


if __name__ == "__main__":
    unittest.main()
