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
from threading import RLock
from typing import Any


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
    tyre_pressure_psi: tuple[float | None, ...]
    tyre_core_temp_c: tuple[float | None, ...]
    brake_temp_c: tuple[float | None, ...]
    car_damage: tuple[float | None, ...]
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
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self._path))
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("CREATE TABLE IF NOT EXISTS session_meta (id INTEGER PRIMARY KEY CHECK(id=1), session_id TEXT NOT NULL, track TEXT, car TEXT, baseline_lap INTEGER NOT NULL, last_cursor INTEGER, complete INTEGER NOT NULL, gap_count INTEGER NOT NULL, blockers TEXT NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS lap_records (session_id TEXT NOT NULL, lap_number INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(session_id, lap_number))")
            self._db.commit()
            self._load()

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
        self._records = [StrategyLapRecord(**{**item, "tyre_pressure_psi": tuple(item["tyre_pressure_psi"]), "tyre_core_temp_c": tuple(item["tyre_core_temp_c"]), "brake_temp_c": tuple(item["brake_temp_c"]), "car_damage": tuple(item["car_damage"])}) for (payload,) in rows for item in (json.loads(payload),)]
        self._recovery_pending = True
        self._complete = False
        self._blockers.add("Persisted lap history is awaiting live ACC session/cursor verification.")

    def _persist_meta(self) -> None:
        if self._db is None or self._session_id is None:
            return
        self._db.execute(
            "INSERT INTO session_meta(id,session_id,track,car,baseline_lap,last_cursor,complete,gap_count,blockers) VALUES(1,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET session_id=excluded.session_id,track=excluded.track,car=excluded.car,baseline_lap=excluded.baseline_lap,last_cursor=excluded.last_cursor,complete=excluded.complete,gap_count=excluded.gap_count,blockers=excluded.blockers",
            (self._session_id, self._track, self._car, self._baseline_lap, self._last_cursor, int(self._complete), self._gap_count, json.dumps(sorted(self._blockers))),
        )
        self._db.commit()
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
        if self._db is not None:
            self._db.execute("DELETE FROM lap_records")
            self._db.commit()
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
            if self._recovery_pending:
                latest = self._records[-1].lap_number if self._records else self._baseline_lap
                if completed_laps == latest:
                    self._recovery_pending = False
                    self._complete = bool(self._persisted_complete and self._gap_count == 0)
                    self._blockers.discard("Persisted lap history is awaiting live ACC session/cursor verification.")
                    if not self._complete:
                        self._blockers.add("Persisted history contains an earlier data gap.")
                else:
                    self._recovery_pending = False
                    self._complete = False
                    self._gap_count += 1
                    self._blockers.add("Live ACC lap cursor does not match the last persisted lap; one or more lap records may be missing.")
            elif self._last_cursor is not None and completed_laps > self._last_cursor:
                # The event consumer should have delivered these transitions
                # before cursor reconciliation. A cursor-only advance is loss.
                self._complete = False
                self._gap_count += 1
                self._blockers.add("ACC lap cursor advanced without matching completed-lap records.")
            elif self._last_cursor is not None and completed_laps < self._last_cursor:
                self._reset_session(session_id, completed_laps, track, car)
                return
            self._last_cursor = completed_laps
            if self._track is None:
                self._track = track
            if self._car is None:
                self._car = car
            self._persist_meta()

    @staticmethod
    def _tuple_values(value: Any) -> tuple[float | None, ...]:
        if not isinstance(value, (tuple, list)):
            return ()
        return tuple(_number(item) for item in value)

    def consume(self, batch: Any, telemetry: Any | None = None) -> None:
        with self._lock:
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
                if self._session_id != event.session_id:
                    # Establish a conservative baseline. Without an observed
                    # zero-lap start, the earlier portion of this session is unknown.
                    self._reset_session(event.session_id, max(0, int(event.payload.get("lap_number", 1)) - 1), self._track, self._car)
                    if self._baseline_lap > 0:
                        self._complete = False
                payload = event.payload
                lap_number = payload.get("lap_number")
                if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
                    self._mark_gap("Completed-lap event has no valid lap number.")
                    continue
                if self._records and lap_number <= self._records[-1].lap_number:
                    self._mark_gap("Completed-lap event order is not strictly increasing.")
                    continue
                physics_view = getattr(telemetry, "physics", None)
                graphics_view = getattr(telemetry, "graphics", None)
                physics = physics_view.data if physics_view is not None and physics_view.is_fresh else None
                graphics = graphics_view.data if graphics_view is not None and graphics_view.is_fresh else None
                boundary_ns = event.source_timestamp_ns
                physics_ts = physics_view.capture_timestamp_ns if physics is not None else None
                physics_near_boundary = (
                    physics is not None and physics_ts is not None and boundary_ns is not None
                    and abs(physics_ts - boundary_ns) <= 1_000_000_000
                )
                if not physics_near_boundary:
                    physics = None
                validity = payload.get("lap_valid") if payload.get("validity_known") else None
                out_lap = payload.get("out_lap") if isinstance(payload.get("out_lap"), bool) else None
                classification = "classified" if validity is not None and out_lap is not None else "pending_classification"
                record = StrategyLapRecord(
                    session_id=event.session_id, lap_number=lap_number,
                    lap_time_ms=payload.get("lap_time_ms") if isinstance(payload.get("lap_time_ms"), int) else None,
                    lap_valid=validity, out_lap=out_lap, classification=classification,
                    fuel_remaining_l=_number(getattr(physics, "fuel_kg", None)) if physics is not None else None,
                    fuel_per_lap_l=_number(getattr(graphics, "fuel_per_lap_l", None)) if graphics is not None else None,
                    fuel_used_l=_number(getattr(graphics, "used_fuel_l", None)) if graphics is not None else None,
                    tyre_compound=getattr(graphics, "tyre_compound", None) if graphics is not None else None,
                    tyre_pressure_psi=self._tuple_values(getattr(physics, "tyre_pressure_psi", None)) if physics is not None else (),
                    tyre_core_temp_c=self._tuple_values(getattr(physics, "tyre_core_temp_c", None)) if physics is not None else (),
                    brake_temp_c=self._tuple_values(getattr(physics, "brake_temp_c", None)) if physics is not None else (),
                    car_damage=self._tuple_values(getattr(physics, "car_damage", None)) if physics is not None else (),
                    graphics_capture_sequence=getattr(graphics_view, "capture_sequence", None) if graphics_view is not None else None,
                    graphics_capture_timestamp_ns=getattr(graphics_view, "capture_timestamp_ns", None) if graphics_view is not None else None,
                    physics_capture_sequence=getattr(physics_view, "capture_sequence", None) if physics_near_boundary else None,
                    physics_capture_timestamp_ns=physics_ts if physics_near_boundary else None,
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
                    self._db.execute("INSERT OR REPLACE INTO lap_records(session_id,lap_number,payload) VALUES(?,?,?)", (record.session_id, record.lap_number, json.dumps(asdict(record))))
                    self._db.commit()
                self._last_cursor = lap_number
            self._persist_meta()

    def _mark_gap(self, reason: str) -> None:
        self._complete = False
        self._gap_count += 1
        self._blockers.add(reason)

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
            }

    def close(self) -> None:
        with self._lock:
            self._persist_meta()
            if self._db is not None:
                self._db.close()
                self._db = None
