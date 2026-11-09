from __future__ import annotations

import struct
import threading
import time
import unittest

from race_engineer_acquisition.acquirer import PhysicsAcquirer
from race_engineer_acquisition.graphics import GraphicsAcquirer, RawGraphicsRead
from race_engineer_acquisition.health import AcquisitionHealth
from race_engineer_acquisition.models import RawPhysicsRead
from race_engineer_acquisition.ring_buffer import AcquisitionRingBuffer
from race_engineer_acquisition.static import RawStaticRead, StaticAcquirer
from race_engineer_acquisition.supervisor import AcquisitionStream, AcquisitionSupervisor


class StepClock:
    def __init__(self):
        self.value = 100

    def __call__(self):
        value = self.value
        self.value += 10
        return value


class FailsOnce:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def read_physics(self):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary source read failure")
        return self.value

    def read_graphics(self):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary source read failure")
        return self.value

    def read_static(self):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary source read failure")
        return self.value


class AcquisitionHealthTests(unittest.TestCase):
    def test_physics_source_failure_and_recovery_are_counted(self):
        source = FailsOnce(RawPhysicsRead(1, 1, b"physics"))
        acquirer = PhysicsAcquirer(source, AcquisitionRingBuffer(2), clock_ns=StepClock())
        with self.assertRaisesRegex(OSError, "temporary"):
            acquirer.capture_once()
        failed = acquirer.health.snapshot
        self.assertEqual(failed.source_read_failures, 1)
        self.assertEqual(failed.consecutive_failures, 1)
        self.assertIn("temporary source read failure", failed.last_error)
        acquirer.capture_once()
        recovered = acquirer.health.snapshot
        self.assertEqual(recovered.successful_reads, 1)
        self.assertEqual(recovered.consecutive_failures, 0)
        self.assertIsNotNone(recovered.last_successful_read_ns)
        self.assertEqual(recovered.last_read_duration_ns, 10)

    def test_graphics_source_failure_and_recovery_are_counted(self):
        raw = RawGraphicsRead(1, 1, 1, struct.pack("<i", 1) + b"graphics")
        source = FailsOnce(raw)
        acquirer = GraphicsAcquirer(source, AcquisitionRingBuffer(2), clock_ns=StepClock())
        with self.assertRaisesRegex(OSError, "temporary"):
            acquirer.capture_once()
        acquirer.capture_once()
        health = acquirer.health.snapshot
        self.assertEqual(health.source_read_failures, 1)
        self.assertEqual(health.successful_reads, 1)
        self.assertEqual(health.consecutive_failures, 0)

    def test_static_source_failure_and_recovery_are_counted(self):
        source = FailsOnce(RawStaticRead(b"static"))
        acquirer = StaticAcquirer(source, AcquisitionRingBuffer(2), clock_ns=StepClock())
        with self.assertRaisesRegex(OSError, "temporary"):
            acquirer.capture_once()
        acquirer.capture_once()
        health = acquirer.health.snapshot
        self.assertEqual(health.source_read_failures, 1)
        self.assertEqual(health.successful_reads, 1)
        self.assertEqual(health.consecutive_failures, 0)

    def test_worker_health_updates_reuse_state_without_losing_metrics(self):
        health = AcquisitionHealth()
        worker_state = health._read_health

        health.record_read_success(100, 10)
        health.record_read_failure(OSError("temporary"))
        health.record_read_success(200, 20)
        health.record_buffer_rejection()

        snapshot = health.snapshot
        self.assertIs(health._read_health, worker_state)
        self.assertEqual(snapshot.successful_reads, 2)
        self.assertEqual(snapshot.source_read_failures, 1)
        self.assertEqual(snapshot.consecutive_failures, 0)
        self.assertEqual(snapshot.last_successful_read_ns, 200)
        self.assertEqual(snapshot.last_read_duration_ns, 20)
        self.assertEqual(snapshot.max_read_duration_ns, 20)
        self.assertEqual(snapshot.buffer_rejections, 1)
        self.assertEqual(snapshot.last_error, "OSError: temporary")

    def test_health_snapshot_is_coherent_during_worker_updates(self):
        health = AcquisitionHealth()
        finished = threading.Event()
        errors = []

        def writer():
            for value in range(1, 5001):
                health.record_read_success(value, value)
            finished.set()

        thread = threading.Thread(target=writer)
        thread.start()
        while not finished.is_set():
            snapshot = health.snapshot
            if snapshot.last_successful_read_ns is not None:
                if not (
                    snapshot.successful_reads == snapshot.last_successful_read_ns
                    == snapshot.last_read_duration_ns
                    == snapshot.max_read_duration_ns
                ):
                    errors.append(snapshot)
                    break
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        final = health.snapshot
        self.assertEqual(final.successful_reads, 5000)
        self.assertEqual(final.last_successful_read_ns, 5000)
        self.assertEqual(final.max_read_duration_ns, 5000)

    def test_buffer_rejection_is_in_common_health(self):
        class SequenceSource:
            def __init__(self):
                self.packet = 0

            def read_physics(self):
                self.packet += 1
                return RawPhysicsRead(self.packet, self.packet, b"x")

        acquirer = PhysicsAcquirer(SequenceSource(), AcquisitionRingBuffer(1))
        acquirer.capture_once()
        acquirer.capture_once()
        self.assertEqual(acquirer.health.snapshot.buffer_rejections, 1)
        self.assertEqual(acquirer.metrics.buffer_rejection_count, 1)


    def test_supervisor_health_transitions_from_idle_to_running_to_stopped(self):
        entered = threading.Event()
        health = AcquisitionHealth()

        def worker(stop):
            entered.set()
            stop.wait(1)

        supervisor = AcquisitionSupervisor([
            AcquisitionStream("static", worker, lambda: None, health)
        ])
        self.assertEqual(health.snapshot.lifecycle_state, "idle")
        supervisor.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(supervisor.status["static"]["health"].lifecycle_state, "running")
        self.assertEqual(supervisor.stop(timeout=1), ())
        self.assertEqual(supervisor.status["static"]["health"].lifecycle_state, "stopped")

    def test_supervisor_exposes_running_and_failed_health(self):
        entered = threading.Event()
        release = threading.Event()
        health = AcquisitionHealth()

        def worker(stop):
            entered.set()
            release.wait(1)
            raise RuntimeError("fatal worker error")

        supervisor = AcquisitionSupervisor([
            AcquisitionStream("physics", worker, lambda: None, health)
        ])
        self.assertEqual(health.snapshot.lifecycle_state, "idle")
        supervisor.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(supervisor.status["physics"]["health"].lifecycle_state, "running")
        release.set()
        deadline = time.monotonic() + 1
        while (
            supervisor.status["physics"]["state"] != "failed"
            or supervisor.status["physics"]["health"].lifecycle_state != "failed"
        ) and time.monotonic() < deadline:
            time.sleep(0.005)
        status = supervisor.status["physics"]
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["health"].lifecycle_state, "failed")
        self.assertIn("fatal worker error", status["error"])
        supervisor.stop(timeout=1)


if __name__ == "__main__":
    unittest.main()
