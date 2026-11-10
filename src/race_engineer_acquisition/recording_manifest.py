"""Common sidecar manifest generation for independent ACC raw recordings.

This module is called by recording control scripts only after acquisition and
recording workers have stopped. It performs no work in acquisition hot loops.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from .static import WindowsACCStaticSource
from .static_decoder import decode_static_candidate_b


_SESSION_FIELDS = (
    "sm_version", "ac_version", "car_model", "track", "track_configuration",
    "player_name", "player_surname", "player_nick", "is_online", "layout_id",
)


def collect_static_session_metadata(
    source_factory: Callable[[], Any] = WindowsACCStaticSource,
) -> tuple[dict[str, Any], list[str]]:
    """Read and conservatively decode Static metadata outside acquisition workers."""
    metadata = {field: None for field in _SESSION_FIELDS}
    warnings: list[str] = []
    source = None
    try:
        source = source_factory()
        decoded = decode_static_candidate_b(source.read_static().payload)
        metadata = {field: getattr(decoded, field) for field in _SESSION_FIELDS}
    except Exception as exc:
        warnings.append(
            f"ACC Static session metadata unavailable: {type(exc).__name__}: {exc}"
        )
    finally:
        if source is not None:
            try:
                source.close()
            except Exception as exc:
                warnings.append(
                    f"ACC Static metadata mapping close failed: {type(exc).__name__}: {exc}"
                )
    return metadata, warnings


def build_recording_manifest(
    stream: str,
    report: dict[str, Any],
    *,
    recording_format_version: int,
    session_metadata: dict[str, Any] | None = None,
    metadata_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the stable schema-v1 manifest from an existing stream report."""
    if stream not in {"physics", "graphics", "static"}:
        raise ValueError(f"Unsupported ACC recording stream: {stream}")
    if recording_format_version <= 0:
        raise ValueError("recording_format_version must be positive")

    started = report.get("started_at_utc")
    finished = report.get("finished_at_utc")
    if stream == "static":
        started = started or report.get("started_at_utc")
        finished = finished or report.get("finished_at_utc")

    if stream == "physics":
        acquired = int(report.get("reconciliation", {}).get("acquired", 0))
        persisted = int(report.get("reconciliation", {}).get("persisted", 0))
        failed = int(report.get("reconciliation", {}).get("recorder_failed_samples", 0))
        acq_reject = int(report.get("reconciliation", {}).get("acquisition_buffer_rejections", 0))
        rec_reject = int(report.get("reconciliation", {}).get("recorder_buffer_rejections", 0))
        last_capture = report.get("acquisition_metrics", {}).get("last_capture_sequence")
        first_packet = report.get("acquisition_metrics", {}).get("first_packet_id")
        last_packet = report.get("acquisition_metrics", {}).get("last_packet_id")
        recovery = report.get("recovery_validation") or {}
        recovery_valid = bool(report.get("recovery_validation_passed"))
        recovered = recovery.get("recovered_snapshot_count")
        truncated = recovery.get("truncated_bytes")
        delta = report.get("reconciliation", {}).get("delta")
    elif stream == "graphics":
        recon = report.get("reconciliation", {})
        acquired, persisted = int(recon.get("acquired", 0)), int(recon.get("persisted", 0))
        failed = int(recon.get("recorder_write_failures", 0))
        acq_reject = int(recon.get("acquisition_buffer_rejections", 0))
        rec_reject = int(recon.get("recorder_buffer_rejections", 0))
        last_capture = report.get("acquisition_metrics", {}).get("last_capture_sequence")
        first_packet = report.get("acquisition_metrics", {}).get("first_packet_id")
        last_packet = report.get("acquisition_metrics", {}).get("last_packet_id")
        recovery = report.get("recovery_validation") or {}
        recovery_valid = bool(report.get("recovery_validation_passed"))
        recovered = recovery.get("recovered_snapshot_count")
        truncated = recovery.get("truncated_bytes")
        delta = recon.get("delta")
    else:
        acquisition = report.get("acquisition", {})
        recorder = report.get("recorder", {})
        recovery = report.get("recovery", {})
        accounting = report.get("accounting", {})
        acquired = int(acquisition.get("changed_pages", 0))
        persisted = int(recorder.get("persisted_pages", 0))
        failed = int(recorder.get("failed_pages", 0))
        acq_reject = int(acquisition.get("buffer_rejections", 0))
        rec_reject = int(recorder.get("queue_rejections", 0))
        last_capture = acquisition.get("last_capture_sequence")
        first_packet = None
        last_packet = None
        recovery_valid = (
            recovery.get("truncated_bytes") == 0
            and recovery.get("recovered_pages") == persisted
        )
        recovered = recovery.get("recovered_pages")
        truncated = recovery.get("truncated_bytes")
        delta = accounting.get("reconciliation_delta")

    status = report.get("status", "failed")
    completed = status == "completed"
    reasons = list(report.get("completion_failure_reasons", []))
    if not completed and not reasons:
        reasons.append("Stream-specific recording validation did not complete successfully.")

    session = {field: None for field in _SESSION_FIELDS}
    if session_metadata:
        for field in _SESSION_FIELDS:
            if field in session_metadata:
                session[field] = session_metadata[field]

    warnings = list(metadata_warnings or [])
    return {
        "schema_version": 1,
        "recording_id": str(uuid.uuid4()),
        "stream": stream,
        "recording_file": report["recording_file"],
        "started_at_utc": started,
        "finished_at_utc": finished,
        "application_version": None,
        "recording_format_version": recording_format_version,
        "completion_status": "completed" if completed else ("incomplete" if report.get("shutdown_timed_out") else "failed"),
        "completion_failure_reasons": reasons,
        "session": session,
        "stream_summary": {
            "captured_count": acquired,
            "persisted_count": persisted,
            "failed_count": failed,
            "acquisition_rejection_count": acq_reject,
            "recorder_rejection_count": rec_reject,
            "first_capture_sequence": 1 if acquired else None,
            "last_capture_sequence": last_capture,
            "first_source_packet_id": first_packet,
            "last_source_packet_id": last_packet,
        },
        "integrity": {
            "recovery_valid": recovery_valid,
            "recovered_count": recovered,
            "truncated_bytes": truncated,
            "reconciliation_delta": delta,
            "metadata_warnings": warnings,
        },
    }


def attach_recording_manifest(
    stream: str, report: dict[str, Any], *, recording_format_version: int,
) -> dict[str, Any]:
    """Collect best-effort Static metadata and attach the common manifest."""
    metadata, warnings = collect_static_session_metadata()
    report["manifest"] = build_recording_manifest(
        stream, report, recording_format_version=recording_format_version,
        session_metadata=metadata, metadata_warnings=warnings,
    )
    return report
