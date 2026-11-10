"""ACC-only Qt host embedding the React dashboard and owning acquisition lifecycle."""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import TelemetryBridge
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime


class ACCDesktopWindow(QMainWindow):
    def __init__(self, *, app: QApplication, static_root: Path | None = None) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("Race Engineer ACC")
        self.resize(1500, 940)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet("QMainWindow { background: #0b1118; }")

        self._runtime = create_acc_acquisition_runtime()
        self._bridge = TelemetryBridge(static_root or Path(__file__).resolve().parents[1] / "web_ui" / "dist")
        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)
        self._bridge_url = self._bridge.start()
        self._runtime.supervisor.start()
        self._view.load(QUrl(self._bridge_url))

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(50)
        self._publish_timer.timeout.connect(self._publish_snapshot)
        self._publish_timer.start()
        self.statusBar().showMessage("ACC Shared Memory · waiting for telemetry")

    def _publish_snapshot(self) -> None:
        consumer = self._runtime.physics_consumer.snapshot
        physics = consumer.to_payload()
        timestamp = consumer.latest_capture_timestamp_ns
        connected = timestamp is not None and (time.perf_counter_ns() - timestamp) < 1_000_000_000
        snapshot = {
            "connected": connected,
            "source": "ACC Shared Memory / Physics",
            "physics": physics,
            "acquisition": self._runtime.supervisor.status,
        }
        self._bridge.publish(snapshot)
        if connected:
            self.statusBar().showMessage(
                f"ACC Physics LIVE · {consumer.processed_count:,} decoded · {consumer.decode_error_count} decode errors"
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
    try:
        window = ACCDesktopWindow(app=app)
    except Exception as exc:
        QMessageBox.critical(None, "Race Engineer ACC startup failed", str(exc))
        return 1
    window.show()
    return app.exec()
