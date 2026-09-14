import contextlib
import io
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from omarchy_calendar_sync import cli, config, ical, normalize

MIN = "2026-03-01T00:00:00+00:00"
MAX = "2026-04-01T00:00:00+00:00"
TZ = ZoneInfo("America/New_York")
FEED = {"id": "personal", "name": "Personal", "url": "https://example.com/private-secret.ics"}


def calendar(body, extra=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n" + extra
            + body + "END:VCALENDAR\r\n").encode()


def event(body):
    return "BEGIN:VEVENT\r\n" + body + "END:VEVENT\r\n"


@unittest.skipUnless(importlib.util.find_spec("icalendar") and
                     importlib.util.find_spec("recurring_ical_events"), "optional iCal dependencies")
class TestIcal(unittest.TestCase):
    def test_feed_timezone_and_floating_recurrence_exclusion(self):
        data = calendar(event(
            "UID:floating-series\r\nDTSTART:20260310T090000\r\nDURATION:PT30M\r\n"
            "RRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20260311T090000\r\n"
        ), "X-WR-TIMEZONE:Europe/Moscow\r\n")
        events = ical.parse(data, MIN, MAX, TZ)
        self.assertEqual(len(events), 2)
        self.assertEqual([e["start"]["dateTime"] for e in events],
                         ["2026-03-10T09:00:00+03:00", "2026-03-12T09:00:00+03:00"])

    def test_cancelled_occurrence_is_not_restored_by_master(self):
        data = calendar(event(
            "UID:series\r\nDTSTART:20260310T090000Z\r\nDURATION:PT30M\r\n"
            "RRULE:FREQ=DAILY;COUNT=3\r\n"
        ) + event(
            "UID:series\r\nRECURRENCE-ID:20260311T090000Z\r\n"
            "DTSTART:20260311T090000Z\r\nSTATUS:CANCELLED\r\n"
        ))
        self.assertEqual(len(ical.parse(data, MIN, MAX, TZ)), 2)

    def test_recurrence_exclusions_overrides_and_dst(self):
        data = calendar(event(
            "UID:series\r\nDTSTART;TZID=America/New_York:20260306T090000\r\n"
            "DTEND;TZID=America/New_York:20260306T100000\r\n"
            "RRULE:FREQ=DAILY;COUNT=5\r\n"
            "EXDATE;TZID=America/New_York:20260307T090000\r\nSUMMARY:Regular\r\n"
        ) + event(
            "UID:series\r\nRECURRENCE-ID;TZID=America/New_York:20260309T090000\r\n"
            "DTSTART;TZID=America/New_York:20260309T110000\r\n"
            "DTEND;TZID=America/New_York:20260309T120000\r\nSUMMARY:Moved\r\n"
        ))
        events = ical.parse(data, MIN, MAX, TZ)
        self.assertEqual(len(events), 4)
        self.assertEqual(len({e["id"] for e in events}), 4)
        starts = [e["start"]["dateTime"] for e in events]
        self.assertIn("2026-03-06T09:00:00-05:00", starts)
        self.assertIn("2026-03-08T09:00:00-04:00", starts)
        self.assertIn("2026-03-09T11:00:00-04:00", starts)

    def test_all_day_exclusive_end_and_missing_end(self):
        data = calendar(event("UID:days\r\nDTSTART;VALUE=DATE:20260305\r\n"
                              "DTEND;VALUE=DATE:20260308\r\n")
                        + event("UID:day\r\nDTSTART;VALUE=DATE:20260310\r\n"))
        events = ical.parse(data, MIN, MAX, TZ)
        rows = normalize.normalize_all(events, {**FEED, "color": "#4285f4"}, TZ)
        self.assertEqual([r["dateKey"] for r in rows],
                         ["2026-03-05", "2026-03-06", "2026-03-07", "2026-03-10"])
        self.assertTrue(all(r["allDay"] for r in rows))

    def test_floating_time_duration_and_folded_text(self):
        data = calendar(event("UID:floating\r\nDTSTART:20260310T090000\r\n"
                              "DURATION:PT30M\r\nSUMMARY:Long \'title\'\r\n continued\r\n"))
        result = ical.parse(data, MIN, MAX, TZ)[0]
        self.assertEqual(result["start"]["dateTime"], "2026-03-10T09:00:00-04:00")
        self.assertEqual(result["end"]["dateTime"], "2026-03-10T09:30:00-04:00")
        self.assertEqual(result["summary"], "Long 'title'continued")

    def test_cancelled_and_outside_window_are_removed(self):
        data = calendar(event("UID:cancelled\r\nDTSTART:20260310T090000Z\r\nSTATUS:CANCELLED\r\n")
                        + event("UID:old\r\nDTSTART:20250101T090000Z\r\n"))
        self.assertEqual(ical.parse(data, MIN, MAX, TZ), [])

    def test_malformed_feed_fails_instead_of_clearing_calendar(self):
        with self.assertRaises(ical.IcalError):
            ical.parse(b"<html>Login required</html>", MIN, MAX, TZ)

    def test_failed_download_redacts_url(self):
        with patch("omarchy_calendar_sync.ical.build_opener") as opener:
            opener.return_value.open.side_effect = OSError(FEED["url"])
            with self.assertRaises(ical.IcalError) as caught:
                ical.download(FEED["url"])
        self.assertNotIn("private-secret", str(caught.exception))

    def test_webcal_uses_https_and_bounds_download(self):
        with patch("omarchy_calendar_sync.ical.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b"calendar"
            self.assertEqual(ical.download("webcal://example.com/feed"), b"calendar")
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.com/feed")
            response.read.assert_called_once_with(ical.MAX_BYTES + 1)

    def test_sync_uses_ical_without_gws_and_keeps_old_file_on_failure(self):
        data = calendar(event("UID:one\r\nDTSTART:20260310T090000Z\r\nSUMMARY:Meeting\r\n"))
        client = ical.Ical([FEED], TZ, fetch=lambda url: data)
        cfg = {**config.DEFAULTS, "source": "ical", "ical": {"feeds": [FEED]}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "events.json"
            self.assertEqual(cli.run(client, cfg, datetime(2026, 3, 10, tzinfo=timezone.utc), out, TZ), 0)
            old = out.read_text()
            self.assertEqual(json.loads(old)["source"], "ical")
            self.assertNotIn("private-secret", old)
            client.fetch = lambda url: b"invalid"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.run(client, cfg, datetime(2026, 3, 10, tzinfo=timezone.utc), out, TZ), 1)
            self.assertEqual(out.read_text(), old)


class TestIcalConfig(unittest.TestCase):
    def test_invalid_feeds_report_no_secret(self):
        for changes in ({"url": "http://example.com/private-secret"}, {"color": None}, {"name": ""}):
            with self.subTest(changes=changes):
                with self.assertRaises(config.ConfigError) as caught:
                    config.validate_source({"source": "ical", "ical": {"feeds": [{**FEED, **changes}]}})
                self.assertNotIn("private-secret", str(caught.exception))

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.validate_source({"source": "ical", "ical": {"feeds": [FEED, FEED]}})

    def test_main_selects_ical_without_google(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"source": "ical", "ical": {"feeds": [FEED]}}))
            with patch.object(cli, "Gws") as google, patch.object(cli, "run", return_value=0) as run:
                self.assertEqual(cli.main(["--config", str(path)]), 0)
            google.assert_not_called()
            self.assertIsInstance(run.call_args.args[0], ical.Ical)


class TestSetupIcal(unittest.TestCase):
    def test_setup_writes_private_config_and_installs_venv_service(self):
        from omarchy_calendar_sync import setup_ical
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar-sync.json"
            path.write_text(json.dumps({"calendars": {"include": ["old-google-id"]}}))
            with patch.object(config, "CONFIG_PATH", path), \
                 patch.object(Path, "home", return_value=Path(tmp)), \
                 patch.object(setup_ical.getpass, "getpass", side_effect=[FEED["url"], ""]), \
                 patch("builtins.input", side_effect=["Personal", ""]), \
                 patch.object(cli, "main", return_value=0), \
                 patch.object(setup_ical.subprocess, "run") as systemctl:
                self.assertEqual(setup_ical.main(), 0)
            cfg = config.load(path)
            self.assertEqual(cfg["source"], "ical")
            self.assertEqual(cfg["ical"]["feeds"][0]["url"], FEED["url"])
            self.assertEqual(cfg["calendars"]["include"], [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            service = (Path(tmp) / ".config/systemd/user/omarchy-calendar-sync.service").read_text()
            self.assertIn(setup_ical.sys.executable, service)
            self.assertNotIn(FEED["url"], service)
            self.assertEqual(systemctl.call_count, 2)
