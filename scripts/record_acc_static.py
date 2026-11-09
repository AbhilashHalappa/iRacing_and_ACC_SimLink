"""Record changed raw ACC Static pages off the acquisition thread.

Run on Windows with ACC open. Only the initial page and later changed pages
are queued; unchanged refreshes are never persisted.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import StaticAcquirer, WindowsACCStaticSource
from race_engineer_acquisition.static_recording import (
    StaticRecorderWorker, recover_static_recording,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("--refresh-seconds", type=float, default=1.0)
    parser.add_argument("--acquisition-buffer-capacity", type=int, default=64)
    parser.add_argument("--recorder-buffer-capacity", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=Path("user_data/raw_recordings"))
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.refresh_seconds <= 0:
        parser.error("duration and refresh interval must be positive")
    if min(args.acquisition_buffer_capacity, args.recorder_buffer_capacity, args.batch_size) <= 0:
        parser.error("buffer capacities and batch size must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_utc = datetime.now(timezone.utc)
    stem = started_utc.strftime("acc_static_%Y%m%dT%H%M%S_%fZ")
    recording_path = args.output_dir / f"{stem}.straw"
    report_path = args.output_dir / f"{stem}.json"

    source = WindowsACCStaticSource()
    page_size = source.page_size
    acquisition_buffer = AcquisitionRingBuffer(args.acquisition_buffer_capacity)
    recorder_buffer = AcquisitionRingBuffer(args.recorder_buffer_capacity)
    acquirer = StaticAcquirer(source, acquisition_buffer)
    recorder = StaticRecorderWorker(
        recorder_buffer, recording_path, page_size=page_size, batch_size=args.batch_size,
    )
    acquisition_stop = threading.Event()
    recorder_stop = threading.Event()
    producer_done = threading.Event()
    dispatcher_done = threading.Event()
    producer_errors: list[str] = []
    dispatcher_stats = {"transferred": 0, "in_flight": None}

    def producer() -> None:
        try:
            acquirer.run(
                acquisition_stop,
                refresh_interval_ns=max(1, round(args.refresh_seconds * 1_000_000_000)),
            )
        except Exception as exc:
            producer_errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                source.close()
            except Exception as exc:
                producer_errors.append(f"source close {type(exc).__name__}: {exc}")
            producer_done.set()

    def dispatcher() -> None:
        while not producer_done.is_set() or acquisition_buffer.size:
            item = acquisition_buffer.try_get()
            if item is None:
                time.sleep(0.0005)
                continue
            dispatcher_stats["in_flight"] = item.capture_sequence
            if recorder_buffer.try_put(item):
                dispatcher_stats["transferred"] += 1
            dispatcher_stats["in_flight"] = None
        dispatcher_done.set()

    recorder_thread = threading.Thread(
        target=recorder.run, args=(recorder_stop,), name="ACC-Static-Recorder", daemon=True
    )
    dispatcher_thread = threading.Thread(
        target=dispatcher, name="ACC-Static-Dispatcher", daemon=True
    )
    producer_thread = threading.Thread(
        target=producer, name="ACC-Static-Acquisition", daemon=True
    )

    producer_thread.start()
    recorder_thread.start()
    dispatcher_thread.start()
    producer_thread.join(args.duration_seconds)
    if producer_thread.is_alive():
        acquisition_stop.set()
        producer_thread.join(10.0)
    else:
        acquisition_stop.set()
    if producer_thread.is_alive():
        raise RuntimeError("Static acquisition worker did not stop within 10 seconds")
    dispatcher_thread.join(10.0)
    if dispatcher_thread.is_alive():
        raise RuntimeError("Static dispatcher did not drain within 10 seconds")
    recorder_stop.set()
    recorder_thread.join(30.0)
    if recorder_thread.is_alive():
        raise RuntimeError("Static recorder did not drain within 30 seconds")

    recovery = recover_static_recording(recording_path)
    acquired = acquirer.metrics.capture_count
    persisted = recorder.metrics.persisted_snapshot_count
    acquisition_rejected = acquisition_buffer.total_rejection_count
    recorder_rejected = recorder_buffer.total_rejection_count
    failed = recorder.metrics.failed_snapshot_count
    pending = acquisition_buffer.size + recorder_buffer.size
    in_flight = int(dispatcher_stats["in_flight"] is not None) + recorder.metrics.in_flight_snapshot_count
    delta = acquired - persisted - acquisition_rejected - recorder_rejected - failed - pending - in_flight
    report = {
        "recording_file": recording_path.name,
        "format_version": 2,
        "page_size": page_size,
        "acquisition": {
            "reads": acquirer.metrics.read_count,
            "changed_pages": acquired,
            "unchanged_reads": acquirer.metrics.unchanged_read_count,
            "buffer_rejections": acquisition_rejected,
            "last_capture_sequence": acquirer.metrics.last_capture_sequence,
        },
        "dispatcher": {"transferred": dispatcher_stats["transferred"]},
        "recorder": {
            "persisted_pages": persisted,
            "blocks": recorder.metrics.persisted_block_count,
            "write_failures": recorder.metrics.write_failure_count,
            "failed_pages": failed,
            "queue_rejections": recorder_rejected,
            "max_block_write_duration_ns": recorder.metrics.max_block_write_duration_ns,
        },
        "recovery": {
            "valid_blocks": recovery.valid_block_count,
            "recovered_pages": recovery.recovered_snapshot_count,
            "truncated_bytes": recovery.truncated_bytes,
        },
        "accounting": {"pending": pending, "in_flight": in_flight, "reconciliation_delta": delta},
        "producer_errors": producer_errors,
        "recorder_error": recorder.error,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Status                  : {'completed' if not producer_errors and recorder.error is None else 'failed'}")
    print(f"Recording               : {recording_path}")
    print(f"Report                  : {report_path}")
    print(f"Mapping page size       : {page_size} bytes")
    print(f"Reads                   : {acquirer.metrics.read_count}")
    print(f"Changed pages acquired  : {acquired}")
    print(f"Unchanged reads         : {acquirer.metrics.unchanged_read_count}")
    print(f"Persisted               : {persisted}")
    print(f"Recorder write failures : {recorder.metrics.write_failure_count}")
    print(f"Acquisition rejects     : {acquisition_rejected}")
    print(f"Recorder queue rejects  : {recorder_rejected}")
    print(f"Pending                 : {pending}")
    print(f"Reconciliation delta    : {delta}")
    print(f"Recovery validation     : {recovery.recovered_snapshot_count == persisted and recovery.truncated_bytes == 0}")
    print(f"Source packet ID        : None")
    print(f"Source timestamp        : None")
    print(f"Producer errors         : {producer_errors}")
    print(f"Recorder error          : {recorder.error}")
    return 0 if (
        not producer_errors and recorder.error is None
        and persisted == acquired and acquisition_rejected == 0
        and recorder_rejected == 0 and pending == 0 and in_flight == 0
        and delta == 0 and recovery.recovered_snapshot_count == persisted
        and recovery.truncated_bytes == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
