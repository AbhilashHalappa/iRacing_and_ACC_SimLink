"""Independent, transparent, frameless always-on-top windows for Overview tiles."""
from __future__ import annotations

import logging
import traceback

from PySide6.QtCore import QObject, QSettings, Qt, QUrl, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QToolButton


logger = logging.getLogger(__name__)


SUPPORTED_TILES = {
    "driver_trace", "speed", "gear", "rpm", "pedals", "laps", "lap_history",
    "weather", "map", "session", "brakes", "tyres", "fuel", "warnings",
    "hardware", "delta", "sectors", "position", "electronics", "pit_stint",
    "damage", "pressure_targets", "race_control", "car_status",
}
TILE_TITLES = {
    "driver_trace": "Driver inputs", "speed": "Speed", "gear": "Gear",
    "rpm": "Engine RPM", "pedals": "Driver inputs", "laps": "Lap times",
    "lap_history": "Lap time history", "weather": "Track weather",
    "map": "Track map", "session": "Session", "brakes": "Brake Info",
    "tyres": "Tyre condition", "fuel": "Fuel", "warnings": "Penalties & warnings",
    "hardware": "Hardware connections", "delta": "Delta to best lap",
    "sectors": "Sector performance", "position": "Race position & gaps",
    "electronics": "Car electronics", "pit_stint": "Pit stop & stint",
    "damage": "Vehicle damage", "pressure_targets": "Tyre pressure targets",
    "race_control": "Race control", "car_status": "Car lights & status",
}


