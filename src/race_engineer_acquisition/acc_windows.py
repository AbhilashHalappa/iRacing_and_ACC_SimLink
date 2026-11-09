"""Read-only ACC Physics Shared Memory adapter for Windows.

The ctypes Physics layout follows the 800-byte ACC Shared Memory v1.9 layout
corroborated by independent implementations and live raw-page evidence. This
module copies the raw page only; channel decoding is downstream from acquisition.
"""
from __future__ import annotations

import ctypes
import os
from typing import Protocol

from .models import RawPhysicsRead

PHYSICS_MAP = r"Local\acpmf_physics"

# Layout provenance: AbhilashHalappa/Race-Engineer-ACC,
# branch diagnostic/high-res-capture-2026-11-07,
# src/acc_shared_memory_extended.py, blob e9a54bda008cb6ff1797dfdc14b07b297a461ab9.

class _Physics(ctypes.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [
        ("packet_id", ctypes.c_int32), ("throttle", ctypes.c_float),
        ("brake", ctypes.c_float), ("fuel_kg", ctypes.c_float),
        ("gear_raw", ctypes.c_int32), ("rpm", ctypes.c_int32),
        ("steering", ctypes.c_float), ("speed_kph", ctypes.c_float),
        ("velocity", ctypes.c_float * 3), ("acc_g", ctypes.c_float * 3),
        ("wheel_slip", ctypes.c_float * 4), ("wheel_load", ctypes.c_float * 4),
        ("tyre_pressure_psi", ctypes.c_float * 4), ("wheel_angular_speed", ctypes.c_float * 4),
        ("tyre_wear_unused", ctypes.c_float * 4), ("tyre_dirty", ctypes.c_float * 4),
        ("tyre_core_temp_c", ctypes.c_float * 4), ("camber_unused", ctypes.c_float * 4),
        ("suspension_travel", ctypes.c_float * 4), ("drs_unused", ctypes.c_float),
        ("tc", ctypes.c_float), ("heading", ctypes.c_float), ("pitch", ctypes.c_float),
        ("roll", ctypes.c_float), ("cg_height_unused", ctypes.c_float),
        ("car_damage", ctypes.c_float * 5), ("tyres_out_unused", ctypes.c_int32),
        ("pit_limiter_on", ctypes.c_int32), ("abs", ctypes.c_float),
        ("kers_charge_unused", ctypes.c_float), ("kers_input_unused", ctypes.c_float),
        ("autoshifter_on", ctypes.c_int32), ("ride_height_unused", ctypes.c_float * 2),
        ("turbo_boost", ctypes.c_float), ("ballast_unused", ctypes.c_float),
        ("air_density_unused", ctypes.c_float), ("air_temp_c", ctypes.c_float),
        ("road_temp_c", ctypes.c_float), ("local_angular_velocity", ctypes.c_float * 3),
        ("final_ff", ctypes.c_float), ("performance_meter_unused", ctypes.c_float),
        ("engine_brake_unused", ctypes.c_int32), ("ers_recovery_unused", ctypes.c_int32),
        ("ers_power_unused", ctypes.c_int32), ("ers_heat_unused", ctypes.c_int32),
        ("ers_charging_unused", ctypes.c_int32), ("kers_current_unused", ctypes.c_float),
        ("drs_available_unused", ctypes.c_int32), ("drs_enabled_unused", ctypes.c_int32),
        ("brake_temp_c", ctypes.c_float * 4), ("clutch", ctypes.c_float),
        ("tyre_temp_i_unused", ctypes.c_float * 4), ("tyre_temp_m_unused", ctypes.c_float * 4),
        ("tyre_temp_o_unused", ctypes.c_float * 4), ("is_ai_controlled", ctypes.c_int32),
        ("tyre_contact_point", ctypes.c_float * 12), ("tyre_contact_normal", ctypes.c_float * 12),
        ("tyre_contact_heading", ctypes.c_float * 12), ("brake_bias", ctypes.c_float),
        ("local_velocity", ctypes.c_float * 3), ("p2p_activation_unused", ctypes.c_int32),
        ("p2p_status_unused", ctypes.c_int32), ("current_max_rpm", ctypes.c_int32),
        ("mz_unused", ctypes.c_float * 4), ("fx_unused", ctypes.c_float * 4), ("fy_unused", ctypes.c_float * 4),
        ("slip_ratio", ctypes.c_float * 4), ("slip_angle", ctypes.c_float * 4),
        ("tc_in_action_unused", ctypes.c_int32), ("abs_in_action_unused", ctypes.c_int32),
        ("suspension_damage_unused", ctypes.c_float * 4), ("tyre_temp_unused", ctypes.c_float * 4),
        ("water_temp_c", ctypes.c_float), ("brake_pressure", ctypes.c_float * 4),
        ("front_brake_compound", ctypes.c_int32), ("rear_brake_compound", ctypes.c_int32),
        ("pad_life", ctypes.c_float * 4), ("disc_life", ctypes.c_float * 4),
        ("ignition_on", ctypes.c_int32), ("starter_engine_on", ctypes.c_int32),
        ("engine_running", ctypes.c_int32), ("tail_reserved", ctypes.c_ubyte * 16),
    ]


PHYSICS_SIZE = ctypes.sizeof(_Physics)


class _MappingProtocol(Protocol):
    def read_packet_id(self) -> int: ...
    def copy_page(self) -> bytes: ...
    def close(self) -> None: ...


class _WindowsNamedMemory:
    """Read-only mapping of ACC's named Physics shared-memory page."""

    def __init__(self, name: str = PHYSICS_MAP) -> None:
        if os.name != "nt":
            raise OSError("ACC Shared Memory requires Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
        ]
        self._kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        self._kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_size_t
        ]
        self._kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self._kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self._kernel32.UnmapViewOfFile.restype = ctypes.c_int
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_int

        self._handle = self._kernel32.OpenFileMappingW(0x0004, 0, name)
        if not self._handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"Cannot open {name}. Is ACC running?")
        self._view = self._kernel32.MapViewOfFile(
            self._handle, 0x0004, 0, 0, 0
        )
        if not self._view:
            error = ctypes.get_last_error()
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
            raise OSError(error, f"Cannot map {name}")

    def read_packet_id(self) -> int:
        if not self._view:
            raise OSError("ACC Physics shared-memory view is closed")
        # packet_id is the first aligned int32 field in the audited ACC layout.
        # This is a best-effort observation; ACC does not expose a formal
        # cross-process snapshot/sequence-lock contract here.
        return int(ctypes.c_int32.from_address(self._view).value)

    def copy_page(self) -> bytes:
        if not self._view:
            raise OSError("ACC Physics shared-memory view is closed")
        return ctypes.string_at(self._view, PHYSICS_SIZE)

    def close(self) -> None:
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class WindowsACCPhysicsSource:
    """PhysicsSource implementation; no decoding, UI callbacks or disk I/O."""

    def __init__(self, mapping_factory=_WindowsNamedMemory) -> None:
        self._mapping_factory = mapping_factory
        self._mapping: _MappingProtocol | None = None

    def read_physics(self) -> RawPhysicsRead:
        if self._mapping is None:
            self._mapping = self._mapping_factory()
        before = self._mapping.read_packet_id()
        payload = self._mapping.copy_page()
        after = self._mapping.read_packet_id()
        if len(payload) != PHYSICS_SIZE:
            raise ValueError(
                f"ACC Physics page size mismatch: {len(payload)} != {PHYSICS_SIZE}"
            )
        return RawPhysicsRead(before, after, payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
