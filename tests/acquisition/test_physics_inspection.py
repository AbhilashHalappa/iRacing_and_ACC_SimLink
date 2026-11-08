from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from race_engineer_acquisition.acc_windows import PHYSICS_SIZE, _Physics
from race_engineer_acquisition.inspection import inspect_recording, read_raw_payloads
from race_engineer_acquisition.models import PhysicsSnapshot
from race_engineer_acquisition.recorder import RawPhysicsRecordingWriter


def make_payload(throttle: float, brake: float, rpm: int) -> bytes:
    page = _Physics()
    page.packet_id = rpm
    page.throttle = throttle
    page.brake = brake
    page.rpm = rpm
    page.speed_kph = 0.0
    return bytes(page)


class PhysicsInspectionTests(unittest.TestCase):
    def test_reads_and_summarizes_every_field_component_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.accraw"
            payloads = [make_payload(0.0, 0.0, 800), make_payload(1.0, 0.0, 3000),
                        make_payload(0.0, 0.5, 1200)]
            with RawPhysicsRecordingWriter(path, payload_size=PHYSICS_SIZE) as writer:
                writer.write_batch([
                    PhysicsSnapshot(i + 1, i + 10, i, i + 1, i + 1, payload)
                    for i, payload in enumerate(payloads)
                ])

            size, samples = read_raw_payloads(path)
            self.assertEqual(size, PHYSICS_SIZE)
            self.assertEqual(len(samples), 3)
            report = inspect_recording(path)
            by_name = {row["name"]: row for row in report["fields"]}
            self.assertEqual(report["snapshot_count"], 3)
            self.assertEqual(by_name["throttle"]["observed_behavior"], "varies")
            self.assertEqual(by_name["brake"]["maximum"], 0.5)
            self.assertEqual(by_name["rpm"]["minimum"], 800.0)
            self.assertEqual(by_name["rpm"]["maximum"], 3000.0)
            self.assertEqual(by_name["rpm"]["field_type"], "int32")
            self.assertEqual(by_name["rpm"]["field_offset_bytes"], 20)
            self.assertEqual(by_name["rpm"]["field_size_bytes"], 4)
            self.assertEqual(by_name["rpm"]["array_length"], 1)
            self.assertEqual(by_name["rpm"]["component_offset_bytes"], 20)
            self.assertTrue(by_name["rpm"]["unique_values_count_exact"])
            self.assertEqual(by_name["speed_kph"]["observed_behavior"], "constant")
            expected_components = sum(
                field_type._length_ if hasattr(field_type, "_length_") else 1
                for _field_name, field_type in _Physics._fields_
            )
            self.assertEqual(report["field_component_count"], expected_components)
            self.assertIn("wheel_slip[3]", by_name)

    def test_marks_unique_value_count_as_lower_bound_when_limit_is_reached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "many-unique-values.accraw"
            snapshots = []
            for index in range(4096):
                page = _Physics()
                page.speed_kph = float(index)
                snapshots.append(
                    PhysicsSnapshot(index + 1, index + 1, index, index + 1,
                                    index + 1, bytes(page))
                )

            with RawPhysicsRecordingWriter(path, payload_size=PHYSICS_SIZE) as writer:
                writer.write_batch(snapshots)

            report = inspect_recording(path)
            speed = next(row for row in report["fields"] if row["name"] == "speed_kph")
            self.assertEqual(speed["unique_values_observed"], 4096)
            self.assertEqual(speed["unique_values_limit"], 4096)
            self.assertFalse(speed["unique_values_count_exact"])

    def test_rejects_corrupt_block_checksum_without_modifying_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.accraw"
            with RawPhysicsRecordingWriter(path, payload_size=PHYSICS_SIZE) as writer:
                writer.write_batch([PhysicsSnapshot(1, 1, 1, 2, 2, make_payload(0, 0, 800))])
            original = path.read_bytes()
            damaged = bytearray(original)
            damaged[-1] ^= 0xFF
            path.write_bytes(damaged)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                read_raw_payloads(path)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
