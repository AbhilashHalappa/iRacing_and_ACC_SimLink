"""ACC-only Qt host embedding the React dashboard and owning acquisition lifecycle."""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QStandardPaths, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime
from ..race_engineer_acquisition.out_lap import ACCOutLapObserver
from ..race_engineer_acquisition.static_decoder import decode_static_candidate_b


class ACCDesktopWindow(QMainWindow):
    def __init__(self, *, app: QApplication, static_root: Path | None = None) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("Race Engineer ACC")
        self.resize(1500, 940)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet("QMainWindow { background: #0b1118; }")

        self._runtime = create_acc_acquisition_runtime()
        self._car_model: str | None = None
        self._track: str | None = None
        self._track_configuration: str | None = None
        self._out_lap_observer = ACCOutLapObserver()
        self._runtime.supervisor.start()
        self._bridge = TelemetryBridge(static_root or Path(__file__).resolve().parents[1] / "web_ui" / "dist", port=8765)

        # Use a named, disk-backed profile: the implicit QWebEngineView profile
        # is not a dependable store for settings that must survive app restarts.
        app_data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
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
            self._runtime.supervisor.stop(timeout=5.0)
            raise
        self._view.load(QUrl(self._bridge_url))

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(50)
        self._publish_timer.timeout.connect(self._publish_snapshot)
        self._publish_timer.start()
        self.statusBar().showMessage("ACC Shared Memory · waiting for telemetry")

    def _refresh_static_identity(self) -> None:
        # Static is acquired independently at low frequency. Drain its SPSC
        # queue here, downstream of acquisition, and retain the latest valid ID.
        static_ring = self._runtime.buffers["static"]
        while True:
            sample = static_ring.try_get()
            if sample is None:
                break
            try:
                decoded = decode_static_candidate_b(sample.payload)
                self._car_model = decoded.car_model
                self._track = decoded.track
                self._track_configuration = decoded.track_configuration
            except ValueError:
                # Keep the last known-good identity if a page is malformed.
                continue

    def _publish_snapshot(self) -> None:
        self._refresh_static_identity()
        consumer = self._runtime.physics_consumer.snapshot
        graphics_consumer = self._runtime.graphics_consumer.snapshot
        physics = consumer.to_payload()
        graphics = graphics_consumer.to_payload()
        graphics_latest = graphics_consumer.latest
        physics_latest = consumer.latest
        if graphics_latest is not None and physics_latest is not None:
            session_key = (
                graphics_latest.session_index,
                graphics_latest.session,
            )
            graphics["lap_status"] = (
                "out"
                if self._out_lap_observer.observe(
                    graphics_latest, physics_latest.speed_kph, session_key
                )
                else None
            )
        else:
            graphics["lap_status"] = None
        timestamp = consumer.latest_capture_timestamp_ns
        connected = timestamp is not None and (time.perf_counter_ns() - timestamp) < 1_000_000_000
        snapshot = {
            "connected": connected,
            "source": "ACC Shared Memory / Physics + Graphics",
            "physics": physics,
            "graphics": graphics,
            "vehicle": {
                "car_model": self._car_model,
                "track": self._track,
                "track_configuration": self._track_configuration,
            },
            "acquisition": self._runtime.supervisor.status,
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
