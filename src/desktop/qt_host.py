"""ACC-only Qt host embedding the React dashboard and owning acquisition lifecycle."""
from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json
import sqlite3
import time

from PySide6.QtCore import QStandardPaths, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime
from ..race_engineer_acquisition.service import RaceEngineerService
from .stream_health import build_stream_freshness


def _migrate_legacy_strategy_history(legacy_path: Path, new_path: Path) -> None:
    """Copy the previous Qt AppLocalDataLocation database into repository data."""
    if new_path.exists() or not legacy_path.is_file():
        return
    new_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(legacy_path))
    destination = sqlite3.connect(str(new_path))
    try:
        source.backup(destination)
    except Exception:
        destination.close()
        new_path.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    destination.close()


class ACCDesktopWindow(QMainWindow):
    def __init__(self, *, app: QApplication, static_root: Path | None = None) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("Race Engineer ACC")
        self.resize(1500, 940)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet("QMainWindow { background: #0b1118; }")

        # Keep runtime-owned data beside the source checkout. Resolve from this
        # file rather than the process working directory so launch location does
        # not change where history and the WebEngine profile are stored.
        project_root = Path(__file__).resolve().parents[2]
        app_data = project_root / "user_data"
        strategy_data = app_data / "strategy"
        strategy_data.mkdir(parents=True, exist_ok=True)

        # Preserve history created by earlier builds that used Qt AppLocalDataLocation.
        legacy_app_data = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
        )
        _migrate_legacy_strategy_history(
            legacy_app_data / "strategy_lap_history.sqlite3",
            strategy_data / "strategy_lap_history.sqlite3",
        )

        self._runtime = create_acc_acquisition_runtime()
        self._race_engineer_service = RaceEngineerService(
            self._runtime,
            history_path=strategy_data / "strategy_lap_history.sqlite3",
        )
        self._car_model: str | None = None
        self._track: str | None = None
        self._track_configuration: str | None = None
        self._last_race_progress_log_signature: tuple[object, ...] | None = None
        self._last_static_metadata_log_signature: tuple[object, ...] | None = None
        self._last_capture_diagnostics_log_signature: tuple[object, ...] | None = None
        try:
            self._runtime.supervisor.start()
            self._race_engineer_service.start()
        except Exception:
            self._race_engineer_service.close()
            self._runtime.supervisor.stop(timeout=5.0)
            raise
        self._bridge = TelemetryBridge(static_root or Path(__file__).resolve().parents[1] / "web_ui" / "dist", port=8765)

        # Use a named, disk-backed profile under the source checkout so browser
        # state and cache follow the same project-local data root.
        profile_data = app_data / "webengine"
        cache_data = app_data / "webengine-cache"
        profile_data.mkdir(parents=True, exist_ok=True)
        cache_data.mkdir(parents=True, exist_ok=True)
        self._web_profile = QWebEngineProfile("RaceEngineerACC", app)
        self._web_profile.setPersistentStoragePath(str(profile_data))
        self._web_profile.setCachePath(str(cache_data))
        self._web_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self._view = QWebEngineView(self)
        self._web_page = QWebEnginePage(self._web_profile, self._view)
        self._view.setPage(self._web_page)
        self.setCentralWidget(self._view)
        try:
            self._bridge_url = self._bridge.start()
        except Exception:
            self._race_engineer_service.close()
            self._runtime.supervisor.stop(timeout=5.0)
            raise
        self._view.load(QUrl(self._bridge_url))

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(50)
        self._publish_timer.timeout.connect(self._publish_snapshot)
        self._publish_timer.start()
        self.statusBar().showMessage("ACC Shared Memory · waiting for telemetry")

    def _publish_snapshot(self) -> None:
        consumer = self._runtime.physics_consumer.snapshot
        graphics_consumer = self._runtime.graphics_consumer.snapshot
        physics = consumer.to_payload()
        graphics = graphics_consumer.to_payload()
        out_lap_status = self._race_engineer_service.out_lap_status()
        graphics["lap_status"] = (
            "out"
            if out_lap_status["fresh"] and out_lap_status["active"]
            else None
        )
        acquisition = self._runtime.supervisor.status
        capture_pipeline: dict[str, object] = {}
        for stream_name, stream_consumer in (
            ("physics", self._runtime.physics_consumer),
            ("graphics", self._runtime.graphics_consumer),
        ):
            ring = self._runtime.buffers[stream_name]
            acquirer_metrics = asdict(self._runtime.acquirers[stream_name].metrics)
            acquirer_metrics.pop("_previous_poll_start_ns", None)
            consumer_snapshot = stream_consumer.snapshot
            capture_pipeline[stream_name] = {
                "acquirer": acquirer_metrics,
                "ring_buffer": {
                    "capacity": ring.capacity,
                    "queued_count": ring.size,
                    "high_water_mark": ring.high_water_mark,
                    "overflow_count": ring.overflow_count,
                    "full_buffer_rejection_count": ring.full_buffer_rejection_count,
                    "lock_contention_count": ring.lock_contention_count,
                    "total_rejection_count": ring.total_rejection_count,
                    "first_lost_sequence": ring.first_lost_sequence,
                    "last_lost_sequence": ring.last_lost_sequence,
                },
                "decoder": {
                    "lifecycle_state": consumer_snapshot.lifecycle_state,
                    "processed_count": consumer_snapshot.processed_count,
                    "decode_error_count": consumer_snapshot.decode_error_count,
                    "last_capture_sequence": consumer_snapshot.last_capture_sequence,
                    "last_error": consumer_snapshot.last_error,
                    "sample_publish_error_count": stream_consumer.sample_publish_error_count,
                },
            }
        performance_diagnostics = self._race_engineer_service.performance_archive_metrics
        sample_delivery = performance_diagnostics.get("sample_delivery", {})
        sample_subscribers = sample_delivery.get("subscribers", {})
        sample_rejections = tuple(sorted(
            (
                name,
                metrics.rejected_count,
                tuple(sorted(metrics.rejected_by_stream.items())),
            )
            for name, metrics in sample_subscribers.items()
        ))
        capture_signature = (
            *(
                (
                    name,
                    values["ring_buffer"]["total_rejection_count"],
                    values["ring_buffer"]["first_lost_sequence"],
                    values["ring_buffer"]["last_lost_sequence"],
                    values["acquirer"].get("buffer_rejection_count", 0),
                    values["decoder"]["decode_error_count"],
                    values["decoder"]["sample_publish_error_count"],
                )
                for name, values in sorted(capture_pipeline.items())
            ),
            sample_rejections,
            performance_diagnostics["capture"].get("result_drop_count", 0),
        )
        if capture_signature != self._last_capture_diagnostics_log_signature:
            self._last_capture_diagnostics_log_signature = capture_signature
            print(
                "[Capture Pipeline Diagnostics] " + json.dumps({
                    "streams": capture_pipeline,
                    "performance_hub": performance_diagnostics,
                }, sort_keys=True, default=lambda value: asdict(value)),
                flush=True,
            )
        static_health = self._runtime.acquirers["static"].health.snapshot
        now_ns = time.perf_counter_ns()
        streams = build_stream_freshness(
            now_ns=now_ns,
            timestamps_ns={
                "physics": consumer.latest_capture_timestamp_ns,
                "graphics": graphics_consumer.latest_capture_timestamp_ns,
                "static": static_health.last_successful_read_ns,
            },
            lifecycle_states={
                name: str(acquisition.get(name, {}).get("state", "missing"))
                for name in ("physics", "graphics", "static")
            },
        )
        connected = streams["physics"]["state"] == "fresh"
        engineer_snapshot = self._race_engineer_service.snapshot(
            track=self._track, car=self._car_model
        )
        static_metadata = engineer_snapshot.get("static_metadata", {})
        static_data = static_metadata.get("data") or {}
        if static_metadata.get("status") == "fresh":
            self._car_model = static_data.get("car_model") or self._car_model
            self._track = static_data.get("track") or self._track
            self._track_configuration = (
                static_data.get("track_configuration") or self._track_configuration
            )
        race_progress = engineer_snapshot.get("race_progress", {})
        raw_graphics = graphics_consumer.latest
        raw_session_time = (
            raw_graphics.session_time_left_ms if raw_graphics is not None else None
        )
        raw_lap_limit = (
            raw_graphics.number_of_laps if raw_graphics is not None else None
        )
        raw_graphics_status = (
            raw_graphics.status if raw_graphics is not None else None
        )
        time_bucket = (
            int(float(raw_session_time) // 30000)
            if isinstance(raw_session_time, (int, float))
            else None
        )
        fuel_strategy = engineer_snapshot.get("fuel_sufficiency_strategy", {})
        fuel_laps = fuel_strategy.get("acc_fuel_laps_remaining")
        fuel_margin = fuel_strategy.get("fuel_margin_laps")
        log_signature = (
            race_progress.get("status"),
            race_progress.get("session_type_code"),
            race_progress.get("completed_laps"),
            race_progress.get("average_lap_time_ms"),
            race_progress.get("lap_time_sample_count"),
            race_progress.get("laps_remaining"),
            fuel_strategy.get("status"),
            round(fuel_laps, 1) if isinstance(fuel_laps, (int, float)) else None,
            round(fuel_margin, 1) if isinstance(fuel_margin, (int, float)) else None,
            race_progress.get("chequered_flag_candidate"),
            raw_graphics_status,
            raw_lap_limit,
            time_bucket,
        )
        if log_signature != self._last_race_progress_log_signature:
            self._last_race_progress_log_signature = log_signature
            diagnostic = {
                **race_progress,
                "fuel_sufficiency_strategy": fuel_strategy,
                "raw_graphics_status": raw_graphics_status,
                "raw_session_time_left": raw_session_time,
                "raw_number_of_laps": raw_lap_limit,
            }
            print(
                "[Race Progress] " + json.dumps(diagnostic, sort_keys=True),
                flush=True,
            )
        static_signature = (
            static_metadata.get("status"),
            static_metadata.get("capture_sequence"),
            static_data.get("track"),
            static_data.get("car_model"),
            static_data.get("track_configuration"),
            static_data.get("is_timed_race"),
            static_data.get("has_extra_lap"),
            static_metadata.get("last_error"),
        )
        if static_signature != self._last_static_metadata_log_signature:
            self._last_static_metadata_log_signature = static_signature
            print(
                "[Static Metadata] " + json.dumps(static_metadata, sort_keys=True),
                flush=True,
            )
        snapshot = {
            "connected": connected,
            "streams": streams,
            "source": "ACC Shared Memory / Physics + Graphics",
            "physics": physics,
            "graphics": graphics,
            "vehicle": {
                "car_model": self._car_model,
                "track": self._track,
                "track_configuration": self._track_configuration,
            },
            "acquisition": acquisition,
            "capture_pipeline": capture_pipeline,
            "performance_archive_metrics": performance_diagnostics,
            **engineer_snapshot,
        }
        self._bridge.publish(snapshot)
        if connected:
            self.statusBar().showMessage(
                f"ACC LIVE · Physics {consumer.processed_count:,} decoded · Graphics {graphics_consumer.processed_count:,} decoded"
            )
        else:
            self.statusBar().showMessage("ACC Shared Memory · waiting for a valid Physics sample")

    def closeEvent(self, event) -> None:
        self._publish_timer.stop()
        self._bridge.stop()
        alive = self._runtime.supervisor.stop(timeout=5.0)
        self._race_engineer_service.close()
        if alive:
            QMessageBox.warning(
                self,
                "ACC acquisition still stopping",
                "These workers have not exited yet: " + ", ".join(alive),
            )
        event.accept()


def run_desktop() -> int:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("RaceEngineerACC")
    app.setApplicationName("RaceEngineerACC")
    try:
        window = ACCDesktopWindow(app=app)
    except Exception as exc:
        QMessageBox.critical(None, "Race Engineer ACC startup failed", str(exc))
        return 1
    window.show()
    return app.exec()
