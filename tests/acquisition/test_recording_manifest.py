from __future__ import annotations

import unittest

from race_engineer_acquisition.recording_manifest import build_recording_manifest


class RecordingManifestTests(unittest.TestCase):
    def test_physics_manifest_maps_accounting_and_packet_metadata(self):
        report = {
            "recording_file": "p.accraw",
            "started_at_utc": "2026-11-10T00:00:00+00:00",
            "finished_at_utc": "2026-11-10T00:01:00+00:00",
            "status": "completed",
            "completion_failure_reasons": [],
            "recovery_validation_passed": True,
            "recovery_validation": {
                "recovered_snapshot_count": 480, "truncated_bytes": 0,
            },
            "acquisition_metrics": {
                "last_capture_sequence": 480, "last_packet_id": 9001,
            },
            "reconciliation": {
                "acquired": 480, "persisted": 480, "recorder_failed_samples": 0,
                "acquisition_buffer_rejections": 0,
                "recorder_buffer_rejections": 0, "delta": 0,
            },
        }
        manifest = build_recording_manifest(
            "physics", report, recording_format_version=2,
            session_metadata={"track": "monza", "layout_id": "acc-static-v1.9-candidate-b"},
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["completion_status"], "completed")
        self.assertEqual(manifest["stream_summary"]["captured_count"], 480)
        self.assertEqual(manifest["stream_summary"]["first_capture_sequence"], 1)
        self.assertEqual(manifest["stream_summary"]["last_source_packet_id"], 9001)
        self.assertEqual(manifest["session"]["track"], "monza")
        self.assertEqual(manifest["integrity"]["reconciliation_delta"], 0)

    def test_graphics_failed_report_is_not_marked_completed(self):
        report = {
            "recording_file": "g.gfxraw", "status": "failed",
            "completion_failure_reasons": ["recorder queue overflow"],
            "recovery_validation_passed": False,
            "recovery_validation": {"recovered_snapshot_count": 8, "truncated_bytes": 0},
            "acquisition_metrics": {"last_capture_sequence": 10, "last_packet_id": 99},
            "reconciliation": {
                "acquired": 10, "persisted": 8, "recorder_write_failures": 0,
                "acquisition_buffer_rejections": 0,
                "recorder_buffer_rejections": 2, "delta": 0,
            },
        }
        manifest = build_recording_manifest("graphics", report, recording_format_version=2)
        self.assertEqual(manifest["completion_status"], "failed")
        self.assertEqual(manifest["completion_failure_reasons"], ["recorder queue overflow"])
        self.assertEqual(manifest["stream_summary"]["recorder_rejection_count"], 2)
        self.assertFalse(manifest["integrity"]["recovery_valid"])

    def test_static_never_invents_source_packet_metadata(self):
        report = {
            "recording_file": "s.straw", "status": "completed",
            "completion_failure_reasons": [],
            "acquisition": {"changed_pages": 1, "last_capture_sequence": 1, "buffer_rejections": 0},
            "recorder": {"persisted_pages": 1, "failed_pages": 0, "queue_rejections": 0},
            "recovery": {"recovered_pages": 1, "truncated_bytes": 0},
            "accounting": {"reconciliation_delta": 0},
        }
        manifest = build_recording_manifest("static", report, recording_format_version=2)
        self.assertIsNone(manifest["stream_summary"]["first_source_packet_id"])
        self.assertIsNone(manifest["stream_summary"]["last_source_packet_id"])
        self.assertEqual(manifest["stream_summary"]["captured_count"], 1)
        self.assertTrue(manifest["integrity"]["recovery_valid"])

    def test_unknown_stream_rejected(self):
        with self.assertRaises(ValueError):
            build_recording_manifest("telemetry", {}, recording_format_version=2)

    def test_failed_report_gets_explicit_reason_when_missing(self):
        manifest = build_recording_manifest(
            "static", {"recording_file": "s.straw", "status": "failed"},
            recording_format_version=2,
        )
        self.assertTrue(manifest["completion_failure_reasons"])


if __name__ == "__main__":
    unittest.main()
