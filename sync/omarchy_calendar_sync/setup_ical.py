"""Interactive feed configuration and installation of the existing timer."""

import getpass
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import uuid

from . import cli, config

COLORS = (
    "#4285f4", "#34a853", "#ea4335", "#fbbc04", "#a142f4",
    "#24c1e0", "#f538a0", "#ff8c42", "#7cb342", "#ab47bc",
)


def unit_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def main():
    path = config.CONFIG_PATH
    raw = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError("calendar-sync.json must contain a JSON object")
    feeds = list((raw.get("ical") or {}).get("feeds", []))
    print("iCal calendars: enter a private HTTPS or webcal subscription link.")
    print("Links are hidden while typing. Leave the link empty to finish.")
    if feeds:
        print(f"Keeping {len(feeds)} existing subscriptions.")
    while True:
        url = getpass.getpass("iCal link: ").strip()
        if not url:
            break
        name = input("Calendar name: ").strip() or "Calendar"
        used_colors = {feed.get("color", "#4285f4").lower() for feed in feeds}
        available = [color for color in COLORS if color not in used_colors]
        default_color = random.choice(available or COLORS)
        color = input(f"Color [{default_color}]: ").strip() or default_color
        feed = {"id": "ical-" + uuid.uuid4().hex, "url": url, "name": name, "color": color}
        try:
            config.validate_source({"source": "ical", "ical": {"feeds": [feed]}})
        except config.ConfigError as error:
            print(error)
            continue
        if any(existing["url"] == url for existing in feeds):
            print("This subscription is already configured.")
            continue
        feeds.append(feed)
    if not feeds:
        print("No subscriptions added.")
        return 1
    if raw.get("source", "google") != "ical":
        raw["calendars"] = {"include": [], "exclude": []}
    raw.update(source="ical", ical={"feeds": feeds})
    config.validate_source(raw)
    cli.write_atomic(path, raw)
    os.chmod(path, 0o600)
    if cli.main([]) != 0:
        print("Configuration saved, but sync failed. Fix the subscription and run setup again.")
        return 1

    sync_dir = Path(__file__).resolve().parent.parent
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = (sync_dir / "systemd/omarchy-calendar-sync.service").read_text()
    command = f"ExecStart={unit_quote(sys.executable)} {unit_quote(sync_dir / 'omarchy-calendar-sync')}"
    service = "\n".join(command if line.startswith("ExecStart=") else line
                        for line in service.splitlines()) + "\n"
    (unit_dir / "omarchy-calendar-sync.service").write_text(service)
    (unit_dir / "omarchy-calendar-sync.timer").write_text(
        (sync_dir / "systemd/omarchy-calendar-sync.timer").read_text())
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "omarchy-calendar-sync.timer"], check=True)
    print("Connected. Calendars refresh every five minutes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, config.ConfigError, subprocess.CalledProcessError):
        print("Setup failed. Check calendar-sync.json and the systemd user session.", file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.", file=sys.stderr)
        sys.exit(1)
