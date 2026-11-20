from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from race_engineer_acquisition.decoded_sample_fanout import DecodedSampleFanOut
from race_engineer_acquisition.graphics import GraphicsSnapshot
from race_engineer_acquisition.graphics_consumer import GraphicsDecodeConsumer
from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.physics_consumer import PhysicsDecodeConsumer
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer


class DecodedConsumerFanOutIntegrationTests(unittest.TestCase):
    def test_physics_consumer_publishes_decoded_sample_with_source_metadata(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = PhysicsDecodeConsumer(ring)
        fanout = DecodedSampleFanOut()
        subscription = fanout.subscribe("history", capacity=4)
        decoded = SimpleNamespace(packet_id=17, speed_kph=123.4)
        consumer.set_sample_publisher(fanout.publish)
        snapshot = PhysicsSnapshot(
            capture_sequence=41,
            acc_physics_packet_id=17,
            read_start_ns=1000,
            read_complete_ns=1010,
            capture_timestamp_ns=1010,
            payload=b"physics-page",
        )
        self.assertTrue(ring.try_put(snapshot))

        with patch(
            "race_engineer_acquisition.physics_consumer.decode_physics",
            return_value=decoded,
        ):
            self.assertEqual(consumer.process_pending(), 1)

        sample = subscription.read_nowait()
        self.assertIsNotNone(sample)
        self.assertEqual(sample.stream, "physics")
        self.assertEqual(sample.capture_sequence, 41)
        self.assertEqual(sample.capture_timestamp_ns, 1010)
        self.assertIs(sample.data, decoded)
        self.assertEqual(consumer.snapshot.processed_count, 1)

    def test_graphics_consumer_publishes_decoded_sample_with_source_metadata(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = GraphicsDecodeConsumer(ring)
        fanout = DecodedSampleFanOut()
        subscription = fanout.subscribe("history", capacity=4)
        decoded = SimpleNamespace(packet_id=23, position=2)
        consumer.set_sample_publisher(fanout.publish)
        snapshot = GraphicsSnapshot(
            capture_sequence=52,
            acc_graphics_packet_id=23,
            read_start_ns=2000,
            read_complete_ns=2020,
            capture_timestamp_ns=2020,
            payload=b"graphics-page",
        )
        self.assertTrue(ring.try_put(snapshot))

        with patch(
            "race_engineer_acquisition.graphics_consumer.decode_graphics",
            return_value=decoded,
        ):
            self.assertEqual(consumer.process_pending(), 1)

        sample = subscription.read_nowait()
        self.assertIsNotNone(sample)
        self.assertEqual(sample.stream, "graphics")
        self.assertEqual(sample.capture_sequence, 52)
        self.assertEqual(sample.capture_timestamp_ns, 2020)
        self.assertIs(sample.data, decoded)
        self.assertEqual(consumer.snapshot.processed_count, 1)

    def test_publisher_failure_does_not_stop_physics_decoding(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = PhysicsDecodeConsumer(ring)
        consumer.set_sample_publisher(
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("publisher failed"))
        )
        decoded = SimpleNamespace(packet_id=17)
        self.assertTrue(ring.try_put(PhysicsSnapshot(
            1, 17, 10, 20, 20, b"physics-page"
        )))

        with patch(
            "race_engineer_acquisition.physics_consumer.decode_physics",
            return_value=decoded,
        ):
            self.assertEqual(consumer.process_pending(), 1)

        self.assertEqual(consumer.snapshot.processed_count, 1)
        self.assertEqual(consumer.snapshot.decode_error_count, 0)
        self.assertEqual(consumer.sample_publish_error_count, 1)

    def test_publisher_failure_does_not_stop_graphics_decoding(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = GraphicsDecodeConsumer(ring)
        consumer.set_sample_publisher(
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("publisher failed"))
        )
        decoded = SimpleNamespace(packet_id=23)
        self.assertTrue(ring.try_put(GraphicsSnapshot(
            1, 23, 10, 20, 20, b"graphics-page"
        )))

        with patch(
            "race_engineer_acquisition.graphics_consumer.decode_graphics",
            return_value=decoded,
        ):
            self.assertEqual(consumer.process_pending(), 1)

        self.assertEqual(consumer.snapshot.processed_count, 1)
        self.assertEqual(consumer.snapshot.decode_error_count, 0)
        self.assertEqual(consumer.sample_publish_error_count, 1)


    def test_decode_error_detail_is_retained_after_later_success(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = PhysicsDecodeConsumer(ring)
        self.assertTrue(ring.try_put(PhysicsSnapshot(1, 17, 10, 20, 20, b"bad")))
        self.assertTrue(ring.try_put(PhysicsSnapshot(2, 18, 30, 40, 40, b"good")))
        with patch(
            "race_engineer_acquisition.physics_consumer.decode_physics",
            side_effect=[ValueError("bad physics page"), SimpleNamespace(packet_id=18)],
        ):
            self.assertEqual(consumer.process_pending(), 2)
        self.assertEqual(consumer.snapshot.decode_error_count, 1)
        self.assertIsNone(consumer.snapshot.last_error)
        self.assertIn("bad physics page", consumer.snapshot.last_decode_error)

    def test_graphics_decode_error_detail_is_retained_after_later_success(self) -> None:
        ring = AcquisitionRingBuffer(4)
        consumer = GraphicsDecodeConsumer(ring)
        self.assertTrue(ring.try_put(GraphicsSnapshot(1, 23, 10, 20, 20, b"bad")))
        self.assertTrue(ring.try_put(GraphicsSnapshot(2, 24, 30, 40, 40, b"good")))
        with patch(
            "race_engineer_acquisition.graphics_consumer.decode_graphics",
            side_effect=[ValueError("bad graphics page"), SimpleNamespace(packet_id=24)],
        ):
            self.assertEqual(consumer.process_pending(), 2)
        self.assertEqual(consumer.snapshot.decode_error_count, 1)
        self.assertIsNone(consumer.snapshot.last_error)
        self.assertIn("bad graphics page", consumer.snapshot.last_decode_error)


if __name__ == "__main__":
    unittest.main()
