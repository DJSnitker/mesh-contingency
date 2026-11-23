"""Running the radio from the bot's own computer while it runs: adverts and a
look at the contacts, without stopping the bot or using the mesh.

- Typed into the bot's terminal: advert, advert flood, contacts [name], help.
- From another shell: kill -USR1 <pid> sends a flood advert.
- From config.toml, so new radios learn the node by themselves:

    [advert]
    every_hours = 12       # advert this often (default 0, never)
    flood = true           # flood (the whole mesh) or zero-hop (default true)
    at_startup = true      # also advert when the bot starts (default true)

The time of the last advert of each kind (flood, zero-hop) is kept in
adverts.json next to config.toml, whether it was scheduled or sent by hand, so
a restart doesn't reset the schedule: the next scheduled advert goes out
every_hours after the last one of its kind, at startup if that's overdue.
The startup advert is skipped if one of its kind went out less than
STARTUP_GAP ago, so a bot that systemd keeps restarting doesn't flood the
mesh every 30 seconds.
"""

import asyncio
import sys
import time

from meshcore import EventType

from .contacts import contact_rows

ADVERT_KEYS = {"at_startup", "every_hours", "flood"}
ADVERTS_FILE = "adverts.json"
# Seconds before trying again when the radio refuses a scheduled advert.
RETRY_SECONDS = 600
# No startup advert if one of its kind went out this recently (seconds).
STARTUP_GAP = 30 * 60
HELP = """Console commands:
  advert          zero-hop advert (radios in direct range)
  advert flood    flood advert (repeated across the mesh)
  contacts [name] the radio's contacts, or those whose name or key starts with name
  help            this list
Ctrl+C stops the bot."""


def load_advert(config):
    """Return (at_startup, every_hours, flood) from [advert]. Exits on a mistake."""
    section = config.get("advert", {})
    if not isinstance(section, dict) or set(section) - ADVERT_KEYS:
        raise SystemExit(f"[advert] may only set {', '.join(sorted(ADVERT_KEYS))}.")
    at_startup, flood = section.get("at_startup", True), section.get("flood", True)
    if not isinstance(at_startup, bool) or not isinstance(flood, bool):
        raise SystemExit("[advert] at_startup and flood must be true or false.")
    every_hours = section.get("every_hours", 0)
    if isinstance(every_hours, bool) or not isinstance(every_hours, (int, float)) or every_hours < 0:
        raise SystemExit("[advert] every_hours must be a number of hours, or 0 for never.")
    return at_startup, every_hours, flood


def _last_key(flood):
    return "last_flood" if flood else "last_zero_hop"


def record_advert(store, flood):
    """Note that an advert of this kind went out now."""
    store.data[_last_key(flood)] = time.time()
    store.save()


def seconds_until_advert(store, every_hours, flood):
    """Seconds until an advert of this kind is due again (0 if overdue or
    there hasn't been one), from the times kept in store."""
    last = store.data.get(_last_key(flood))
    if not isinstance(last, (int, float)):
        return 0
    return max(0.0, last + every_hours * 3600 - time.time())


async def send_advert(mc, flood, why, store=None):
    """Make the radio advert and print the outcome; why says who asked. If
    store is given, the time is recorded there for the schedule. Returns True
    if the radio accepted it."""
    kind = "flood" if flood else "zero-hop"
    res = await mc.commands.send_advert(flood=flood)
    if res.type == EventType.ERROR:
        print(f"Advert failed ({why}): radio rejected {kind} advert: {res.payload}", flush=True)
        return False
    print(f"Sent {kind} advert ({why})", flush=True)
    if store is not None:
        record_advert(store, flood)
    return True


async def advert_at_startup(mc, flood, store):
    """The startup advert, unless one of its kind went out less than
    STARTUP_GAP ago (a restart soon after another). Returns True if sent."""
    last = store.data.get(_last_key(flood))
    if isinstance(last, (int, float)) and 0 <= time.time() - last < STARTUP_GAP:
        kind = "flood" if flood else "zero-hop"
        print(f"No {kind} advert at startup: one went out {round((time.time() - last) / 60)} min ago.", flush=True)
        return False
    return await send_advert(mc, flood, "at startup", store)


async def advert_on_schedule(mc, store, every_hours, flood):
    """Advert whenever one is due: every_hours after the last advert of this
    kind, scheduled or sent by hand (recorded in store)."""
    while True:
        wait = seconds_until_advert(store, every_hours, flood)
        if wait:
            await asyncio.sleep(wait)
            continue  # check again: one may have been sent by hand meanwhile
        if not await send_advert(mc, flood, "scheduled", store):
            await asyncio.sleep(RETRY_SECONDS)


def list_contacts(mc, wanted=""):
    """The radio's contacts as printable lines, filtered by name or key start."""
    rows = contact_rows(mc, wanted)
    lines = [f"  {key[:12]}  {name}" + (f" ({kind})" if kind not in ("", "chat") else "") for name, key, kind in rows]
    what = f" matching {wanted.lower()}" if wanted else ""
    return "\n".join([f"{len(rows)} contact(s){what}:"] + lines)


async def run_console_command(mc, line, store=None):
    """Carry out one line typed into the bot's terminal; adverts are
    recorded in store, if given."""
    words = line.split()
    if not words:
        return
    command, rest = words[0].lower(), words[1:]
    if command == "advert" and rest in ([], ["flood"]):
        await send_advert(mc, bool(rest), "console", store)
    elif command == "contacts" and len(rest) <= 1:
        print(list_contacts(mc, rest[0] if rest else ""), flush=True)
    else:
        print(HELP if command == "help" else f"Unknown console command: {line.strip()}\n{HELP}", flush=True)


def watch_console(loop, on_line, stdin=None):
    """Call on_line(text) for each line typed into the terminal. Returns a
    function that stops watching, or None if there is no terminal to read
    (running as a service, or on Windows)."""
    stdin = stdin or sys.stdin
    try:
        if not stdin.isatty():
            return None
        fd = stdin.fileno()

        def readable():
            line = stdin.readline()
            if not line:  # end of input (Ctrl+D)
                loop.remove_reader(fd)
                return
            on_line(line)

        loop.add_reader(fd, readable)
    except (AttributeError, NotImplementedError, OSError, ValueError):
        return None
    return lambda: loop.remove_reader(fd)
