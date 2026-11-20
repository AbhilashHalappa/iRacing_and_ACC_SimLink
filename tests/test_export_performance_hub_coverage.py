import csv

from tools.export_performance_hub_coverage import (
    COLUMNS,
    _coverage_rows_for_trace,
    build_coverage_rows,
    write_session_coverage,
)
from race_engineer_acquisition.performance_lap_archive import (
    GRAPHICS_ARCHIVE_FIELDS,
    PHYSICS_ARCHIVE_FIELDS,
)


def test_field_coverage_separates_missing_keys_null_values_and_capture_provenance():
    physics = {
        "capture_sequence": 11,
        "capture_timestamp_ns": 1001,
        "data": {name: None for name in PHYSICS_ARCHIVE_FIELDS},
    }
    physics["data"]["throttle"] = 0.75
    del physics["data"]["brake"]

    graphics = {
        "capture_sequence": 21,
        "capture_timestamp_ns": 1002,
        **{name: None for name in GRAPHICS_ARCHIVE_FIELDS},
    }
    graphics["sector"] = 2

    rows = _coverage_rows_for_trace(
        {
            "session_id": "run-one",
            "lap_number": 4,
            "trace_status": "retained",
        },
        {"physics": [physics], "graphics": [graphics]},
        {
            "ok": False,
            "physics_missing_archive_fields": ["brake"],
            "graphics_missing_archive_fields": [],
        },
    )

    throttle = next(row for row in rows if row["stream"] == "physics" and row["field"] == "throttle")
    brake = next(row for row in rows if row["stream"] == "physics" and row["field"] == "brake")
    rpm = next(row for row in rows if row["stream"] == "physics" and row["field"] == "rpm")
    sector = next(row for row in rows if row["stream"] == "graphics" and row["field"] == "sector")

    assert throttle["non_null_sample_count"] == 1
    assert throttle["coverage_percent"] == 100.0
    assert brake["missing_key_sample_count"] == 1
    assert brake["null_value_sample_count"] == 0
    assert brake["field_in_all_samples"] is False
    assert rpm["null_value_sample_count"] == 1
    assert rpm["missing_key_sample_count"] == 0
    assert rpm["coverage_percent"] == 0.0
    assert sector["source_sequence_first"] == 21
    assert sector["source_timestamp_first_ns"] == 1002
    assert sector["stream_validation_status"] == "FAIL"


def test_compact_records_export_evidence_without_claiming_full_trace_coverage(tmp_path):
    rows = [{
        "session_id": "run-compact",
        "lap_number": 8,
        "trace_status": "compact_metadata",
        "quality": {
            "graphics_timing_observation_count": 3,
            "sector_evidence": {"observation_count": 2},
        },
    }]

    result = build_coverage_rows(rows, tmp_path / "unused.sqlite3")

    assert [row["field"] for row in result] == [
        "graphics_timing_change_points",
        "raw_sector_observations",
    ]
    assert all(row["stream_validation_status"] in (
        "COMPACT_EVIDENCE_ONLY", "NOT_ASSIGNED_TO_SECTOR_TIMES"
    ) for row in result)
    assert all(row["coverage_percent"] is None for row in result)


def test_write_session_coverage_creates_session_scoped_csv(tmp_path):
    rows = [{
        "session_id": "run:session/one",
        "lap_number": 2,
        "trace_status": "compact_metadata",
        "quality": {"graphics_timing_observation_count": 1},
    }]

    paths = write_session_coverage(rows, tmp_path / "archive.sqlite3", tmp_path / "reports")

    assert len(paths) == 1
    assert paths[0].parent.name == "run_session_one"
    with paths[0].open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        exported = list(reader)
        assert tuple(reader.fieldnames) == COLUMNS
    assert exported[0]["field"] == "graphics_timing_change_points"
    assert exported[0]["stream_validation_status"] == "COMPACT_EVIDENCE_ONLY"
