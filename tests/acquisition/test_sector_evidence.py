from types import SimpleNamespace as N

from race_engineer_acquisition.sector_evidence import (
    build_sector_observations,
    summarize_sector_evidence,
)


def sample(sequence, timestamp, sector, sector_time):
    return N(
        capture_sequence=sequence,
        capture_timestamp_ns=timestamp,
        data=N(sector=sector, last_sector_time_ms=sector_time),
    )


def test_sector_evidence_preserves_raw_values_and_source_provenance():
    observations = build_sector_observations([
        sample(10, 100, 0, 0),
        sample(11, 200, 0, 0),
        sample(12, 300, 1, 31_200),
        sample(13, 400, 1, 31_200),
        sample(14, 500, 2, 29_800),
    ])

    assert len(observations) == 3
    assert observations[1]["capture_sequence"] == 12
    assert observations[1]["capture_timestamp_ns"] == 300
    assert observations[1]["sector_raw"] == 1
    assert observations[1]["last_sector_time_ms_raw"] == 31_200
    assert observations[1]["sector_value_changed"] is True
    assert observations[1]["last_sector_time_value_changed"] is True
    assert observations[1]["sector_time_assignment"] == "not_inferred"


def test_sector_evidence_does_not_reset_baseline_on_unavailable_values():
    observations = build_sector_observations([
        sample(1, 100, 1, 25_000),
        sample(2, 200, None, None),
        sample(3, 300, 1, 25_000),
        sample(4, 400, 2, 30_000),
    ])

    assert len(observations) == 2
    assert observations[0]["capture_sequence"] == 1
    assert observations[1]["capture_sequence"] == 4


def test_sector_summary_does_not_claim_sector_time_assignments():
    observations = build_sector_observations([
        sample(1, 100, 0, 0),
        sample(2, 200, 1, 30_000),
    ])
    summary = summarize_sector_evidence(observations)

    assert summary["observation_count"] == 2
    assert summary["sector_value_change_count"] == 2
    assert summary["last_sector_time_value_change_count"] == 2
    assert summary["raw_sector_values"] == [0, 1]
    assert summary["sector_time_assignment"] == "not_inferred"
