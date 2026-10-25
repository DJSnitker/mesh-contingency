"""Listen to a MeshCore companion device over USB serial and act on direct messages.

Channel messages are ignored entirely (the alert command only posts to one).
"""

import argparse
import asyncio
import contextlib
import difflib
import glob
import os
import signal
import sys
import time
import tomllib
from pathlib import Path

from meshcore import EventType, MeshCore

from .alerts import AlertTest, AlertWatcher, load_alert_test, load_alerts
from .api import (
    ADMIN,
    DISABLED,
    MAX_REPLY_LEN,
    PUBLIC,
    USER,
    CommandError,
    Context,
    Sender,
    is_authorized,
)
from .area_weather import AreaWeather
from .backup import Backups, load_backup
from .channel_log import KEEP, ChannelLog
from .commands.area import AreaCommand
from .console import (
    ADVERTS_FILE,
    advert_on_schedule,
    load_advert,
    run_console_command,
    seconds_until_advert,
    send_advert,
    watch_console,
)
from .contacts import NoticeBatcher, load_auto_add, load_contact_limits, load_notify_admins, setup_auto_add
from .directory import Directory, DirectoryError, describe, possessive
from .limits import RateLimiter, describe_rate, wait_text
from .names import name_problem
from .output import SafeOutput
from .registry import RENAMED, Registry
from .running import run_command
from .state import State, duration
from .watch import NodeWatch, ask_radio, load_watch
from .web import INSTALL, aiohttp_missing, load_console

# config.toml in the project folder (the parent of this package).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
# How long to wait for the radio when shutting down.
DISCONNECT_SECONDS = 5
# After a restart is asked for, seconds before stopping, so the reply gets out.
RESTART_SECONDS = 2
# The radio's clock this far off the computer's (seconds) is set at startup.
CLOCK_SLACK = 5

# Sent for unknown commands and for commands the sender may not run.
UNRECOGNIZED_REPLY = "unrecognized user or function"
# Send UNRECOGNIZED_REPLY to the same sender at most once per this many
# seconds, so another auto-replying node can't trap us in a reply loop.
UNRECOGNIZED_COOLDOWN = 300
# How alike (0-1, difflib's ratio) a mistyped command must be to one the
# sender may run to be suggested: typos like "hlep", "emial" or "resetpassword"
# are 0.75 or more; "hello" (help), "weather" (health) or "test" (testalert)
# are 0.67 or less.
SUGGEST_CUTOFF = 0.75
# How often to check whether an hourly new-contact summary is due.
SUMMARY_CHECK_SECONDS = 60
# Lines of the log kept for the web console's live log.
LOG_LINES = 500


def find_serial_port():
    """Return the first likely USB serial port, or None."""
    candidates = sorted(glob.glob("/dev/serial/by-id/*")) + sorted(
        glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    )
    return candidates[0] if candidates else None


def load_config(path):
    """Return the parsed TOML config, or {} if the file does not exist."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def parse_command(msg, commands):
    """Return (command, text) for a message naming a known command, or None.

    text is everything after the command name.
    """
    parts = msg.get("text", "").strip().split(None, 1)
    if not parts:
        return None
    command = commands.get(parts[0].lower())
    return (command, parts[1].strip() if len(parts) > 1 else "") if command else None


def nearest_command(word, names, disabled=()):
    """The command in names a mistyped word was meant to be, or None: its new
    name if it was renamed, else the closest. A disabled command's own name
    gets no suggestion: it's not a typo for something else."""
    word = word.lower()
    if word in disabled:
        return None
    if RENAMED.get(word) in names:
        return RENAMED[word]
    close = difflib.get_close_matches(word, names, n=1, cutoff=SUGGEST_CUTOFF)
    return close[0] if close else None


def warn_if_shared(path):
    """Warn if a file holding addresses, keys or passwords can be read or
    changed by other accounts."""
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        print(f"Warning: {path} can be read or changed by other accounts (mode {mode:o}); "
              f"fix with: chmod 600 {path}", flush=True)


def mailrc_path():
    """The mail command's settings file, which may hold an SMTP password."""
    return Path(os.environ.get("MAILRC") or Path.home() / ".mailrc")


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
        print("Warning: couldn't set the radio's clock; set it from the web console (radio clock).", flush=True)
    elif off is None:
        print("Set the radio's clock from the computer's.", flush=True)
    else:
        print(f"Set the radio's clock from the computer's: it was {duration(abs(off))} "
              f"{'ahead' if off > 0 else 'behind'}.", flush=True)


