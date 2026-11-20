"""Durable canonical track-model persistence for Performance Hub.

A canonical model is explicitly anchored to a selected valid reference lap.
Stable corner IDs are minted only when that reference model is persisted; they
are then reused by later candidate-lap matches. No ID is derived from a
track/configuration ordinal alone.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any, Mapping

from .corner_identity import match_corner_identities
from .storage_paths import performance_hub_data_dir

SCHEMA_VERSION = 1


def _normalized_identity_value(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return " ".join(value.strip().casefold().split())


def _track_model_key(track: str, track_configuration: str) -> str:
    identity = {
        "track": _normalized_identity_value(track, "track"),
        "track_configuration": _normalized_identity_value(
            track_configuration, "track_configuration"
        ),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe_model(model: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(dict(model), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"track model must contain finite JSON-compatible values: {exc}") from exc


class CanonicalTrackModelStore:
    """Atomic JSON store for one canonical model per track/configuration."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else performance_hub_data_dir() / "track_models"

    def _path(self, track: str, track_configuration: str) -> Path:
        return self.root / f"{_track_model_key(track, track_configuration)}.json"

    def save_reference_model(
        self,
        track: str,
        track_configuration: str,
        model: Mapping[str, Any],
        *,
        reference_session_id: str,
        reference_lap_number: int,
        reference_lap_time_ms: int | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Persist a selected reference model and assign durable corner IDs.

        Existing canonical models are not replaced unless the caller explicitly
        requests a rebaseline. An explicit rebaseline starts a new stable-corner
        identity set; callers must not treat the new IDs as continuations of the
        previous canonical model.
        """
        if not isinstance(reference_session_id, str) or not reference_session_id.strip():
            raise ValueError("reference_session_id must be a non-empty string")
        if isinstance(reference_lap_number, bool) or not isinstance(reference_lap_number, int) or reference_lap_number < 1:
            raise ValueError("reference_lap_number must be a positive integer")
        if reference_lap_time_ms is not None and (
            isinstance(reference_lap_time_ms, bool)
            or not isinstance(reference_lap_time_ms, int)
            or reference_lap_time_ms <= 0
        ):
            raise ValueError("reference_lap_time_ms must be a positive integer or None")

        normalized = _json_safe_model(model)
        if normalized.get("available") is not True:
            raise ValueError("only an available track model can become canonical")
        if normalized.get("coordinate_system") != "source_xyz_unrotated":
            raise ValueError("canonical model must use source_xyz_unrotated coordinates")
        if not isinstance(normalized.get("points"), list) or not normalized["points"]:
            raise ValueError("canonical model must contain trajectory points")
        if not isinstance(normalized.get("corners"), list):
            raise ValueError("canonical model corners must be a list")

        path = self._path(track, track_configuration)
        if path.exists() and not replace_existing:
            raise FileExistsError(
                "a canonical model already exists for this track/configuration; "
                "explicit rebaseline is required"
            )

        corners = normalized["corners"]
        seen_ids: set[str] = set()
        for corner in corners:
            if not isinstance(corner, dict):
                raise ValueError("each canonical corner must be an object")
            stable_id = corner.get("stable_corner_id")
            if not isinstance(stable_id, str) or not stable_id.strip():
                stable_id = f"corner-{uuid.uuid4().hex}"
            if stable_id in seen_ids:
                raise ValueError("canonical stable corner IDs must be unique")
            seen_ids.add(stable_id)
            corner["stable_corner_id"] = stable_id
            corner["identity_scope"] = "persisted_track_configuration"

        document = {
            "schema_version": SCHEMA_VERSION,
            "track": track.strip(),
            "track_configuration": track_configuration.strip(),
            "track_model_key": _track_model_key(track, track_configuration),
            "reference": {
                "session_id": reference_session_id.strip(),
                "lap_number": reference_lap_number,
                "lap_time_ms": reference_lap_time_ms,
            },
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": normalized,
        }
        encoded = json.dumps(document, indent=2, sort_keys=True, allow_nan=False)

        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.root,
                prefix=f".{path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists() and not replace_existing:
                raise FileExistsError(path)
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return document

    def load(
        self, track: str, track_configuration: str
    ) -> dict[str, Any] | None:
        path = self._path(track, track_configuration)
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"canonical track model is unreadable: {path}: {exc}") from exc
        if document.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported canonical track model schema: {document.get('schema_version')}"
            )
        if document.get("track_model_key") != _track_model_key(track, track_configuration):
            raise ValueError("canonical track model identity does not match requested track/configuration")
        return document

    def match_candidate(
        self,
        track: str,
        track_configuration: str,
        candidate_model: Mapping[str, Any],
        *,
        max_apex_separation_m: float,
        max_apex_distance_delta_m: float,
    ) -> dict[str, Any]:
        """Attach persisted stable corner IDs to a candidate lap model."""
        document = self.load(track, track_configuration)
        if document is None:
            return {
                **dict(candidate_model),
                "identity_matching_available": False,
                "identity_matching_reason": "canonical_track_model_not_found",
            }
        return match_corner_identities(
            document["model"],
            candidate_model,
            max_apex_separation_m=max_apex_separation_m,
            max_apex_distance_delta_m=max_apex_distance_delta_m,
        )

    def list_models(self) -> tuple[dict[str, Any], ...]:
        """List readable canonical model metadata without loading trajectory payloads."""
        if not self.root.is_dir():
            return ()
        result = []
        for path in sorted(self.root.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("schema_version") != SCHEMA_VERSION:
                continue
            result.append({
                "track": document.get("track"),
                "track_configuration": document.get("track_configuration"),
                "track_model_key": document.get("track_model_key"),
                "reference": document.get("reference"),
                "created_at_utc": document.get("created_at_utc"),
                "corner_count": len(document.get("model", {}).get("corners", [])),
            })
        return tuple(result)
