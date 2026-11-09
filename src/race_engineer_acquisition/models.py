"""Small immutable records used at the acquisition boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawPhysicsRead:
    """One copied Physics page and the packet IDs bracketing that copy.

    The ACC adapter is responsible for reading the ID before and after copying
    the shared-memory page. Different IDs mean the snapshot may be torn.
    """

    packet_id_before: int
    packet_id_after: int
    payload: bytes

    @property
    def is_consistent(self) -> bool:
        return self.packet_id_before == self.packet_id_after


@dataclass(frozen=True, slots=True)
class PhysicsSnapshot:
    """Application-owned immutable Physics observation."""

    capture_sequence: int
    acc_physics_packet_id: int
    read_start_ns: int
    read_complete_ns: int
    capture_timestamp_ns: int
    payload: bytes

    @property
    def acquisition_duration_ns(self) -> int:
        return self.read_complete_ns - self.read_start_ns


@dataclass(frozen=True, slots=True)
class BufferLoss:
    """Explicit accounting for an acquired sample not accepted by a buffer."""

    count: int
    first_capture_sequence: int | None
    last_capture_sequence: int | None
