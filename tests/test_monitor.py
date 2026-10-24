import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import monitor


def event(name):
    return {"name": name, "area": "Test", "country": "UK", "lat": 1, "lon": 2, "url": "https://example.com/"}


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "events_snapshot.json"
        state_patch = patch.object(monitor, "STATE", self.state)
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.now = datetime(2026, 10, 24, 8, tzinfo=monitor.ZONE)

    def run_check(self, events, initialize=False):
        with patch.object(monitor, "fetch", return_value={}), patch.object(monitor, "extract", return_value=events):
            monitor.check(self.now, initialize=initialize)

    def test_baseline_is_explicit_and_silent(self):
        with self.assertRaises(RuntimeError):
            self.run_check({"1": event("Old")})
        with patch.object(monitor, "email_alert") as mail:
            self.run_check({"1": event("Old")}, initialize=True)
            mail.assert_not_called()
        self.assertIn("1", json.loads(self.state.read_text())["events"])

    def test_new_ids_only_and_returning_ids_stay_seen(self):
        self.run_check({"1": event("Old")}, initialize=True)
        with patch.object(monitor, "email_alert") as mail:
            self.run_check({"1": event("Renamed"), "2": event("New")})
            mail.assert_called_once_with({"2": event("New")})
        with patch.object(monitor, "email_alert") as mail:
            self.run_check({"2": event("New")})
            self.run_check({"1": event("Returned"), "2": event("New")}, initialize=True)
            mail.assert_not_called()

    def test_email_or_fetch_failure_does_not_advance_snapshot(self):
        self.run_check({"1": event("Old")}, initialize=True)
        before = self.state.read_bytes()
        with patch.object(monitor, "email_alert", side_effect=RuntimeError("SMTP failed")):
            with self.assertRaises(RuntimeError):
                self.run_check({"1": event("Old"), "2": event("New")})
        self.assertEqual(before, self.state.read_bytes())
        with patch.object(monitor, "fetch", side_effect=RuntimeError("Network failed")):
            with self.assertRaises(RuntimeError):
                monitor.check(self.now)
        self.assertEqual(before, self.state.read_bytes())

    def test_corrupt_snapshot_is_not_reset(self):
        self.state.write_text('{"events": []}')
        with self.assertRaises(ValueError):
            self.run_check({"1": event("Old")}, initialize=True)
        self.assertEqual('{"events": []}', self.state.read_text())

    def test_empty_or_partial_feed_is_rejected(self):
        for payload in ({}, {"events": {"features": []}}, {"events": {"features": [{"id": 1}]}}):
            with self.assertRaises(ValueError):
                monitor.extract(payload)

    def test_uk_schedule_across_dst(self):
        for date in ((2026, 7, 3), (2026, 10, 30)):
            for hour in range(24):
                now = datetime(*date, hour, tzinfo=monitor.ZONE)
                self.assertEqual(monitor.due(now), hour == 8 or hour >= 18)
        for month, day, utc_hour in ((7, 6, 7), (10, 26, 8)):
            now = datetime(2026, month, day, utc_hour, tzinfo=timezone.utc).astimezone(monitor.ZONE)
            self.assertTrue(monitor.due(now))
        for hour in range(24):
            self.assertEqual(monitor.due(datetime(2026, 10, 24, hour, tzinfo=monitor.ZONE)), hour <= 8)


if __name__ == "__main__":
    unittest.main()
