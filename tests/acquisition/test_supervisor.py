from __future__ import annotations

import threading
import time
import unittest

from race_engineer_acquisition.supervisor import (
    AcquisitionStartupError,
    AcquisitionStream,
    AcquisitionSupervisor,
)


class SupervisorTests(unittest.TestCase):
    def test_starts_streams_independently_and_stops_closes_once(self):
        started = {name: threading.Event() for name in ("physics", "graphics", "static")}
        closed = {name: 0 for name in started}

        def stream(name):
            def run(stop):
                started[name].set()
                stop.wait(2)
            def close():
                closed[name] += 1
            return AcquisitionStream(name, run, close)

        supervisor = AcquisitionSupervisor([stream(n) for n in started])
        supervisor.start()
        self.assertTrue(all(event.wait(1) for event in started.values()))
        self.assertEqual(supervisor.stop(timeout=1), ())
        self.assertEqual(supervisor.stop(timeout=1), ())
        self.assertEqual(closed, {name: 1 for name in started})
        self.assertTrue(all(item["state"] == "stopped" for item in supervisor.status.values()))

    def test_worker_failure_isolated_and_reported(self):
        release = threading.Event()
        other_started = threading.Event()
        closed = {"bad": 0, "good": 0}

        def bad_run(_stop):
            raise OSError("mapping unavailable")

        def good_run(stop):
            other_started.set()
            stop.wait(2)

        supervisor = AcquisitionSupervisor([
            AcquisitionStream("bad", bad_run, lambda: closed.__setitem__("bad", closed["bad"] + 1)),
            AcquisitionStream("good", good_run, lambda: closed.__setitem__("good", closed["good"] + 1)),
        ])
        supervisor.start()
        self.assertTrue(other_started.wait(1))
        deadline = time.monotonic() + 1
        while supervisor.status["bad"]["state"] != "failed" and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(supervisor.status["bad"]["state"], "failed")
        self.assertIn("mapping unavailable", supervisor.status["bad"]["error"])
        self.assertEqual(supervisor.status["good"]["state"], "running")
        supervisor.stop(timeout=1)
        self.assertEqual(closed, {"bad": 1, "good": 1})

    def test_partial_thread_start_failure_rolls_back_and_closes_all(self):
        created = []
        close_counts = {"first": 0, "second": 0}

        class ThreadFactory:
            def __call__(self, **kwargs):
                if kwargs["name"].endswith("second-Acquisition"):
                    class FailedThread:
                        ident = None
                        def start(self):
                            raise RuntimeError("thread start failed")
                    return FailedThread()
                thread = threading.Thread(**kwargs)
                created.append(thread)
                return thread

        first_stopped = threading.Event()

        def first_run(stop):
            stop.wait(2)
            first_stopped.set()

        supervisor = AcquisitionSupervisor([
            AcquisitionStream("first", first_run, lambda: close_counts.__setitem__("first", close_counts["first"] + 1)),
            AcquisitionStream("second", lambda _stop: None, lambda: close_counts.__setitem__("second", close_counts["second"] + 1)),
        ], thread_factory=ThreadFactory())
        with self.assertRaises(AcquisitionStartupError):
            supervisor.start()
        self.assertTrue(first_stopped.is_set())
        self.assertEqual(close_counts, {"first": 1, "second": 1})
        self.assertEqual(supervisor.status["second"]["state"], "failed")

    def test_rejects_duplicate_stream_names(self):
        stream = AcquisitionStream("same", lambda _stop: None, lambda: None)
        with self.assertRaises(ValueError):
            AcquisitionSupervisor([stream, stream])


if __name__ == "__main__":
    unittest.main()
