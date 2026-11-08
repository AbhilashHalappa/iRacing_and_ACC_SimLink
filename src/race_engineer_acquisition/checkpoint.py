"""Durable, atomic progress checkpoints for interrupted ACC recordings.

A checkpoint is a periodic point-in-time diagnostic snapshot, not a replacement
for the CRC-protected recording. It is written by a separate thread and replaced
atomically so a process kill cannot leave a half-written checkpoint in place of
the previous valid one.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from threading import Event
from typing import Callable


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_checkpoint(path: str | Path, payload: dict) -> None:
    """Atomically persist a checksummed JSON checkpoint and fsync its contents."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical_payload(payload)
    envelope = {
        "payload": payload,
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    encoded = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8") + b"\n"
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    # Directory fsync is supported on POSIX. Windows uses atomic same-volume
    # replacement; opening a directory handle this way is not portable there.
    if os.name != "nt":
        directory_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def read_checkpoint(path: str | Path) -> dict:
    """Read and validate a checkpoint; reject torn or modified JSON payloads."""
    source = Path(path)
    try:
        envelope = json.loads(source.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        checksum = envelope["sha256"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Checkpoint is incomplete or malformed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(checksum, str):
        raise ValueError("Checkpoint envelope has invalid field types")
    actual = hashlib.sha256(_canonical_payload(payload)).hexdigest()
    if not hmac.compare_digest(actual, checksum):
        raise ValueError("Checkpoint checksum mismatch")
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported checkpoint schema version")
    return payload


class PeriodicCheckpointWorker:
    """Write snapshots periodically, without running on acquisition/recorder threads."""

    def __init__(
        self,
        path: str | Path,
        snapshot_factory: Callable[[], dict],
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.path = Path(path)
        self.snapshot_factory = snapshot_factory
        self.interval_seconds = interval_seconds
        self.write_count = 0
        self.error: str | None = None

    def write_once(self) -> None:
        try:
            write_checkpoint(self.path, self.snapshot_factory())
            self.write_count += 1
            self.error = None
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def run(self, stop_event: Event) -> None:
        # Write immediately so even a very short run has a baseline checkpoint.
        self.write_once()
        while not stop_event.wait(self.interval_seconds):
            self.write_once()
        # On a graceful stop, capture final counters after the workers have
        # drained. A forced process termination leaves the last periodic copy.
        self.write_once()
