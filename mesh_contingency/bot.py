"""Listen to a MeshCore companion device over USB serial and act on direct messages.

Channel messages are ignored entirely.
"""

import argparse
import asyncio
import glob
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
from .contacts import load_auto_add, load_notify_admins, setup_auto_add
from .registry import Registry, load_admins, load_users

# config.toml in the project folder (the parent of this package).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"

# Sent for unknown commands and for commands the sender may not run.
UNRECOGNIZED_REPLY = "unrecognized user or function"
# Send UNRECOGNIZED_REPLY to the same sender at most once per this many
# seconds, so another auto-replying node can't trap us in a reply loop.
UNRECOGNIZED_COOLDOWN = 300


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
    users = load_users(config)
    admins = load_admins(config)
    auto_add = load_auto_add(config)
    notify_admins = load_notify_admins(config)
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

    async def send_dm(prefix, text, what="reply"):
        """Send a direct message to a contact by pubkey prefix, retrying until
        the radio reports an ack, and log whether it was delivered."""
        if len(text) > MAX_REPLY_LEN:
            # Error text can echo the sender's input; never exceed the mesh limit.
            text = text[: MAX_REPLY_LEN - 3] + "..."
        contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            # The radio may have learned this node after we loaded contacts.
            await mc.commands.get_contacts()
            contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            print(f"  (no contact {prefix} to send {what} to; is it in the radio's contacts?)", flush=True)
            return
        async with send_lock:
            result = await mc.commands.send_msg_with_retry(contact, text)
        if result is None:
            print(f"  ({what} to {prefix} not acknowledged after retries)", flush=True)
        else:
            print(f"  ({what} to {prefix} delivered)", flush=True)

    background = set()  # running notice tasks, kept so they aren't garbage collected

    def announce_new_contact(key, name, type_name):
        """Tell every admin about a contact the bot just added, without
        holding up the radio's event handling while the messages go out."""
        text = f"New contact: {name or '?'} ({key}, {type_name})"
        for admin in sorted(admins):
            task = asyncio.create_task(send_dm(admin, text, what="new-contact notice"))
            background.add(task)
            task.add_done_callback(background.discard)

    if auto_add is not None:
        await setup_auto_add(mc, auto_add, on_added=announce_new_contact if notify_admins else None)
        if notify_admins and admins:
            print(f"New contacts are announced to {len(admins)} admin(s).")

    commands = registry.build(users, admins, mc)
    for level, who in [(PUBLIC, "anyone"), (USER, f"{len(users)} user(s)"), (ADMIN, f"{len(admins)} admin(s)")]:
        names = [c.name for c in commands.values() if c.permission == level]
        print(f"  {level} commands ({who}): {', '.join(names) or 'none'}")
    print(f"  {DISABLED} commands (nobody): {', '.join(registry.disabled) or 'none'}")
    for warning in registry.warnings:
        print(f"Warning: {warning}")
    for command in commands.values():
        if not command.enabled and command.permission != DISABLED:
            print(f"Warning: no user has {command.name} addresses in {args.config}; "
                  f"{command.name} command disabled.")
    print("Listening for direct messages (Ctrl+C to quit)...")

    async def reply(msg, text):
        """Send text back to the sender of a direct message."""
        await send_dm(msg.get("pubkey_prefix", ""), text)

    def get_sender(msg):
        """Return the Sender of a direct message."""
        prefix = msg.get("pubkey_prefix", "").lower()
        contact = mc.get_contact_by_key_prefix(prefix)
        return Sender((contact or {}).get("adv_name") or prefix, prefix)

    last_unrecognized = {}  # sender -> time.monotonic() of the last UNRECOGNIZED_REPLY

    async def reply_unrecognized(msg, sender, why):
        """Send UNRECOGNIZED_REPLY unless this sender got one recently."""
        now = time.monotonic()
        if now - last_unrecognized.get(sender.key, -UNRECOGNIZED_COOLDOWN) < UNRECOGNIZED_COOLDOWN:
            print(f"  -> {why}; not replying (replied within {UNRECOGNIZED_COOLDOWN}s)", flush=True)
            return
        last_unrecognized[sender.key] = now
        print(f"  -> {why}; sending unrecognized reply", flush=True)
        await reply(msg, UNRECOGNIZED_REPLY)

    async def on_message(event):
        msg = event.payload
        sender = get_sender(msg)
        label = sender.key if sender.name == sender.key else f"{sender.key} {sender.name}"
        print(f"[{label}] {msg.get('text', '')}", flush=True)
        parsed = parse_command(msg, commands)
        if parsed is None:
            if msg.get("text", "").strip():
                await reply_unrecognized(msg, sender, "unrecognized command")
            return
        command, text = parsed
        if not is_authorized(command, sender, users, admins):
            await reply_unrecognized(msg, sender, f"{command.name} denied: sender not approved")
            return
        print(f"  -> running {command.name} {text}".rstrip(), flush=True)
        try:
            result = await asyncio.wait_for(command.execute(text, sender), command.timeout)
        except TimeoutError:
            print(f"  {command.name} timed out after {command.timeout}s", flush=True)
            await reply(msg, f"{command.name}: timed out")
            return
        except CommandError as e:
            print(f"  {e}", flush=True)
            await reply(msg, str(e))
            return
        except Exception as e:
            print(f"  {command.name} failed: {e}", flush=True)
            await reply(msg, f"{command.name}: failed")
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
            await reply(msg, text)
            print(f"  -> replied ({len(text)} chars): {text}", flush=True)

    # Only direct messages; channel messages are never subscribed to.
    mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
    await mc.start_auto_message_fetching()

    try:
        await asyncio.Event().wait()
    finally:
        await mc.stop_auto_message_fetching()
        await mc.disconnect()


def run():
    """Entry point for the mesh-contingency command."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
