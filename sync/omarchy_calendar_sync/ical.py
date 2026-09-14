"""Read private iCalendar feeds without exposing their URLs in output."""

import hashlib
from datetime import datetime, timedelta
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

MAX_BYTES = 20 * 1024 * 1024


class IcalError(Exception):
    """An iCalendar source could not be read."""


class HttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise IcalError("iCal redirect requires HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    request = Request(url, headers={"User-Agent": "Omarchy-Calendar", "Accept": "text/calendar"})
    try:
        with build_opener(HttpsRedirects()).open(request, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise IcalError("iCal feed exceeds 20 MiB")
        return data
    except IcalError:
        raise
    except Exception:
        # HTTP exceptions can contain the private subscription URL.
        raise IcalError("could not download iCal feed; check the link and network") from None


def dependencies():
    try:
        import icalendar
        import recurring_ical_events
    except ImportError:
        raise IcalError("iCal dependencies are missing; run sync/setup --ical") from None
    return icalendar, recurring_ical_events


def endpoint(value, tz):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return {"dateTime": value.isoformat()}
    return {"date": value.isoformat()}


def parse(data, time_min, time_max, local_tz):
    icalendar, recurring = dependencies()
    try:
        calendar = icalendar.Calendar.from_ical(data)
        if calendar.name != "VCALENDAR":
            raise ValueError("not a calendar")
        tz = local_tz
        if calendar.get("X-WR-TIMEZONE"):
            tz = ZoneInfo(str(calendar["X-WR-TIMEZONE"]))
        # Floating times follow the feed's timezone, or the desktop timezone.
        for event in calendar.walk("VEVENT"):
            for key in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                value = event.get(key)
                if value and isinstance(value.dt, datetime) and value.dt.tzinfo is None:
                    value.dt = value.dt.replace(tzinfo=tz)
        events = recurring.of(calendar).between(
            datetime.fromisoformat(time_min), datetime.fromisoformat(time_max)
        )
        result = []
        for event in events:
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            start = event.decoded("DTSTART")
            end = event.decoded("DTEND", None)
            if end is None:
                duration = event.decoded("DURATION", None)
                if duration is None:
                    duration = timedelta(0) if isinstance(start, datetime) else timedelta(days=1)
                end = start + duration
            uid = str(event.get("UID", ""))
            identity = event.decoded("RECURRENCE-ID", start)
            event_id = hashlib.sha256((uid + "|" + identity.isoformat()).encode()).hexdigest()
            result.append({
                "id": event_id,
                "iCalUID": uid,
                "summary": str(event.get("SUMMARY", "")),
                "location": str(event.get("LOCATION", "")),
                "start": endpoint(start, tz),
                "end": endpoint(end, tz),
                "htmlLink": str(event.get("URL", "")),
                "hangoutLink": str(event.get("X-GOOGLE-CONFERENCE", "")),
            })
        return result
    except Exception:
        raise IcalError("could not parse iCal feed; check the calendar format and timezone") from None


class Ical:
    source = "ical"

    def __init__(self, feeds, local_tz, fetch=download):
        self.feeds = feeds
        self.local_tz = local_tz
        self.fetch = fetch

    def check(self):
        dependencies()

    def calendars(self):
        return sorted([
            {"id": feed["id"], "name": feed["name"], "color": feed.get("color", "#4285f4")}
            for feed in self.feeds
        ], key=lambda calendar: calendar["name"])

    def events(self, calendar_id, time_min, time_max):
        feed = next(feed for feed in self.feeds if feed["id"] == calendar_id)
        return parse(self.fetch(feed["url"]), time_min, time_max, self.local_tz)
