"""Desktop host that switches ACC and iRacing readers without restarting Qt/WebEngine."""
from __future__ import annotations
import time
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QMessageBox
from .qt_host import ACCDesktopWindow
from ..iracing import IRacingTelemetryReader
from ..race_engineer_acquisition.supervisor import create_acc_acquisition_runtime
from ..race_engineer_acquisition.decoded_distribution import DecodedTelemetryBroker

class SwitchableDesktopWindow(ACCDesktopWindow):
    switch_requested = Signal(str)

    def __init__(self, *, app, initial_game="acc", static_root=None):
        super().__init__(app=app, static_root=static_root)
        self._active_game = "acc"
        self._iracing_reader = None
        self._bridge.set_game_switch_handler(self.switch_requested.emit)
        self.switch_requested.connect(self.switch_game)
        if initial_game == "iracing":
            self.switch_game("iracing")

    def switch_game(self, game):
        if game not in ("acc", "iracing") or game == self._active_game:
            return
        previous = self._active_game
        try:
            if previous == "acc":
                alive = self._runtime.supervisor.stop(timeout=5.0)
                self._decoded_broker.close()
                if alive:
                    raise RuntimeError("ACC workers still stopping: " + ", ".join(alive))
                self._runtime = self._decoded_broker = None
            else:
                if not self._iracing_reader.close(timeout=3.0):
                    raise RuntimeError("iRacing reader is still stopping")
                self._iracing_reader = None
            self._bridge.publish({"game":game,"connected":False,"streams":{},"physics":None,"graphics":None,"source":"Switching telemetry source"})
            if game == "iracing":
                self._iracing_reader = IRacingTelemetryReader()
                self._iracing_reader.start()
            else:
                runtime = create_acc_acquisition_runtime()
                broker = DecodedTelemetryBroker(runtime)
                try:
                    runtime.supervisor.start()
                    broker.start()
                except Exception:
                    broker.close()
                    runtime.supervisor.stop(timeout=5.0)
                    raise
                self._runtime, self._decoded_broker = runtime, broker
                self._car_model = self._track = self._track_configuration = None
            self._active_game = game
            self.setWindowTitle("SimLink Overview · " + game.upper())
            self.statusBar().showMessage(game.upper() + " · waiting for telemetry")
        except Exception as exc:
            QMessageBox.critical(self, "Game switch failed", str(exc))
            if self._active_game != previous:
                try:
                    if game == "iracing" and self._iracing_reader:
                        self._iracing_reader.close(timeout=3.0)
                        self._iracing_reader = None
                    if previous == "acc":
                        runtime = create_acc_acquisition_runtime()
                        broker = DecodedTelemetryBroker(runtime)
                        runtime.supervisor.start()
                        broker.start()
                        self._runtime, self._decoded_broker = runtime, broker
                    else:
                        self._iracing_reader = IRacingTelemetryReader()
                        self._iracing_reader.start()
                    self._active_game = previous
                except Exception as recovery:
                    QMessageBox.critical(self, "Telemetry recovery failed", str(recovery))

    def _publish_snapshot(self):
        if self._active_game == "acc":
            snapshot_game = super()._publish_snapshot()
            # Tag the unchanged ACC snapshot so the selector reflects the active adapter.
            return snapshot_game
        snap = self._iracing_reader.snapshot()
        captured = snap.pop("captured_at", None)
        if snap.get("connected") and isinstance(captured, (int,float)):
            age = max(0, round((time.monotonic()-captured)*1000))
            state = "fresh" if age <= 1000 else "stale"
            for stream in snap.get("streams", {}).values():
                stream.update({"state":state,"age_ms":age,"threshold_ms":1000,"lifecycle_state":"running"})
            if state != "fresh":
                snap["connected"] = False
        snap["game"] = "iracing"
        self._bridge.publish(snap)
        self.statusBar().showMessage("iRacing LIVE" if snap.get("connected") else "iRacing SDK · waiting for simulator telemetry")

    def closeEvent(self, event):
        self._publish_timer.stop()
        self._bridge.stop()
        try:
            if self._active_game == "acc":
                alive = self._runtime.supervisor.stop(timeout=5.0)
                self._decoded_broker.close()
                if alive:
                    raise RuntimeError("ACC workers still stopping: " + ", ".join(alive))
            elif self._iracing_reader and not self._iracing_reader.close(timeout=3.0):
                raise RuntimeError("iRacing reader is still stopping")
        except Exception as exc:
            QMessageBox.warning(self, "Telemetry shutdown warning", str(exc))
        event.accept()

def run_desktop(initial_game="acc"):
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("SimLink")
    app.setApplicationName("SimLink Overview")
    try:
        window = SwitchableDesktopWindow(app=app, initial_game=initial_game)
    except Exception as exc:
        QMessageBox.critical(None, "SimLink startup failed", str(exc))
        return 1
    window.show()
    return app.exec()
