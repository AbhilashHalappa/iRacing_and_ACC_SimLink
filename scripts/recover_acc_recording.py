"""Inspect and recover a raw ACC Physics recording after an interrupted run.

By default, the scanner preserves all complete CRC-valid blocks and truncates
only an incomplete or corrupt trailing region.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from race_engineer_acquisition.checkpoint import read_checkpoint
from race_engineer_acquisition.recorder import recover_recording


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="Path to a .accraw recording")
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Report the invalid trailing region without modifying the recording",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.recording.is_file():
        raise SystemExit(f"Recording file does not exist: {args.recording}")

    before_size = args.recording.stat().st_size
    recovery = recover_recording(
        args.recording,
        truncate_invalid_tail=not args.no_truncate,
    )
    after_size = args.recording.stat().st_size

    print(f"Recording               : {args.recording}")
    print(f"Valid blocks            : {recovery.valid_block_count}")
    print(f"Recovered snapshots     : {recovery.recovered_snapshot_count}")
    print(f"Last block sequence     : {recovery.last_block_sequence}")
    print(f"Last capture sequence   : {recovery.last_capture_sequence}")
    print(f"Valid bytes             : {recovery.valid_bytes}")
    print(f"Invalid/trailing bytes  : {recovery.truncated_bytes}")
    print(f"File size before        : {before_size}")
    print(f"File size after         : {after_size}")
    print(f"Tail truncated          : {'no (inspection only)' if args.no_truncate else ('yes' if before_size != after_size else 'no')}")

    checkpoint_path = args.recording.with_suffix(".checkpoint.json")
    if checkpoint_path.is_file():
        print(f"Checkpoint              : {checkpoint_path}")
        try:
            checkpoint = read_checkpoint(checkpoint_path)
            if checkpoint.get("recording_file") != args.recording.name:
                raise ValueError("Checkpoint belongs to a different recording file")
            acquisition = checkpoint.get("acquisition", {})
            recorder = checkpoint.get("recorder", {})
            accounting = checkpoint.get("accounting", {})
            acquired = int(acquisition.get("capture_count", 0))
            persisted_at_checkpoint = int(recorder.get("persisted_snapshot_count", 0))
            explicit_losses = (
                int(accounting.get("acquisition_rejections", 0))
                + int(accounting.get("recorder_queue_rejections", 0))
                + int(accounting.get("write_failed", 0))
            )
            outstanding_at_checkpoint = max(
                0, acquired - persisted_at_checkpoint - explicit_losses
            )
            recovered_after_checkpoint = max(
                0, recovery.recovered_snapshot_count - persisted_at_checkpoint
            )
            checkpoint_persisted_missing = max(
                0, persisted_at_checkpoint - recovery.recovered_snapshot_count
            )
            minimum_not_recovered = (
                max(0, outstanding_at_checkpoint - recovered_after_checkpoint)
                + checkpoint_persisted_missing
            )
            print(f"Checkpoint sequence     : {checkpoint.get('checkpoint_sequence')}")
            print(f"Checkpoint time (UTC)   : {checkpoint.get('checkpointed_at_utc')}")
            print(f"Captured at checkpoint  : {acquired}")
            print(f"Last captured sequence  : {acquisition.get('last_capture_sequence')}")
            print(f"Persisted at checkpoint : {persisted_at_checkpoint}")
            print(f"Last persisted sequence : {recorder.get('last_persisted_capture_sequence')}")
            print(f"Acquisition queue       : {checkpoint.get('acquisition_buffer', {}).get('pending', 0)}")
            print(f"Recorder queue          : {checkpoint.get('recorder_buffer', {}).get('pending', 0)}")
            print(f"Dispatcher in flight    : {checkpoint.get('dispatcher', {}).get('in_flight_sequence')}")
            print(f"Recorder in flight      : {recorder.get('in_flight_snapshot_count', 0)}")
            print(f"Outstanding at checkpoint: {outstanding_at_checkpoint}")
            print(f"Recovered beyond checkpoint persisted count: {recovered_after_checkpoint}")
            print(f"Checkpoint-persisted samples missing: {checkpoint_persisted_missing}")
            print(f"Minimum checkpointed samples not recovered: {minimum_not_recovered}")
            print(f"Checkpoint accounting delta: {accounting.get('observed_unclassified_delta')}")
            print("Note: the minimum excludes captures made after the last checkpoint; total crash loss may be higher. A non-zero accounting delta reflects independently sampled counters or an unclassified transfer.")
        except ValueError as exc:
            print(f"Checkpoint validation   : FAILED ({exc})")
    else:
        print("Checkpoint              : not found (legacy recording or checkpoints disabled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
