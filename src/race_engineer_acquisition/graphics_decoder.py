"""Conservative decoder for the four priority ACC Graphics fields.

Offsets/types follow the 1,588-byte candidate SPageFileGraphic layout
corroborated by pinned RaceIQ and Pro Engineer references. The complete
4,096-byte mapping remains acquired and recorded unchanged; this decoder only
reads the required fields and does not certify the official v1.9 ABI.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

GRAPHICS_CANDIDATE_SIZE = 1588
GRAPHICS_REQUIRED_SIZE = 1416

PACKET_ID_OFFSET = 0x000
TC_LEVEL_OFFSET = 0x4F4
ABS_LEVEL_OFFSET = 0x500
FUEL_PER_LAP_OFFSET = 0x504
FUEL_ESTIMATED_LAPS_OFFSET = 0x584


@dataclass(frozen=True, slots=True)
class DecodedGraphics:
    packet_id: int
    tc_level: int
    abs_level: int
    fuel_per_lap_l: float | None
    fuel_estimated_laps: float | None


def _finite_float(payload: bytes, offset: int) -> float | None:
    value = struct.unpack_from("<f", payload, offset)[0]
    return value if math.isfinite(value) else None


def decode_graphics(payload: bytes | bytearray | memoryview) -> DecodedGraphics:
    """Decode the requested fields from one complete candidate Graphics page.

    Float values are preserved when finite. No undocumented sentinel,
    scaling, rounding, or +1 correction is applied.
    """
    view = memoryview(payload)
    if view.nbytes < GRAPHICS_REQUIRED_SIZE:
        raise ValueError(
            "ACC Graphics payload is too short for the requested fields: "
            f"{view.nbytes} < {GRAPHICS_REQUIRED_SIZE}"
        )
    return DecodedGraphics(
        packet_id=struct.unpack_from("<i", view, PACKET_ID_OFFSET)[0],
        tc_level=struct.unpack_from("<i", view, TC_LEVEL_OFFSET)[0],
        abs_level=struct.unpack_from("<i", view, ABS_LEVEL_OFFSET)[0],
        fuel_per_lap_l=_finite_float(view, FUEL_PER_LAP_OFFSET),
        fuel_estimated_laps=_finite_float(view, FUEL_ESTIMATED_LAPS_OFFSET),
    )
