from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from src.desktop.bridge import TelemetryBridge


@dataclass(frozen=True)
class FakeHealthSnapshot:
    lifecycle_state: str
    successful_reads: int


def test_bridge_serializes_nested_acquisition_health_dataclass() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "index.html").write_text("<html>ACC UI</html>", encoding="utf-8")
        bridge = TelemetryBridge(root)
        url = bridge.start()
        try:
            bridge.publish({"acquisition": {"physics": {"health": FakeHealthSnapshot("running", 42)}}})
            with urlopen(url + "api/snapshot", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert payload["acquisition"]["physics"]["health"] == {
                "lifecycle_state": "running",
                "successful_reads": 42,
            }
        finally:
            bridge.stop()


def test_bridge_serves_frontend_and_latest_snapshot_and_sse() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "index.html").write_text("<html>ACC UI</html>", encoding="utf-8")
        bridge = TelemetryBridge(root)
        url = bridge.start()
        try:
            with urlopen(url, timeout=2) as response:
                assert response.status == 200
                assert b"ACC UI" in response.read()

            expected = {"connected": True, "physics": {"data": {"speed_kph": 123.4}}}
            bridge.publish(expected)
            with urlopen(url + "api/snapshot", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert payload["connected"] is True
            assert payload["physics"]["data"]["speed_kph"] == 123.4
            assert payload["revision"] == 1

            with urlopen(url + "events", timeout=2) as response:
                assert response.headers.get_content_type() == "text/event-stream"
                frame = response.readline() + response.readline()
            assert frame.startswith(b"data: {")
            assert b'"speed_kph":123.4' in frame
        finally:
            bridge.stop()
