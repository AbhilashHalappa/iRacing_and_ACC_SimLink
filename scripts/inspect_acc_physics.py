"""Command-line entry point for offline ACC Physics recording inspection."""
from __future__ import annotations

import argparse
from pathlib import Path

from race_engineer_acquisition.inspection import inspect_recording, write_inspection_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="Completed .accraw recording")
    parser.add_argument("--json-out", type=Path, help="JSON report path")
    parser.add_argument("--csv-out", type=Path, help="Optional per-field CSV report path")
    args = parser.parse_args()
    if not args.recording.is_file():
        parser.error(f"recording does not exist: {args.recording}")

    report = inspect_recording(args.recording)
    json_path = args.json_out or args.recording.with_suffix(".physics-inspection.json")
    write_inspection_outputs(report, json_path, args.csv_out)
    varying = sum(row["observed_behavior"] == "varies" for row in report["fields"])
    constant = sum(row["observed_behavior"] == "constant" for row in report["fields"])
    print(f"Recording              : {args.recording}")
    print(f"Snapshots inspected    : {report['snapshot_count']}")
    print(f"Payload size           : {report['payload_size_bytes']} bytes")
    print(f"Field components       : {report['field_component_count']}")
    print(f"Components varying     : {varying}")
    print(f"Components constant    : {constant}")
    print(f"JSON report            : {json_path}")
    if args.csv_out:
        print(f"CSV report             : {args.csv_out}")
    print("Note: variation alone does not establish field meaning or correctness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
