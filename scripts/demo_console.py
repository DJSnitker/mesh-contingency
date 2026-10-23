"""A demo of the web console, for screenshots: the real server and the built
app, on a fake radio with made-up users, messages and history. Nothing of a
real node's is read or written; its data lives in a temporary folder, gone
when it stops.

    .venv/bin/python scripts/demo_console.py                    # open the link it prints
    .venv/bin/python scripts/demo_console.py --screenshots DIR  # save each page, then stop

Needs the console extra (pip install -e ".[console]") and the app built
(cd console && npm ci && npm run build). Screenshots need Chrome or Chromium.
"""

import argparse
import asyncio
import io
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from random import Random
from types import SimpleNamespace

from aiohttp import web

from mesh_contingency.alerts import hashtag_secret
from mesh_contingency.area_weather import AreaWeather
from mesh_contingency.backup import Backups, BackupSettings
from mesh_contingency.channel_log import ChannelLog
from mesh_contingency.commands.join import FILENAME as REQUESTS
from mesh_contingency.commands.mailbox import FILENAME as MAILBOX
from mesh_contingency.commands.status import FILENAME as STATUSES
from mesh_contingency.console import ADVERTS_FILE
from mesh_contingency.directory import Directory
from mesh_contingency.output import SafeOutput
from mesh_contingency.registry import Registry
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, make_context
from mesh_contingency.web.server import STATIC, built, make_app

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = REPO / "config.example.toml"
KEY = "demo"
MIN, HOUR, DAY = 60, 3600, 86400
# The pages, as their paths and the screenshot names.
PAGES = {"": "dashboard", "weather": "weather", "users": "users", "checkins": "checkins", "inbox": "inbox",
         "history": "history", "send": "send", "radio": "radio"}
WIDE, PHONE = (1280, 900), (390, 844)
CHROMES = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")

# The same keys every run, so screenshots don't change for no reason.
_random = Random(7)
ADMIN, MARIA, JAMES, PRIYA, TOM, LENA, RAY, SAM = ("".join(_random.choice("0123456789abcdef") for _ in range(64))
                                                   for _ in range(8))
USERS = {
    MARIA: {"name": "Maria Lopez", "qm": "maria@example.com", "inbox_key": "demo"},
    JAMES: {"name": "James Carter", "email": "jcarter@example.org"},
    PRIYA: {"name": "Priya Shah", "qm": "priya@example.net", "inbox_key": "demo"},
    TOM: {"name": "Tom Becker"},
    LENA: {"name": "Lena Ortiz", "email": "lena@example.com"},
    RAY: {"name": "Ray Whitfield"},
}


# The demo's counties: (place, station, conditions, temperature F, wind, humidity, forecast).
AREAS = {
    "Boone, MO": ("Columbia, MO", "Columbia Regional Airport", "Partly Cloudy", 64, ("S", 9, 18), 58,
                  [("Today", 71, "Partly Sunny", 10), ("Tonight", 52, "Chance Showers", 40),
                   ("Saturday", 66, "Showers Likely", 70)]),
    "Callaway, MO": ("Fulton, MO", "Fulton Elam Mason Airport", "Windy", 61, ("SW", 26, 41), 49,
                     [("Today", 68, "Sunny and Breezy", 0), ("Tonight", 49, "Clear", 0),
                      ("Saturday", 63, "Mostly Sunny", 0)]),
    "Cole, MO": ("Jefferson City, MO", "Jefferson City Memorial Airport", "Light Rain", 57, ("E", 6, None), 91,
                 [("Today", 60, "Rain", 90), ("Tonight", 50, "Rain Likely", 70), ("Saturday", 62, "Cloudy", 20)]),
    # The NWS didn't answer for this one at the last try: its report is old.
    "Howard, MO": ("Fayette, MO", "Boonville Jesse Viertel Airport", "Mostly Cloudy", 59, ("S", 8, None), 66,
                   [("This Afternoon", 69, "Mostly Cloudy", 20), ("Tonight", 51, "Chance Showers", 50)]),
}
STALE = {"Howard, MO": "HTTP Error 503: Service Unavailable"}

# The radio's contacts besides the users' radios: (name, type, hops or None, heard how long ago).
NODES = [("Ridge Top Repeater", 2, 0, 20 * MIN), ("Hwy 63 Repeater", 2, 1, 2 * HOUR),
         ("County EOC Room", 3, 2, 5 * HOUR), ("River Gauge 4", 4, None, 3 * DAY), ("Fulton Relay", 2, None, None)]
