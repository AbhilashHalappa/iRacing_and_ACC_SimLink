"""Legacy Fuel-only lap-history implementation retained for compatibility tests.

The desktop runtime now uses shared StrategyLapHistory for all strategy consumers.



This consumer never reconstructs missing laps. Until out-lap classification and
historical recovery are authoritative, its history is explicitly incomplete
and cannot enable rolling strategy calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FuelLapRecord:
    session_id: str
    lap_number: int
    lap_time_ms: int | None
    lap_valid: bool | None
    out_lap: bool | None
    classification: str
    event_sequence: int


class FuelLapHistory:
    """Consume ordered Stage 2 lap events without inventing missing records."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._records: list[FuelLapRecord] = []
        self._history_complete = False
        self._gap_count = 0
        self._last_event_sequence: int | None = None
        self._blockers: set[str] = {
            "Historical lap history has not been recovered for this session."
        }

    def consume(self, batch: Any) -> None:
        if batch.gap_detected:
            self._history_complete = False
            self._gap_count += 1
            self._blockers.add("Decoded lap-event delivery had a sequence gap.")
        for event in batch.events:
            if self._last_event_sequence is not None and event.sequence != self._last_event_sequence + 1:
                self._history_complete = False
                self._gap_count += 1
                self._blockers.add("Decoded lap-event sequence is discontinuous.")
            self._last_event_sequence = event.sequence

            if event.event_type == "lap.completion_gap":
                self._history_complete = False
                self._gap_count += 1
                self._blockers.add("ACC completed-lap counter skipped one or more laps.")
                continue
            if event.event_type != "lap.completed":
                continue

            payload = event.payload
            if self._session_id != event.session_id:
                self._session_id = event.session_id
                self._records.clear()
                self._history_complete = False
                self._blockers.add("Session history has not been recovered from its beginning.")

            lap_number = payload.get("lap_number")
            if isinstance(lap_number, bool) or not isinstance(lap_number, int) or lap_number < 1:
                self._history_complete = False
                self._blockers.add("Completed-lap event has no valid lap number.")
                continue
            record = FuelLapRecord(
                session_id=event.session_id or "unknown",
                lap_number=lap_number,
                lap_time_ms=payload.get("lap_time_ms"),
                lap_valid=payload.get("lap_valid") if payload.get("validity_known") else None,
                out_lap=payload.get("out_lap"),
                classification=str(payload.get("lap_classification", "unknown")),
                event_sequence=event.sequence,
            )
            if self._records and lap_number <= self._records[-1].lap_number:
                self._history_complete = False
                self._blockers.add("Completed-lap event order is not strictly increasing.")
                continue
            self._records.append(record)

            if record.lap_valid is None:
                self._blockers.add("ACC lap validity is unavailable for one or more laps.")
            elif record.lap_valid is False:
                pass
            if record.out_lap is None or record.classification != "classified":
                self._blockers.add("Out-lap classification is pending for one or more laps.")

    def reconcile_cursor(self, reconciliation: Any) -> None:
        """Record cursor reconciliation without pretending it recovered history."""
        if reconciliation is None:
            self._history_complete = False
            self._blockers.add("Fresh ACC lap-progress reconciliation is unavailable.")
            return
        self._history_complete = False
        self._blockers.add(
            "Lap-progress cursor was reconciled, but historical lap records were not recovered."
        )

    def snapshot(self) -> dict[str, Any]:
        valid = [
            record for record in self._records
            if record.lap_valid is True and record.out_lap is False
            and record.classification == "classified" and record.lap_time_ms
        ]
        eligible = self._history_complete and not self._blockers
        return {
            "session_id": self._session_id,
            "observed_lap_count": len(self._records),
            "valid_lap_count": len(valid),
            "recent_valid_lap_times_ms": [item.lap_time_ms for item in valid[-5:]] if eligible else [],
            "history_complete": eligible,
            "rolling_five_lap_average_ms": (
                sum(item.lap_time_ms for item in valid[-5:]) / min(5, len(valid))
                if eligible and valid else None
            ),
            "event_gap_count": self._gap_count,
            "blockers": sorted(self._blockers),
            "rolling_calculation_enabled": False,
        }
