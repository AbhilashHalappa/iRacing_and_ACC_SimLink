"""Qt desktop host for iRacing, reusing the tested Overview frontend and bridge."""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..iracing import IRacingTelemetryReader


class IRacingDesktopWindow(QMainWindow):
    def __init__(self, *, app: QApplication, static_root: Path | None = None) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("SimLink Overview · iRacing")
        self.resize(1500, 940)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet("QMainWindow { background: #0b1118; }")

        project_root = Path(__file__).resolve().parents[2]
        app_data = project_root / "user_data"
        self._reader = IRacingTelemetryReader()
        self._reader.start()
        self._bridge = TelemetryBridge(
            static_root or Path(__file__).resolve().parents[1] / "web_ui" / "dist",
            port=8765,
        )

        profile_data = app_data / "webengine-iracing"
        cache_data = app_data / "webengine-iracing-cache"
        profile_data.mkdir(parents=True, exist_ok=True)
        cache_data.mkdir(parents=True, exist_ok=True)
        self._web_profile = QWebEngineProfile("SimLinkIRacing", app)
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
            self._view.load(QUrl(self._bridge.start()))
        except Exception:
            self._reader.close()
            raise

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(50)
        self._publish_timer.timeout.connect(self._publish_snapshot)
        self._publish_timer.start()
        self.statusBar().showMessage("iRacing SDK · waiting for simulator")

    def _publish_snapshot(self) -> None:
        snapshot = self._reader.snapshot()
        captured_at = snapshot.pop("captured_at", None)
        connected = bool(snapshot.get("connected"))
        if connected and isinstance(captured_at, (int, float)):
            age_ms = max(0, round((time.monotonic() - captured_at) * 1000))
            state = "fresh" if age_ms <= 1000 else "stale"
            for stream in snapshot.get("streams", {}).values():
                stream.update({"state": state, "age_ms": age_ms, "threshold_ms": 1000, "lifecycle_state": "running"})
            if state != "fresh":
                snapshot["connected"] = False
        self._bridge.publish(snapshot)
        if snapshot.get("connected"):
            count = snapshot.get("physics", {}).get("processed_count", 0)
            self.statusBar().showMessage(f"iRacing LIVE · {count:,} telemetry samples")
        else:
            self.statusBar().showMessage("iRacing SDK · waiting for simulator telemetry")

    def closeEvent(self, event) -> None:
        self._publish_timer.stop()
        self._bridge.stop()
        if not self._reader.close(timeout=3.0):
            QMessageBox.warning(
                self,
                "iRacing reader still stopping",
                "The iRacing telemetry reader has not exited yet.",
            )
        event.accept()


def run_desktop() -> int:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("SimLink")
    app.setApplicationName("SimLink iRacing Overview")
    try:
        window = IRacingDesktopWindow(app=app)
    except Exception as exc:
        QMessageBox.critical(None, "SimLink iRacing startup failed", str(exc))
        return 1
    window.show()
    return app.exec()
