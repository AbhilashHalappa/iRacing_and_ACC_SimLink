import pytest

from src.race_engineer_acquisition.static_decoder import (
    CAR_MODEL_END,
    CAR_MODEL_OFFSET,
    decode_car_model,
)


def test_decodes_kunos_car_model_from_static_page():
    page = bytearray(CAR_MODEL_END)
    encoded = "porsche_992_gt3_r".encode("utf-16-le")
    page[CAR_MODEL_OFFSET:CAR_MODEL_OFFSET + len(encoded)] = encoded
    assert decode_car_model(page) == "porsche_992_gt3_r"


def test_rejects_short_static_page():
    with pytest.raises(ValueError, match="too short"):
        decode_car_model(bytes(CAR_MODEL_END - 1))


def test_rejects_empty_car_model():
    with pytest.raises(ValueError, match="empty"):
        decode_car_model(bytes(CAR_MODEL_END))
