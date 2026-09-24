"""Non-interactive iCal feed management for the settings panel."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import random

from . import cli, config

COLORS = (
    "#4285f4", "#34a853", "#ea4335", "#fbbc04", "#a142f4",
    "#24c1e0", "#f538a0", "#ff8c42", "#7cb342",
)


def _venv_path():
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "omarchy-calendar" / "venv"


def _sync_dir():
    return Path(__file__).resolve().parent.parent


def _unit_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def ensure_runtime():
    """Install iCal dependencies and the timer on the first UI add."""
    venv = _venv_path()
    python = venv / "bin/python"
    if not python.exists():
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        subprocess.run([
            str(python), "-m", "pip", "install", "-r",
            str(_sync_dir() / "requirements-ical.txt"),
        ], check=True)

    # Re-enter through the venv so the sync itself can import icalendar.
    if Path(sys.executable).resolve() != python.resolve():
        env = dict(os.environ)
        env["OMARCHY_CALENDAR_MANAGE_READY"] = "1"
        subprocess.run([str(python), "-m", "omarchy_calendar_sync.manage_ical", *sys.argv[1:]],
                       check=True, env=env)
        raise SystemExit(0)

    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    template = (_sync_dir() / "systemd/omarchy-calendar-sync.service").read_text()
    command = f"ExecStart={_unit_quote(python)} {_unit_quote(_sync_dir() / 'omarchy-calendar-sync')}"
    service = "\n".join(command if line.startswith("ExecStart=") else line
                         for line in template.splitlines()) + "\n"
    (unit_dir / "omarchy-calendar-sync.service").write_text(service)
    (unit_dir / "omarchy-calendar-sync.timer").write_text(
        (_sync_dir() / "systemd/omarchy-calendar-sync.timer").read_text())
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run([
        "systemctl", "--user", "enable", "--now", "omarchy-calendar-sync.timer"
    ], check=True)


def _read(path):
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("calendar-sync.json must contain a JSON object")
    return value


def _save(path, raw):
    cli.write_atomic(path, raw)
    os.chmod(path, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="omarchy-calendar-manage-ical")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--add", metavar="URL")
    actions.add_argument("--remove", metavar="ID")
    parser.add_argument("--name", default="")
    parser.add_argument("--color", default=None)
    args = parser.parse_args(argv)

    if args.add is not None:
        ensure_runtime()

    path = config.CONFIG_PATH
    raw = _read(path)
    for legacy_key in ("source", "profile", "gwsPath", "calendars"):
        raw.pop(legacy_key, None)
    ical = raw.get("ical") if isinstance(raw.get("ical"), dict) else {}
    feeds = list(ical.get("feeds") or [])

    if args.add is not None:
        feed = {
            "id": "ical-" + uuid.uuid4().hex,
            "url": args.add.strip(),
        }
        if args.name.strip():
            feed["name"] = args.name.strip()
        feed["color"] = args.color.strip() if args.color and args.color.strip() else random.choice(COLORS)
        if any(existing.get("url") == feed["url"] for existing in feeds):
            raise ValueError("This subscription is already configured")
        feeds.append(feed)
    else:
        before = len(feeds)
        feeds = [feed for feed in feeds if feed.get("id") != args.remove]
        if len(feeds) == before:
            raise ValueError("Calendar was not found")

    raw["ical"] = {"feeds": feeds}
    config.validate_ical(raw)
    _save(path, raw)

    # Refresh immediately; the existing systemd timer remains responsible for
    # subsequent updates. A failed fetch leaves the previous events file intact.
    return cli.main([])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, json.JSONDecodeError, config.ConfigError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