class _OverlayWebView(QWebEngineView):
    """Forward Alt-drag gestures while leaving ordinary web interactions intact."""

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def mousePressEvent(self, event):
        if self._owner._begin_gesture(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._owner._move_gesture(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._owner._end_gesture(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TileOverlayWindow(QMainWindow):
    """Frameless tile window; hold Alt and drag to move or resize it."""

    def __init__(self, tile_id: str, profile, bridge_url: str, settings: QSettings, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.tile_id = tile_id
        self._settings = settings
        self._gesture = None
        self._gesture_global = None
        self._gesture_geometry = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("QMainWindow { background: transparent; }")
        self._view = _OverlayWebView(self)
        self._view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._view.setStyleSheet("background: transparent;")
        self._page = QWebEnginePage(profile, self._view)
        self._page.setBackgroundColor(QColor(0, 0, 0, 0))
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)
        self.close_button = QToolButton(self)
        self.close_button.setText("×")
        self.close_button.setToolTip("Close this overlay")
        self.close_button.setAccessibleName("Close overlay")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setAutoRaise(False)
        self.close_button.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet(
            "QToolButton { background-color: rgba(18, 24, 34, 218); color: #e8edf5; "
            "border: 1px solid rgba(205, 216, 232, 105); border-radius: 7px; "
            "font-size: 18px; font-weight: 500; padding: 0px; margin: 0px; }"
            "QToolButton:hover { background-color: #d94b5b; color: #ffffff; "
            "border-color: #f08b96; }"
            "QToolButton:pressed { background-color: #ad3544; }"
        )
        self.close_button.clicked.connect(self.close)
        self.setMinimumSize(220, 130)
        saved = settings.value(f"geometry/{tile_id}")
        if saved and self.restoreGeometry(saved):
            pass
        else:
            size = (680, 360) if tile_id in ("driver_trace", "lap_history", "hardware", "pressure_targets", "map") else (380, 260)
            self.resize(*size)
            self.move(120 + (len(tile_id) * 13) % 260, 100 + (len(tile_id) * 17) % 180)
        url = QUrl(bridge_url)
        url.setQuery("overlay=" + tile_id)
        self._view.loadFinished.connect(self._on_load_finished)
        logger.info("Overlay %s: loading %s", tile_id, url.toString())
        self._view.load(url)

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            logger.info("Overlay %s: web page loaded", self.tile_id)
        else:
            logger.error(
                "Overlay %s: web page load failed (URL: %s)",
                self.tile_id,
                self._view.url().toString(),
            )

    def _begin_gesture(self, event) -> bool:
        # Alt+left-drag moves; Alt+right-drag resizes. Normal clicks remain
        # available to the tile's own controls and charts.
        if not (event.modifiers() & Qt.KeyboardModifier.AltModifier):
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            self._gesture = "move"
        elif event.button() == Qt.MouseButton.RightButton:
            self._gesture = "resize"
        else:
            return False
        self._gesture_global = event.globalPosition().toPoint()
        self._gesture_geometry = self.geometry()
        return True

    def _move_gesture(self, event) -> bool:
        if not self._gesture or self._gesture_global is None or self._gesture_geometry is None:
            return False
        delta = event.globalPosition().toPoint() - self._gesture_global
        if self._gesture == "move":
            self.move(self._gesture_geometry.topLeft() + delta)
        else:
            self.resize(
                max(self.minimumWidth(), self._gesture_geometry.width() + delta.x()),
                max(self.minimumHeight(), self._gesture_geometry.height() + delta.y()),
            )
        return True

    def _end_gesture(self, event) -> bool:
        if not self._gesture:
            return False
        self._gesture = None
        self._gesture_global = None
        self._gesture_geometry = None
        self._save_geometry()
        return True

    def _position_close_button(self):
        if not self.isVisible():
            return
        top_right = self.mapToGlobal(
            self.rect().topRight()
        )
        self.close_button.move(
            top_right.x() - self.close_button.width() - 7,
            top_right.y() + 7,
        )
        self.close_button.show()
        self.close_button.raise_()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._position_close_button()
        self._save_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_close_button()
        self._save_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_close_button()

    def closeEvent(self, event):
        self.close_button.hide()
        super().closeEvent(event)

    def _save_geometry(self):
        if self.isVisible():
            self._settings.setValue(f"geometry/{self.tile_id}", self.saveGeometry())


class OverlayWindowManager(QObject):
    def __init__(self, *, profile, bridge_url: str, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.bridge_url = bridge_url
        self.parent = parent
        self.settings = QSettings("SimLink", "SimLink Overlays")
        self.windows: dict[str, TileOverlayWindow] = {}
        from PySide6.QtWidgets import QApplication
        self._app = QApplication.instance()
        if self._app is not None:
            self._app.installEventFilter(self)

        self.enabled_tiles = [
            tile for tile in self.settings.value("enabled_tiles", [], type=list)
            if tile in SUPPORTED_TILES
        ]

    def eventFilter(self, watched, event):
        # QWebEngine routes pointer events through internal render widgets, so
        # overriding QWebEngineView mouse handlers alone is not reliable.
        # Filter events at the application level and handle only events whose
        # top-level window is one of our tile overlays.
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget

        if not isinstance(watched, QWidget):
            return False
        window = watched.window()
        if not isinstance(window, TileOverlayWindow):
            return False

        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            if window._begin_gesture(event):
                event.accept()
                return True
        elif event_type == QEvent.Type.MouseMove:
            if window._move_gesture(event):
                event.accept()
                return True
        elif event_type == QEvent.Type.MouseButtonRelease:
            if window._end_gesture(event):
                event.accept()
                return True
        return False

    def apply(self, tile_ids: list[str]) -> None:
        clean = list(dict.fromkeys(tile for tile in tile_ids if tile in SUPPORTED_TILES))
        logger.info("Applying overlay selection: %s", clean)
        for tile_id in list(self.windows):
            if tile_id not in clean:
                window = self.windows.pop(tile_id)
                try:
                    window.close()
                    window.deleteLater()
                    logger.info("Overlay %s: closed", tile_id)
                except Exception:
                    logger.exception("Overlay %s: failed while closing", tile_id)
        for tile_id in clean:
            try:
                if tile_id not in self.windows:
                    # Keep overlays as independent top-level windows. Parenting them
                    # to the main window makes Windows minimize them with their owner.
                    window = TileOverlayWindow(
                        tile_id, self.profile, self.bridge_url, self.settings, None
                    )
                    self.windows[tile_id] = window
                    logger.info("Overlay %s: window constructed", tile_id)
                else:
                    window = self.windows[tile_id]
                window.show()
                window.raise_()
                logger.info(
                    "Overlay %s: show requested; visible=%s geometry=%s",
                    tile_id,
                    window.isVisible(),
                    window.geometry().getRect(),
                )
                QTimer.singleShot(
                    0,
                    lambda current_id=tile_id, current_window=window: self._verify_visible(current_id, current_window),
                )
            except Exception:
                logger.error(
                    "Overlay %s: creation/show failed\n%s",
                    tile_id,
                    traceback.format_exc(),
                )
                failed = self.windows.pop(tile_id, None)
                if failed is not None:
                    try:
                        failed.close()
                        failed.deleteLater()
                    except Exception:
                        logger.exception("Overlay %s: cleanup after failure failed", tile_id)
        self.enabled_tiles = [tile for tile in clean if tile in self.windows]
        self.settings.setValue("enabled_tiles", self.enabled_tiles)
        logger.info("Overlay selection applied; active windows: %s", self.enabled_tiles)

    @staticmethod
    def _verify_visible(tile_id: str, window: TileOverlayWindow) -> None:
        try:
            logger.info(
                "Overlay %s: post-event-loop visibility=%s minimized=%s geometry=%s",
                tile_id,
                window.isVisible(),
                window.isMinimized(),
                window.geometry().getRect(),
            )
            if not window.isVisible():
                logger.error("Overlay %s: Qt did not make the window visible", tile_id)
        except RuntimeError:
            logger.exception("Overlay %s: window was destroyed before visibility check", tile_id)

    def close_all(self) -> None:
        if self._app is not None:
            self._app.removeEventFilter(self)
        for window in self.windows.values():
            window.close()
            window.deleteLater()
        self.windows.clear()
