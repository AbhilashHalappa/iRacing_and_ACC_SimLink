import struct
import unittest

from race_engineer_acquisition.static_decoder import (
    STATIC_LOGICAL_SIZE,
    STATIC_LAYOUT_VARIANT_B,
    decode_static_candidate_b,
)


def put_string(page: bytearray, offset: int, count: int, value: str) -> None:
    encoded = value.encode("utf-16-le")
    page[offset:offset + min(len(encoded), count * 2)] = encoded[:count * 2]


def put_i32(page: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<i", page, offset, value)


def put_f32(page: bytearray, offset: int, value: float) -> None:
    struct.pack_into("<f", page, offset, value)


class StaticDecoderTests(unittest.TestCase):
    def make_page(self) -> bytes:
        page = bytearray(4096)
        for offset, count, value in [
            (0, 15, "1.9"), (30, 15, "1.7"),
            (68, 33, "porsche_992_gt3_r"), (134, 33, "monza"),
            (200, 33, "Abhi"), (266, 33, "H"),
            (524, 33, "track config"), (604, 33, "skin"),
            (688, 33, "DHE"), (754, 33, "WH"),
        ]:
            put_string(page, offset, count, value)
        for offset, value in [
            (64, 25), (400, 3), (412, 9250), (464, 1),
            (488, 1), (492, 1), (596, 0), (600, 0),
            (672, 0), (684, 0),
        ]:
            put_i32(page, offset, value)
        for offset, value in [
            (416, 120.0), (468, 1.0), (472, 1.0),
            (476, 1.0), (484, 0.0), (592, 0.0),
        ]:
            put_f32(page, offset, value)
        return bytes(page)

    def test_decodes_live_qualified_variant_b_fields(self):
        decoded = decode_static_candidate_b(self.make_page())
        self.assertEqual(decoded.layout_id, STATIC_LAYOUT_VARIANT_B)
        self.assertEqual(decoded.sm_version, "1.9")
        self.assertEqual(decoded.car_model, "porsche_992_gt3_r")
        self.assertEqual(decoded.track, "monza")
        self.assertEqual(decoded.sector_count, 3)
        self.assertEqual(decoded.max_rpm, 9250)
        self.assertEqual(decoded.max_fuel, 120.0)
        self.assertEqual(decoded.car_skin, "skin")
        self.assertEqual(decoded.dry_tyres_name, "DHE")
        self.assertEqual(decoded.wet_tyres_name, "WH")
        self.assertFalse(decoded.is_online)

    def test_rejects_page_shorter_than_candidate_layout(self):
        with self.assertRaises(ValueError):
            decode_static_candidate_b(bytes(STATIC_LOGICAL_SIZE - 1))

    def test_rejects_non_boolean_values_in_boolean_fields(self):
        page = bytearray(self.make_page())
        put_i32(page, 464, 2)
        with self.assertRaisesRegex(ValueError, "PenaltiesEnabled"):
            decode_static_candidate_b(bytes(page))


if __name__ == "__main__":
    unittest.main()
