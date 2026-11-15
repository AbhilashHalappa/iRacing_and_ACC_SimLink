from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from race_engineer_acquisition.engineering_snapshot import (
    RaceEngineerSnapshotAggregator,
)


@dataclass(frozen=True)
class FakeDecoded:
    packet_id: int
    value: float


@dataclass(frozen=True)
class FakeConsumerSnapshot:
    lifecycle_state: str
    latest: object | None
    latest_capture_timestamp_ns: int | None
    last_capture_sequence: int | None
    decode_error_count: int = 0
    last_error: str | None = None


@dataclass(frozen=True)
class FakeHealthSnapshot:
    lifecycle_state: str = "running"
    last_successful_read_ns: int | None = 10_000
    source_read_failures: int = 0
    buffer_rejections: int = 0
    last_error: str | None = None


class EngineeringSnapshotTests(unittest.TestCase):
    NOW = 20_000

    def make_runtime(
        self,
        *,
        physics_timestamp=19_500,
        graphics_timestamp=19_000,
        physics_state="running",
        graphics_state="running",
        acquisition_state="running",
        static_timestamp=19_500,
        physics_data=None,
        graphics_data=None,
    ):
        physics_data = physics_data or FakeDecoded(101, 1.0)
        graphics_data = graphics_data or FakeDecoded(202, 2.0)
        return SimpleNamespace(
            physics_consumer=SimpleNamespace(
                snapshot=FakeConsumerSnapshot(
                    physics_state, physics_data, physics_timestamp, 11
                )
            ),
            graphics_consumer=SimpleNamespace(
                snapshot=FakeConsumerSnapshot(
                    graphics_state, graphics_data, graphics_timestamp, 22
                )
            ),
            static_consumer=SimpleNamespace(
                snapshot=FakeConsumerSnapshot(
                    acquisition_state, FakeDecoded(303, 3.0), static_timestamp, 33
                )
            ),
            acquirers={
                "physics": SimpleNamespace(
                    health=SimpleNamespace(
                        snapshot=FakeHealthSnapshot(
                            lifecycle_state=acquisition_state,
                            last_successful_read_ns=physics_timestamp,
                        )
                    )
                ),
                "graphics": SimpleNamespace(
                    health=SimpleNamespace(
                        snapshot=FakeHealthSnapshot(
                            lifecycle_state=acquisition_state,
                            last_successful_read_ns=graphics_timestamp,
                        )
                    )
                ),
                "static": SimpleNamespace(
                    health=SimpleNamespace(
                        snapshot=FakeHealthSnapshot(
                            lifecycle_state=acquisition_state,
                            last_successful_read_ns=static_timestamp,
                        )
                    )
                ),
            },
        )

    def test_freshness_is_evaluated_per_stream_without_claiming_sync(self):
        runtime = self.make_runtime()
        result = RaceEngineerSnapshotAggregator(
            runtime,
            physics_max_age_ms=0.001,
            graphics_max_age_ms=0.002,
            static_read_max_age_ms=0.02,
            clock_ns=lambda: self.NOW,
        ).snapshot()

        self.assertTrue(result.physics.is_fresh)
        self.assertTrue(result.graphics.is_fresh)
        self.assertTrue(result.combined_live_data_fresh)
        self.assertEqual(result.physics.sample_age_ns, 500)
        self.assertEqual(result.graphics.sample_age_ns, 1_000)
        self.assertEqual(result.physics.packet_id, 101)
        self.assertEqual(result.graphics.packet_id, 202)
        self.assertTrue(result.static.is_read_fresh)

    def test_stale_physics_does_not_hide_fresh_graphics(self):
        runtime = self.make_runtime(physics_timestamp=10_000)
        result = RaceEngineerSnapshotAggregator(
            runtime,
            physics_max_age_ms=0.001,
            graphics_max_age_ms=0.002,
            clock_ns=lambda: self.NOW,
        ).snapshot()

        self.assertFalse(result.physics.is_fresh)
        self.assertTrue(result.graphics.is_fresh)
        self.assertFalse(result.combined_live_data_fresh)
        # Keep the last good sample visible for diagnostics; consumers must
        # gate engineering decisions on is_fresh.
        self.assertIsNotNone(result.physics.data)

    def test_stopped_consumer_is_not_fresh_even_with_recent_sample(self):
        runtime = self.make_runtime(physics_state="stopped")
        result = RaceEngineerSnapshotAggregator(
            runtime, clock_ns=lambda: self.NOW
        ).snapshot()
        self.assertFalse(result.physics.is_fresh)

    def test_missing_sample_is_unavailable_and_not_fresh(self):
        runtime = self.make_runtime(
            physics_timestamp=None,
            physics_data=None,
        )
        runtime.physics_consumer.snapshot = FakeConsumerSnapshot(
            "running", None, None, None
        )
        result = RaceEngineerSnapshotAggregator(
            runtime, clock_ns=lambda: self.NOW
        ).snapshot()
        self.assertFalse(result.physics.is_available)
        self.assertFalse(result.physics.is_fresh)
        self.assertIsNone(result.physics.packet_id)

    def test_future_timestamp_is_not_fresh(self):
        runtime = self.make_runtime(physics_timestamp=self.NOW + 1)
        result = RaceEngineerSnapshotAggregator(
            runtime, clock_ns=lambda: self.NOW
        ).snapshot()
        self.assertFalse(result.physics.is_fresh)
        self.assertEqual(result.physics.sample_age_ns, -1)

    def test_static_health_and_decoded_metadata_are_both_exposed(self):
        runtime = self.make_runtime(static_timestamp=19_500)
        result = RaceEngineerSnapshotAggregator(
            runtime,
            static_read_max_age_ms=0.001,
            clock_ns=lambda: self.NOW,
        ).snapshot()
        self.assertTrue(result.static.is_read_fresh)
        self.assertFalse(hasattr(result.static, "data"))
        self.assertFalse(hasattr(result.static, "packet_id"))
        self.assertTrue(result.static_decoded.is_fresh)
        self.assertEqual(result.static_decoded.packet_id, 303)

    def test_invalid_freshness_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            RaceEngineerSnapshotAggregator(
                self.make_runtime(), physics_max_age_ms=0
            )


if __name__ == "__main__":
    unittest.main()
