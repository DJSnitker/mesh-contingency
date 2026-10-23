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

from mesh_contingency.backup import Backups, BackupSettings
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
PAGES = {"": "dashboard", "users": "users", "checkins": "checkins", "inbox": "inbox", "history": "history",
         "send": "send", "radio": "radio"}
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
    directory = Directory(USERS, {ADMIN})
    commands = Registry(config).build(directory, radio, state)
    ctx = make_context("console", directory=directory, state=state, radio=radio, commands=commands)

    # The node watch with nothing wrong, weather alerts for four counties, and
    # backups (real ones: Back up now works, into the folder).
    state.watch = SimpleNamespace(active=[])
    state.alert_watcher = SimpleNamespace(last_check=now - 3 * MIN, problem=None, unmapped=[],
                                          settings=SimpleNamespace(counties=["A", "B", "C", "D"]))
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
