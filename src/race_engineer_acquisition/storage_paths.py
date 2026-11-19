"""Shared repository-relative storage locations for generated application data.

The project root is derived from this module's location, never from the process
working directory, user profile, drive letter, or a machine-specific path.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3


def project_root() -> Path:
    """Return the repository root containing the src/ directory."""
    return Path(__file__).resolve().parents[2]


def performance_hub_data_dir() -> Path:
    """Return the repository-relative Performance Hub data directory."""
    return project_root() / "user_data" / "PerformanceHub"


def default_performance_archive_path() -> Path:
    return performance_hub_data_dir() / "lap_archive.sqlite3"


def default_monitor_reports_dir() -> Path:
    return performance_hub_data_dir() / "monitor_reports"


def _legacy_performance_hub_data_dir() -> Path:
    """Locate the former per-user location solely for one-time data migration."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "RaceEngineerACC" / "PerformanceHub"
    root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return root / "race-engineer-acc" / "performance_hub"


def migrate_legacy_performance_hub_data() -> dict[str, bool]:
    """Copy legacy archive/evidence into the repository-relative location.

    The SQLite backup API captures a consistent database including committed
    WAL content. Legacy files are deliberately retained as a recovery copy.
    Existing destination files are never overwritten.
    """
    legacy_dir = _legacy_performance_hub_data_dir()
    target_dir = performance_hub_data_dir()
    if legacy_dir.resolve() == target_dir.resolve() or not legacy_dir.exists():
        return {"archive_copied": False, "reports_copied": False}

    target_dir.mkdir(parents=True, exist_ok=True)
    archive_copied = False
    reports_copied = False
    legacy_db = legacy_dir / "lap_archive.sqlite3"
    target_db = target_dir / "lap_archive.sqlite3"

    if legacy_db.is_file() and not target_db.exists():
        temporary_db = target_dir / "lap_archive.sqlite3.migrating"
        if temporary_db.exists():
            temporary_db.unlink()
        source_uri = legacy_db.resolve().as_uri() + "?mode=ro"
        source = sqlite3.connect(source_uri, uri=True, timeout=10.0)
        destination = sqlite3.connect(str(temporary_db), timeout=10.0)
        try:
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise sqlite3.DatabaseError(
                    f"Legacy Performance Hub archive integrity check failed: {integrity}"
                )
            destination.commit()
        except Exception:
            destination.close()
            source.close()
            temporary_db.unlink(missing_ok=True)
            raise
        else:
            destination.close()
            source.close()
        os.replace(temporary_db, target_db)
        archive_copied = True

    legacy_reports = legacy_dir / "monitor_reports"
    target_reports = target_dir / "monitor_reports"
    if legacy_reports.is_dir():
        target_reports.mkdir(parents=True, exist_ok=True)
        for source_path in legacy_reports.rglob("*"):
            relative = source_path.relative_to(legacy_reports)
            destination_path = target_reports / relative
            if source_path.is_dir():
                destination_path.mkdir(parents=True, exist_ok=True)
            elif not destination_path.exists():
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)
                reports_copied = True

    return {"archive_copied": archive_copied, "reports_copied": reports_copied}
