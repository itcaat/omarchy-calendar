import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from omarchy_calendar_sync import config

CALENDARS = [
    {"id": "a@example.com", "name": "Personal", "color": "#f83a22"},
    {"id": "b@example.com", "name": "Phases of the Moon", "color": "#fad165"},
    {"id": "c@example.com", "name": "Destify", "color": "#ffad46"},
]


class TestLoad(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        loaded = config.load(Path("/nonexistent/calendar-sync.json"))
        self.assertEqual(loaded, config.DEFAULTS)

    def test_partial_file_is_filled_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"futureDays": 90}}))
            loaded = config.load(path)
            self.assertEqual(loaded["window"]["futureDays"], 90)
            self.assertEqual(
                loaded["window"]["pastDays"], config.DEFAULTS["window"]["pastDays"]
            )

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text("{not json")
            with self.assertRaises(config.ConfigError):
                config.load(path)

    def test_defaults_are_not_mutated_by_a_returned_config(self):
        loaded = config.load(Path("/nonexistent/calendar-sync.json"))
    def test_null_window_keys_fill_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": None}))
            loaded = config.load(path)
            self.assertEqual(loaded["window"], config.DEFAULTS["window"])

    def test_null_past_days_raises_config_error_naming_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"pastDays": None}}))
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("pastDays", str(ctx.exception))

    def test_non_numeric_future_days_raises_config_error_naming_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({"window": {"futureDays": "soon"}}))
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(path)
            self.assertIn("futureDays", str(ctx.exception))

class TestWindowBounds(unittest.TestCase):
    def test_bounds_bracket_now(self):
        now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        time_min, time_max = config.window_bounds(config.DEFAULTS, now)
        self.assertTrue(time_min.startswith("2026-08-03"))
        self.assertTrue(time_max.startswith("2026-10-09"))

    def test_bounds_respect_custom_window(self):
        now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        cfg = {"window": {"pastDays": 1, "futureDays": 2}}
        time_min, time_max = config.window_bounds(cfg, now)
        self.assertTrue(time_min.startswith("2026-08-09"))
        self.assertTrue(time_max.startswith("2026-08-12"))


if __name__ == "__main__":
    unittest.main()
