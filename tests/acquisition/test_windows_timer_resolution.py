import unittest

from race_engineer_acquisition.timing_windows import WindowsTimerResolution


class FakeWinMM:
    def __init__(self, begin_result=0, end_result=0):
        self.begin_result = begin_result
        self.end_result = end_result
        self.calls = []

    def timeBeginPeriod(self, period):
        self.calls.append(("begin", period))
        return self.begin_result

    def timeEndPeriod(self, period):
        self.calls.append(("end", period))
        return self.end_result


class WindowsTimerResolutionTests(unittest.TestCase):
    def test_requests_and_releases_timer_resolution(self):
        api = FakeWinMM()
        with WindowsTimerResolution(1, winmm=api) as timer:
            self.assertTrue(timer.active)
            self.assertEqual(api.calls, [("begin", 1)])
        self.assertFalse(timer.active)
        self.assertEqual(api.calls, [("begin", 1), ("end", 1)])

    def test_failed_begin_does_not_attempt_release(self):
        api = FakeWinMM(begin_result=97)
        timer = WindowsTimerResolution(1, winmm=api)
        with self.assertRaises(OSError):
            timer.__enter__()
        self.assertFalse(timer.active)
        self.assertEqual(api.calls, [("begin", 1)])

    def test_zero_disables_timer_request(self):
        api = FakeWinMM()
        with WindowsTimerResolution(0, winmm=api) as timer:
            self.assertFalse(timer.active)
        self.assertEqual(api.calls, [])

    def test_period_must_not_be_negative(self):
        with self.assertRaises(ValueError):
            WindowsTimerResolution(-1)

    def test_failed_end_is_reported(self):
        api = FakeWinMM(end_result=97)
        with self.assertRaises(OSError):
            with WindowsTimerResolution(1, winmm=api):
                pass


if __name__ == "__main__":
    unittest.main()
