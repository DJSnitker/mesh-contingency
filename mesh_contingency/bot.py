"""Listen to a MeshCore companion device over USB serial and act on direct messages.

Channel messages are ignored entirely (the alert command only posts to one).
"""

import argparse
import asyncio
import contextlib
import glob
import signal
import time
import tomllib
from pathlib import Path

from meshcore import EventType, MeshCore

from .api import (
    ADMIN,
    DISABLED,
    MAX_REPLY_LEN,
    PUBLIC,
    USER,
    CommandError,
    CommandResult,
    Sender,
    is_authorized,
    to_messages,
)
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
from .directory import Directory, describe, possessive
from .limits import RateLimiter, describe_rate, wait_text
from .registry import Registry
from .state import State

# config.toml in the project folder (the parent of this package).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
# How long to wait for the radio when shutting down.
DISCONNECT_SECONDS = 5

# Sent for unknown commands and for commands the sender may not run.
UNRECOGNIZED_REPLY = "unrecognized user or function"
# Send UNRECOGNIZED_REPLY to the same sender at most once per this many
# seconds, so another auto-replying node can't trap us in a reply loop.
UNRECOGNIZED_COOLDOWN = 300
# How often to check whether an hourly new-contact summary is due.
SUMMARY_CHECK_SECONDS = 60


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


async def main():
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
                print(f"Warning: no user has {command.name} addresses in {directory.name}.", flush=True)

    def on_users_reloaded(summary):
        print(f"{directory.name} reloaded: {summary}", flush=True)
        warn_unconfigured()
        check_shared_prefixes()

    def on_users_error(reason):
        """A new version of the users file can't be used: say so, and keep
        the current users."""
        print(f"Warning: {directory.name} not reloaded: {reason}; keeping the current users.", flush=True)
        tell_admins(f"{directory.name} not reloaded: {reason}", "users-file notice")

    warn_unconfigured()
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
    stop_console = watch_console(loop, lambda line: in_background(run_console_command(mc, line, advert_times)))
    if stop_console:
        print("Type help for console commands (advert, advert flood, contacts).")
    when = f"every {directory.reload_seconds}s" if directory.reload_seconds else "on reload or SIGHUP only"
    print(f"Users file: {directory.path} (checked {when}).")
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
        return Sender(contact.get("adv_name") or prefix, contact["public_key"].lower())

    check_shared_prefixes()

    last_unrecognized = {}  # key prefix -> time.monotonic() of the last UNRECOGNIZED_REPLY
    limiter = RateLimiter()

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
        # A private command's text (a message, a passphrase) is never printed.
        private = parsed is not None and parsed[0].private
        print(f"[{label}] {parsed[0].name + ' (private)' if private else msg.get('text', '')}", flush=True)
        state.saw(sender.public_key or prefix, sender.name)  # the name the node advertises, for roster
        if parsed is None:
            if msg.get("text", "").strip():
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
        print(f"  -> running {command.name} {'' if private else text}".rstrip(), flush=True)
        try:
            result = await asyncio.wait_for(command.execute(text, sender), command.timeout)
        except TimeoutError:
            print(f"  {command.name} timed out after {command.timeout}s", flush=True)
            await reply(msg, sender, f"{command.name}: timed out")
            return
        except CommandError as e:
            print(f"  {command.name}: refused" if private else f"  {e}", flush=True)
            await reply(msg, sender, str(e))
            return
        except Exception as e:
            print(f"  {command.name} failed: {type(e).__name__ if private else e}", flush=True)
            await reply(msg, sender, f"{command.name}: failed")
            return
        if not isinstance(result, CommandResult):
            # Function commands may return just the reply.
            result = CommandResult(console=result if isinstance(result, str) else "", reply=result)
        if result.console:
            print(result.console, flush=True)
        messages = to_messages(result.reply)
        if not messages:
            print("  -> no reply", flush=True)
        # A long reply comes as several messages, sent in order.
        for text in messages:
            await reply(msg, sender, text)
            print(f"  -> replied ({len(text)} chars)" + ("" if private else f": {text}"), flush=True)

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
    # Only direct messages; channel messages are never subscribed to.
    mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
    await mc.start_auto_message_fetching()

    try:
        await stopping.wait()
    finally:
        watcher.cancel()
        summaries.cancel()
        if adverts:
            adverts.cancel()
        if stop_console:
            stop_console()
        with contextlib.suppress(AttributeError, NotImplementedError):
            loop.remove_signal_handler(signal.SIGHUP)
            loop.remove_signal_handler(signal.SIGUSR1)
            loop.remove_signal_handler(signal.SIGTERM)
        # A lost radio may not answer; don't hang on it.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(mc.stop_auto_message_fetching(), DISCONNECT_SECONDS)
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