async def main():
    # Everything printed may include text from the mesh; escape any terminal
    # control sequences in it.
    output = SafeOutput(sys.stdout, keep=LOG_LINES)
    with contextlib.redirect_stdout(output):
        return await _main(output)


async def _main(output):
    parser = argparse.ArgumentParser(prog="mesh-contingency", description=__doc__)
    parser.add_argument("-p", "--port", help="serial port (auto-detected if omitted)")
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument("--debug", action="store_true", help="verbose library logging")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"config file (default: {DEFAULT_CONFIG})")
    args = parser.parse_args()

    config = load_config(args.config)
    # Users and admins live in their own file, reloaded while the bot runs.
    directory = Directory.from_config(config, args.config)
    if not directory.load():
        print(f"Warning: {directory.path} not found; no users or admins until it is created.")
    auto_add = load_auto_add(config)
    notify_admins = load_notify_admins(config)
    max_new_per_hour, notices_per_hour = load_contact_limits(config)
    advert_at_startup, advert_every_hours, advert_flood = load_advert(config)
    alert_settings = load_alerts(config)
    test_settings = load_alert_test(config, alert_settings.channel)
    watch_settings = load_watch(config)
    backup_settings = load_backup(config, args.config.resolve().parent)
    console_settings = load_console(config)
    # Check the [commands] config and import the enabled commands before
    # connecting, so mistakes show up straight away.
    registry = Registry(config)

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
        state.counts["sent"] += 1
        if contact is None:
            state.counts["undelivered"] += 1
            print(f"  (no contact {prefix} to send {what} to; is it in the radio's contacts?)", flush=True)
            return
        async with send_lock:
            result = await mc.commands.send_msg_with_retry(contact, text)
        if result is None:
            state.undelivered()
            print(f"  ({what} to {prefix} not acknowledged after retries)", flush=True)
        else:
            state.delivered()
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

    def tell_admins(text, what):
        """Send text to every current admin in the background."""
        for admin in sorted(directory.admins):
            send_later(admin, text, what)

    notices = NoticeBatcher(notices_per_hour)

    def announce_new_contact(key, name, type_name):
        """Tell every admin about a contact the bot just added, unless this
        hour's notices are used up (then it goes in the hourly summary)."""
        if notices.allow():
            tell_admins(f"New contact: {name or '?'} ({key}, {type_name})", "new-contact notice")

    async def send_summaries():
        """Send the hourly summary of contacts not announced or not added."""
        while True:
            await asyncio.sleep(SUMMARY_CHECK_SECONDS)
            text = notices.summary()
            if text:
                print(text, flush=True)
                if notify_admins:
                    tell_admins(text, "new-contact summary")

    def protected_keys():
        """Users' and admins' full keys, as of now."""
        return directory.users.keys() | directory.admins

    def announce_blocked(prefix, name, target):
        """Warn every admin about a node posing as a user or admin. Sent even
        with notify_admins off, since it may be an attack."""
        who = describe(target, directory.users)
        tell_admins(f"Blocked {prefix} {name or '?'}: posing as {who} (same key prefix, different key)",
                    "blocked-contact alert")

    if auto_add is not None:
        await setup_auto_add(mc, auto_add, on_added=announce_new_contact if notify_admins else None,
                             protected=protected_keys, on_blocked=announce_blocked,
                             max_new_per_hour=max_new_per_hour, on_skipped=notices.skipped)
        if notify_admins and directory.admins:
            print(f"New contacts are announced to {len(directory.admins)} admin(s).")

    # Who has messaged the node, and the state files (statuses, the mailbox),
    # kept next to config.toml.
    state = State(args.config.resolve().parent)
    commands = registry.build(directory, mc, state, send_later)
    for level, who in [(PUBLIC, "anyone"), (USER, f"{len(directory.users)} user(s)"),
                       (ADMIN, f"{len(directory.admins)} admin(s)")]:
        names = [c.name for c in commands.values() if c.permission == level]
        print(f"  {level} commands ({who}): {', '.join(names) or 'none'}")
    print(f"  {DISABLED} commands (nobody): {', '.join(registry.disabled) or 'none'}")
    for warning in registry.warnings:
        print(f"Warning: {warning}")
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

    def warn_unconfigured():
        for command in commands.values():
            if not command.enabled and command.permission != DISABLED:
                # A command may say why it's off; the email commands are off with no addresses.
                why = getattr(command, "unconfigured", None)
                print(f"Warning: {why or f'no user has {command.name} addresses in {directory.name}'}.", flush=True)

    def convert_settings():
        """Move addresses saved under an old command name (quickim) to the
        new one (qm), keeping the order of each user's settings."""
        changes, moved = {}, set()
        for key, user in directory.users.items():
            for old, new in RENAMED.items():
                if old in user and new not in user:
                    user = changes[key] = {(new if k == old else k): v for k, v in user.items()}
                    moved.add(old)
        if not changes:
            return
        moved = sorted(moved)
        try:
            directory.save_users(changes)
        except DirectoryError as e:
            print(f"Warning: {', '.join(moved)} settings not converted: {directory.name} {e}", flush=True)
            return
        print(f"{directory.name}: {', '.join(f'{old} is now {RENAMED[old]}' for old in moved)} "
              f"for {len(changes)} user(s)", flush=True)

    def on_users_reloaded(summary):
        print(f"{directory.name} reloaded: {summary}", flush=True)
        convert_settings()
        if directory.path:
            warn_if_shared(directory.path)
        warn_unconfigured()
        check_shared_prefixes()
        if state.watch and "users" in state.watch.announced:
            state.watch.wake.set()  # so it says the file is fixed

    def on_users_error(reason):
        """A new version of the users file can't be used: say so, and keep
        the current users."""
        print(f"Warning: {directory.name} not reloaded: {reason}; keeping the current users.", flush=True)
        if state.watch:
            state.watch.wake.set()  # it tells the admins, and again when it's fixed
        else:
            tell_admins(f"{directory.name} not reloaded: {reason}", "users-file notice")

    convert_settings()
    directory.on_change.append(on_users_reloaded)
    # Watch the users file; SIGHUP (kill -HUP <pid>) reloads it straight away.
    wake = asyncio.Event()
    with contextlib.suppress(AttributeError, NotImplementedError):  # no SIGHUP on Windows
        asyncio.get_running_loop().add_signal_handler(signal.SIGHUP, wake.set)
    watcher = asyncio.create_task(directory.watch(wake, on_users_error))
    summaries = asyncio.create_task(send_summaries())
    loop = asyncio.get_running_loop()
    # When each kind of advert last went out, scheduled or by hand.
    advert_times = state.store(ADVERTS_FILE)
    # kill -USR1 <pid> sends a flood advert, for a bot running without a terminal.
    with contextlib.suppress(AttributeError, NotImplementedError):  # no SIGUSR1 on Windows
        loop.add_signal_handler(signal.SIGUSR1, lambda: in_background(send_advert(mc, True, "SIGUSR1", advert_times)))
    if advert_at_startup:
        await send_advert(mc, advert_flood, "at startup", advert_times)
    adverts = None
    if advert_every_hours:
        # So new radios learn the node; the schedule carries on across restarts.
        wait = seconds_until_advert(advert_times, advert_every_hours, advert_flood)
        print(f"Sending a {'flood' if advert_flood else 'zero-hop'} advert every {advert_every_hours:g} hour(s); "
              f"next {'now' if not wait else 'in ' + wait_text(wait)}.")
        adverts = asyncio.create_task(advert_on_schedule(mc, advert_times, advert_every_hours, advert_flood))
    auto_alerts = None
    if alert_settings.counties:
        alert_watcher = state.alert_watcher = AlertWatcher(mc, alert_settings, state)
        print(f"Watching NWS alerts for {alert_watcher.describe()}.")
        auto_alerts = asyncio.create_task(alert_watcher.run())
    alert_test = state.alert_test = AlertTest(mc, test_settings, state, alert_settings.counties)
    if problem := alert_test.problem():
        raise SystemExit(f"{problem}. Shorten it.")
    alert_tests = None
    if test_settings.weekly:
        print(f"Weekly alert test: {alert_test.describe()}.")
        alert_tests = asyncio.create_task(alert_test.run())
    backups = state.backups = Backups(backup_settings, state, args.config.resolve(), directory)
    scheduled_backups = None
    if backup_settings.every_hours:
        wait = backups.seconds_until_due()
        print(f"Backups: {backups.describe()}; next {'now' if not wait else 'in ' + wait_text(wait)}.")
        scheduled_backups = asyncio.create_task(backups.run())
    else:
        print(f"Backups: {backups.describe()}.")
    if backups.same_disk():
        print(f"Note: {backup_settings.to} is on the same disk as the bot's data; a backup on another disk "
              "(a USB stick, a second drive) survives that disk failing.")
    node_watch = None
    if watch_settings.enabled:
        def tell_watch(text):
            print(f"Watch: {text}", flush=True)
            tell_admins(text, "watch notice")

        state.watch = NodeWatch(mc, watch_settings, state, directory, tell_watch)
        print(f"Watching the node {state.watch.describe()}; problems go to {len(directory.admins)} admin(s).")
        node_watch = asyncio.create_task(state.watch.run())
    # Uses of each command by each sender, over the radio and from the web console.
    limiter = RateLimiter()
    web_console = None
    if console_settings.enabled and aiohttp_missing():
        print(f"Warning: [console] is enabled, but the web console needs aiohttp: run {INSTALL} in the project "
              "folder and restart. Running without it.")
    elif console_settings.enabled:
        from .web.server import ConsoleServer

        console_ctx = Context(name="console", directory=directory, radio=mc, commands=commands, state=state,
                              send=send_later, limits=registry.limits)
        web_console = ConsoleServer(console_settings, console_ctx, args.config.resolve().parent, limiter, output)
        if not await web_console.start():
            web_console = None
    if web_console:
        state.channel_log = ChannelLog()
        print(f"Channel messages for the web console: the newest {KEEP} of each channel, in memory only.")
    area_weather = None
    # The reports the console's Area Weather page and the area command show.
    area_command = any(isinstance(c, AreaCommand) for c in commands.values())
    if (web_console or area_command) and state.alert_watcher:
        state.area_weather = AreaWeather(state.alert_watcher, state)
        print(f"Area weather: {state.area_weather.describe()}.")
        area_weather = asyncio.create_task(state.area_weather.run())
    # After the alert watcher: area is off without one.
    warn_unconfigured()
    stop_console = watch_console(loop, lambda line: in_background(run_console_command(mc, line, advert_times)))
    if stop_console:
        print("Type help for console commands (advert, advert flood, contacts).")
    when = f"every {directory.reload_seconds}s" if directory.reload_seconds else "on reload or SIGHUP only"
    print(f"Users file: {directory.path} (checked {when}).")
    for path in (args.config.resolve(), directory.path, mailrc_path()):
        if path:
            warn_if_shared(path)
    print("Listening for direct messages (Ctrl+C to quit)...")

    def message_prefix(msg):
        """The 6-byte key prefix (12 hex chars) a direct message comes with."""
        return msg.get("pubkey_prefix", "").lower()

    async def reply(msg, sender, text):
        """Send text back to the sender of a direct message."""
        await send_dm(sender.public_key or message_prefix(msg), text)

    def contacts_with_prefix(prefix):
        return [c for c in mc.contacts.values() if prefix and c.get("public_key", "").lower().startswith(prefix)]

    reported_shared = set()  # (prefix, contacts' keys) already reported

    def check_shared_prefixes():
        """Warn (once per set of contacts) about a user's or admin's key
        prefix shared by several contacts in the radio, which leaves that
        person unable to use their rights until the impostor is removed."""
        for key in sorted(protected_keys()):
            matches = contacts_with_prefix(key[:12])
            report = (key[:12], frozenset(c["public_key"] for c in matches))
            if len(matches) < 2 or report in reported_shared:
                continue
            reported_shared.add(report)
            who = describe(key, directory.users)
            print(f"Warning: {len(matches)} contacts share {possessive(who)} key prefix {key[:12]}; {who} has no "
                  f"user or admin rights until the impostor is removed from the radio's contacts.", flush=True)
            tell_admins(f"{len(matches)} contacts share {possessive(who)} key prefix {key[:12]}: remove the impostor "
                        f"from the radio", "shared-prefix alert")

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
                print(f"  ({len(matches)} contacts share key prefix {prefix}; sender not identified)", flush=True)
                check_shared_prefixes()  # tell the admins if it's a user's or admin's prefix
            return Sender(prefix, None)
        contact = matches[0]
        sync_names([contact])
        return Sender(contact.get("adv_name") or prefix, contact["public_key"].lower())

    unsaved_names = set()  # (key, name) the users file couldn't take, so it isn't retried each message

    def sync_names(contacts):
        """Keep each user's name in the users file the same as their radio's
        name, which is what everyone on the mesh sees."""
        changes = {}
        for contact in contacts:
            key = contact.get("public_key", "").lower()
            name = contact.get("adv_name") or ""
            user = directory.users.get(key)
            if user is None or not name or user.get("name") == name or (key, name) in unsaved_names:
                continue
            if name_problem(name):  # what join would refuse
                unsaved_names.add((key, name))
                print(f"Warning: {possessive(describe(key, directory.users))} radio is now called {name!r}, "
                      f"which can't be used; keeping {describe(key, directory.users)}", flush=True)
                continue
            changes[key] = {"name": name, **user}
            changes[key]["name"] = name
        if not changes:
            return
        old = {key: describe(key, directory.users) for key in changes}
        try:
            directory.save_users(changes)
        except DirectoryError as e:
            unsaved_names.update((key, settings["name"]) for key, settings in changes.items())
            print(f"Warning: radio names not saved: {directory.name} {e}", flush=True)
            return
        for key, settings in changes.items():
            print(f"{old[key]} ({key[:12]}) is now {settings['name']}, the radio's name", flush=True)
            state.record("radio", f"{old[key]} ({key[:12]}) is now {settings['name']}")

    sync_names(mc.contacts.values())
    check_shared_prefixes()

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
        state.counts["messages"] += 1
        sender = await get_sender(msg)
        prefix = message_prefix(msg)
        label = prefix if sender.name == prefix else f"{prefix} {sender.name}"
        parsed = parse_command(msg, commands)
        # A private command's text (a message, a passphrase) is never printed.
        private = parsed is not None and parsed[0].private
        print(f"[{label}] {parsed[0].name + ' (private)' if private else msg.get('text', '')}", flush=True)
        state.saw(sender.public_key or prefix, sender.name)  # the name the node advertises, for roster
        if parsed is None:
            words = msg.get("text", "").split()
            if not words:
                return
            # Users and admins are told the nearest command they may run;
            # strangers learn nothing about the commands there are.
            if sender.public_key in directory.users or sender.public_key in directory.admins:
                mine = [c.name for c in commands.values()
                        if is_authorized(c, sender, directory.users, directory.admins)]
                nearest = nearest_command(words[0], mine, registry.disabled)
                if nearest:
                    # Only the first word is repeated: the rest may be a passphrase.
                    print(f"  -> unrecognized command; suggesting {nearest}", flush=True)
                    await reply(msg, sender, f"unknown command {words[0][:30]}; did you mean {nearest}? "
                                             "help lists yours")
                    return
            await reply_unrecognized(msg, sender, "unrecognized command")
            return
        command, text = parsed
        if not is_authorized(command, sender, directory.users, directory.admins):
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
        answer = await run_command(command, text, sender, state)
        # A long reply comes as several messages, sent in order.
        for text in answer.messages:
            await reply(msg, sender, text)
            print(f"  -> replied ({len(text)} chars)" + ("" if private else f": {text}"), flush=True)

    # Stop on SIGTERM (systemctl stop) as on Ctrl+C, or when the radio is lost
    # for good: the library's few quick reconnects failed, so exit with an
    # error and let the service manager start the bot again.
    stopping = asyncio.Event()
    lost = []
    restarting = []  # why, when a restart was asked for (radio reboot from the console)

    def restart(why):
        """Restart on purpose: stop shortly (so the command's reply gets
        out first) with an error, for the service manager to start the bot
        again. The radio dropping meanwhile is expected, not a problem."""
        if not restarting:
            restarting.append(why)
            print(f"Restarting: {why}.", flush=True)
            loop.call_later(RESTART_SECONDS, stopping.set)

    state.restart = restart

    async def on_disconnect(event):
        reason = (event.payload or {}).get("reason", "unknown")
        if restarting:
            stopping.set()
        elif reason != "manual_disconnect":
            lost.append(reason)
            print(f"Lost the radio ({reason}); stopping.", flush=True)
            if state.watch:
                state.watch.lost_radio(reason)  # told to the admins once it's back
            stopping.set()

    with contextlib.suppress(NotImplementedError):  # not on Windows
        loop.add_signal_handler(signal.SIGTERM, stopping.set)
    mc.subscribe(EventType.DISCONNECTED, on_disconnect)
    # Commands come only by direct message. Channel messages are only kept,
    # for the web console to show, and only while it's on.
    mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
    if state.channel_log:
        async def on_channel_message(event):
            state.channel_log.heard(event.payload)

        mc.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_message)
    await mc.start_auto_message_fetching()

    try:
        await stopping.wait()
    finally:
        watcher.cancel()
        summaries.cancel()
        if adverts:
            adverts.cancel()
        if auto_alerts:
            auto_alerts.cancel()
        if alert_tests:
            alert_tests.cancel()
        if node_watch:
            node_watch.cancel()
        if scheduled_backups:
            scheduled_backups.cancel()
        if area_weather:
            area_weather.cancel()
        if stop_console:
            stop_console()
        if web_console:
            await web_console.stop()
        with contextlib.suppress(AttributeError, NotImplementedError):
            loop.remove_signal_handler(signal.SIGHUP)
            loop.remove_signal_handler(signal.SIGUSR1)
            loop.remove_signal_handler(signal.SIGTERM)
        # A lost radio may not answer; don't hang on it, and disconnect even
        # if it didn't stop fetching.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(mc.stop_auto_message_fetching(), DISCONNECT_SECONDS)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(mc.disconnect(), DISCONNECT_SECONDS)
    if lost or restarting:
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