# Channel messages since the bot started, oldest first: (slot, minutes ago,
# sender or None for this node, text, hops, SNR).
CHANNEL_MESSAGES = [
    (0, 170, "Hwy 63 Repeater", "Repeater on battery power, solar charging", 1, 4.25),
    (0, 95, "tom-hh", "Anyone copy near Ashland? Cell is down here", 2, -2.5),
    (0, 88, "maria-hh", "Copy Tom, we hear you in Columbia", 1, 6.0),
    (1, 75, None, "Callaway, MO ALERT: Wind Advisory until Fri 3:10PM", None, None),
    (2, 40, None, "Net check-in at 19:00 on this channel. Send ok to the node if you can't make it.", None, None),
    (2, 31, "james-hh", "At the shelter, 14 people, water OK", 2, 3.5),
    (2, 18, "priya-hh", "Power out on the east side; I'm on battery", 255, 9.75),
    (3, 12, "County EOC", "EOC open until 22:00. Report road closures here.", 2, 1.5),
]
NODE_KEYS = ["".join(_random.choice("0123456789abcdef") for _ in range(64)) for _ in NODES]


def area_report(county, now):
    """What AreaWeather would have for one of AREAS."""
    place, station, text, temp, wind, humidity, periods = AREAS[county]
    old = 45 * MIN if county in STALE else 0
    return {"problem": STALE.get(county), "place": place, "station": station, "observed": now - 22 * MIN - old,
            "text": text, "temp_f": temp, "feels_f": None, "humidity": humidity, "wind_dir": wind[0],
            "wind_mph": wind[1], "gust_mph": wind[2], "updated": now - 6 * MIN - old,
            "periods": [{"name": name, "temp": t, "unit": "F", "text": forecast, "pop": pop, "wind": None}
                        for name, t, forecast, pop in periods]}


def demo_context(folder, now=None):
    """A context for the console, as a node two days into a net would have,
    with its data in `folder`. Returns (ctx, output)."""
    now = time.time() if now is None else now
    folder = Path(folder)
    config_path = folder / "config.toml"
    shutil.copyfile(EXAMPLE_CONFIG, config_path)
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    state = State(folder)
    state.started = now - (2 * DAY + 5 * HOUR)
    radio = FakeMeshCore()
    radio.self_info["name"] = "Ridgeview Relay"
    # The bot's two channels, as it adds them at startup, and a private one.
    radio.channels[1:4] = [(name, hashtag_secret(name)) for name in ("#contingency-wx", "#contingency-comm")] + [
        ("Ridgeview ARES", bytes(range(1, 17)))]
    for n, key in enumerate([ADMIN, MARIA, JAMES, PRIYA, TOM, LENA, RAY]):
        radio.known[key] = "Net Control" if key == ADMIN else USERS[key]["name"].split()[0].lower() + "-hh"
        radio.details[key] = {"out_path_len": n % 3, "last_advert": int(now - (n + 1) * 47 * MIN)}
    for (name, kind, hops, heard), key in zip(NODES, NODE_KEYS, strict=True):
        radio.known[key] = name
        radio.details[key] = {"type": kind, "out_path_len": -1 if hops is None else hops,
                              "last_advert": int(now - heard) if heard else 0}
    directory = Directory(USERS, {ADMIN})
    commands = Registry(config).build(directory, radio, state)
    ctx = make_context("console", directory=directory, state=state, radio=radio, commands=commands)

    # The node watch with nothing wrong, weather alerts for four counties (one
    # with an alert out), their weather, and backups (real ones: Back up now
    # works, into the folder).
    state.watch = SimpleNamespace(active=[])
    state.alert_watcher = SimpleNamespace(
        last_check=now - 3 * MIN, problem=None, unmapped=[],
        settings=SimpleNamespace(counties=list(AREAS), channel="#contingency-wx"),
        codes={county: {"code": f"MOC{n:03}"} for n, county in enumerate(AREAS)},
        current={"Callaway, MO": [{"event": "Wind Advisory", "severity": "Minor", "headline": None,
                                   "ends": now + 5 * HOUR}]})
    state.area_weather = AreaWeather(state.alert_watcher, state)
    # What the radio heard on its channels: (slot, minutes ago, sender, text, hops, SNR); None: this node.
    state.channel_log = ChannelLog()
    for slot, ago, sender, text, hops, snr in CHANNEL_MESSAGES:
        if sender is None:
            state.channel_log.sent(slot, "Ridgeview Relay", text, now - ago * MIN)
        else:
            state.channel_log.heard({"channel_idx": slot, "text": f"{sender}: {text}", "path_len": hops, "SNR": snr},
                                    now - ago * MIN)
    state.area_weather.reports = {county: area_report(county, now) for county in AREAS}
    backups_folder = folder / "backups"
    state.backups = Backups(BackupSettings(to=str(backups_folder), folder=backups_folder), state, config_path,
                            directory)
    state.backups.store.data["last"] = now - 4 * HOUR
    state.store(ADVERTS_FILE).data["last_flood"] = now - 7 * HOUR

    state.saw(ADMIN, "Net Control")
    for key, ago in [(MARIA, 12 * MIN), (JAMES, 40 * MIN), (PRIYA, 3 * HOUR), (TOM, 26 * HOUR), (LENA, 2 * DAY)]:
        state.seen[key] = (USERS[key]["name"], now - ago)
    state.counts.update(messages=148, sent=131, undelivered=2)
    state.store(STATUSES).data.update({
        MARIA: {"name": "Maria Lopez", "status": "ok", "time": now - 12 * MIN},
        JAMES: {"name": "James Carter", "status": "ok, at the shelter", "time": now - 40 * MIN},
        ADMIN: {"name": "Net Control", "status": "ok", "time": now - 55 * MIN},
        PRIYA: {"name": "Priya Shah", "status": "ok, power out", "time": now - 3 * HOUR},
    })
    # The console never shows what messages say, so these say nothing.
    state.store(MAILBOX).data.update({
        TOM: [{"from": "Maria Lopez", "time": now - 2 * HOUR, "read": False, "text": "-"},
              {"from": "console", "time": now - 50 * MIN, "read": False, "text": "-"}],
        PRIYA: [{"from": "James Carter", "time": now - 5 * HOUR, "read": True, "sealed": "-"}],
        LENA: [{"from": "Net Control", "time": now - DAY, "read": False, "sealed": "-"}],
    })
    state.store(REQUESTS).data[SAM] = {"name": "Sam Rivera", "time": now - 25 * MIN}
    state.store(HISTORY_FILE).data["entries"] = [{"time": now - ago, "by": by, "what": what} for by, what, ago in [
        ("Net Control", "approved Lena Ortiz", 2 * DAY),
        ("Net Control", "approved Ray Whitfield", 30 * HOUR),
        ("console", "posted to #contingency-comm: net check-in at 19:00", 6 * HOUR),
        ("Priya Shah", "set a passphrase", 4 * HOUR),
        ("console", "left a message for Tom Becker", 50 * MIN),
    ]]

    output = SafeOutput(io.StringIO(), keep=50)
    for line in ["Connected to Ridgeview Relay.", "Listening for direct messages (Ctrl+C to quit)...",
                 "From Maria Lopez: ok", "To Maria Lopez: Checked in: ok"]:
        output.write(line + "\n")
    return ctx, output


