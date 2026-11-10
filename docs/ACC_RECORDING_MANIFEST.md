# ACC Recording Manifest — Common Metadata Contract

**Status:** Schema design for acquisition Issue #9  
**Applies to:** Physics, Graphics and Static recording reports  
**Manifest schema version:** 1  
**Raw recording format:** Stream-specific; currently version 2

## Purpose and compatibility

Every completed or incomplete raw recording has a sidecar JSON report containing a top-level `manifest` object. Existing stream-specific report fields remain in place during this migration; consumers can adopt the common manifest without breaking current validation scripts. The manifest is written only by the recording/control thread after acquisition has stopped and recorder finalization/recovery has completed. It is never assembled or serialized in an acquisition worker.

The manifest describes one file and one stream. Physics, Graphics and Static remain independent recordings; a shared session label is descriptive metadata only and does not imply sample-level synchronization.

## Common fields

| Field | Type | Contract |
|---|---|---|
| `schema_version` | integer | Manifest schema version; currently `1` |
| `recording_id` | string | Unique UUID for this recording file |
| `stream` | string | `physics`, `graphics`, or `static` |
| `recording_file` | string | File name relative to the report directory |
| `started_at_utc` | string | ISO-8601 UTC timestamp, explicit `Z` or `+00:00` |
| `finished_at_utc` | string or null | ISO-8601 UTC finalization time; null if finalization did not complete |
| `application_version` | string or null | Installed/source application version when discoverable; null when repository metadata does not define one |
| `recording_format_version` | integer | Version encoded in the raw recording header |
| `completion_status` | string | `completed`, `incomplete`, or `failed` |
| `completion_failure_reasons` | array of strings | Empty only when all stream completion gates pass |
| `session` | object | ACC metadata fields, each nullable when unavailable |
| `stream_summary` | object | Stream-specific counts and source sequence/packet ranges |
| `integrity` | object | Recovery/CRC and accounting reconciliation summary |

## Session metadata

The `session` object has these nullable fields: `sm_version`, `ac_version`, `car_model`, `track`, `track_configuration`, `player_name`, `player_surname`, `player_nick`, `is_online`, and `layout_id`.

These values may be populated only from a successfully decoded ACC Static page using the explicitly qualified Static candidate layout. Preserve the decoder's `layout_id` as provenance. If the Static page is unavailable, too short, or fails strict decoding, leave the affected values null and add a non-fatal metadata warning; do not guess from Physics/Graphics values, filenames, UI state, or another stream's report. Metadata warnings do not by themselves make a raw recording incomplete.

## Stream summary

All streams include `captured_count`, `persisted_count`, `failed_count`, `acquisition_rejection_count`, `recorder_rejection_count`, `first_capture_sequence`, and `last_capture_sequence`.

Physics and Graphics additionally include `first_source_packet_id` and `last_source_packet_id`. Static sets both to null because ACC Static has no documented source packet ID. Do not substitute capture sequence or a Physics/Graphics packet ID.

Counts must reconcile with the stream's existing accounting report. The manifest is a compact index, not a replacement for detailed acquisition, dispatcher, recorder, checkpoint, or recovery metrics.

## Integrity

The `integrity` object includes `recovery_valid`, `recovered_count`, `truncated_bytes`, `reconciliation_delta`, and `metadata_warnings`. For streams without a checkpoint worker, checkpoint fields are omitted rather than fabricated.

A successful completion requires the existing stream-specific completion policy to pass, all required samples to be persisted, no required queue losses/failures/pending work, a valid recovered recording with no truncated tail, and zero reconciliation delta. A partial but recoverable raw file is still `incomplete` or `failed`, not `completed`.

## Example

```json
{
  "manifest": {
    "schema_version": 1,
    "recording_id": "UUID",
    "stream": "static",
    "recording_file": "acc_static_....straw",
    "started_at_utc": "2026-11-10T00:00:00+00:00",
    "finished_at_utc": "2026-11-10T00:02:00+00:00",
    "application_version": null,
    "recording_format_version": 2,
    "completion_status": "completed",
    "completion_failure_reasons": [],
    "session": {
      "sm_version": null,
      "ac_version": null,
      "car_model": null,
      "track": null,
      "track_configuration": null,
      "player_name": null,
      "player_surname": null,
      "player_nick": null,
      "is_online": null,
      "layout_id": null
    },
    "stream_summary": {
      "captured_count": 1,
      "persisted_count": 1,
      "failed_count": 0,
      "acquisition_rejection_count": 0,
      "recorder_rejection_count": 0,
      "first_capture_sequence": 1,
      "last_capture_sequence": 1,
      "first_source_packet_id": null,
      "last_source_packet_id": null
    },
    "integrity": {
      "recovery_valid": true,
      "recovered_count": 1,
      "truncated_bytes": 0,
      "reconciliation_delta": 0,
      "metadata_warnings": ["ACC Static metadata not available"]
    }
  }
}
```

The example is illustrative; the UUID and counts are not actual recording evidence.
