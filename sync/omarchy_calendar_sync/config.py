"""User configuration for the sync.

Absent config is a valid state: every key has a default, so a first run works
with no file at all.
"""

import copy
import json
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_PATH = Path.home() / ".config" / "omarchy" / "calendar-sync.json"

DEFAULTS = {
    "source": "google",
    "ical": {"feeds": []},
    "profile": str(Path.home() / ".config" / "gws-omarchy-calendar"),
    # Resolved to an absolute path by sync/setup. A systemd user service
    # does not inherit an interactive shell PATH, so relying on the bare
    # name works from a terminal and fails from the timer.
    "gwsPath": "gws",
    "calendars": {"include": [], "exclude": []},
    "window": {"pastDays": 7, "futureDays": 60},
}


class ConfigError(Exception):
    """Raised when the config file exists but cannot be used."""


def load(path=None):
    """Load config, filling in defaults for anything absent."""
    path = Path(path) if path is not None else CONFIG_PATH

    if not path.exists():
        return _merge(copy.deepcopy(DEFAULTS), {})

    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a JSON object")

    merged = _merge(copy.deepcopy(DEFAULTS), raw)

    validate_source(merged)

    _validate_calendars(merged.get("calendars"))

    window = merged.get("window")
    if isinstance(window, dict):
        window["pastDays"] = _coerce_days(window.get("pastDays"), "window.pastDays")
        window["futureDays"] = _coerce_days(
            window.get("futureDays"), "window.futureDays"
        )

    return merged


def validate_source(config):
    if config.get("source") not in ("google", "ical"):
        raise ConfigError("source must be google or ical")
    if config["source"] != "ical":
        return
    settings = config.get("ical")
    feeds = settings.get("feeds") if isinstance(settings, dict) else None
    if not isinstance(feeds, list) or not feeds:
        raise ConfigError("ical.feeds must be a non-empty list")
    ids = set()
    for index, feed in enumerate(feeds, 1):
        label = f"iCal feed {index}"
        if not isinstance(feed, dict):
            raise ConfigError(f"{label} must be an object")
        for key in ("id", "name", "url"):
            if not isinstance(feed.get(key), str) or not feed[key].strip():
                raise ConfigError(f"{label} requires {key}")
        try:
            url = urlsplit(feed["url"])
            valid = (url.scheme in ("https", "webcal") and url.hostname
                     and not url.username and not url.password and not url.fragment)
            valid = valid and not any(c.isspace() for c in feed["url"])
            url.port
        except ValueError:
            valid = False
        if not valid:
            raise ConfigError(f"{label} requires an HTTPS or webcal URL without credentials")
        if feed["id"] in ids:
            raise ConfigError("iCal feed ids must be unique")
        ids.add(feed["id"])
        color = feed.get("color", "#4285f4")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ConfigError(f"{label} color must be #RRGGBB")


def _merge(defaults, override):
    """One level of nesting is all this config has, so this stays simple."""
    merged = {}
    for key, fallback in defaults.items():
        value = override.get(key, fallback)
        if value is None:
            # An explicit null for a nested key means "not set", not "empty".
            value = fallback
        if isinstance(fallback, dict) and isinstance(value, dict):
            merged[key] = {**fallback, **value}
        else:
            merged[key] = value
    return merged


def _validate_calendars(calendars):
    """Reject a non-list include or exclude instead of silently misreading it."""
    if not isinstance(calendars, dict):
        return
    for key in ("include", "exclude"):
        value = calendars.get(key)
        if value is not None and not isinstance(value, list):
            raise ConfigError(f"calendars.{key} must be a list")


def _coerce_days(value, key):
    """Turn a window day count into an int, or fail loudly naming the key."""
    if isinstance(value, bool):
        raise ConfigError(f"{key} must be a number")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"{key} must be a number") from None
    raise ConfigError(f"{key} must be a number")


def select_calendars(calendars, config):
    """Apply the include and exclude lists. Exclude always wins."""
    rules = config.get("calendars") or {}
    include = set(rules.get("include") or [])
    exclude = set(rules.get("exclude") or [])

    selected = []
    for calendar in calendars:
        keys = {calendar["id"], calendar["name"]}
        if keys & exclude:
            continue
        if include and not (keys & include):
            continue
        selected.append(calendar)
    return selected


def window_bounds(config, now):
    """Return RFC3339 timeMin and timeMax for the events query."""
    window = config.get("window") or {}
    past = int(window.get("pastDays", DEFAULTS["window"]["pastDays"]))
    future = int(window.get("futureDays", DEFAULTS["window"]["futureDays"]))
    return (
        (now - timedelta(days=past)).isoformat(),
        (now + timedelta(days=future)).isoformat(),
    )
