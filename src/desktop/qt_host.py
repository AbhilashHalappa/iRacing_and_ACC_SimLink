"""ACC-only Qt host embedding the React dashboard and owning acquisition lifecycle."""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import time

from PySide6.QtCore import QStandardPaths, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime
from ..race_engineer_acquisition.static_decoder import decode_static_candidate_b
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
        out_lap_status = self._race_engineer_service.out_lap_status()
        graphics["lap_status"] = (
            "out"
            if out_lap_status["fresh"] and out_lap_status["active"]
            else None
        )
        acquisition = self._runtime.supervisor.status
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
            int(float(raw_session_time) // 30)
            if isinstance(raw_session_time, (int, float))
            else None
        )
        log_signature = (
            race_progress.get("status"),
            race_progress.get("session_type_code"),
            race_progress.get("completed_laps"),
            raw_graphics_status,
            raw_lap_limit,
            time_bucket,
        )
        if log_signature != self._last_race_progress_log_signature:
            self._last_race_progress_log_signature = log_signature
            diagnostic = {
                **race_progress,
                "raw_graphics_status": raw_graphics_status,
                "raw_session_time_left": raw_session_time,
                "raw_number_of_laps": raw_lap_limit,
            }
            print(
                "[Race Progress] " + json.dumps(diagnostic, sort_keys=True),
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
