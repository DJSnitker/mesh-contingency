"""Post National Weather Service alerts to MeshCore's Public channel, and
answer the admins' direct-message commands, through a companion radio on USB.

Channel messages are ignored; commands come only by direct message.
"""

import argparse
import asyncio
import contextlib
import glob
import signal
import sys
import time
from pathlib import Path

from mesh_commands import DISABLED, LEVELS, CommandError, Dispatcher, KeyRoles, MeshLink, describe_rate
from mesh_commands.limits import wait_text
from mesh_commands.output import SafeOutput
from meshcore import EventType, MeshCore

from .alerts import AlertTest, AlertWatcher, load_alert_test, load_alerts
from .config import load_admins, load_commands, load_config, retired_settings
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
from .state import State, duration

# config.toml in the project folder (the parent of this package).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
# How long to wait for the radio when shutting down.
DISCONNECT_SECONDS = 5
# How long to wait for the radio to answer a question at startup.
RADIO_SECONDS = 5
# The radio's clock this far off the computer's (seconds) is set at startup.
CLOCK_SLACK = 5

def find_serial_port():
    """Return the first likely USB serial port, or None."""
    candidates = sorted(glob.glob("/dev/serial/by-id/*")) + sorted(
        glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    )
    return candidates[0] if candidates else None


async def ask_radio(request, wanted, seconds=RADIO_SECONDS):
    """The payload of the radio's answer to request() if it is of type
    wanted, or None if it answered otherwise or not in time."""
    try:
        res = await asyncio.wait_for(request(), seconds)
    except Exception:
        return None
    return res.payload if res is not None and res.type == wanted else None


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
    registry = load_commands(config)
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

    roles = KeyRoles(admins=admins)
    link = MeshLink(mc, roles)  # sends direct messages, one at a time, and says who sent each one

    # The state files (the alerts posted, the advert times), next to config.toml.
    state = State(args.config.resolve().parent)
    commands = registry.build(mc, roles, link.send_later, extras={"state": state})
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
        loop.add_signal_handler(signal.SIGUSR1,
                                lambda: link.in_background(send_advert(mc, True, "SIGUSR1", advert_times)))
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
    stop_console = watch_console(loop, lambda line: link.in_background(run_console_command(mc, line, advert_times)))
    if stop_console:
        print("Type help for console commands (advert, advert flood, contacts).")
    warn_if_shared(args.config.resolve())
    print("Listening for direct messages (Ctrl+C to quit)...")

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
    link.listen(Dispatcher(commands, roles, link.send, registry.disabled))
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
