"""Launch the SimLink Overview desktop application for ACC or iRacing.

Build frontend/ first with npm.cmd run build, then use:
    python -m src.main --game acc
    python -m src.main --game iracing
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    if os.name != "nt":
        print("The desktop telemetry runtime requires Windows.", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="SimLink live Overview dashboard")
    parser.add_argument(
        "--game",
        choices=("acc", "iracing"),
        default="acc",
        help="Telemetry source to use (default: acc).",
    )
    args = parser.parse_args()

    try:
        from .desktop.switchable_host import run_desktop
    except ImportError as exc:
        print(f"Desktop dependencies are missing: {exc}", file=sys.stderr)
        print("Install requirements-desktop.txt and rebuild the frontend.", file=sys.stderr)
        return 2
    return run_desktop(initial_game=args.game)


if __name__ == "__main__":
    raise SystemExit(main())
