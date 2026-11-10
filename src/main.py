"""Launch the greenfield ACC-only Qt desktop application.

Build the React frontend first from frontend/ with: npm.cmd run build
Then launch from the repository root with: python -m src.main
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    if os.name != "nt":
        print("The ACC Shared Memory desktop runtime requires Windows.", file=sys.stderr)
        return 2
    try:
        from .desktop.qt_host import run_desktop
    except ImportError as exc:
        print(f"Desktop dependencies are missing: {exc}", file=sys.stderr)
        print("Install requirements-desktop.txt and rebuild the frontend.", file=sys.stderr)
        return 2
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
