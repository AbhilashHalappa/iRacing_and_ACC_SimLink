from __future__ import annotations

import sqlite3

from race_engineer_acquisition import storage_paths


def test_performance_hub_paths_are_anchored_to_repository_not_working_directory(tmp_path, monkeypatch):
    expected_root = storage_paths.Path(storage_paths.__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)

    assert storage_paths.project_root() == expected_root
    assert storage_paths.performance_hub_data_dir() == expected_root / "user_data" / "PerformanceHub"
    assert storage_paths.default_performance_archive_path() == (
        expected_root / "user_data" / "PerformanceHub" / "lap_archive.sqlite3"
    )
    assert storage_paths.default_monitor_reports_dir() == (
        expected_root / "user_data" / "PerformanceHub" / "monitor_reports"
    )


def test_legacy_archive_and_session_evidence_are_copied_without_deleting_source(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy" / "PerformanceHub"
    target_dir = tmp_path / "repository" / "user_data" / "PerformanceHub"
    legacy_dir.mkdir(parents=True)
    legacy_db = legacy_dir / "lap_archive.sqlite3"
    with sqlite3.connect(legacy_db) as db:
        db.execute("CREATE TABLE laps (lap_number INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO laps VALUES (7)")

    legacy_reports = legacy_dir / "monitor_reports" / "session-one"
    legacy_reports.mkdir(parents=True)
    (legacy_reports / "laps_session-one.csv").write_text("lap_number\\n7\\n", encoding="utf-8")

    monkeypatch.setattr(storage_paths, "_legacy_performance_hub_data_dir", lambda: legacy_dir)
    monkeypatch.setattr(storage_paths, "performance_hub_data_dir", lambda: target_dir)

    result = storage_paths.migrate_legacy_performance_hub_data()

    assert result == {"archive_copied": True, "reports_copied": True}
    with sqlite3.connect(target_dir / "lap_archive.sqlite3") as db:
        assert db.execute("SELECT lap_number FROM laps").fetchall() == [(7,)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert (target_dir / "monitor_reports" / "session-one" / "laps_session-one.csv").read_text(
        encoding="utf-8"
    ) == "lap_number\\n7\\n"
    assert legacy_db.is_file()
    assert (legacy_reports / "laps_session-one.csv").is_file()


def test_migration_never_overwrites_existing_destination_archive(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy" / "PerformanceHub"
    target_dir = tmp_path / "repository" / "user_data" / "PerformanceHub"
    legacy_dir.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    with sqlite3.connect(legacy_dir / "lap_archive.sqlite3") as db:
        db.execute("CREATE TABLE laps (lap_number INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO laps VALUES (1)")
    with sqlite3.connect(target_dir / "lap_archive.sqlite3") as db:
        db.execute("CREATE TABLE laps (lap_number INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO laps VALUES (2)")

    monkeypatch.setattr(storage_paths, "_legacy_performance_hub_data_dir", lambda: legacy_dir)
    monkeypatch.setattr(storage_paths, "performance_hub_data_dir", lambda: target_dir)

    result = storage_paths.migrate_legacy_performance_hub_data()

    assert result["archive_copied"] is False
    with sqlite3.connect(target_dir / "lap_archive.sqlite3") as db:
        assert db.execute("SELECT lap_number FROM laps").fetchall() == [(2,)]
    assert (legacy_dir / "lap_archive.sqlite3").is_file()
