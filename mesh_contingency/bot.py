"""Post National Weather Service alerts to MeshCore's Public channel, and
answer the admins' direct-message commands, through a companion radio on USB.

Channel messages are ignored; commands come only by direct message.
"""

import argparse
import asyncio
import contextlib
import difflib
import glob
import signal
import sys
import time
from pathlib import Path

from meshcore import EventType, MeshCore

from .alerts import AlertTest, AlertWatcher, load_alert_test, load_alerts
from .api import DISABLED, LEVELS, MAX_REPLY_LEN, CommandError, Sender, is_authorized
from .config import load_admins, load_config, retired_settings
from .console import (
    ADVERTS_FILE,
    advert_on_schedule,
    load_advert,
    run_console_command,
    seconds_until_advert,
    send_advert,
    watch_console,
)
from .contacts import add_admins
from .limits import RateLimiter, describe_rate, wait_text
from .output import SafeOutput
from .registry import Registry
from .running import run_command
from .state import State, duration

# config.toml in the project folder (the parent of this package).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
# How long to wait for the radio when shutting down.
DISCONNECT_SECONDS = 5
# How long to wait for the radio to answer a question at startup.
RADIO_SECONDS = 5
# The radio's clock this far off the computer's (seconds) is set at startup.
CLOCK_SLACK = 5

# Sent for unknown commands and for commands the sender may not run.
UNRECOGNIZED_REPLY = "unrecognized user or function"
# Send UNRECOGNIZED_REPLY to the same sender at most once per this many
# seconds, so another auto-replying node can't trap us in a reply loop.
UNRECOGNIZED_COOLDOWN = 300
# How alike (0-1, difflib's ratio) a mistyped command must be to one the
# sender may run to be suggested: typos like "hlep" or "alret" are 0.75 or
# more; "hello" (help) or "test" (testalert) are less.
SUGGEST_CUTOFF = 0.75


def find_serial_port():
    """Return the first likely USB serial port, or None."""
    candidates = sorted(glob.glob("/dev/serial/by-id/*")) + sorted(
        glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    )
    return candidates[0] if candidates else None


def parse_command(msg, commands):
    """Return (command, text) for a message naming a known command, or None.

    text is everything after the command name.
    """
    parts = msg.get("text", "").strip().split(None, 1)
    if not parts:
        return None
    command = commands.get(parts[0].lower())
    return (command, parts[1].strip() if len(parts) > 1 else "") if command else None


async def ask_radio(request, wanted, seconds=RADIO_SECONDS):
    """The payload of the radio's answer to request() if it is of type
    wanted, or None if it answered otherwise or not in time."""
    try:
        res = await asyncio.wait_for(request(), seconds)
    except Exception:
        return None
    return res.payload if res is not None and res.type == wanted else None


def nearest_command(word, names, disabled=()):
    """The command in names a mistyped word was meant to be, or None. A
    disabled command's own name gets no suggestion: it's not a typo for
    something else."""
    word = word.lower()
    if word in disabled:
        return None
    close = difflib.get_close_matches(word, names, n=1, cutoff=SUGGEST_CUTOFF)
    return close[0] if close else None


def warn_if_shared(path):
    """Warn if the config can be changed (or read) by other accounts: whoever
    can change it chooses the admins."""
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        print(f"Warning: {path} can be read or changed by other accounts (mode {mode:o}); "
              f"fix with: chmod 600 {path}", flush=True)


async def set_clock(mc):
    """Set the radio's clock from the computer's if it's off: the radio
    keeps no time across a reboot or a power cut, and dates its messages and
    adverts by it."""
    now = time.time()
    found = await ask_radio(mc.commands.get_time, EventType.CURRENT_TIME) or {}
    off = found["time"] - now if found.get("time") else None
    if off is not None and abs(off) < CLOCK_SLACK:
        return
    if await ask_radio(lambda: mc.commands.set_time(int(time.time())), EventType.OK) is None:
        print("Warning: couldn't set the radio's clock.", flush=True)
    elif off is None:
        print("Set the radio's clock from the computer's.", flush=True)
    else:
        print(f"Set the radio's clock from the computer's: it was {duration(abs(off))} "
              f"{'ahead' if off > 0 else 'behind'}.", flush=True)


