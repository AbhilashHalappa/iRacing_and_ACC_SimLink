"""Conservative candidate-lap assembly from Stage 2 samples and ACC lap events.

This module has no acquisition, decoder, broker, storage, or UI ownership.
It correlates independent Physics and Graphics samples by their original
monotonic capture timestamps; it never joins streams by array index.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from .current_lap_trace import CurrentLapTraceSnapshot, build_current_lap_trace_snapshot


@dataclass(frozen=True, slots=True)
class CompactLapMetadata:
    session_id: str
    lap_number: int
    lap_time_ms: int | None
    lap_valid: bool | None
    out_lap: bool | None
    start_timestamp_ns: int
    end_timestamp_ns: int
    physics_sample_count: int
    graphics_sample_count: int
    reason: str
    # Compact change-point evidence only; never retain full invalid/out-lap traces.
    graphics_timing_observations: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class CompletedLapTrace:
    session_id: str
    lap_number: int
    lap_time_ms: int
    start_timestamp_ns: int
    end_timestamp_ns: int
    physics_samples: tuple[Any, ...]
    graphics_samples: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class LapAssemblyDiagnostic:
    kind: str
    session_id: str | None
    lap_number: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class LapAssemblyOutput:
    completed: tuple[CompletedLapTrace, ...] = ()
    compact: tuple[CompactLapMetadata, ...] = ()
    diagnostics: tuple[LapAssemblyDiagnostic, ...] = ()


class CandidateLapAssembler:
    """Assemble full traces between trusted ACC lap-start/completion events.

    The existing Overview out-lap observer can provide the start/finish
    crossing that starts Lap 1. If that event was not observed (for example,
    the app attached after the crossing), the first completion event remains
    a conservative anchor and no incomplete historical lap is fabricated.

    An event is finalized only after both independent stream timestamp
    watermarks reach its boundary. Invalid, out-lap, and unknown-validity laps
    produce compact metadata only. Counter gaps, session changes, timestamp
    regressions, and bounded-buffer overflow invalidate the affected interval.
    """

    STREAMS = ("physics", "graphics")

    def __init__(self, *, max_samples_per_stream: int = 100_000) -> None:
        if max_samples_per_stream < 1:
            raise ValueError("max_samples_per_stream must be positive")
        self._capacity = max_samples_per_stream
        self._session_id: str | None = None
        self._start_timestamp_ns: int | None = None
        self._start_lap_number: int | None = None
        self._buffers: dict[str, deque[Any]] = {
            stream: deque() for stream in self.STREAMS
        }
        self._watermarks: dict[str, int | None] = {
            stream: None for stream in self.STREAMS
        }
        self._last_sequence: dict[str, int | None] = {
            stream: None for stream in self.STREAMS
        }
        self._overflow_streams: set[str] = set()
        self._quality_reasons: set[str] = set()
        # Samples may reach the worker before the asynchronous broker emits
        # the trusted Lap 1 start event. Keep a bounded pre-boundary window.
        self._pre_boundary_dropped_through: dict[str, int | None] = {
            stream: None for stream in self.STREAMS
        }
        self._pending_events: deque[Any] = deque()
        self._last_event_sequence: int | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def waiting_for_boundary(self) -> bool:
        return self._start_timestamp_ns is None

    def reset(self) -> None:
        self._session_id = None
        self._start_timestamp_ns = None
        self._start_lap_number = None
        self._pending_events.clear()
        self._last_event_sequence = None
        self._clear_interval()

    def _clear_interval(self) -> None:
        for stream in self.STREAMS:
            self._buffers[stream].clear()
            self._watermarks[stream] = None
            self._last_sequence[stream] = None
        self._overflow_streams.clear()
        self._quality_reasons.clear()
        for stream in self.STREAMS:
            self._pre_boundary_dropped_through[stream] = None

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, Mapping):
            return value.get(key, default)
        return getattr(value, key, default)

    @staticmethod
    def _valid_nonnegative_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    def ingest_sample(self, sample: Any) -> LapAssemblyOutput:
        stream = self._get(sample, "stream")
        if stream not in self.STREAMS:
            return LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("unsupported_stream", self._session_id, None,
                                      f"Unsupported decoded stream: {stream!r}"),
            ))
        sequence = self._get(sample, "capture_sequence")
        timestamp = self._get(sample, "capture_timestamp_ns")
        if not self._valid_nonnegative_int(sequence) or not self._valid_nonnegative_int(timestamp):
            return LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("invalid_sample_metadata", self._session_id, None,
                                      f"{stream} sample has invalid sequence/timestamp"),
            ))
        previous_sequence = self._last_sequence[stream]
        previous_timestamp = self._watermarks[stream]
        if previous_sequence is not None and sequence <= previous_sequence:
            self._quality_reasons.add(f"{stream}_sequence_not_increasing")
            return self._drain_events()
        if previous_sequence is not None and sequence > previous_sequence + 1:
            self._quality_reasons.add(f"{stream}_sequence_gap")
        if previous_timestamp is not None and timestamp < previous_timestamp:
            self._quality_reasons.add(f"{stream}_timestamp_regressed")
            self._last_sequence[stream] = sequence
            return self._drain_events()

        self._last_sequence[stream] = sequence
        self._watermarks[stream] = timestamp
        buffer = self._buffers[stream]
        if self._start_timestamp_ns is None:
            # A bounded rolling pre-boundary window lets a delayed lap.started
            # event retain samples captured just after the actual crossing.
            if len(buffer) >= self._capacity:
                dropped = buffer.popleft()
                dropped_timestamp = self._get(dropped, "capture_timestamp_ns")
                previous_dropped = self._pre_boundary_dropped_through[stream]
                if isinstance(dropped_timestamp, int):
                    self._pre_boundary_dropped_through[stream] = (
                        dropped_timestamp if previous_dropped is None
                        else max(previous_dropped, dropped_timestamp)
                    )
            buffer.append(sample)
        elif timestamp > self._start_timestamp_ns:
            if len(buffer) < self._capacity:
                buffer.append(sample)
            else:
                self._overflow_streams.add(stream)
        return self._drain_events()

    def mark_stream_gap(
        self, stream: str, *, first_missing_sequence: int | None = None,
        last_missing_sequence: int | None = None,
    ) -> LapAssemblyOutput:
        """Downgrade the active candidate after the subscription reports loss."""
        if stream not in self.STREAMS:
            raise ValueError(f"Unsupported decoded stream: {stream!r}")
        self._quality_reasons.add(f"{stream}_subscription_gap")
        detail = f"{stream} sample subscription reported loss"
        if first_missing_sequence is not None or last_missing_sequence is not None:
            detail += (
                f" (first_missing={first_missing_sequence},"
                f" last_missing={last_missing_sequence})"
            )
        return LapAssemblyOutput(diagnostics=(
            LapAssemblyDiagnostic("sample_gap", self._session_id,
                                  self._start_lap_number, detail),
        ))

    def mark_event_gap(self) -> LapAssemblyOutput:
        """Discard the active interval after event-mailbox loss; await a new anchor."""
        session_id = self._session_id
        lap_number = self._start_lap_number
        self._start_timestamp_ns = None
        self._start_lap_number = None
        self._pending_events.clear()
        self._clear_interval()
        return LapAssemblyOutput(diagnostics=(
            LapAssemblyDiagnostic(
                "event_gap", session_id, lap_number,
                "Lap-event subscription reported loss; waiting for a fresh boundary anchor",
            ),
        ))

    def ingest_event(self, event: Any) -> LapAssemblyOutput:
        event_type = self._get(event, "event_type")
        event_sequence = self._get(event, "sequence")
        if self._valid_nonnegative_int(event_sequence):
            if self._last_event_sequence is not None and event_sequence <= self._last_event_sequence:
                return LapAssemblyOutput(diagnostics=(
                    LapAssemblyDiagnostic("event_sequence_not_increasing", self._session_id, None,
                                          "Lap event sequence was repeated or regressed"),
                ))
            self._last_event_sequence = event_sequence

        if event_type not in ("lap.started", "lap.completed", "lap.completion_gap"):
            return LapAssemblyOutput()

        session_id = self._get(event, "session_id")
        timestamp = self._get(event, "source_timestamp_ns")
        payload = self._get(event, "payload", {})
        if not isinstance(session_id, str) or not session_id:
            return LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("missing_session_id", None, None,
                                      "Lap boundary has no session identity"),
            ))
        if not self._valid_nonnegative_int(timestamp):
            return LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("missing_boundary_timestamp", session_id, None,
                                      "Lap boundary has no valid source timestamp"),
            ))
        if not isinstance(payload, Mapping):
            return LapAssemblyOutput(diagnostics=(
                LapAssemblyDiagnostic("invalid_event_payload", session_id, None,
                                      "Lap event payload is not a mapping"),
            ))

        if self._session_id != session_id:
            previous = self._session_id
            self._session_id = session_id
            self._start_timestamp_ns = None
            self._start_lap_number = None
            self._pending_events.clear()
            if previous is not None:
                if event_type == "lap.started":
                    # The new session's sample worker may already have
                    # delivered frames before this boundary event. Retain only
                    # samples after its timestamp; discard the old interval.
                    for stream in self.STREAMS:
                        self._buffers[stream] = deque(
                            sample for sample in self._buffers[stream]
                            if self._get(sample, "capture_timestamp_ns") > timestamp
                        )
                        dropped_through = self._pre_boundary_dropped_through[stream]
                        if dropped_through is not None and dropped_through > timestamp:
                            self._overflow_streams.add(stream)
                        self._pre_boundary_dropped_through[stream] = None
                else:
                    self._clear_interval()
                diagnostic = LapAssemblyDiagnostic(
                    "session_changed", previous, None,
                    "Previous candidate interval discarded at session transition",
                )
            else:
                # Preserve the bounded pre-boundary sample window until we
                # know whether this first event is a trusted lap.started.
                diagnostic = None
        else:
            diagnostic = None

        if event_type == "lap.started":
            lap_number = payload.get("lap_number")
            if not self._valid_nonnegative_int(lap_number) or lap_number < 1:
                return LapAssemblyOutput(diagnostics=tuple(
                    item for item in (diagnostic, LapAssemblyDiagnostic(
                        "invalid_lap_number", session_id, None,
                        "Lap-start event has no valid lap number",
                    )) if item is not None
                ))
            if self._start_timestamp_ns is not None:
                return LapAssemblyOutput(diagnostics=tuple(
                    item for item in (diagnostic, LapAssemblyDiagnostic(
                        "unexpected_lap_start", session_id, lap_number,
                        "Lap-start event arrived while another interval was active",
                    )) if item is not None
                ))
            self._start_timestamp_ns = timestamp
            self._start_lap_number = lap_number
            for stream in self.STREAMS:
                buffer = self._buffers[stream]
                self._buffers[stream] = deque(
                    sample for sample in buffer
                    if self._get(sample, "capture_timestamp_ns") > timestamp
                )
                dropped_through = self._pre_boundary_dropped_through[stream]
                if dropped_through is not None and dropped_through > timestamp:
                    self._overflow_streams.add(stream)
                self._pre_boundary_dropped_through[stream] = None
            return LapAssemblyOutput(diagnostics=tuple(
                [diagnostic] if diagnostic is not None else []
            ))

        if event_type == "lap.completion_gap":
            self._start_timestamp_ns = timestamp
            self._start_lap_number = payload.get("current_completed_laps")
            self._pending_events.clear()
            self._clear_interval()
            return LapAssemblyOutput(diagnostics=tuple(
                item for item in (diagnostic, LapAssemblyDiagnostic(
                    "completion_gap", session_id, self._start_lap_number,
                    "ACC completed-lap counter jumped; no missing laps were fabricated",
                )) if item is not None
            ))

        lap_number = payload.get("lap_number")
        if not self._valid_nonnegative_int(lap_number) or lap_number < 1:
            return LapAssemblyOutput(diagnostics=tuple(
                item for item in (diagnostic, LapAssemblyDiagnostic(
                    "invalid_lap_number", session_id, None,
                    "Completed-lap event has no valid lap number",
                )) if item is not None
            ))

        if self._start_timestamp_ns is None:
            # No trusted lap.started event was observed; preserve the existing
            # conservative behavior and use this completion only as an anchor.
            self._clear_interval()
            self._start_timestamp_ns = timestamp
            self._start_lap_number = lap_number
            return LapAssemblyOutput(diagnostics=tuple(
                [diagnostic] if diagnostic is not None else []
            ))

        if timestamp <= self._start_timestamp_ns:
            self._quality_reasons.add("lap_boundary_timestamp_not_increasing")
            return LapAssemblyOutput(diagnostics=tuple(
                item for item in (diagnostic, LapAssemblyDiagnostic(
                    "boundary_timestamp_not_increasing", session_id, lap_number,
                    "Completed-lap boundary did not advance in monotonic time",
                )) if item is not None
            ))

        self._pending_events.append(event)
        output = self._drain_events()
        if diagnostic is not None:
            return LapAssemblyOutput(
                output.completed, output.compact, (diagnostic,) + output.diagnostics
            )
        return output

    @classmethod
    def _compact_graphics_timing_observations(
        cls, samples: tuple[Any, ...]
    ) -> tuple[Mapping[str, Any], ...]:
        """Keep timing/classification change points for compact lap records.

        This deliberately does not copy every Graphics sample. Full eligible
        laps retain the complete high-resolution streams in the trace archive;
        compact invalid/out-lap records retain only changes to timing, sector,
        and validity evidence, with their original source sequence/timestamp.
        """
        fields = (
            "sector", "last_sector_time_ms", "last_time_ms", "best_time_ms",
            "split_ms", "delta_lap_time_ms", "is_valid_lap", "completed_laps",
            "current_time_ms", "current_time_str", "last_time_str",
            "best_time_str", "split_time_str", "delta_lap_time_str",
        )
        change_fields = (
            "sector", "last_sector_time_ms", "last_time_ms", "best_time_ms",
            "split_ms", "delta_lap_time_ms", "is_valid_lap", "completed_laps",
        )
        observations: list[Mapping[str, Any]] = []
        # Keep the last observed non-null value per field. Decoded samples can
        # legitimately contain unavailable values; a missing value must not
        # erase the comparison baseline and create a false change point later.
        previous: dict[str, Any] = {}
        for sample in samples:
            data = cls._get(sample, "data")
            values = {name: cls._get(data, name) for name in fields}
            changed = [
                name for name in change_fields
                if values[name] is not None
                and (name not in previous or values[name] != previous[name])
            ]
            if changed:
                observations.append({
                    "observation_kind": "graphics_timing_change_point",
                    "source_stream": "graphics",
                    "capture_sequence": cls._get(sample, "capture_sequence"),
                    "capture_timestamp_ns": cls._get(sample, "capture_timestamp_ns"),
                    "changed_fields": changed,
                    "data": values,
                })
            for name, value in values.items():
                if value is not None:
                    previous[name] = value
        return tuple(observations)

    def _drain_events(self) -> LapAssemblyOutput:
        completed: list[CompletedLapTrace] = []
        compact: list[CompactLapMetadata] = []
        diagnostics: list[LapAssemblyDiagnostic] = []
        while self._pending_events:
            event = self._pending_events[0]
            boundary = self._get(event, "source_timestamp_ns")
            if any(
                watermark is None or watermark < boundary
                for watermark in self._watermarks.values()
            ):
                break

            self._pending_events.popleft()
            payload = self._get(event, "payload", {})
            lap_number = payload["lap_number"]
            lap_time = payload.get("lap_time_ms")
            lap_valid = payload.get("lap_valid")
            out_lap = payload.get("out_lap")
            physics = self._take_through("physics", boundary)
            graphics = self._take_through("graphics", boundary)
            reasons = set(self._quality_reasons)
            if self._overflow_streams:
                reasons.update(f"{stream}_sample_buffer_overflow"
                               for stream in self._overflow_streams)

            eligible = (
                lap_valid is True
                and out_lap is False
                and self._valid_nonnegative_int(lap_time)
                and lap_time > 0
                and not reasons
            )
            if eligible:
                completed.append(CompletedLapTrace(
                    session_id=self._session_id or "",
                    lap_number=lap_number,
                    lap_time_ms=lap_time,
                    start_timestamp_ns=self._start_timestamp_ns or 0,
                    end_timestamp_ns=boundary,
                    physics_samples=physics,
                    graphics_samples=graphics,
                ))
            else:
                reason = (
                    ";".join(sorted(reasons)) if reasons else
                    "invalid_lap" if lap_valid is False else
                    "out_lap" if out_lap is True else
                    "validity_unknown" if not isinstance(lap_valid, bool) else
                    "lap_timing_unavailable"
                )
                compact.append(CompactLapMetadata(
                    session_id=self._session_id or "",
                    lap_number=lap_number,
                    lap_time_ms=lap_time if self._valid_nonnegative_int(lap_time) else None,
                    lap_valid=lap_valid if isinstance(lap_valid, bool) else None,
                    out_lap=out_lap if isinstance(out_lap, bool) else None,
                    start_timestamp_ns=self._start_timestamp_ns or 0,
                    end_timestamp_ns=boundary,
                    physics_sample_count=len(physics),
                    graphics_sample_count=len(graphics),
                    reason=reason,
                    graphics_timing_observations=(
                        self._compact_graphics_timing_observations(graphics)
                    ),
                ))
            self._start_timestamp_ns = boundary
            self._start_lap_number = lap_number
            self._quality_reasons.clear()
            self._overflow_streams.clear()
        return LapAssemblyOutput(tuple(completed), tuple(compact), tuple(diagnostics))

    def current_lap_snapshot(self, *, snapshot_timestamp_ns: int | None = None) -> CurrentLapTraceSnapshot:
        """Return a detached bounded view of the active interval."""
        active = self._start_timestamp_ns is not None
        physics = tuple(self._buffers["physics"]) if active else ()
        graphics = tuple(self._buffers["graphics"]) if active else ()
        return build_current_lap_trace_snapshot(
            session_id=self._session_id, lap_number=self._start_lap_number,
            start_timestamp_ns=self._start_timestamp_ns,
            snapshot_timestamp_ns=snapshot_timestamp_ns,
            physics_samples=physics, graphics_samples=graphics,
            quality_reasons=tuple(self._quality_reasons),
            overflow_streams=tuple(self._overflow_streams),
            per_stream_capacity=self._capacity, active=active,
        )

    def _take_through(self, stream: str, boundary_ns: int) -> tuple[Any, ...]:
        buffer = self._buffers[stream]
        selected: list[Any] = []
        while buffer:
            timestamp = self._get(buffer[0], "capture_timestamp_ns")
            if timestamp > boundary_ns:
                break
            selected.append(buffer.popleft())
        return tuple(selected)
