"""Downstream consumer for the priority ACC Graphics telemetry fields."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import struct
import time
from threading import Event, Lock
from typing import Any, Callable

from .graphics import GraphicsSnapshot
from .graphics_decoder import DecodedGraphics, decode_graphics
from .ring_buffer import AcquisitionRingBuffer


@dataclass(frozen=True, slots=True)
class GraphicsConsumerSnapshot:
    lifecycle_state: str
    processed_count: int
    decode_error_count: int
    last_capture_sequence: int | None
    last_error: str | None
    latest: DecodedGraphics | None
    latest_capture_timestamp_ns: int | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "stream": "graphics",
            "lifecycle_state": self.lifecycle_state,
            "processed_count": self.processed_count,
            "decode_error_count": self.decode_error_count,
            "last_capture_sequence": self.last_capture_sequence,
            "last_error": self.last_error,
            "capture_timestamp_ns": self.latest_capture_timestamp_ns,
            "data": asdict(self.latest) if self.latest is not None else None,
        }


class GraphicsDecodeConsumer:
    """Decode only after raw snapshots have left the independent Graphics ring."""

    def __init__(
        self,
        source: AcquisitionRingBuffer[GraphicsSnapshot],
        *,
        idle_wait_seconds: float = 0.001,
    ) -> None:
        if idle_wait_seconds <= 0:
            raise ValueError("idle_wait_seconds must be positive")
        self._source = source
        self._idle_wait_seconds = idle_wait_seconds
        self._lock = Lock()
        self._lifecycle_state = "idle"
        self._processed_count = 0
        self._decode_error_count = 0
        self._last_capture_sequence: int | None = None
        self._last_error: str | None = None
        self._latest: DecodedGraphics | None = None
        self._latest_capture_timestamp_ns: int | None = None
        self._update_notifier: Callable[[], None] | None = None
        self._sample_publisher: Callable[[str, int, int, Any], None] | None = None
        self._sample_publish_error_count = 0

    def set_update_notifier(self, notifier: Callable[[], None] | None) -> None:
        """Install an optional constant-time dirty notifier for decoded publication."""
        with self._lock:
            self._update_notifier = notifier

    def set_sample_publisher(
        self, publisher: Callable[[str, int, int, Any], None] | None
    ) -> None:
        """Attach the nonblocking Stage 2 decoded-sample fan-out publisher."""
        with self._lock:
            self._sample_publisher = publisher

    def _publish_sample(self, raw: GraphicsSnapshot, decoded: DecodedGraphics) -> None:
        with self._lock:
            publisher = self._sample_publisher
        if publisher is None:
            return
        try:
            publisher(
                stream="graphics",
                capture_sequence=raw.capture_sequence,
                capture_timestamp_ns=raw.capture_timestamp_ns,
                data=decoded,
            )
        except Exception:
            # A downstream distribution failure must not terminate decoding.
            with self._lock:
                self._sample_publish_error_count += 1

    def _notify_update(self) -> None:
        with self._lock:
            notifier = self._update_notifier
        if notifier is not None:
            try:
                notifier()
            except Exception:
                # Distribution notification must never fail the decoder worker.
                pass

    @property
    def sample_publish_error_count(self) -> int:
        """Number of unexpected exceptions raised by the Stage 2 sample publisher."""
        with self._lock:
            return self._sample_publish_error_count

    @property
    def snapshot(self) -> GraphicsConsumerSnapshot:
        with self._lock:
            return GraphicsConsumerSnapshot(
                lifecycle_state=self._lifecycle_state,
                processed_count=self._processed_count,
                decode_error_count=self._decode_error_count,
                last_capture_sequence=self._last_capture_sequence,
                last_error=self._last_error,
                latest=self._latest,
                latest_capture_timestamp_ns=self._latest_capture_timestamp_ns,
            )

    def process_pending(self, *, max_items: int | None = None) -> int:
        if max_items is not None and max_items < 0:
            raise ValueError("max_items cannot be negative")
        processed = 0
        while max_items is None or processed < max_items:
            raw = self._source.try_get()
            if raw is None:
                break
            try:
                decoded = decode_graphics(raw.payload)
                if decoded.packet_id != raw.acc_graphics_packet_id:
                    raise ValueError(
                        "decoded packet ID does not match acquisition packet ID "
                        f"({decoded.packet_id} != {raw.acc_graphics_packet_id})"
                    )
            except (ValueError, struct.error) as exc:
                with self._lock:
                    self._decode_error_count += 1
                    self._last_capture_sequence = raw.capture_sequence
                    self._last_error = f"{type(exc).__name__}: {exc}"
            else:
                with self._lock:
                    self._processed_count += 1
                    self._last_capture_sequence = raw.capture_sequence
                    self._last_error = None
                    self._latest = decoded
                    self._latest_capture_timestamp_ns = raw.capture_timestamp_ns
                self._publish_sample(raw, decoded)
            processed += 1
        if processed:
            # Signal once per drained batch, outside the decoder state lock.
            self._notify_update()
        return processed

    def run(self, stop_event: Event, producer_done: Event) -> None:
        with self._lock:
            self._lifecycle_state = "running"
        self._notify_update()
        try:
            while not producer_done.is_set() or self._source.size > 0:
                if self.process_pending() == 0:
                    if stop_event.is_set():
                        time.sleep(self._idle_wait_seconds)
                    else:
                        stop_event.wait(self._idle_wait_seconds)
        finally:
            with self._lock:
                self._lifecycle_state = "stopped"
            self._notify_update()
