import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from race_engineer_acquisition.checkpoint import read_checkpoint, write_checkpoint


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_round_trip_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.checkpoint.json"
            payload = {
                "schema_version": 1,
                "checkpoint_sequence": 7,
                "acquisition": {"capture_count": 123, "last_capture_sequence": 123},
            }
            write_checkpoint(path, payload)
            self.assertEqual(read_checkpoint(path), payload)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_checkpoint_rejects_modified_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.checkpoint.json"
            write_checkpoint(path, {"schema_version": 1, "checkpoint_sequence": 1})
            path.write_text(
                path.read_text(encoding="utf-8").replace('"checkpoint_sequence":1', '"checkpoint_sequence":2'),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                read_checkpoint(path)

    def test_failed_atomic_replace_preserves_previous_valid_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.checkpoint.json"
            original = {"schema_version": 1, "checkpoint_sequence": 1}
            write_checkpoint(path, original)
            with patch("race_engineer_acquisition.checkpoint.os.replace", side_effect=OSError("simulated replace failure")):
                with self.assertRaises(OSError):
                    write_checkpoint(path, {"schema_version": 1, "checkpoint_sequence": 2})
            self.assertEqual(read_checkpoint(path), original)
            self.assertTrue(path.with_name(path.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
