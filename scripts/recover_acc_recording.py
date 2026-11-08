"""Inspect and recover a raw ACC Physics recording after an interrupted run.

By default, the scanner preserves all complete CRC-valid blocks and truncates
only an incomplete or corrupt trailing region.
"""
from __future__ import annotations

import argparse
from pathlib import Path

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
