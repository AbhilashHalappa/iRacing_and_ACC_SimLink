from race_engineer_acquisition.analysis_coach import (
    rank_corner_opportunities,
    summarize_recurring_opportunities,
)


def test_coach_ranks_only_measured_positive_corner_time_losses():
    reference = [{
        "corner_id": "turn-01",
        "available": True,
        "braking_point_m": 100.0,
        "minimum_speed_mps": 20.0,
        "throttle_pickup_point_m": 150.0,
        "turn_in_point_m": 110.0,
    }]
    comparison = [
        {
            "corner_id": "turn-01",
            "available": True,
            "corner_time_delta_s": 0.4,
            "braking_point_m": 108.0,
            "minimum_speed_mps": 18.0,
            "throttle_pickup_point_m": 158.0,
            "turn_in_point_m": 115.0,
        },
        {
            "corner_id": "turn-02",
            "available": True,
            "corner_time_delta_s": -0.2,
            "braking_point_m": 80.0,
        },
    ]
    result = rank_corner_opportunities(reference, comparison)
    assert len(result) == 1
    assert result[0]["rank"] == 1
    assert result[0]["time_loss_s"] == 0.4
    assert result[0]["evidence_level"] == "measured_comparison"
    assert result[0]["causal_claim"] == "not_made"
    assert result[0]["measured_differences"][0]["direction"] == "later"
    assert any(
        item["direction"] == "lower"
        for item in result[0]["measured_differences"]
    )


def test_coach_does_not_create_opportunities_without_reference_or_metrics():
    assert rank_corner_opportunities([], [{
        "corner_id": "turn-1", "available": True, "corner_time_delta_s": 1.0,
    }]) == ()
    assert rank_corner_opportunities([{
        "corner_id": "turn-1", "available": True,
    }], [{
        "corner_id": "turn-1", "available": True,
        "corner_time_delta_s": 0.5,
    }]) == ()


def test_recurring_opportunity_summary_counts_each_session_once():
    reports = [
        [{
            "corner_id": "turn-1",
            "measured_differences": [
                {"metric": "braking_point_m"},
                {"metric": "throttle_pickup_point_m"},
            ],
        }],
        [{
            "corner_id": "turn-1",
            "measured_differences": [
                {"metric": "braking_point_m"},
                {"metric": "braking_point_m"},
            ],
        }],
        [{
            "corner_id": "turn-2",
            "measured_differences": [{"metric": "minimum_speed_mps"}],
        }],
    ]
    result = summarize_recurring_opportunities(reports)
    assert result[0]["corner_id"] == "turn-1"
    assert result[0]["metric"] == "braking_point_m"
    assert result[0]["session_count"] == 2