def screenshots(url, folder, chrome):
    """Save each page, wide, and the dashboard phone-sized, as PNGs in folder."""
    folder.mkdir(parents=True, exist_ok=True)
    shots = [(path, name, WIDE) for path, name in PAGES.items()] + [("", "dashboard-phone", PHONE)]
    for path, name, (width, height) in shots:
        with tempfile.TemporaryDirectory() as profile:  # a new profile: it logs in with the key
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                            f"--window-size={width},{height}", "--timeout=5000",
                            f"--screenshot={folder / (name + '.png')}", url.replace("/?", f"/{path}?")],
                           check=True, capture_output=True)
        print(f"Saved {folder / (name + '.png')}", flush=True)


async def main(port, folder_for_shots):
    if not built(STATIC):
        raise SystemExit("The app isn't built: in console/, run npm ci and npm run build.")
    chrome = None
    if folder_for_shots:
        chrome = next((found for name in CHROMES if (found := shutil.which(name))), None)
        if not chrome:
            raise SystemExit(f"Screenshots need Chrome or Chromium ({', '.join(CHROMES)}).")
    with tempfile.TemporaryDirectory(prefix="demo-console-") as folder:
        ctx, output = demo_context(folder)
        runner = web.AppRunner(make_app(ctx, KEY, port, output=output), access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", port).start()
            url = f"http://127.0.0.1:{port}/?key={KEY}"
            if folder_for_shots:
                await asyncio.to_thread(screenshots, url, Path(folder_for_shots), chrome)
            else:
                print(f"Demo console: {url} (Ctrl+C to stop)", flush=True)
                await asyncio.Event().wait()
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A demo of the web console, with made-up data.")
    parser.add_argument("--port", type=int, default=8799, help="port on 127.0.0.1 (default 8799)")
    parser.add_argument("--screenshots", metavar="DIR", help="save a PNG of each page in DIR, then stop")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.port, args.screenshots))
    except KeyboardInterrupt:
        sys.exit(0)
