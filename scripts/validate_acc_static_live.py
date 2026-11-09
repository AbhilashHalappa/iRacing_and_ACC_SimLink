"""Live, read-only ACC Static validation. Run with ACC open on Windows."""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import StaticAcquirer, WindowsACCStaticSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.seconds < 2 or args.interval <= 0:
        parser.error("--seconds must be >= 2 and --interval must be > 0")

    source = WindowsACCStaticSource()
    try:
        page_size = source.page_size
        buffer = AcquisitionRingBuffer(capacity=max(8, int(args.seconds / args.interval) + 4))
        acquirer = StaticAcquirer(source, buffer)
        print(f"mapping=Local\\acpmf_static")
        print(f"mapping_size_bytes={page_size}")
        print("source_packet_id=unavailable (not defined by Static layout)")
        print("source_timestamp=unavailable (not defined by Static layout)")
        print(f"capture_window_seconds={args.seconds}")
        print("Keep ACC running. If practical, change session/car/track during this window.")
        deadline = time.monotonic()
        end = deadline + args.seconds
        while time.monotonic() < end:
            snapshot = acquirer.capture_once()
            if snapshot is not None:
                digest = hashlib.sha256(snapshot.payload).hexdigest()
                print(
                    f"CAPTURE sequence={snapshot.capture_sequence} "
                    f"bytes={len(snapshot.payload)} sha256={digest} "
                    f"read_start_ns={snapshot.read_start_ns} "
                    f"read_complete_ns={snapshot.read_complete_ns} "
                    f"source_packet_id=None source_timestamp_ns=None"
                )
            deadline += args.interval
            time.sleep(max(0.0, deadline - time.monotonic()))

        m = acquirer.metrics
        print("--- SUMMARY ---")
        print(f"mapping_size_bytes={page_size}")
        print(f"reads={m.read_count}")
        print(f"emitted_snapshots={m.capture_count}")
        print(f"unchanged_reads={m.unchanged_read_count}")
        print(f"buffer_rejections={m.buffer_rejection_count}")
        print(f"last_capture_sequence={m.last_capture_sequence}")
        print(f"max_read_duration_ns={m.max_acquisition_duration_ns}")
        print("cross_stream_sync=invented: no")
        return 0 if m.read_count > 0 and m.capture_count >= 1 and m.buffer_rejection_count == 0 else 2
    finally:
        source.close()


if __name__ == "__main__":
    raise SystemExit(main())
