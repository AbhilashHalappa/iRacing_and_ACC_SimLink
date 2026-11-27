"""ACC-only Qt host embedding the React dashboard and owning acquisition lifecycle."""
from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json
import time

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime
from ..race_engineer_acquisition.decoded_distribution import DecodedTelemetryBroker
from .stream_health import build_stream_freshness


class ACCDesktopWindow(QMainWindow):
    overlays_requested = Signal(list)
    overlay_theme_requested = Signal(str)

    def __init__(self, *, app: QApplication, static_root: Path | None = None) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("Race Engineer ACC")
        self.resize(1500, 940)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet("QMainWindow { background: #0b1118; }")

        # Keep the WebEngine profile beside the source checkout, independent of
        # the process working directory.
        project_root = Path(__file__).resolve().parents[2]
        app_data = project_root / "user_data"
        self._runtime = create_acc_acquisition_runtime()
        # Overview needs only decoded live state and the shared out-lap observer.
        # Strategy history, Performance Hub archives and assessment workers are not started.
        self._decoded_broker = DecodedTelemetryBroker(self._runtime)
        self._car_model: str | None = None
        self._track: str | None = None
        self._track_configuration: str | None = None
        self._last_capture_diagnostics_log_signature: tuple[object, ...] | None = None
        try:
            self._runtime.supervisor.start()
            self._decoded_broker.start()
        except Exception:
            self._decoded_broker.close()
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
            self._decoded_broker.close()
            self._runtime.supervisor.stop(timeout=5.0)
            raise
        self._view.load(QUrl(self._bridge_url))

        from .overlay_windows import OverlayWindowManager
        self._overlay_manager = OverlayWindowManager(
            profile=self._web_profile,
            bridge_url=self._bridge_url,
            parent=self,
            on_selection_changed=self._bridge.set_overlay_ids,
        )
        self._bridge.set_overlay_ids(self._overlay_manager.enabled_tiles)
        self._bridge.set_overlay_handler(self.overlays_requested.emit)
        self._bridge.set_theme_handler(self.overlay_theme_requested.emit)
        self.overlays_requested.connect(
            self._overlay_manager.apply,
            Qt.ConnectionType.QueuedConnection,
        )
        self.overlay_theme_requested.connect(
            self._overlay_manager.set_theme,
            Qt.ConnectionType.QueuedConnection,
        )
        self._overlay_manager.apply(self._overlay_manager.enabled_tiles)

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
        out_lap_status = self._decoded_broker.out_lap_status
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
                    "last_decode_error": consumer_snapshot.last_decode_error,
                },
            }
        capture_signature = tuple(
            (
                name,
                values["ring_buffer"]["total_rejection_count"],
                values["ring_buffer"]["first_lost_sequence"],
                values["ring_buffer"]["last_lost_sequence"],
                values["acquirer"].get("buffer_rejection_count", 0),
                values["decoder"]["decode_error_count"],
            )
            for name, values in sorted(capture_pipeline.items())
        )
        if capture_signature != self._last_capture_diagnostics_log_signature:
            self._last_capture_diagnostics_log_signature = capture_signature
            print(
                "[Capture Pipeline Diagnostics] " + json.dumps({
                    "streams": capture_pipeline,
                }, sort_keys=True, default=lambda value: asdict(value) if hasattr(value, "__dataclass_fields__") else str(value)),
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
        static_snapshot = self._runtime.static_consumer.snapshot
        static_data = (
            asdict(static_snapshot.latest)
            if static_snapshot.latest is not None
            else {}
        )
        self._car_model = static_data.get("car_model") or self._car_model
        self._track = static_data.get("track") or self._track
        self._track_configuration = (
            static_data.get("track_configuration") or self._track_configuration
        )
        snapshot = {
            "game": "acc",
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
        self._overlay_manager.close_all()
        self._bridge.stop()
        alive = self._runtime.supervisor.stop(timeout=5.0)
        self._decoded_broker.close()
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
