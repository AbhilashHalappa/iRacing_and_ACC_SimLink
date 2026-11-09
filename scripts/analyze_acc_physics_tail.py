#!/usr/bin/env python3
"""Offline analysis of ACC Physics tail-correlation CSV captures.

This script reads only the CSV files produced by
scripts/probe_acc_physics_correlations.py. It performs no ACC shared-memory
access and makes no changes to production data.

It reports:
- signed and absolute tail-channel distributions, RMS and non-zero counts;
- Pearson correlations of absolute tail amplitude against absolute acceleration
  and per-sample suspension-travel changes;
- lagged correlations over a configurable window (positive lag means the
  predictor occurs before the tail response);
- isolated high-amplitude tail events and nearby motion/suspension values.

Example:
  python scripts/analyze_acc_physics_tail.py user_data/raw_recordings/physics-correlations-*.csv
  python scripts/analyze_acc_physics_tail.py --max-lag-ms 200 --event-percentile 99 user_data/raw_recordings/physics-correlations-*.csv

Correlation is descriptive, not proof of channel meaning or causation.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

TAILS = ("tail_784", "tail_788", "tail_792", "tail_796")
WHEELS = ("fl", "fr", "rl", "rr")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def lagged_pearson(tail: list[float], predictor: list[float], lag: int) -> float | None:
    # Positive lag: predictor at an earlier sample is compared with tail now.
    if lag > 0:
        return pearson(tail[lag:], predictor[:-lag])
    if lag < 0:
        return pearson(tail[:lag], predictor[-lag:])
    return pearson(tail, predictor)


def load_csv(path: Path) -> list[dict[str, float]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {
            "elapsed_s", "speed_kph", "throttle", "brake",
            "acc_g_x", "acc_g_y", "acc_g_z",
            *(f"susp_travel_{wheel}" for wheel in WHEELS),
            *TAILS,
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        rows: list[dict[str, float]] = []
        for line, raw in enumerate(reader, start=2):
            try:
                row = {key: float(raw[key]) for key in required}
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"{path}:{line}: invalid numeric value: {exc}") from exc
            if not all(math.isfinite(value) for value in row.values()):
                continue
            rows.append(row)
    return rows


def build_predictors(rows: list[dict[str, float]]) -> dict[str, list[float]]:
    predictors = {
        "abs_acc_g_x": [abs(row["acc_g_x"]) for row in rows],
        "abs_acc_g_y": [abs(row["acc_g_y"]) for row in rows],
        "abs_acc_g_z": [abs(row["acc_g_z"]) for row in rows],
    }
    for wheel in WHEELS:
        travel = [row[f"susp_travel_{wheel}"] for row in rows]
        predictors[f"abs_susp_delta_{wheel}"] = [
            0.0 if i == 0 else abs(travel[i] - travel[i - 1])
            for i in range(len(travel))
        ]
    return predictors


def analyse(path: Path, args: argparse.Namespace) -> None:
    rows = load_csv(path)
    print("\n" + "=" * 88)
    print(f"FILE: {path}")
    print(f"Samples: {len(rows)}")
    if len(rows) < 10:
        print("Insufficient samples; skipping.")
        return

    elapsed = [row["elapsed_s"] for row in rows]
    intervals = [b - a for a, b in zip(elapsed, elapsed[1:]) if b > a]
    sample_ms = statistics.median(intervals) * 1000.0 if intervals else 10.0
    max_lag = max(0, round(args.max_lag_ms / sample_ms))
    print(f"Median sample interval: {sample_ms:.2f} ms")
    print(f"Lag window: +/-{max_lag} samples (~{max_lag * sample_ms:.0f} ms)")

    predictors = build_predictors(rows)
    print("\nTail amplitude statistics:")
    for name in TAILS:
        signed = [row[name] for row in rows]
        absolute = [abs(value) for value in signed]
        rms = math.sqrt(statistics.fmean(value * value for value in signed))
        nonzero = sum(value != 0.0 for value in signed)
        print(
            f"  {name}: min={min(signed):+.6f} max={max(signed):+.6f} "
            f"mean_abs={statistics.fmean(absolute):.6f} "
            f"RMS={rms:.6f} p95_abs={percentile(absolute, .95):.6f} "
            f"p99_abs={percentile(absolute, .99):.6f} "
            f"nonzero={nonzero}/{len(signed)} ({100*nonzero/len(signed):.2f}%)"
        )

    print("\nZero-lag Pearson correlation: abs(tail) vs motion predictors")
    for tail_name in TAILS:
        tail_abs = [abs(row[tail_name]) for row in rows]
        parts = []
        for predictor_name, values in predictors.items():
            r = pearson(tail_abs, values)
            parts.append(f"{predictor_name}={'n/a' if r is None else f'{r:+.3f}'}")
        print(f"  {tail_name}: " + " | ".join(parts))

    print("\nStrongest lagged correlations (abs(tail) vs predictor)")
    for tail_name in TAILS:
        tail_abs = [abs(row[tail_name]) for row in rows]
        print(f"  {tail_name}:")
        for predictor_name, values in predictors.items():
            candidates = [
                (abs(r), r, lag)
                for lag in range(-max_lag, max_lag + 1)
                if (r := lagged_pearson(tail_abs, values, lag)) is not None
            ]
            if not candidates:
                print(f"    {predictor_name:20s} n/a")
                continue
            _, best_r, best_lag = max(candidates)
            relation = "predictor leads" if best_lag > 0 else (
                "tail leads" if best_lag < 0 else "same sample"
            )
            print(
                f"    {predictor_name:20s} r={best_r:+.3f} "
                f"lag={best_lag * sample_ms:+.0f}ms ({relation})"
            )

    print(
        f"\nLargest tail events (top {args.events} per channel; "
        f"event threshold p{args.event_percentile:g})"
    )
    for tail_name in TAILS:
        amplitudes = [abs(row[tail_name]) for row in rows]
        threshold = percentile(amplitudes, args.event_percentile / 100.0)
        candidates = sorted(
            (i for i, value in enumerate(amplitudes) if value >= threshold and value > 0),
            key=lambda i: amplitudes[i],
            reverse=True,
        )
        selected: list[int] = []
        for index in candidates:
            if all(abs(index - prior) > args.event_spacing for prior in selected):
                selected.append(index)
            if len(selected) >= args.events:
                break
        print(f"  {tail_name}: threshold={threshold:.6f}")
        if not selected:
            print("    no non-zero events")
            continue
        for index in selected:
            row = rows[index]
            nearby = []
            left, right = max(0, index - 5), min(len(rows), index + 6)
            for predictor_name, values in predictors.items():
                peak = max(values[left:right]) if right > left else 0.0
                nearby.append(f"{predictor_name}={values[index]:.4g}/winmax:{peak:.4g}")
            print(
                f"    t={row['elapsed_s']:.3f}s sample={index} "
                f"value={row[tail_name]:+.5f} speed={row['speed_kph']:.1f}kph "
                + " | ".join(nearby)
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Probe CSV files to analyse")
    parser.add_argument("--max-lag-ms", type=float, default=200.0,
                        help="Maximum absolute lag in milliseconds (default: 200)")
    parser.add_argument("--event-percentile", type=float, default=99.0,
                        help="Tail absolute-amplitude event percentile (default: 99)")
    parser.add_argument("--events", type=int, default=8,
                        help="Maximum separated events per channel (default: 8)")
    parser.add_argument("--event-spacing", type=int, default=10,
                        help="Minimum sample spacing between reported peaks (default: 10)")
    args = parser.parse_args()
    if args.max_lag_ms < 0 or not 50 <= args.event_percentile <= 100:
        parser.error("--max-lag-ms must be non-negative and --event-percentile between 50 and 100")
    if args.events < 1 or args.event_spacing < 1:
        parser.error("--events and --event-spacing must be positive")

    paths: list[Path] = []
    for pattern in args.files:
        matches = sorted(pattern.parent.glob(pattern.name)) if any(c in pattern.name for c in "*?[") else [pattern]
        paths.extend(matches)
    paths = list(dict.fromkeys(paths))
    if not paths:
        parser.error("No CSV files matched.")
    failures = 0
    for path in paths:
        if not path.is_file():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            failures += 1
            continue
        try:
            analyse(path, args)
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
