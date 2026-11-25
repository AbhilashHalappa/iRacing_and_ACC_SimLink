from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from race_engineer_acquisition.decoded_distribution import DecodedTelemetryBroker


class _Consumer:
    def set_update_notifier(self, notifier):
        self.notifier = notifier


class _Runtime:
    def __init__(self):
        self.physics_consumer = _Consumer()
        self.graphics_consumer = _Consumer()
        self.static_consumer = _Consumer()


def test_overview_monitor_exposes_fresh_out_lap_state_without_strategy_services():
    graphics = SimpleNamespace(
        status=2,
        session_index=0,
        session=0,
        completed_laps=0,
        normalized_car_position=0.92,
        is_in_pit=False,
        is_in_pit_lane=False,
        setup_menu_visible=False,
    )
    physics = SimpleNamespace(speed_kph=80.0)
    telemetry = SimpleNamespace(
        graphics=SimpleNamespace(is_fresh=True, data=graphics),
        physics=SimpleNamespace(is_fresh=True, data=physics),
    )

    with patch(
        "race_engineer_acquisition.decoded_distribution.RaceEngineerSnapshotAggregator"
    ) as aggregator:
        aggregator.return_value.snapshot.return_value = telemetry
        monitor = DecodedTelemetryBroker(_Runtime())
        monitor.start()
        try:
            status = monitor.out_lap_status
            assert status["fresh"] is True
            assert status["active"] is True
            assert status["source"] == "ACCOutLapObserver"
            assert "event_delivery" not in monitor.metrics
            assert "sample_delivery" not in monitor.metrics
        finally:
            assert monitor.close()
