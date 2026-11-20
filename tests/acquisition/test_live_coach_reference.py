from race_engineer_acquisition.live_coach_reference import (
    list_live_coach_reference_candidates,
    load_live_coach_reference,
)


class FakeArchive:
    def __init__(self, rows, traces):
        self.rows = tuple(rows)
        self.traces = dict(traces)

    def read_laps(self, **filters):
        rows = self.rows
        for key in ("session_id", "car_model", "track", "track_configuration"):
            value = filters.get(key)
            if value is not None:
                rows = tuple(row for row in rows if row.get(key) == value)
        return rows[:filters.get("limit", 100)]

    def read_lap_metadata(self, session_id, lap_number):
        return next((row for row in self.rows if row["session_id"] == session_id and row["lap_number"] == lap_number), None)

    def read_trace(self, session_id, lap_number):
        return self.traces.get((session_id, lap_number))


def _row(**overrides):
    row = {
        "session_id": "session-a", "lap_number": 4,
        "car_model": "GT3", "track": "Test Circuit",
        "track_configuration": "GP", "lap_time_ms": 100000,
        "completed_at_utc": "2026-11-20T10:00:00Z",
        "lap_valid": 1, "out_lap": 0, "trace_status": "retained",
        "physics_sample_count": 100, "graphics_sample_count": 50,
        "pinned_pb": False,
    }
    row.update(overrides)
    return row


def _trace():
    return {
        "physics": [{"capture_sequence": 10, "capture_timestamp_ns": 1000, "data": {"speed_kph": 180}}],
        "graphics": [{"capture_sequence": 20, "capture_timestamp_ns": 1010, "data": {"distance_traveled_m": 100}}],
    }


def test_reference_candidates_include_only_valid_non_out_retained_complete_identity_laps():
    rows = (
        _row(),
        _row(lap_number=5, out_lap=1),
        _row(lap_number=6, lap_valid=0),
        _row(lap_number=7, trace_status="evicted_age"),
        _row(lap_number=8, track_configuration=None),
        _row(lap_number=9, physics_sample_count=0),
    )
    archive = FakeArchive(rows, {("session-a", 4): _trace()})

    result = list_live_coach_reference_candidates(
        archive, car_model="GT3", track="Test Circuit",
        track_configuration="GP",
    )

    assert len(result) == 1
    assert result[0]["reference_id"] if "reference_id" in result[0] else result[0]["lap_number"] == 4
    assert result[0]["lap_number"] == 4


def test_explicit_reference_load_preserves_original_stream_provenance():
    archive = FakeArchive((_row(),), {("session-a", 4): _trace()})

    result = load_live_coach_reference(
        archive, session_id="session-a", lap_number=4,
        car_model="GT3", track="Test Circuit",
        track_configuration="GP",
    )

    assert result["reference_id"] == "session-a:4"
    assert result["physics"][0]["capture_sequence"] == 10
    assert result["graphics"][0]["capture_sequence"] == 20
    assert result["physics"][0]["capture_timestamp_ns"] == 1000
    assert result["graphics"][0]["capture_timestamp_ns"] == 1010
    assert result["trace_semantics"] == "original_acc_samples_with_capture_provenance"


def test_reference_selection_rejects_identity_mismatch_and_missing_trace():
    archive = FakeArchive((_row(),), {("session-a", 4): _trace()})

    try:
        load_live_coach_reference(
            archive, session_id="session-a", lap_number=4,
            car_model="GT3", track="Test Circuit",
            track_configuration="Sprint",
        )
    except ValueError as exc:
        assert "track_configuration" in str(exc)
    else:
        raise AssertionError("identity mismatch must be rejected")

    archive.traces.clear()
    try:
        load_live_coach_reference(
            archive, session_id="session-a", lap_number=4,
            car_model="GT3", track="Test Circuit",
            track_configuration="GP",
        )
    except ValueError as exc:
        assert "trace" in str(exc)
    else:
        raise AssertionError("missing trace must be rejected")
