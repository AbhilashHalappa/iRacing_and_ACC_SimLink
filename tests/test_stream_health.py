from src.desktop.stream_health import (
    STREAM_FRESHNESS_THRESHOLDS_NS,
    build_stream_freshness,
)


def test_stream_freshness_is_classified_independently():
    now = 5_000_000_000
    result = build_stream_freshness(
        now_ns=now,
        timestamps_ns={
            "physics": now - 500_000_000,
            "graphics": now - 2_000_000_000,
            "static": now - 500_000_000,
        },
        lifecycle_states={
            "physics": "running",
            "graphics": "running",
            "static": "running",
        },
    )

    assert result["physics"]["state"] == "fresh"
    assert result["graphics"]["state"] == "stale"
    assert result["static"]["state"] == "fresh"
    assert result["graphics"]["age_ms"] == 2000


def test_missing_stream_has_no_age_and_does_not_affect_other_streams():
    result = build_stream_freshness(
        now_ns=10_000_000_000,
        timestamps_ns={"physics": 9_900_000_000, "graphics": None, "static": None},
        lifecycle_states={"physics": "running", "graphics": "running", "static": "running"},
    )

    assert result["physics"]["state"] == "fresh"
    assert result["graphics"]["state"] == "missing"
    assert result["static"]["state"] == "missing"
    assert result["graphics"]["age_ms"] is None


def test_failed_or_stopped_stream_is_unavailable():
    result = build_stream_freshness(
        now_ns=10_000_000_000,
        timestamps_ns={
            "physics": 9_900_000_000,
            "graphics": 9_900_000_000,
            "static": 9_900_000_000,
        },
        lifecycle_states={"physics": "failed", "graphics": "stopped", "static": "running"},
    )

    assert result["physics"]["state"] == "unavailable"
    assert result["graphics"]["state"] == "unavailable"
    assert result["static"]["state"] == "fresh"


def test_stream_thresholds_are_explicit_and_static_allows_slow_refresh():
    assert STREAM_FRESHNESS_THRESHOLDS_NS == {
        "physics": 1_000_000_000,
        "graphics": 1_500_000_000,
        "static": 3_500_000_000,
    }


def test_stream_recovers_to_fresh_when_new_sample_arrives():
    now = 10_000_000_000
    lifecycle = {"physics": "running", "graphics": "running", "static": "running"}
    stale = build_stream_freshness(
        now_ns=now,
        timestamps_ns={
            "physics": 9_900_000_000,
            "graphics": 7_900_000_000,
            "static": 9_900_000_000,
        },
        lifecycle_states=lifecycle,
    )
    assert stale["graphics"]["state"] == "stale"
    assert stale["physics"]["state"] == "fresh"

    recovered = build_stream_freshness(
        now_ns=now,
        timestamps_ns={
            "physics": 9_900_000_000,
            "graphics": 9_900_000_000,
            "static": 9_900_000_000,
        },
        lifecycle_states=lifecycle,
    )
    assert recovered["graphics"]["state"] == "fresh"
    assert recovered["physics"]["state"] == "fresh"
