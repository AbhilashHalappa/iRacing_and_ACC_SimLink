"""Deterministic completion policy for required raw ACC recordings.

Optional consumers are deliberately excluded from this decision: their failure
must not change the required recorder's delivery or completion result.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fanout import ConsumerQueueMetrics


@dataclass(frozen=True, slots=True)
class RecordingCompletionDecision:
    completed: bool
    reasons: tuple[str, ...]


def evaluate_recording_completion(
    *,
    acquired: int,
    persisted: int,
    acquisition_rejections: int,
    pending_acquisition: int,
    dispatcher_in_flight: int,
    required_delivery_rejections: int,
    required_consumer: ConsumerQueueMetrics,
    dispatcher_error: str | None,
    producer_error: str | None,
    recorder_error: str | None,
    recovery_valid: bool,
    checkpoint_valid: bool,
    shutdown_timed_out: bool,
) -> RecordingCompletionDecision:
    """Return completed only when the required recorder is fully reconciled.

    The current Physics recording path has one required consumer: the raw
    recorder. Its processed_count is the persisted count because the recorder
    acknowledges only after write, flush and fsync have succeeded.
    """
    reasons: list[str] = []

    if not required_consumer.required:
        reasons.append("required_recorder_not_registered_as_required")
    if required_consumer.offered_count != (
        required_consumer.dispatched_count + required_consumer.rejected_count
    ):
        reasons.append("required_consumer_offer_accounting_mismatch")
    if required_consumer.dispatched_count != (
        required_consumer.processed_count
        + required_consumer.failed_count
        + required_consumer.pending_count
    ):
        reasons.append("required_consumer_delivery_accounting_mismatch")
    if required_consumer.processed_count != persisted:
        reasons.append("persisted_count_does_not_match_recorder_acknowledgements")
    if required_consumer.rejected_count:
        reasons.append("required_recorder_queue_rejected_samples")
    if required_consumer.failed_count or required_consumer.failed:
        reasons.append("required_recorder_consumer_failed_samples_or_worker")
    if required_consumer.pending_count:
        reasons.append("required_recorder_has_pending_or_in_flight_samples")
    if required_delivery_rejections:
        reasons.append("required_delivery_rejections")
    if acquisition_rejections:
        reasons.append("acquisition_queue_rejected_samples")
    if pending_acquisition:
        reasons.append("acquisition_queue_not_drained")
    if dispatcher_in_flight:
        reasons.append("dispatcher_has_in_flight_sample")
    if acquired != (
        persisted
        + acquisition_rejections
        + required_consumer.rejected_count
        + required_consumer.failed_count
        + pending_acquisition
        + required_consumer.pending_count
        + dispatcher_in_flight
    ):
        reasons.append("end_to_end_sample_accounting_mismatch")
    if dispatcher_error:
        reasons.append("dispatcher_failed")
    if producer_error:
        reasons.append("acquisition_or_shutdown_error")
    if recorder_error:
        reasons.append("recorder_writer_failed")
    if not recovery_valid:
        reasons.append("recording_recovery_or_crc_validation_failed")
    if not checkpoint_valid:
        reasons.append("checkpoint_validation_failed")
    if shutdown_timed_out:
        reasons.append("shutdown_timeout_worker_still_running")

    return RecordingCompletionDecision(not reasons, tuple(reasons))
