"""Independent, transparent, frameless always-on-top windows for Overview tiles."""
from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow


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
        self.setMinimumSize(320, 170)
        saved = settings.value(f"geometry/{tile_id}")
        if saved and self.restoreGeometry(saved):
            pass
        else:
            size = (680, 360) if tile_id in ("driver_trace", "lap_history", "hardware", "pressure_targets", "map") else (380, 260)
            self.resize(*size)
            self.move(120 + (len(tile_id) * 13) % 260, 100 + (len(tile_id) * 17) % 180)
        url = QUrl(bridge_url)
        url.setQuery("overlay=" + tile_id)
        self._view.load(url)

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

    def moveEvent(self, event):
        super().moveEvent(event)
        self._save_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._save_geometry()

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
        for tile_id in list(self.windows):
            if tile_id not in clean:
                window = self.windows.pop(tile_id)
                window.close()
                window.deleteLater()
        for tile_id in clean:
            if tile_id not in self.windows:
                # Keep overlays as independent top-level windows. Parenting them
                # to the main window makes Windows minimize them with their owner.
                window = TileOverlayWindow(
                    tile_id, self.profile, self.bridge_url, self.settings, None
                )
                self.windows[tile_id] = window
                window.show()
            else:
                self.windows[tile_id].show()
                self.windows[tile_id].raise_()
        self.enabled_tiles = clean
        self.settings.setValue("enabled_tiles", clean)

    def close_all(self) -> None:
        if self._app is not None:
            self._app.removeEventFilter(self)
        for window in self.windows.values():
            window.close()
            window.deleteLater()
        self.windows.clear()
