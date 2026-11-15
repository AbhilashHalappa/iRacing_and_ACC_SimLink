import pytest

from src.race_engineer_acquisition.static_decoder import (
    STATIC_LOGICAL_SIZE,
    decode_static_candidate_b,
)


def test_decodes_porsche_992_car_model_from_static_page():
    page = bytearray(STATIC_LOGICAL_SIZE)
    encoded = "porsche_992_gt3_r".encode("utf-16-le")
    page[68:68 + len(encoded)] = encoded
    decoded = decode_static_candidate_b(bytes(page))
    assert decoded.car_model == "porsche_992_gt3_r"


def test_rejects_short_static_page():
    with pytest.raises(ValueError, match="too short"):
        decode_static_candidate_b(bytes(STATIC_LOGICAL_SIZE - 1))


def test_rejects_invalid_static_boolean_fields():
    page = bytearray(STATIC_LOGICAL_SIZE)
    page[464:468] = (2).to_bytes(4, "little", signed=True)
    with pytest.raises(ValueError, match="PenaltiesEnabled"):
        decode_static_candidate_b(bytes(page))



def test_preserves_unknown_auto_clutch_value_without_rejecting_static_page():
    page = bytearray(STATIC_LOGICAL_SIZE)
    page[488:492] = (2).to_bytes(4, "little", signed=True)

    decoded = decode_static_candidate_b(bytes(page))

    assert decoded.auto_clutch == 2
    assert decoded.is_timed_race is False
