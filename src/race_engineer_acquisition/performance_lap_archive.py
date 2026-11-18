"""Transactional, bounded per-lap archive for Performance Hub.

This module is downstream of the Stage 2 candidate-lap assembler. It owns one
SQLite writer connection, stores compressed source-preserving traces, and
applies the accepted count/age/global-size retention policy. It never touches
ACC shared memory, acquisition buffers, decoder workers, or UI state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
import time
from typing import Any, Callable, Mapping
import zlib


@dataclass(frozen=True, slots=True)
class PerformanceArchiveConfig:
    max_storage_bytes: int = 2 * 1024 * 1024 * 1024
    max_age_days: int = 365
    recent_laps_per_identity: int = 30
    compression_level: int = 6
    diagnostic_limit: int = 5000

    def __post_init__(self) -> None:
        if self.max_storage_bytes < 1:
            raise ValueError("max_storage_bytes must be positive")
        if self.max_age_days < 1:
            raise ValueError("max_age_days must be positive")
        if self.recent_laps_per_identity < 1:
            raise ValueError("recent_laps_per_identity must be positive")
        if not 0 <= self.compression_level <= 9:
            raise ValueError("compression_level must be between 0 and 9")
        if self.diagnostic_limit < 1:
            raise ValueError("diagnostic_limit must be positive")


@dataclass(frozen=True, slots=True)
class LapArchiveContext:
    car_model: str | None = None
    track: str | None = None
    track_configuration: str | None = None
    session_index: int | None = None
    session_type: int | None = None
    weather: Mapping[str, Any] | None = None
    metadata_source_timestamps_ns: Mapping[str, int | None] | None = None


@dataclass(frozen=True, slots=True)
class ArchiveWriteResult:
    completed_stored: int = 0
    compact_stored: int = 0
    trace_rejected: int = 0
    diagnostics_stored: int = 0
    storage_bytes: int = 0
    storage_blocked: bool = False


def default_performance_archive_path() -> Path:
    """Return a per-user writable archive path without depending on the CWD."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "RaceEngineerACC" / "PerformanceHub" / "lap_archive.sqlite3"
    root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return root / "race-engineer-acc" / "performance_hub" / "lap_archive.sqlite3"


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported trace value: {type(value).__name__}")


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (value == value)
        and value not in (float("inf"), float("-inf"))
    )


