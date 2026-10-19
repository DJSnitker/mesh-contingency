#!/usr/bin/env python3
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

from commands import ADMIN, PUBLIC, USER, CommandError, Sender, build_commands, load_admins, load_users
from commands.base import MAX_REPLY_LEN
from contacts import load_auto_add, setup_auto_add

DEFAULT_CONFIG = Path(__file__).with_name("config.toml")

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


def is_authorized(command, sender, users, admins):
    """Return True if the sender may run the command."""
    if command.permission == PUBLIC:
        return True
    if command.permission == USER:
        return sender.key in users
    if command.permission == ADMIN:
        return sender.key in admins
    return False


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--port", help="serial port (auto-detected if omitted)")
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument("--debug", action="store_true", help="verbose library logging")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"config file (default: {DEFAULT_CONFIG.name})")
    args = parser.parse_args()

    config = load_config(args.config)
    users = load_users(config)
    admins = load_admins(config)
    auto_add = load_auto_add(config)

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
    if auto_add is not None:
        await setup_auto_add(mc, auto_add)

    commands = build_commands(config, mc)
    for level, who in [(PUBLIC, "anyone"), (USER, f"{len(users)} user(s)"), (ADMIN, f"{len(admins)} admin(s)")]:
        names = [c.name for c in commands.values() if c.permission == level]
        print(f"  {level} commands ({who}): {', '.join(names) or 'none'}")
    for command in commands.values():
        if not command.enabled:
            print(f"Warning: no user has {command.name} addresses in {args.config}; "
                  f"{command.name} command disabled.")
    print("Listening for direct messages (Ctrl+C to quit)...")

    async def reply(msg, text):
        """Send text back to the sender of a direct message, retrying until the
        radio reports an ack, and log whether it was delivered."""
        if len(text) > MAX_REPLY_LEN:
            # Error text can echo the sender's input; never exceed the mesh limit.
            text = text[: MAX_REPLY_LEN - 3] + "..."
        prefix = msg.get("pubkey_prefix", "")
        contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            # The radio may have learned this node after we loaded contacts.
            await mc.commands.get_contacts()
            contact = mc.get_contact_by_key_prefix(prefix)
        if contact is None:
            print(f"  (no contact {prefix} to reply to; is the sender in the radio's contacts?)", flush=True)
            return
        result = await mc.commands.send_msg_with_retry(contact, text)
        if result is None:
            print(f"  (reply to {prefix} not acknowledged after retries)", flush=True)
        else:
            print(f"  (reply to {prefix} delivered)", flush=True)

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
            result = await command.execute(text, sender)
        except CommandError as e:
            print(f"  {e}", flush=True)
            await reply(msg, str(e))
            return
        except Exception as e:
            print(f"  {command.name} failed: {e}", flush=True)
            await reply(msg, f"{command.name}: failed")
            return
        print(result.console, flush=True)
        await reply(msg, result.reply)
        print(f"  -> replied ({len(result.reply)} chars): {result.reply}", flush=True)

    # Only direct messages; channel messages are never subscribed to.
    mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
    await mc.start_auto_message_fetching()

    try:
        await asyncio.Event().wait()
    finally:
        await mc.stop_auto_message_fetching()
        await mc.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
