"""Shared compact completed-lap history for all Race Engineer strategies.

Only one record is retained per completed lap. Live decisions continue to use
fresh decoded snapshots; this module supplies historical context and trends.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from queue import Full, Queue
from threading import RLock, Thread


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True, slots=True)
class StrategyLapRecord:
    session_id: str
    lap_number: int
    lap_time_ms: int | None
    lap_valid: bool | None
    out_lap: bool | None
    classification: str
    fuel_remaining_l: float | None
    fuel_per_lap_l: float | None
    fuel_used_l: float | None
    tyre_compound: str | None
    position: int | None
    gap_ahead_ms: int | None
    gap_behind_ms: int | None
    penalty_time_s: float | None
    mandatory_pit_done: bool | None
    driver_stint_left_ms: int | None
    rain_intensity: int | None
    track_grip_status: int | None
    tyre_pressure_psi: tuple[float | None, ...]
    tyre_core_temp_c: tuple[float | None, ...]
    brake_temp_c: tuple[float | None, ...]
    car_damage: tuple[float | None, ...]
    air_temp_c: float | None
    road_temp_c: float | None
    graphics_capture_sequence: int | None
    graphics_capture_timestamp_ns: int | None
    physics_capture_sequence: int | None
    physics_capture_timestamp_ns: int | None
    event_sequence: int


class StrategyLapHistory:
    """Bounded, session-scoped history shared by every strategy consumer."""

    def __init__(self, storage_path: str | Path | None = None, *, max_records: int = 256) -> None:
        if max_records < 1:
            raise ValueError("max_records must be positive")
        self._lock = RLock()
        self._path = Path(storage_path) if storage_path is not None else None
        self._max_records = max_records
        self._records: list[StrategyLapRecord] = []
        self._session_id: str | None = None
        self._track: str | None = None
        self._car: str | None = None
        self._baseline_lap = 0
        self._last_event_sequence: int | None = None
        self._last_cursor: int | None = None
        self._complete = False
        self._persisted_complete = False
        self._gap_count = 0
        self._blockers: set[str] = set()
        self._recovery_pending = False
        self._db: sqlite3.Connection | None = None
        self._writer_queue: Queue[Any] | None = None
        self._writer_thread: Thread | None = None
        self._persistence_error: str | None = None
        self._closed = False
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self._path), check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("CREATE TABLE IF NOT EXISTS session_meta (id INTEGER PRIMARY KEY CHECK(id=1), session_id TEXT NOT NULL, track TEXT, car TEXT, baseline_lap INTEGER NOT NULL, last_cursor INTEGER, complete INTEGER NOT NULL, gap_count INTEGER NOT NULL, blockers TEXT NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS lap_records (session_id TEXT NOT NULL, lap_number INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(session_id, lap_number))")
            self._db.commit()
            self._load()
            self._writer_queue = Queue(maxsize=512)
            self._writer_thread = Thread(
                target=self._writer_loop,
                name="ACC-Strategy-Lap-History-Writer",
                daemon=True,
            )
            self._writer_thread.start()

    @property
    def recovery_pending(self) -> bool:
        with self._lock:
            return self._recovery_pending

    def _load(self) -> None:
        assert self._db is not None
        row = self._db.execute("SELECT session_id, track, car, baseline_lap, last_cursor, complete, gap_count, blockers FROM session_meta WHERE id=1").fetchone()
        if row is None:
            return
        self._session_id, self._track, self._car, self._baseline_lap, self._last_cursor, was_complete, self._gap_count, blockers = row
        self._persisted_complete = bool(was_complete)
        self._complete = self._persisted_complete
        self._blockers = set(json.loads(blockers))
        rows = self._db.execute("SELECT payload FROM lap_records WHERE session_id=? ORDER BY lap_number", (self._session_id,)).fetchall()
        optional_fields = (
            "position", "gap_ahead_ms", "gap_behind_ms", "penalty_time_s",
            "mandatory_pit_done", "driver_stint_left_ms", "rain_intensity",
            "track_grip_status", "air_temp_c", "road_temp_c",
        )
        loaded_records = []
        for (payload,) in rows:
            item = json.loads(payload)
            for field in optional_fields:
                item.setdefault(field, None)
            for field in ("tyre_pressure_psi", "tyre_core_temp_c", "brake_temp_c", "car_damage"):
                item[field] = tuple(item[field])
            loaded_records.append(StrategyLapRecord(**item))
        self._records = loaded_records[-self._max_records:]
        self._recovery_pending = True
        self._complete = False
        self._blockers.add("Persisted lap history is awaiting live ACC session/cursor verification.")

    def _enqueue_persistence(self, operation: tuple[Any, ...]) -> bool:
        queue = self._writer_queue
        if queue is None or self._closed:
            return False
        try:
            queue.put_nowait(operation)
            return True
        except Full:
            self._complete = False
            self._persistence_error = "The compact history persistence queue is full."
            self._blockers.add(self._persistence_error)
            return False

    def _writer_loop(self) -> None:
        assert self._writer_queue is not None
        assert self._db is not None
        while True:
            operation = self._writer_queue.get()
            try:
                if operation is None:
                    break
                kind = operation[0]
                if kind == "reset":
                    self._db.execute("DELETE FROM lap_records")
                elif kind == "record":
                    _, session_id, lap_number, payload = operation
                    self._db.execute(
                        "INSERT OR REPLACE INTO lap_records(session_id,lap_number,payload) VALUES(?,?,?)",
                        (session_id, lap_number, payload),
                    )
                elif kind == "trim":
                    _, session_id, max_records = operation
                    self._db.execute(
                        "DELETE FROM lap_records WHERE session_id=? AND lap_number NOT IN (SELECT lap_number FROM lap_records WHERE session_id=? ORDER BY lap_number DESC LIMIT ?)",
                        (session_id, session_id, max_records),
                    )
                elif kind == "meta":
                    _, values = operation
                    self._db.execute(
                        "INSERT INTO session_meta(id,session_id,track,car,baseline_lap,last_cursor,complete,gap_count,blockers) VALUES(1,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET session_id=excluded.session_id,track=excluded.track,car=excluded.car,baseline_lap=excluded.baseline_lap,last_cursor=excluded.last_cursor,complete=excluded.complete,gap_count=excluded.gap_count,blockers=excluded.blockers",
                        values,
                    )
                self._db.commit()
            except Exception as exc:
                with self._lock:
                    self._complete = False
                    self._persistence_error = f"{type(exc).__name__}: {exc}"
                    self._blockers.add("Compact lap history could not be persisted.")
            finally:
                self._writer_queue.task_done()
        self._db.close()
        self._db = None

    def _persist_meta(self) -> None:
        if self._db is None or self._session_id is None:
            return
        values = (
            self._session_id, self._track, self._car, self._baseline_lap,
            self._last_cursor, int(self._complete), self._gap_count,
            json.dumps(sorted(self._blockers)),
        )
        if self._enqueue_persistence(("meta", values)):
            self._persisted_complete = self._complete

    def _reset_session(self, session_id: str, completed_laps: int, track: str | None, car: str | None) -> None:
        self._session_id = session_id
        self._track, self._car = track, car
        self._baseline_lap = completed_laps
        self._last_cursor = completed_laps
        self._records.clear()
        self._last_event_sequence = None
        self._gap_count = 0
        self._complete = completed_laps == 0
        self._persisted_complete = self._complete
        self._recovery_pending = False
        self._blockers = set() if self._complete else {"Application attached after the session had already completed laps; earlier lap history is unavailable."}
        self._enqueue_persistence(("reset",))
        self._persist_meta()

    def observe_live_cursor(self, session_id: str, completed_laps: int, *, track: str | None = None, car: str | None = None) -> None:
        """Verify session continuity against fresh decoded Graphics progress."""
        with self._lock:
            if self._session_id is None:
                self._reset_session(session_id, completed_laps, track, car)
                return
            identity_mismatch = (
                self._session_id != session_id
                or (self._track is not None and track is not None and self._track != track)
                or (self._car is not None and car is not None and self._car != car)
            )
            if identity_mismatch:
                self._reset_session(session_id, completed_laps, track, car)
                return
            recovery_was_pending = self._recovery_pending
            if self._recovery_pending:
                latest = self._records[-1].lap_number if self._records else self._baseline_lap
                if completed_laps == latest:
                    self._recovery_pending = False
                    self._complete = bool(self._persisted_complete and self._gap_count == 0)
                    self._blockers.discard("Persisted lap history is awaiting live ACC session/cursor verification.")
                    if not self._complete and self._gap_count:
                        self._blockers.add("Persisted history contains an earlier data gap.")
                else:
                    self._recovery_pending = False
                    self._complete = False
                    self._gap_count += 1
                    self._blockers.add("Live ACC lap cursor does not match the last persisted lap; one or more lap records may be missing.")
            elif self._last_cursor is not None and completed_laps > self._last_cursor:
                self._complete = False
                self._gap_count += 1
                self._blockers.add("ACC lap cursor advanced without matching completed-lap records.")
            elif self._last_cursor is not None and completed_laps < self._last_cursor:
                self._reset_session(session_id, completed_laps, track, car)
                return
            changed = recovery_was_pending or self._last_cursor != completed_laps
            self._last_cursor = completed_laps
            if self._track is None and track is not None:
                self._track = track
                changed = True
            if self._car is None and car is not None:
                self._car = car
                changed = True
            if changed:
                self._persist_meta()

    @staticmethod
    def _tuple_values(value: Any) -> tuple[float | None, ...]:
        if not isinstance(value, (tuple, list)):
            return ()
        return tuple(_number(item) for item in value)

    def consume(self, batch: Any, telemetry: Any | None = None) -> None:
        with self._lock:
            changed = bool(batch.events) or bool(batch.gap_detected)
            if batch.gap_detected:
                self._mark_gap("Decoded lap-event delivery had a sequence gap.")
            for event in batch.events:
                if self._last_event_sequence is not None and event.sequence != self._last_event_sequence + 1:
                    self._mark_gap("Decoded lap-event sequence is discontinuous.")
                self._last_event_sequence = event.sequence
                if event.event_type == "lap.completion_gap":
                    self._mark_gap("ACC completed-lap counter skipped one or more laps.")
                    continue
                if event.event_type != "lap.completed" or not event.session_id:
                    continue
                payload = event.payload
                lap_number = payload.get("lap_number")
                if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
                    self._mark_gap("Completed-lap event has no valid lap number.")
                    continue
                if self._session_id != event.session_id:
                    self._reset_session(event.session_id, lap_number - 1, self._track, self._car)
                if self._records and lap_number <= self._records[-1].lap_number:
                    self._mark_gap("Completed-lap event order is not strictly increasing.")
                    continue
                if self._records and lap_number > self._records[-1].lap_number + 1:
                    self._mark_gap("Completed-lap records contain a lap-number gap.")

                strategy_sample = payload.get("strategy_sample")
                physics_values = None
                graphics_values = None
                physics_sequence = None
                physics_timestamp = None
                if isinstance(strategy_sample, Mapping):
                    candidate_physics = strategy_sample.get("physics")
                    candidate_graphics = strategy_sample.get("graphics")
                    if isinstance(candidate_physics, Mapping):
                        physics_values = candidate_physics
                        physics_timestamp = candidate_physics.get("capture_timestamp_ns")
                        physics_sequence = candidate_physics.get("capture_sequence")
                    if isinstance(candidate_graphics, Mapping):
                        graphics_values = candidate_graphics
                else:
                    # Compatibility for direct unit/legacy event producers.
                    physics_view = getattr(telemetry, "physics", None)
                    graphics_view = getattr(telemetry, "graphics", None)
                    physics_data = physics_view.data if physics_view is not None and physics_view.is_fresh else None
                    graphics_data = graphics_view.data if graphics_view is not None and graphics_view.is_fresh else None
                    physics_timestamp = physics_view.capture_timestamp_ns if physics_data is not None else None
                    physics_sequence = physics_view.capture_sequence if physics_data is not None else None
                    physics_values = {
                        "fuel_remaining_l": getattr(physics_data, "fuel_kg", None),
                        "tyre_pressure_psi": getattr(physics_data, "tyre_pressure_psi", ()),
                        "tyre_core_temp_c": getattr(physics_data, "tyre_core_temp_c", ()),
                        "brake_temp_c": getattr(physics_data, "brake_temp_c", ()),
                        "car_damage": getattr(physics_data, "car_damage", ()),
                        "air_temp_c": getattr(physics_data, "air_temp_c", None),
                        "road_temp_c": getattr(physics_data, "road_temp_c", None),
                    } if physics_data is not None else None
                    graphics_values = {
                        "fuel_per_lap_l": getattr(graphics_data, "fuel_per_lap_l", None),
                        "fuel_used_l": getattr(graphics_data, "used_fuel_l", None),
                        "tyre_compound": getattr(graphics_data, "tyre_compound", None),
                        "position": getattr(graphics_data, "position", None),
                        "gap_ahead_ms": getattr(graphics_data, "gap_ahead_ms", None),
                        "gap_behind_ms": getattr(graphics_data, "gap_behind_ms", None),
                        "penalty_time_s": getattr(graphics_data, "penalty_time_s", None),
                        "mandatory_pit_done": getattr(graphics_data, "mandatory_pit_done", None),
                        "driver_stint_left_ms": getattr(graphics_data, "driver_stint_left_ms", None),
                        "rain_intensity": getattr(graphics_data, "rain_intensity", None),
                        "track_grip_status": getattr(graphics_data, "track_grip_status", None),
                    } if graphics_data is not None else None

                boundary_ns = event.source_timestamp_ns
                physics_near_boundary = (
                    physics_values is not None
                    and isinstance(physics_timestamp, int)
                    and boundary_ns is not None
                    and abs(physics_timestamp - boundary_ns) <= 1_000_000_000
                )
                if not physics_near_boundary:
                    physics_values = None
                    physics_sequence = None
                    physics_timestamp = None
                validity = payload.get("lap_valid") if isinstance(payload.get("lap_valid"), bool) else None
                out_lap = payload.get("out_lap") if isinstance(payload.get("out_lap"), bool) else None
                classification = "classified" if validity is not None and out_lap is not None else "pending_classification"
                record = StrategyLapRecord(
                    session_id=event.session_id, lap_number=lap_number,
                    lap_time_ms=payload.get("lap_time_ms") if isinstance(payload.get("lap_time_ms"), int) and not isinstance(payload.get("lap_time_ms"), bool) else None,
                    lap_valid=validity, out_lap=out_lap, classification=classification,
                    fuel_remaining_l=_number(physics_values.get("fuel_remaining_l")) if physics_values is not None else None,
                    fuel_per_lap_l=_number(graphics_values.get("fuel_per_lap_l")) if graphics_values is not None else None,
                    fuel_used_l=_number(graphics_values.get("fuel_used_l")) if graphics_values is not None else None,
                    tyre_compound=graphics_values.get("tyre_compound") if graphics_values is not None else None,
                    position=_integer(graphics_values.get("position")) if graphics_values is not None else None,
                    gap_ahead_ms=_integer(graphics_values.get("gap_ahead_ms")) if graphics_values is not None else None,
                    gap_behind_ms=_integer(graphics_values.get("gap_behind_ms")) if graphics_values is not None else None,
                    penalty_time_s=_number(graphics_values.get("penalty_time_s")) if graphics_values is not None else None,
                    mandatory_pit_done=graphics_values.get("mandatory_pit_done") if graphics_values is not None and isinstance(graphics_values.get("mandatory_pit_done"), bool) else None,
                    driver_stint_left_ms=_integer(graphics_values.get("driver_stint_left_ms")) if graphics_values is not None else None,
                    rain_intensity=_integer(graphics_values.get("rain_intensity")) if graphics_values is not None else None,
                    track_grip_status=_integer(graphics_values.get("track_grip_status")) if graphics_values is not None else None,
                    tyre_pressure_psi=self._tuple_values(physics_values.get("tyre_pressure_psi")) if physics_values is not None else (),
                    tyre_core_temp_c=self._tuple_values(physics_values.get("tyre_core_temp_c")) if physics_values is not None else (),
                    brake_temp_c=self._tuple_values(physics_values.get("brake_temp_c")) if physics_values is not None else (),
                    car_damage=self._tuple_values(physics_values.get("car_damage")) if physics_values is not None else (),
                    air_temp_c=_number(physics_values.get("air_temp_c")) if physics_values is not None else None,
                    road_temp_c=_number(physics_values.get("road_temp_c")) if physics_values is not None else None,
                    graphics_capture_sequence=getattr(event, "source_capture_sequence", None),
                    graphics_capture_timestamp_ns=event.source_timestamp_ns,
                    physics_capture_sequence=physics_sequence,
                    physics_capture_timestamp_ns=physics_timestamp,
                    event_sequence=event.sequence,
                )
                self._records.append(record)
                if len(self._records) > self._max_records:
                    self._records = self._records[-self._max_records:]
                if record.lap_valid is None:
                    self._blockers.add("ACC lap validity is unavailable for one or more records.")
                if record.out_lap is None:
                    self._blockers.add("Existing Overview out-lap classification is unavailable for one or more records.")
                if self._db is not None:
                    self._enqueue_persistence((
                        "record", record.session_id, record.lap_number,
                        json.dumps(asdict(record)),
                    ))
                    self._enqueue_persistence((
                        "trim", record.session_id, self._max_records
                    ))
                self._last_cursor = lap_number
            if changed:
                self._persist_meta()

    def _mark_gap(self, reason: str) -> None:
        self._complete = False
        self._gap_count += 1
        self._blockers.add(reason)

    def read_records(self, *, limit: int | None = None) -> tuple[StrategyLapRecord, ...]:
        """Return immutable compact records for internal strategy consumers."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            records = self._records if limit is None else self._records[-limit:]
            return tuple(records)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            eligible = [r for r in self._records if r.lap_valid is True and r.out_lap is False and r.classification == "classified" and r.lap_time_ms]
            return {
                "session_id": self._session_id,
                "track": self._track,
                "car": self._car,
                "observed_lap_count": len(self._records),
                "valid_timed_lap_count": len(eligible),
                "recent_valid_lap_times_ms": [r.lap_time_ms for r in eligible[-5:]],
                "recent_records": [asdict(r) for r in self._records[-10:]],
                "history_complete": self._complete and not self._recovery_pending,
                "history_scope": "current_session_recent_window",
                "event_gap_count": self._gap_count,
                "classification_pending_count": sum(r.classification != "classified" for r in self._records),
                "blockers": sorted(self._blockers),
                "high_resolution_telemetry_stored": False,
                "persistence_error": self._persistence_error,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._persist_meta()
            self._closed = True
            queue = self._writer_queue
            thread = self._writer_thread
        if queue is not None and thread is not None:
            queue.put(None)
            thread.join()
            self._writer_thread = None
            self._writer_queue = None