async def main():
    # Everything printed may include text from the mesh; escape any terminal
    # control sequences in it.
    output = SafeOutput(sys.stdout)
    with contextlib.redirect_stdout(output):
        return await _main()


async def _main():
    parser = argparse.ArgumentParser(prog="mesh-contingency", description=__doc__)
    parser.add_argument("-p", "--port", help="serial port (auto-detected if omitted)")
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument("--debug", action="store_true", help="verbose library logging")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"config file (default: {DEFAULT_CONFIG})")
    args = parser.parse_args()

    # Check the whole config before connecting, so mistakes show up straight away.
    config = load_config(args.config)
    admins, admin_warnings = load_admins(config, args.config)
    advert_at_startup, advert_every_hours, advert_flood = load_advert(config)
    alert_settings = load_alerts(config)
    test_settings = load_alert_test(config, alert_settings.channel)
    registry = Registry(config)
    for warning in [retired_settings(config), *admin_warnings]:
        if warning:
            print(f"Warning: {warning}")

    port = args.port or find_serial_port()
    if not port:
        raise SystemExit("No serial device found. Plug in the radio or pass --port.")

    print(f"Connecting to {port} @ {args.baud}...")
    mc = await MeshCore.create_serial(port, args.baud, debug=args.debug, auto_reconnect=True)
    if mc is None:
        raise SystemExit(f"Could not connect to MeshCore device on {port}.")

    # Load contacts so direct messages can show the sender's name and be
    # replied to, and keep them current as the radio learns new nodes.
    await mc.ensure_contacts()
    mc.auto_update_contacts = True
    print(f"Connected to {mc.self_info.get('name')}. {len(mc.contacts)} contacts.")
    await set_clock(mc)
    if note := await add_admins(mc, admins):
        print(note)

    # One message at a time: the radio matches each ack to the message it
    # just sent, so overlapping sends could confuse delivery tracking.
    send_lock = asyncio.Lock()

    async def send_dm(key, text, what="reply"):
        """Send a direct message to a contact by public key (or, for a sender
        we couldn't identify, the prefix they wrote from), retrying until the
        radio reports an ack, and log whether it was delivered."""
        if len(text) > MAX_REPLY_LEN:
            # Error text can echo the sender's input; never exceed the mesh limit.
            text = text[: MAX_REPLY_LEN - 3] + "..."
        prefix = key[:12]  # logged instead of the full key
        contact = mc.get_contact_by_key_prefix(key)
        if contact is None:
            # The radio may have learned this node after we loaded contacts.
            await mc.commands.get_contacts()
            contact = mc.get_contact_by_key_prefix(key)
        if contact is None:
            print(f"  (no contact {prefix} to send {what} to; is it in the radio's contacts?)", flush=True)
            return
        async with send_lock:
            result = await mc.commands.send_msg_with_retry(contact, text)
        if result is None:
            print(f"  ({what} to {prefix} not acknowledged after retries)", flush=True)
        else:
            print(f"  ({what} to {prefix} delivered)", flush=True)

    background = set()  # running background tasks, kept so they aren't garbage collected

    def in_background(coro):
        """Run a coroutine as a background task, kept until it finishes."""
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    def send_later(key, text, what="notice"):
        """Send a direct message in the background, without holding up the
        radio's event handling (or a command's reply) while it goes out."""
        in_background(send_dm(key, text, what=what))

    # The state files (the alerts posted, the advert times), next to config.toml.
    state = State(args.config.resolve().parent)
    commands = registry.build(admins, mc, state, send_later)
    for level in LEVELS[:-1]:
        names = [c.name for c in commands.values() if c.permission == level]
        if names:
            who = f"{len(admins)} admin(s)" if level == "admin" else "anyone" if level == "public" else "users"
            print(f"  {level} commands ({who}): {', '.join(names)}")
    print(f"  {DISABLED} commands (nobody): {', '.join(registry.disabled) or 'none'}")
    for warning in registry.warnings:
        print(f"Warning: {warning}")
    if not admins and any(c.permission == "admin" for c in commands.values()):
        print("Note: no admins in [admins] keys in config.toml, so nobody can use the admin commands.")
    defaults = ", ".join(f"{level} {describe_rate(rate)}" for level, rate in registry.limits.rates.items())
    print(f"Rate limits per sender and command: {defaults} (unless a command sets rate).")

    # Setup that needs the radio, such as alert making sure its channel exists.
    for command in commands.values():
        try:
            note = await asyncio.wait_for(command.start(), command.timeout)
        except CommandError as e:
            print(f"Warning: {e}")
        except Exception as e:
            print(f"Warning: {command.name} could not get ready: {e or type(e).__name__}")
        else:
            if note:
                print(note)
    for command in commands.values():
        if not command.enabled and command.permission != DISABLED:
            print(f"Warning: {getattr(command, 'unconfigured', None) or f'{command.name} is not set up'}.")

    loop = asyncio.get_running_loop()
    # When each kind of advert last went out, scheduled or by hand.
    advert_times = state.store(ADVERTS_FILE)
    # kill -USR1 <pid> sends a flood advert, for a bot running without a terminal.
    with contextlib.suppress(AttributeError, NotImplementedError):  # no SIGUSR1 on Windows
        loop.add_signal_handler(signal.SIGUSR1, lambda: in_background(send_advert(mc, True, "SIGUSR1", advert_times)))
    if advert_at_startup:
        await send_advert(mc, advert_flood, "at startup", advert_times)
    tasks = []
    if advert_every_hours:
        # So admins' radios learn the node; the schedule carries on across restarts.
        wait = seconds_until_advert(advert_times, advert_every_hours, advert_flood)
        print(f"Sending a {'flood' if advert_flood else 'zero-hop'} advert every {advert_every_hours:g} hour(s); "
              f"next {'now' if not wait else 'in ' + wait_text(wait)}.")
        tasks.append(asyncio.create_task(advert_on_schedule(mc, advert_times, advert_every_hours, advert_flood)))
    if alert_settings.counties:
        alert_watcher = state.alert_watcher = AlertWatcher(mc, alert_settings, state)
        print(f"Watching NWS alerts for {alert_watcher.describe()}.")
        tasks.append(asyncio.create_task(alert_watcher.run()))
    else:
        print("Warning: no counties in [alerts] counties in config.toml, so no weather alerts will be posted.")
    alert_test = state.alert_test = AlertTest(mc, test_settings, state, alert_settings.counties)
    if problem := alert_test.problem():
        raise SystemExit(f"{problem}. Shorten it.")
    if test_settings.weekly:
        print(f"Weekly alert test: {alert_test.describe()}.")
        tasks.append(asyncio.create_task(alert_test.run()))
    # Uses of each command by each sender.
    limiter = RateLimiter()
    stop_console = watch_console(loop, lambda line: in_background(run_console_command(mc, line, advert_times)))
    if stop_console:
        print("Type help for console commands (advert, advert flood, contacts).")
    warn_if_shared(args.config.resolve())
    print("Listening for direct messages (Ctrl+C to quit)...")

    def message_prefix(msg):
        """The 6-byte key prefix (12 hex chars) a direct message comes with."""
        return msg.get("pubkey_prefix", "").lower()

    async def reply(msg, sender, text):
        """Send text back to the sender of a direct message."""
        await send_dm(sender.public_key or message_prefix(msg), text)

    def contacts_with_prefix(prefix):
        return [c for c in mc.contacts.values() if prefix and c.get("public_key", "").lower().startswith(prefix)]

    async def get_sender(msg):
        """Return the Sender of a direct message.

        A message carries only the sender's key prefix, so it is matched to
        the radio's contacts for the full public key that permissions use. If
        no contact or more than one has the prefix, the sender is unidentified
        (public_key None): a node with a copied prefix never gets rights.
        """
        prefix = message_prefix(msg)
        matches = contacts_with_prefix(prefix)
        if not matches:
            # The radio may have learned this node after we loaded contacts.
            await mc.commands.get_contacts()
            matches = contacts_with_prefix(prefix)
        if len(matches) != 1:
            if matches:
                admin = any(c["public_key"].lower() in admins for c in matches)
                print(f"  ({len(matches)} contacts share key prefix {prefix}; sender not identified"
                      f"{'; one is an admin, so remove the impostor from the radio' if admin else ''})", flush=True)
            return Sender(prefix, None)
        contact = matches[0]
        return Sender(contact.get("adv_name") or prefix, contact["public_key"].lower())

    last_unrecognized = {}  # key prefix -> time.monotonic() of the last UNRECOGNIZED_REPLY

    async def reply_unrecognized(msg, sender, why):
        """Send UNRECOGNIZED_REPLY unless this sender got one recently."""
        now = time.monotonic()
        prefix = message_prefix(msg)
        if now - last_unrecognized.get(prefix, -UNRECOGNIZED_COOLDOWN) < UNRECOGNIZED_COOLDOWN:
            print(f"  -> {why}; not replying (replied within {UNRECOGNIZED_COOLDOWN}s)", flush=True)
            return
        last_unrecognized[prefix] = now
        print(f"  -> {why}; sending unrecognized reply", flush=True)
        await reply(msg, sender, UNRECOGNIZED_REPLY)

    async def on_message(event):
        msg = event.payload
        sender = await get_sender(msg)
        prefix = message_prefix(msg)
        label = prefix if sender.name == prefix else f"{prefix} {sender.name}"
        parsed = parse_command(msg, commands)
        # Only the command's name is printed, never what was sent with it
        # (an alert's text) or what doesn't parse as a command.
        print(f"[{label}] {parsed[0].name if parsed else 'not a command'}", flush=True)
        if parsed is None:
            words = msg.get("text", "").split()
            if not words:
                return
            # Admins are told the nearest command they may run; strangers
            # learn nothing about the commands there are.
            if sender.public_key in admins:
                mine = [c.name for c in commands.values() if is_authorized(c, sender, {}, admins)]
                nearest = nearest_command(words[0], mine, registry.disabled)
                if nearest:
                    print(f"  -> unrecognized command; suggesting {nearest}", flush=True)
                    await reply(msg, sender, f"unknown command {words[0][:30]}; did you mean {nearest}? "
                                             "help lists yours")
                    return
            await reply_unrecognized(msg, sender, "unrecognized command")
            return
        command, text = parsed
        if not is_authorized(command, sender, {}, admins):
            await reply_unrecognized(msg, sender, f"{command.name} denied: sender not approved")
            return
        wait, first = limiter.check(sender.public_key or prefix, command.name, command.rate)
        if wait:
            # Told once; after that silence, so the limit can't make us transmit.
            if first:
                print(f"  -> {command.name} limit reached ({describe_rate(command.rate)}); replying once", flush=True)
                await reply(msg, sender, f"{command.name}: limit reached, try again in {wait_text(wait)}")
            else:
                print(f"  -> {command.name} limit reached; not replying", flush=True)
            return
        answer = await run_command(command, text, sender)
        # A long reply comes as several messages, sent in order.
        for text in answer.messages:
            await reply(msg, sender, text)
            print(f"  -> replied ({len(text)} chars)", flush=True)

    # Stop on SIGTERM (systemctl stop) as on Ctrl+C, or when the radio is lost
    # for good: the library's few quick reconnects failed, so exit with an
    # error and let the service manager start the bot again.
    stopping = asyncio.Event()
    lost = []

    async def on_disconnect(event):
        reason = (event.payload or {}).get("reason", "unknown")
        if reason != "manual_disconnect":
            lost.append(reason)
            print(f"Lost the radio ({reason}); stopping.", flush=True)
            stopping.set()

    with contextlib.suppress(NotImplementedError):  # not on Windows
        loop.add_signal_handler(signal.SIGTERM, stopping.set)
    mc.subscribe(EventType.DISCONNECTED, on_disconnect)
    mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
    await mc.start_auto_message_fetching()

    try:
        await stopping.wait()
    finally:
        for task in tasks:
            task.cancel()
        if stop_console:
            stop_console()
        with contextlib.suppress(AttributeError, NotImplementedError):
            loop.remove_signal_handler(signal.SIGUSR1)
            loop.remove_signal_handler(signal.SIGTERM)
        # A lost radio may not answer; don't hang on it, and disconnect even
        # if it didn't stop fetching.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(mc.stop_auto_message_fetching(), DISCONNECT_SECONDS)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(mc.disconnect(), DISCONNECT_SECONDS)
    if lost:
        return 1
    print("Stopped.")
    return 0


def run():
    """Entry point for the mesh-contingency command."""
    try:
        code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        return
    if code:
        raise SystemExit(code)