class PerformanceLapArchive:
    """Single-owner SQLite archive with atomic trace finalization and retention."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        config: PerformanceArchiveConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else default_performance_archive_path()
        self.config = config or PerformanceArchiveConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._closed = False
        self._last_error: str | None = None
        self._storage_limit_rejections = 0
        self._db: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None,
                                 check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            version = int(db.execute("PRAGMA user_version").fetchone()[0])
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"Archive schema {version} is newer than supported "
                    f"schema {self.SCHEMA_VERSION}"
                )
            self._create_schema(db)
            integrity = db.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise sqlite3.DatabaseError(f"Archive integrity check failed: {integrity}")
            self._db = db
            self._apply_startup_retention()
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            if self._db is not None:
                self._db.close()
                self._db = None

    @classmethod
    def _create_schema(cls, db: sqlite3.Connection) -> None:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                first_seen_utc TEXT NOT NULL,
                session_index INTEGER,
                session_type INTEGER
            );
            CREATE TABLE IF NOT EXISTS laps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                lap_number INTEGER NOT NULL,
                car_model TEXT,
                track TEXT,
                track_configuration TEXT,
                completed_at_utc TEXT NOT NULL,
                lap_time_ms INTEGER,
                lap_valid INTEGER,
                out_lap INTEGER,
                start_timestamp_ns INTEGER NOT NULL,
                end_timestamp_ns INTEGER NOT NULL,
                physics_sample_count INTEGER NOT NULL,
                graphics_sample_count INTEGER NOT NULL,
                weather_json TEXT NOT NULL,
                quality_json TEXT NOT NULL,
                trace_blob BLOB,
                trace_bytes INTEGER NOT NULL DEFAULT 0,
                trace_status TEXT NOT NULL,
                reason TEXT,
                pinned_pb INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session_id, lap_number),
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_laps_identity_recent
                ON laps(car_model, track, track_configuration, completed_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_laps_pinned
                ON laps(pinned_pb, trace_bytes);
            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                lap_number INTEGER,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
        """)
        db.execute(f"PRAGMA user_version={cls.SCHEMA_VERSION}")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _apply_startup_retention(self) -> None:
        if self._db is None:
            return
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._apply_age_retention(self._db, self._now())
            self._apply_global_retention(self._db)
            self._trim_diagnostics(self._db)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def _apply_age_retention(self, db: sqlite3.Connection, now: datetime) -> None:
        cutoff = _utc_iso(now - timedelta(days=self.config.max_age_days))
        db.execute(
            """UPDATE laps SET trace_blob=NULL, trace_bytes=0,
               trace_status='evicted_age'
               WHERE pinned_pb=0 AND trace_blob IS NOT NULL
               AND completed_at_utc < ?""",
            (cutoff,),
        )
        db.execute(
            """DELETE FROM laps WHERE pinned_pb=0 AND completed_at_utc < ?
               AND trace_blob IS NULL""",
            (cutoff,),
        )
        db.execute("DELETE FROM sessions WHERE session_id NOT IN (SELECT DISTINCT session_id FROM laps)")

    def _apply_global_retention(self, db: sqlite3.Connection) -> None:
        total = int(db.execute("SELECT COALESCE(SUM(trace_bytes),0) FROM laps").fetchone()[0])
        if total <= self.config.max_storage_bytes:
            return
        rows = db.execute(
            """SELECT id, trace_bytes FROM laps
               WHERE trace_blob IS NOT NULL AND pinned_pb=0
               ORDER BY completed_at_utc ASC, id ASC"""
        ).fetchall()
        for row_id, size in rows:
            db.execute(
                "UPDATE laps SET trace_blob=NULL, trace_bytes=0, trace_status='evicted_storage' WHERE id=?",
                (row_id,),
            )
            total -= int(size)
            if total <= self.config.max_storage_bytes:
                break

    def _trim_diagnostics(self, db: sqlite3.Connection) -> None:
        db.execute(
            """DELETE FROM diagnostics WHERE id NOT IN (
               SELECT id FROM diagnostics ORDER BY id DESC LIMIT ?
            )""",
            (self.config.diagnostic_limit,),
        )

    @staticmethod
    def _identity(context: LapArchiveContext) -> tuple[str | None, str | None, str | None]:
        car = context.car_model.strip() if isinstance(context.car_model, str) else None
        track = context.track.strip() if isinstance(context.track, str) else None
        config = context.track_configuration if isinstance(context.track_configuration, str) else None
        return car or None, track or None, config

    @staticmethod
    def _context(value: LapArchiveContext | Mapping[str, Any] | None) -> LapArchiveContext:
        if isinstance(value, LapArchiveContext):
            return value
        if isinstance(value, Mapping):
            return LapArchiveContext(
                car_model=value.get("car_model"),
                track=value.get("track"),
                track_configuration=value.get("track_configuration"),
                session_index=value.get("session_index"),
                session_type=value.get("session_type"),
                weather=value.get("weather"),
                metadata_source_timestamps_ns=value.get("metadata_source_timestamps_ns"),
            )
        return LapArchiveContext()

    def _encode_trace(self, trace: Any) -> tuple[bytes, dict[str, Any]]:
        physics_samples = tuple(_get(trace, "physics_samples", ()) or ())
        graphics_samples = tuple(_get(trace, "graphics_samples", ()) or ())
        if not physics_samples or not graphics_samples:
            raise ValueError("A retained trace requires Physics and Graphics samples")

        physics_payload: list[dict[str, Any]] = []
        for sample in physics_samples:
            data = _get(sample, "data")
            physics_payload.append({
                "capture_sequence": _get(sample, "capture_sequence"),
                "capture_timestamp_ns": _get(sample, "capture_timestamp_ns"),
                "data": _jsonable(data),
            })

        graphics_payload: list[dict[str, Any]] = []
        position_count = 0
        progress_count = 0
        for sample in graphics_samples:
            data = _get(sample, "data")
            progress = _get(data, "normalized_car_position")
            distance = _get(data, "distance_traveled_m")
            world = _get(data, "player_world_position")
            if (
                isinstance(world, (tuple, list)) and len(world) >= 2
                and sum(_finite_number(item) for item in world) >= 2
            ):
                position_count += 1
            if _finite_number(progress):
                progress_count += 1
            graphics_payload.append({
                "capture_sequence": _get(sample, "capture_sequence"),
                "capture_timestamp_ns": _get(sample, "capture_timestamp_ns"),
                "normalized_car_position": progress,
                "distance_traveled_m": distance,
                "player_world_position": _jsonable(world),
                "packet_id": _get(data, "packet_id"),
            })

        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "session_id": _get(trace, "session_id"),
            "lap_number": _get(trace, "lap_number"),
            "physics": physics_payload,
            "graphics": graphics_payload,
        }
        raw = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        compressed = zlib.compress(raw, level=self.config.compression_level)
        quality = {
            "physics_sample_count": len(physics_payload),
            "graphics_sample_count": len(graphics_payload),
            "graphics_position_sample_count": position_count,
            "graphics_progress_sample_count": progress_count,
            "racing_line_available": position_count > 0,
            "source_sequences_preserved": True,
            "source_timestamps_preserved": True,
        }
        return compressed, quality

    def _insert_session(self, db: sqlite3.Connection, session_id: str,
                        context: LapArchiveContext, now_iso: str) -> None:
        db.execute(
            """INSERT INTO sessions(session_id,first_seen_utc,session_index,session_type)
               VALUES(?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 session_index=COALESCE(excluded.session_index,sessions.session_index),
                 session_type=COALESCE(excluded.session_type,sessions.session_type)""",
            (session_id, now_iso, context.session_index, context.session_type),
        )

    def _store_lap(
        self, db: sqlite3.Connection, lap: Any, context: LapArchiveContext,
        now_iso: str, *, compact: bool,
    ) -> tuple[bool, bool]:
        session_id = _get(lap, "session_id")
        lap_number = _get(lap, "lap_number")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Lap archive record has no session_id")
        if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
            raise ValueError("Lap archive record has an invalid lap_number")
        if db.execute(
            "SELECT 1 FROM laps WHERE session_id=? AND lap_number=?",
            (session_id, lap_number),
        ).fetchone():
            return False, False

        self._insert_session(db, session_id, context, now_iso)
        car, track, track_config = self._identity(context)
        identity_complete = car is not None and track is not None and track_config is not None
        requested_trace = not compact
        trace_blob: bytes | None = None
        quality: dict[str, Any] = {
            "physics_sample_count": int(
                _get(lap, "physics_sample_count", len(_get(lap, "physics_samples", ()) or ())) or 0
            ),
            "graphics_sample_count": int(
                _get(lap, "graphics_sample_count", len(_get(lap, "graphics_samples", ()) or ())) or 0
            ),
            "racing_line_available": False,
            "source_sequences_preserved": False,
            "source_timestamps_preserved": False,
        }
        trace_status = "compact_metadata" if compact else "identity_incomplete"
        reason = _get(lap, "reason") if compact else None
        if not compact:
            try:
                trace_blob, quality = self._encode_trace(lap)
                trace_status = "retained" if identity_complete else "identity_incomplete"
            except Exception as exc:
                compact = True
                reason = f"trace_unavailable:{type(exc).__name__}"
                trace_status = "compact_metadata"

        if trace_blob is not None:
            current_pinned = db.execute(
                """SELECT id,lap_time_ms,trace_bytes FROM laps
                   WHERE car_model=? AND track=? AND track_configuration=?
                   AND pinned_pb=1 AND trace_blob IS NOT NULL LIMIT 1""",
                (car, track, track_config),
            ).fetchone() if identity_complete else None
            new_time = _get(lap, "lap_time_ms")
            becomes_pb = identity_complete and (
                current_pinned is None
                or (isinstance(new_time, int) and new_time > 0
                    and new_time < int(current_pinned[1] or 0))
            )
            pinned_bytes = int(db.execute(
                "SELECT COALESCE(SUM(trace_bytes),0) FROM laps WHERE pinned_pb=1 AND trace_blob IS NOT NULL"
            ).fetchone()[0])
            if becomes_pb and current_pinned is not None:
                pinned_bytes -= int(current_pinned[2])
            if pinned_bytes + len(trace_blob) > self.config.max_storage_bytes:
                trace_blob = None
                trace_status = "rejected_storage_limit"
                reason = "global_storage_limit_preserving_pinned_references"
                self._storage_limit_rejections += 1

        lap_valid_value = True if requested_trace else _get(lap, "lap_valid")
        out_lap_value = False if requested_trace else _get(lap, "out_lap")
        weather = dict(context.weather or {})
        source_timestamps = dict(context.metadata_source_timestamps_ns or {})
        quality["metadata_source_timestamps_ns"] = source_timestamps
        quality["identity_complete"] = identity_complete
        db.execute(
            """INSERT INTO laps(
                session_id,lap_number,car_model,track,track_configuration,
                completed_at_utc,lap_time_ms,lap_valid,out_lap,
                start_timestamp_ns,end_timestamp_ns,physics_sample_count,
                graphics_sample_count,weather_json,quality_json,trace_blob,
                trace_bytes,trace_status,reason,pinned_pb
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (
                session_id, lap_number, car, track, track_config, now_iso,
                _get(lap, "lap_time_ms"),
                (1 if lap_valid_value is True else 0 if lap_valid_value is False else None),
                (1 if out_lap_value is True else 0 if out_lap_value is False else None),
                int(_get(lap, "start_timestamp_ns", 0) or 0),
                int(_get(lap, "end_timestamp_ns", 0) or 0),
                int(_get(lap, "physics_sample_count", quality["physics_sample_count"]) or 0),
                int(_get(lap, "graphics_sample_count", quality["graphics_sample_count"]) or 0),
                json.dumps(weather, separators=(",", ":"), allow_nan=False),
                json.dumps(quality, separators=(",", ":"), allow_nan=False),
                trace_blob, len(trace_blob) if trace_blob is not None else 0,
                trace_status, reason,
            ),
        )
        row_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])

        if trace_blob is not None and identity_complete:
            if becomes_pb:
                db.execute(
                    """UPDATE laps SET pinned_pb=0 WHERE car_model=? AND track=?
                       AND track_configuration=?""",
                    (car, track, track_config),
                )
                db.execute("UPDATE laps SET pinned_pb=1 WHERE id=?", (row_id,))
            self._apply_identity_retention(db, car, track, track_config)
            self._apply_global_retention(db)
        return True, trace_blob is None and requested_trace

    def _apply_identity_retention(
        self, db: sqlite3.Connection, car: str, track: str, track_config: str
    ) -> None:
        rows = db.execute(
            """SELECT id,pinned_pb FROM laps WHERE car_model=? AND track=?
               AND track_configuration=? AND trace_blob IS NOT NULL
               AND lap_valid=1 AND out_lap=0
               ORDER BY completed_at_utc DESC,id DESC""",
            (car, track, track_config),
        ).fetchall()
        keep = {int(row[0]) for row in rows[:self.config.recent_laps_per_identity]}
        keep.update(int(row[0]) for row in rows if row[1])
        for row_id, _pinned in rows:
            if int(row_id) not in keep:
                db.execute(
                    """UPDATE laps SET trace_blob=NULL,trace_bytes=0,
                       trace_status='evicted_count' WHERE id=?""",
                    (row_id,),
                )

    def write_output(
        self, output: Any, context: LapArchiveContext | Mapping[str, Any] | None = None
    ) -> ArchiveWriteResult:
        """Atomically persist one assembler output and apply all retention rules."""
        if self._db is None or self._closed:
            raise RuntimeError(self._last_error or "Performance lap archive is unavailable")
        archive_context = self._context(context)
        now = self._now()
        now_iso = _utc_iso(now)
        completed_stored = compact_stored = rejected = diagnostics_stored = 0
        db = self._db
        with self._lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._apply_age_retention(db, now)
                for lap in tuple(_get(output, "completed", ()) or ()):
                    inserted, trace_rejected = self._store_lap(
                        db, lap, archive_context, now_iso, compact=False
                    )
                    completed_stored += int(inserted)
                    rejected += int(trace_rejected)
                for lap in tuple(_get(output, "compact", ()) or ()):
                    inserted, _ = self._store_lap(
                        db, lap, archive_context, now_iso, compact=True
                    )
                    compact_stored += int(inserted)
                for diagnostic in tuple(_get(output, "diagnostics", ()) or ()):
                    db.execute(
                        """INSERT INTO diagnostics(session_id,lap_number,kind,detail,created_at_utc)
                           VALUES(?,?,?,?,?)""",
                        (
                            _get(diagnostic, "session_id"), _get(diagnostic, "lap_number"),
                            str(_get(diagnostic, "kind", "unknown")),
                            str(_get(diagnostic, "detail", "")), now_iso,
                        ),
                    )
                    diagnostics_stored += 1
                self._apply_global_retention(db)
                self._trim_diagnostics(db)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return ArchiveWriteResult(
            completed_stored=completed_stored,
            compact_stored=compact_stored,
            trace_rejected=rejected,
            diagnostics_stored=diagnostics_stored,
            storage_bytes=self.storage_bytes,
            storage_blocked=self.storage_blocked,
        )

    @property
    def storage_bytes(self) -> int:
        with self._lock:
            if self._db is None:
                return 0
            row = self._db.execute("SELECT COALESCE(SUM(trace_bytes),0) FROM laps").fetchone()
            return int(row[0] or 0)

    @property
    def storage_blocked(self) -> bool:
        with self._lock:
            if self._db is None:
                return True
            row = self._db.execute(
                "SELECT COALESCE(SUM(trace_bytes),0) FROM laps WHERE pinned_pb=1"
            ).fetchone()
            return int(row[0] or 0) >= self.config.max_storage_bytes

    @property
    def metrics(self) -> dict[str, Any]:
        if self._db is None:
            return {
                "available": False, "path": str(self.path), "last_error": self._last_error,
                "storage_bytes": 0, "storage_limit_bytes": self.config.max_storage_bytes,
                "storage_blocked": True, "storage_limit_rejections": self._storage_limit_rejections,
            }
        with self._lock:
            if self._db is None:
                return {
                    "available": False, "path": str(self.path), "last_error": self._last_error,
                    "storage_bytes": 0, "storage_limit_bytes": self.config.max_storage_bytes,
                    "storage_blocked": True, "storage_limit_rejections": self._storage_limit_rejections,
                }
            counts = self._db.execute(
                """SELECT COUNT(*),SUM(CASE WHEN trace_blob IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN trace_blob IS NULL THEN 1 ELSE 0 END)
                   FROM laps"""
            ).fetchone()
            storage_bytes = int(self._db.execute(
                "SELECT COALESCE(SUM(trace_bytes),0) FROM laps"
            ).fetchone()[0] or 0)
            pinned_bytes = int(self._db.execute(
                "SELECT COALESCE(SUM(trace_bytes),0) FROM laps WHERE pinned_pb=1"
            ).fetchone()[0] or 0)
        return {
            "available": True,
            "path": str(self.path),
            "schema_version": self.SCHEMA_VERSION,
            "lap_metadata_count": int(counts[0] or 0),
            "retained_trace_count": int(counts[1] or 0),
            "compact_metadata_count": int(counts[2] or 0),
            "storage_bytes": storage_bytes,
            "storage_limit_bytes": self.config.max_storage_bytes,
            "storage_blocked": pinned_bytes >= self.config.max_storage_bytes,
            "storage_limit_rejections": self._storage_limit_rejections,
            "max_age_days": self.config.max_age_days,
            "recent_laps_per_identity": self.config.recent_laps_per_identity,
            "last_error": self._last_error,
        }

    def read_laps(
        self, *, car_model: str | None = None, track: str | None = None,
        track_configuration: str | None = None, limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self.path.exists():
            return ()
        uri = self.path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
            clauses: list[str] = []
            values: list[Any] = []
            for column, value in (
                ("car_model", car_model), ("track", track),
                ("track_configuration", track_configuration),
            ):
                if value is not None:
                    clauses.append(f"{column}=?")
                    values.append(value)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = db.execute(
                """SELECT laps.session_id,lap_number,car_model,track,track_configuration,
                   completed_at_utc,lap_time_ms,lap_valid,out_lap,start_timestamp_ns,
                   end_timestamp_ns,physics_sample_count,graphics_sample_count,
                   weather_json,quality_json,trace_status,reason,
                   pinned_pb,trace_bytes,sessions.first_seen_utc
                   FROM laps JOIN sessions ON sessions.session_id=laps.session_id"""
                + where + " ORDER BY completed_at_utc DESC,id DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        keys = (
            "session_id","lap_number","car_model","track","track_configuration",
            "completed_at_utc","lap_time_ms","lap_valid","out_lap",
            "start_timestamp_ns","end_timestamp_ns","physics_sample_count",
            "graphics_sample_count","weather_json",
            "quality_json","trace_status","reason","pinned_pb","trace_bytes",
            "session_first_seen_utc",
        )
        result=[]
        for row in rows:
            item=dict(zip(keys,row))
            item["weather"] = json.loads(item.pop("weather_json"))
            item["quality"] = json.loads(item.pop("quality_json"))
            item["pinned_pb"] = bool(item["pinned_pb"])
            result.append(item)
        return tuple(result)

    def read_trace(self, session_id: str, lap_number: int) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        uri = self.path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
            row = db.execute(
                "SELECT trace_blob,trace_status FROM laps WHERE session_id=? AND lap_number=?",
                (session_id, lap_number),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return json.loads(zlib.decompress(row[0]).decode("utf-8"))
        except Exception as exc:
            return {"status": "corrupt", "error": f"{type(exc).__name__}: {exc}"}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._db is not None:
                db = self._db
                try:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    db.close()
                    self._db = None


class PerformanceLapPersistenceWorker:
    """Drain assembly results and perform all archive I/O on one background thread."""

    def __init__(
        self, capture_worker: Any, archive: PerformanceLapArchive,
        context_provider: Callable[[], LapArchiveContext | Mapping[str, Any] | None],
        *, poll_interval_s: float = 0.02,
    ) -> None:
        self._capture = capture_worker
        self._archive = archive
        self._context_provider = context_provider
        self._poll_interval_s = poll_interval_s
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._processed_output_count = 0
        self._failed_output_count = 0
        self._stored_lap_count = 0
        self._last_error: str | None = None
        self._last_result: dict[str, Any] | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(
                target=self._run, name="ACC-Performance-Lap-Archive-Writer", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        while True:
            output = self._capture.read_result()
            if output is None:
                if self._stop.is_set():
                    return
                self._stop.wait(self._poll_interval_s)
                continue
            try:
                context = self._context_provider()
                result = self._archive.write_output(output, context)
                with self._lock:
                    self._processed_output_count += 1
                    self._stored_lap_count += result.completed_stored + result.compact_stored
                    self._last_result = asdict(result)
            except Exception as exc:
                with self._lock:
                    self._processed_output_count += 1
                    self._failed_output_count += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"

    def close(self, *, timeout: float = 10.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, timeout))
            return not thread.is_alive()
        return True

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "processed_output_count": self._processed_output_count,
                "failed_output_count": self._failed_output_count,
                "stored_lap_count": self._stored_lap_count,
                "last_error": self._last_error,
                "last_result": self._last_result,
            }
