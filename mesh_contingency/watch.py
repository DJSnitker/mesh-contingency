"""Watching the node itself: direct messages to the admins when something
goes wrong, so problems don't wait for someone to send health.

[watch] in config.toml (on unless enabled = false). Every few minutes the
watcher reads the radio's battery and uptime and looks at what the bot has
seen, and tells every admin when a problem starts ("Node problem: ...") and
when it's over ("Node ok again: ..."):

- battery: the radio's battery below battery_volts (ok again a little above);
- undelivered: undelivered_in_row direct messages in a row not acknowledged;
- email: an email couldn't be sent for a reason at the node (no internet,
  login refused...), until one is sent;
- errors: `errors` commands failed or timed out within ERROR_WINDOW;
- users: the users file can't be reloaded, until it can;
- backup: a backup of the bot's data failed, until one works.

It also says when the radio has restarted: its uptime went backwards.
Restarting the bot doesn't restart the radio, so this is always a real
restart (power, USB, a crash), even one that restarted the bot too.

A problem is announced at most once an hour, so a value going back and forth
can't flood the mesh; its "ok again" follows once. What has been announced,
and when the radio last started, are kept in watch.json next to config.toml,
so a restart of the bot doesn't announce an ongoing problem again.
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass

from meshcore import EventType

from .state import ago

WATCH_FILE = "watch.json"
WATCH_KEYS = {"enabled", "every_minutes", "battery_volts", "undelivered_in_row", "errors"}
DEFAULT_EVERY_MINUTES = 5
MIN_EVERY_MINUTES = 1
ERROR_WINDOW = 30 * 60  # seconds in which `errors` command errors make a problem
NOTICE_GAP = 3600  # seconds between two announcements of the same problem
BATTERY_MARGIN = 0.1  # volts above battery_volts before the battery is ok again
# The radio's start time is worked out from its uptime, which comes in whole
# seconds and a little late; a later start by more than this is a restart.
RESTART_SLACK = 120
RADIO_SECONDS = 5  # how long to wait for the radio to answer
# Each problem's name in health, and what the "ok again" notice says.
LABELS = {"battery": "battery low", "undelivered": "replies undelivered", "email": "email failing",
          "errors": "command errors", "users": "users file", "backup": "backup failing"}


async def ask_radio(request, wanted, seconds=RADIO_SECONDS):
    """The payload of a radio request, or None if it fails, is refused or
    takes too long."""
    try:
        result = await asyncio.wait_for(request(), seconds)
    except Exception:
        return None
    return result.payload if result is not None and result.type == wanted else None


@dataclass(frozen=True)
class WatchSettings:
    enabled: bool = True
    every_minutes: float = DEFAULT_EVERY_MINUTES
    battery_volts: float = 3.5  # 0 for no battery check
    undelivered_in_row: int = 5  # 0 for no check
    errors: int = 3  # within ERROR_WINDOW; 0 for no check


def load_watch(config):
    """WatchSettings from [watch] in config.toml. Exits on a mistake."""
    section = config.get("watch", {})
    if not isinstance(section, dict) or set(section) - WATCH_KEYS:
        raise SystemExit(f"[watch] may only set {', '.join(sorted(WATCH_KEYS))}.")
    defaults = WatchSettings()
    enabled = section.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise SystemExit("[watch] enabled must be true or false.")

    def number(key, minimum, whole=False):
        value = section.get(key, getattr(defaults, key))
        kinds = int if whole else (int, float)
        if isinstance(value, bool) or not isinstance(value, kinds) or value < minimum:
            raise SystemExit(f"[watch] {key} must be a {'whole ' if whole else ''}number, at least {minimum}.")
        return value

    return WatchSettings(enabled, number("every_minutes", MIN_EVERY_MINUTES), number("battery_volts", 0),
                         number("undelivered_in_row", 0, whole=True), number("errors", 0, whole=True))


class NodeWatch:
    """Tells the admins about problems with the node, as they start and end."""

    def __init__(self, radio, settings, state, directory, tell):
        self.radio = radio
        self.settings = settings
        self.state = state
        self.directory = directory
        self.tell = tell  # tell(text): a notice for every admin
        # {"announced": {problem: time}, "noticed": {problem: time}, "radio_started": time}
        self.store = state.store(WATCH_FILE)
        self.wake = asyncio.Event()  # set to check straight away
        self.voltage = None  # the battery at the last check, if the radio said
        self.active = []  # the problems found at the last check, for health

    @property
    def announced(self):
        """Problems the admins have been told about and not yet told are over."""
        return self.store.data.setdefault("announced", {})

    @property
    def noticed(self):
        """When each problem (or a radio restart) was last announced."""
        return self.store.data.setdefault("noticed", {})

    def describe(self):
        """For startup."""
        checks = [f"battery below {self.settings.battery_volts:g}V" if self.settings.battery_volts else "",
                  "radio restarts",
                  f"{self.settings.undelivered_in_row} undelivered in a row" if self.settings.undelivered_in_row
                  else "",
                  "email failing",
                  f"{self.settings.errors} errors in {ERROR_WINDOW // 60} min" if self.settings.errors else "",
                  f"{self.directory.name} not reloading",
                  "backups failing" if self.state.backups else ""]
        return f"every {self.settings.every_minutes:g} min: {', '.join(c for c in checks if c)}"

    def problems(self, now):
        """{problem: what's wrong} for each problem there is now."""
        settings, state, found = self.settings, self.state, {}
        volts = settings.battery_volts
        if volts:
            if self.voltage is None:  # the radio didn't say; no change
                if "battery" in self.announced:
                    found["battery"] = "battery low"
            elif self.voltage < volts or ("battery" in self.announced and self.voltage < volts + BATTERY_MARGIN):
                found["battery"] = f"battery low, {self.voltage:.2f}V (below {volts:.2f}V)"
        if settings.undelivered_in_row and state.undelivered_in_row >= settings.undelivered_in_row:
            found["undelivered"] = f"{state.undelivered_in_row} messages in a row not delivered"
        if state.emails.failing:
            found["email"] = f"email failing: {state.emails.failing}"
        if settings.errors:
            recent = state.recent_errors(ERROR_WINDOW, now)
            if recent >= settings.errors:
                found["errors"] = (f"{recent} command errors in {ERROR_WINDOW // 60} min, "
                                   f"last {state.last_error[1]}")
        if self.directory.problem:
            found["users"] = f"{self.directory.name} not reloaded: {self.directory.problem[1]}"
        if state.backups and state.backups.failing:
            found["backup"] = f"backup to {state.backups.settings.to} failing: {state.backups.failing}"
        return found

    def ok_text(self, problem):
        if problem == "battery":
            return f"battery {self.voltage:.2f}V" if self.voltage is not None else "battery ok"
        return {"undelivered": "messages delivered", "email": "an email was sent",
                "errors": "no more command errors", "users": f"{self.directory.name} reloaded",
                "backup": "a backup was made"}[problem]

    def check_restart(self, uptime, now):
        """Announce a radio restart if its uptime went backwards since the
        last check (or the last run of the bot)."""
        started = now - uptime
        before = self.store.data.get("radio_started")
        if before is None or started > before + RESTART_SLACK:
            self.store.data["radio_started"] = started
        if before is not None and started > before + RESTART_SLACK:
            text = f"Node problem: the radio restarted {ago(started, now)} (power, USB or a crash)"
            if now - self.noticed.get("restart", 0) >= NOTICE_GAP:
                self.noticed["restart"] = now
                self.tell(text)
            else:
                print(f"Watch: {text}; admins told within the hour, not again", flush=True)

    async def check(self):
        """Read the radio, then announce new problems and ones that are over."""
        radio = self.radio
        stats = await ask_radio(radio.commands.get_stats_core, EventType.STATS_CORE) or {}
        battery = await ask_radio(radio.commands.get_bat, EventType.BATTERY) or {}
        millivolts = battery.get("level") or stats.get("battery_mv")
        self.voltage = millivolts / 1000 if millivolts else None
        now = time.time()
        if "uptime_secs" in stats:
            self.check_restart(stats["uptime_secs"], now)
        found = self.problems(now)
        self.active = list(found)
        for problem, text in found.items():
            if problem not in self.announced and now - self.noticed.get(problem, 0) >= NOTICE_GAP:
                self.announced[problem] = self.noticed[problem] = now
                self.tell(f"Node problem: {text}")
        for problem in [p for p in self.announced if p not in found]:
            del self.announced[problem]
            self.tell(f"Node ok again: {self.ok_text(problem)}")
        self.store.save()

    async def run(self):
        """Check every every_minutes, or straight away when woken, until
        cancelled; a failed check is logged and tried again next time."""
        while True:
            try:
                await self.check()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Watch: check failed: {e}; trying again in {self.settings.every_minutes:g} min", flush=True)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), self.settings.every_minutes * 60)
            self.wake.clear()
