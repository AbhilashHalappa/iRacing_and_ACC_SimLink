"""Service-owned runtime worker for Performance Hub candidate-lap assembly.

This worker consumes only the existing Stage 2 bounded decoded-sample and
lap-event subscriptions. It never touches acquisition, decoders or shared memory.
"""
from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any

from .candidate_lap_assembler import CandidateLapAssembler, LapAssemblyOutput


class PerformanceLapCaptureWorker:
    """Drain independent Stage 2 feeds and expose bounded assembly results."""

    def __init__(
        self, sample_subscription: Any, event_subscription: Any, *,
        sample_capacity: int = 100_000, result_capacity: int = 4,
        poll_interval_s: float = 0.01,
    ) -> None:
        self._samples = sample_subscription
        self._events = event_subscription
        self._assembler = CandidateLapAssembler(max_samples_per_stream=sample_capacity)
        self._results: Queue[LapAssemblyOutput] = Queue(maxsize=result_capacity)
        self._poll_interval_s = poll_interval_s
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._last_rejected_count = 0
        self._pre_boundary_sample_loss = False
        self._result_drop_count = 0
        self._processed_sample_count = 0
        self._processed_event_count = 0
        self._diagnostic_count = 0
        self._last_error: str | None = None
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            self._thread = Thread(
                target=self._run, name="ACC-Performance-Lap-Capture", daemon=True
            )
            self._thread.start()

    def _publish(self, output: LapAssemblyOutput) -> None:
        if not (output.completed or output.compact or output.diagnostics):
            return
        with self._lock:
            self._diagnostic_count += len(output.diagnostics)
        try:
            self._results.put_nowait(output)
        except Full:
            # Never block acquisition-facing consumers. The archive writer
            # drains this bounded handoff; if it falls behind, loss is explicit
            # and visible in result_drop_count.
            with self._lock:
                self._result_drop_count += len(output.completed) + len(output.compact)
                self._diagnostic_count += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            did_work = False
            try:
                metrics = self._samples.metrics
                rejected = metrics.rejected_count
                if rejected > self._last_rejected_count:
                    # The fan-out metric is aggregate across Physics and
                    # Graphics, so conservatively invalidate both streams.
                    # A delayed lap.started event may still place some samples
                    # from this pre-boundary period inside Lap 1.
                    if self._assembler.waiting_for_boundary:
                        self._pre_boundary_sample_loss = True
                    else:
                        for stream in CandidateLapAssembler.STREAMS:
                            self._publish(self._assembler.mark_stream_gap(stream))
                    self._last_rejected_count = rejected
                    did_work = True

                # Establish lap boundaries before draining samples in this
                # pass. Samples may have accumulated while the worker was idle;
                # feeding them first would discard them before the first anchor.
                batch = self._events.read_batch(max_events=128)
                if batch.gap_detected:
                    self._publish(self._assembler.mark_event_gap())
                    did_work = True
                for event in batch.events:
                    was_waiting_for_boundary = self._assembler.waiting_for_boundary
                    self._publish(self._assembler.ingest_event(event))
                    event_type = getattr(event, "event_type", None)
                    if event_type == "lap.started" and was_waiting_for_boundary:
                        if self._pre_boundary_sample_loss:
                            for stream in CandidateLapAssembler.STREAMS:
                                self._publish(self._assembler.mark_stream_gap(stream))
                        self._pre_boundary_sample_loss = False
                    elif (
                        event_type in ("lap.completed", "lap.completion_gap")
                        and was_waiting_for_boundary
                    ):
                        # No lap.started event was observed, so this completion
                        # or counter-gap event is only a conservative re-attachment
                        # anchor; earlier sample loss predates the new interval.
                        self._pre_boundary_sample_loss = False
                    with self._lock:
                        self._processed_event_count += 1
                    did_work = True

                for sample in self._samples.read_batch(4096):
                    self._publish(self._assembler.ingest_sample(sample))
                    with self._lock:
                        self._processed_sample_count += 1
                    did_work = True
            except Exception as exc:
                with self._lock:
                    self._last_error = f"{type(exc).__name__}: {exc}"
            if not did_work:
                self._stop.wait(self._poll_interval_s)

    def read_result(self) -> LapAssemblyOutput | None:
        try:
            return self._results.get_nowait()
        except Empty:
            return None

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started": self._started,
                "running": self._thread is not None and self._thread.is_alive(),
                "processed_sample_count": self._processed_sample_count,
                "processed_event_count": self._processed_event_count,
                "queued_result_count": self._results.qsize(),
                "result_drop_count": self._result_drop_count,
                "diagnostic_count": self._diagnostic_count,
                "last_error": self._last_error,
                "sample_rejected_count": self._last_rejected_count,
            }

    def close(self, *, timeout: float = 2.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True
