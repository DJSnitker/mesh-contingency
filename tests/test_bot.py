import asyncio
import contextlib
import hashlib
import io
import json
import os
import signal
import socket
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from meshcore import EventType

from mesh_contingency import bot
from mesh_contingency.api import (
    ADMIN,
    DISABLED,
    MAX_PARTS,
    MAX_REPLY_LEN,
    PUBLIC,
    USER,
    Command,
    CommandResult,
    Sender,
    split_reply,
)
from mesh_contingency.commands.mail import NO_INTERNET, SendError
from mesh_contingency.state import State
from mesh_contingency.testing import FakeMeshCore, event, full_key, make_contact
from mesh_contingency.web import aiohttp_missing


async def echo(text, sender, ctx):
    """A plugin command for the tests: replies with its text, or nothing."""
    return f"{ctx.options.get('prefix', '')}{text}" if text else None


async def slow(text, sender, ctx):
    await asyncio.sleep(10)


class BrokenStart(Command):
    """A plugin command whose startup fails."""

    async def start(self):
        raise RuntimeError("radio said no")

    async def execute(self, text, sender):
        return "still works"


# Key prefixes, as direct messages carry them; the config holds full_key(prefix).
DANA = "d0d0d0d0d0d0"  # user
ADMIN_KEY = "adadadadadad"  # admin only
STRANGER = "ffeeddccbbaa"  # in contacts, but neither user nor admin

CONFIG = """
# Backups next to the test's config, and only when asked.
[backup]
to = "test-backups"
every_hours = 0

[commands]
help = { permission = "public" }
wx = { permission = "public" }
verse = { permission = "public" }
qm = { permission = "user" }
emailall = { permission = "user" }
email = { permission = "user" }
advert = { permission = "admin" }
contacts = { permission = "admin" }
contact = { permission = "admin" }
radio = { permission = "admin" }
reload = { permission = "admin" }
ok = { permission = "public" }
status = { permission = "public" }
clearstatus = { permission = "admin" }
checkins = { permission = "admin" }
roster = { permission = "user" }
health = { permission = "admin" }
history = { permission = "admin" }
msg = { permission = "user" }
inbox = { permission = "user" }
clearinbox = { permission = "user" }
setpass = { permission = "user" }
alert = { permission = "admin" }
alertmap = { permission = "admin" }
testalert = { permission = "admin" }
comm = { permission = "admin" }
backup = { permission = "admin" }
join = { permission = "public" }
approve = { permission = "admin" }
deny = { permission = "admin" }
setqm = { permission = "user" }
addgroup = { permission = "user" }
cleargroup = { permission = "user" }
users = { permission = "admin" }
whois = { permission = "admin" }
remove = { permission = "admin" }
resetpass = { permission = "admin" }
whoami = { permission = "user" }
leave = { permission = "user" }
"""

USERS = f"""
[admin]
keys = ["{full_key(ADMIN_KEY)}"]

[users.{full_key(DANA)}]
name = "Dana"
qm = "partner@example.com"
"""


class FindSerialPortTest(unittest.TestCase):
    def test_prefers_by_id_then_sorted_tty(self):
        ports = {"/dev/serial/by-id/*": ["/dev/serial/by-id/usb-radio"],
                 "/dev/ttyACM*": ["/dev/ttyACM1"], "/dev/ttyUSB*": ["/dev/ttyUSB0"]}
        with mock.patch("mesh_contingency.bot.glob.glob", side_effect=lambda p: ports[p]):
            self.assertEqual(bot.find_serial_port(), "/dev/serial/by-id/usb-radio")
        ports["/dev/serial/by-id/*"] = []
        with mock.patch("mesh_contingency.bot.glob.glob", side_effect=lambda p: ports[p]):
            self.assertEqual(bot.find_serial_port(), "/dev/ttyACM1")

    def test_none_found(self):
        with mock.patch("mesh_contingency.bot.glob.glob", return_value=[]):
            self.assertIsNone(bot.find_serial_port())


class LoadConfigTest(unittest.TestCase):
    def test_parses_toml(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[admin]\nkeys = ["abc"]\n')
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(bot.load_config(f.name), {"admin": {"keys": ["abc"]}})

    def test_missing_file_is_empty_config(self):
        self.assertEqual(bot.load_config("/nonexistent/config.toml"), {})


class IsAuthorizedTest(unittest.TestCase):
    def check(self, permission, key):
        command = SimpleNamespace(permission=permission)
        return bot.is_authorized(command, Sender("x", full_key(key)),
                                 users={full_key(DANA): {}}, admins={full_key(ADMIN_KEY)})

    def test_matrix(self):
        self.assertTrue(self.check(PUBLIC, STRANGER))
        self.assertTrue(self.check(USER, DANA))
        self.assertFalse(self.check(USER, ADMIN_KEY))  # admin is not automatically a user
        self.assertFalse(self.check(USER, STRANGER))
        self.assertTrue(self.check(ADMIN, ADMIN_KEY))
        self.assertFalse(self.check(ADMIN, DANA))
        self.assertFalse(self.check(DISABLED, ADMIN_KEY))
        self.assertFalse(self.check(DISABLED, DANA))
        self.assertFalse(self.check("unknown-level", DANA))


class RunTest(unittest.TestCase):
    def test_runs_main(self):
        with mock.patch("mesh_contingency.bot.main", mock.AsyncMock(return_value=0)) as main:
            bot.run()
        main.assert_awaited_once()

    def test_a_lost_radio_exits_with_an_error(self):
        with mock.patch("mesh_contingency.bot.main", mock.AsyncMock(return_value=1)):
            with self.assertRaises(SystemExit) as stopped:
                bot.run()
        self.assertEqual(stopped.exception.code, 1)

    def test_ctrl_c_stops_cleanly(self):
        out = io.StringIO()
        with mock.patch("mesh_contingency.bot.main", mock.AsyncMock(side_effect=KeyboardInterrupt)), \
                contextlib.redirect_stdout(out):
            bot.run()
        self.assertIn("Stopped.", out.getvalue())

    def test_startup_errors_still_exit(self):
        with mock.patch("mesh_contingency.bot.main", mock.AsyncMock(side_effect=SystemExit("No serial device"))):
            with self.assertRaisesRegex(SystemExit, "No serial device"):
                bot.run()


class ParseCommandTest(unittest.TestCase):
    COMMANDS = {"wx": "WX", "email": "NE"}

    def parse(self, text):
        return bot.parse_command({"text": text}, self.COMMANDS)

    def test_name_and_text(self):
        self.assertEqual(self.parse("wx 10001"), ("WX", "10001"))
        self.assertEqual(self.parse("  WX   10001  "), ("WX", "10001"))
        self.assertEqual(self.parse("wx"), ("WX", ""))

    def test_text_keeps_inner_spacing(self):
        self.assertEqual(self.parse("email a@b.com  two  spaces"), ("NE", "a@b.com  two  spaces"))
        self.assertEqual(self.parse("email line1\nline2"), ("NE", "line1\nline2"))

    def test_not_a_command(self):
        for text in ("", "   ", "hello", "wxx 10001", "alert hi"):
            self.assertIsNone(self.parse(text), text)
        self.assertIsNone(bot.parse_command({}, self.COMMANDS))


class NearestCommandTest(unittest.TestCase):
    NAMES = ["help", "inbox", "qm", "setqm", "resetpass", "setpass", "checkins", "alert", "advert", "health"]

    def test_close(self):
        for word, expected in [("hlep", "help"), ("INBOX", "inbox"), ("resetpassword", "resetpass"),
                               ("checkin", "checkins"), ("adver", "advert"), ("hello", None), ("weather", None),
                               ("x", None)]:
            self.assertEqual(bot.nearest_command(word, self.NAMES), expected, word)

    def test_renamed(self):
        self.assertEqual(bot.nearest_command("quickim", self.NAMES), "qm")
        self.assertEqual(bot.nearest_command("setquickim", self.NAMES), "setqm")
        self.assertIsNone(bot.nearest_command("quickim", ["help"]))  # qm not theirs

    def test_a_disabled_command_is_not_a_typo(self):
        self.assertIsNone(bot.nearest_command("advert", ["alert"], disabled=["advert"]))

    def test_our_own_reply_is_not_a_command(self):
        # A node that echoes our replies back can't start a loop.
        self.assertIsNone(bot.nearest_command("unknown", self.NAMES))
        self.assertIsNone(bot.nearest_command(bot.UNRECOGNIZED_REPLY.split()[0], self.NAMES))


class MainTest(unittest.IsolatedAsyncioTestCase):
    """Runs bot.main() against a fake radio and drives it with messages."""

    async def start(self, config=CONFIG, contacts=None, argv=None, radio=None, users=USERS, config_file=None):
        """Start the bot with config.toml and users.toml (if users isn't None)
        in a temporary folder, or with config_file from write_files."""
        self.radio = radio or FakeMeshCore(contacts if contacts is not None else
                                           {DANA: "Dana", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        config_file = config_file or self.write_files(config, users)

        self.clock = 1000.0
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.enterContext(mock.patch("mesh_contingency.bot.time",
                                     SimpleNamespace(monotonic=lambda: self.clock, time=time.time)))
        self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial",
                                     mock.AsyncMock(return_value=self.radio)))
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", str(config_file)]
                                     + (argv or [])))

        self.task = asyncio.create_task(bot.main())
        listening = asyncio.create_task(self.radio.listening.wait())
        await asyncio.wait({self.task, listening}, return_when=asyncio.FIRST_COMPLETED)
        listening.cancel()
        if self.task.done():
            self.task.result()  # re-raise a startup failure
        self.addAsyncCleanup(self.stop)

    def write_files(self, config, users):
        """Write config.toml and users.toml (unless users is None) to a
        temporary folder and return the config's path."""
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        config_file = folder / "config.toml"
        config_file.write_text(config)
        config_file.chmod(0o600)
        self.users_file = folder / "users.toml"
        if users is not None:
            self.users_file.write_text(users)
            self.users_file.chmod(0o600)
        # Not the real ~/.mailrc
        self.mailrc = folder / ".mailrc"
        self.enterContext(mock.patch.dict("os.environ", {"MAILRC": str(self.mailrc)}))
        return config_file

    async def main_exits(self, config, users, error):
        """Check bot.main() stops with this error before connecting."""
        config_file = self.write_files(config, users)
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", str(config_file)]))
        connect = self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial", mock.AsyncMock()))
        with self.assertRaisesRegex(SystemExit, error):
            await bot.main()
        connect.assert_not_called()

    async def stop(self):
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task

    def replies(self):
        return [text for _, text in self.radio.sent]

    # --- startup and shutdown

    async def test_channel_messages_only_with_the_web_console(self):
        await self.start()
        self.assertNotIn(EventType.CHANNEL_MSG_RECV, self.radio.handlers)
        await self.stop()

    @unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp")
    async def test_channel_messages_kept_for_the_web_console(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        state = {}
        real_state = bot.State

        def keep(*args, **kwargs):
            state["it"] = real_state(*args, **kwargs)
            return state["it"]

        self.enterContext(mock.patch("mesh_contingency.bot.State", keep))
        await self.start(CONFIG + f"\n[console]\nenabled = true\nport = {port}\n")
        self.assertIn("Channel messages for the web console: the newest 200 of each channel, in memory only.",
                      self.out.getvalue())
        await self.radio.deliver(EventType.CHANNEL_MSG_RECV, {"channel_idx": 0, "text": "Alice: hello", "path_len": 1})
        self.assertEqual([(m["sender"], m["text"]) for m in state["it"].channel_log.messages(0)], [("Alice", "hello")])
        # Not taken as a command, nor answered.
        self.assertEqual(self.replies(), [])

    async def test_a_right_clock_is_left_alone(self):
        await self.start()
        self.assertEqual([c for c, _ in self.radio.settings_calls], [])
        self.assertNotIn("radio's clock", self.out.getvalue())

    async def test_the_radios_clock_is_set_at_startup(self):
        radio = FakeMeshCore({DANA: "Dana", ADMIN_KEY: "Admin"})
        radio.clock = time.time() - 4 * 3600 - 125  # after a reboot: it keeps no time
        await self.start(radio=radio)
        [(call, (when,))] = self.radio.settings_calls
        self.assertEqual(call, "set_time")
        self.assertAlmostEqual(when, time.time(), delta=5)
        self.assertIn("Set the radio's clock from the computer's: it was 4h 2m behind.\n", self.out.getvalue())

    async def test_a_clock_the_radio_wont_take_is_a_warning(self):
        radio = FakeMeshCore({DANA: "Dana", ADMIN_KEY: "Admin"})
        radio.clock = 1000.0
        radio.settings_result = event(EventType.ERROR, {})
        await self.start(radio=radio)
        self.assertIn("Warning: couldn't set the radio's clock; set it from the web console (radio clock).\n",
                      self.out.getvalue())
        self.assertFalse(self.task.done())  # it runs on

    async def test_startup(self):
        await self.start()
        # No channel messages
        self.assertEqual(set(self.radio.handlers), {EventType.CONTACT_MSG_RECV, EventType.DISCONNECTED})
        self.assertTrue(self.radio.auto_update_contacts)
        out = self.out.getvalue()
        self.assertIn("public commands (anyone): help, wx, verse, ok, status, join\n", out)
        self.assertIn("user commands (1 user(s)): qm, emailall, email, roster, msg, inbox, clearinbox, "
                      "setpass, setqm, addgroup, cleargroup, whoami, leave\n", out)
        self.assertIn("admin commands (1 admin(s)): advert, contacts, contact, radio, reload, clearstatus, checkins, "
                      "health, history, alert, alertmap, testalert, comm, backup, approve, deny, users, whois, "
                      "remove, resetpass\n", out)
        self.assertIn("Rate limits per sender and command: public 10/hour, user 30/hour, admin none", out)
        self.assertIn("disabled commands (nobody): none", out)
        self.assertIn("Warning: no user has emailall addresses in users.toml.", out)
        self.assertNotIn("no user has qm addresses", out)
        self.assertIn(f"Users file: {self.users_file} (checked every 5s).", out)
        self.assertEqual(self.radio.manual_add_calls, [])  # no [contacts] section

    async def test_alert_channel_added_at_startup(self):
        await self.start()
        self.assertEqual(self.radio.channels[1][0], "#contingency-wx")
        self.assertIn("alert: #contingency-wx is channel slot 1 (added to the radio).", self.out.getvalue())

    async def test_comm_channel_added_at_startup(self):
        await self.start()
        self.assertEqual(self.radio.channels[2][0], "#contingency-comm")
        self.assertIn("comm: #contingency-comm is channel slot 2 (added to the radio).", self.out.getvalue())

    async def test_alert_channel_already_on_the_radio(self):
        radio = FakeMeshCore({DANA: "Dana", ADMIN_KEY: "Admin"})
        radio.channels[3] = ("#contingency-wx", hashlib.sha256(b"#contingency-wx").digest()[:16])
        await self.start(radio=radio)
        self.assertIn("alert: #contingency-wx is channel slot 3.", self.out.getvalue())
        self.assertEqual([name for name, _ in radio.channels].count("#contingency-wx"), 1)

    async def test_no_channel_slot_is_a_warning_not_a_stop(self):
        radio = FakeMeshCore({DANA: "Dana", ADMIN_KEY: "Admin"})
        radio.channels[1:] = [(f"ch{i}", bytes([i]) * 16) for i in range(1, 8)]
        await self.start(radio=radio)
        self.assertIn("Warning: alert: no free channel slot on the radio for #contingency-wx", self.out.getvalue())
        self.assertIn("Listening for direct messages", self.out.getvalue())

    async def test_alert_disabled_leaves_channels_alone(self):
        await self.start(CONFIG.replace('alert = { permission = "admin" }', 'alert = { permission = "disabled" }'))
        self.assertNotIn("#contingency-wx", [name for name, _ in self.radio.channels])

    async def test_failed_start_is_a_warning(self):
        await self.start(CONFIG + '[commands.broken]\nhandler = "tests.test_bot:BrokenStart"\npermission = "public"\n')
        self.assertIn("Warning: broken could not get ready: radio said no", self.out.getvalue())
        await self.radio.dm(STRANGER, "broken")
        self.assertEqual(self.replies(), ["still works"])

    async def test_contacts_section_enables_auto_add(self):
        await self.start(CONFIG + '\n[contacts]\nauto_add = ["chat"]\n')
        self.assertEqual(self.radio.manual_add_calls, [True])
        self.assertIn(EventType.NEW_CONTACT, self.radio.handlers)

    async def test_commands_missing_from_config_are_disabled(self):
        config = (CONFIG.replace('advert = { permission = "admin" }\n', "")
                  .replace('emailall = { permission = "user" }', 'emailall = { permission = "disabled" }'))
        await self.start(config)
        out = self.out.getvalue()
        self.assertIn("disabled commands (nobody): emailall, advert", out)
        self.assertIn("Warning: advert has no [commands.advert] section; disabled.", out)
        # Disabled anyway, so no second warning about missing addresses.
        self.assertNotIn("no user has emailall addresses", out)
        await self.radio.dm(ADMIN_KEY, "advert")
        self.assertEqual(self.radio.adverts, [])
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])
        self.assertIn("unrecognized command; sending unrecognized reply", self.out.getvalue())

    async def test_permission_changed_in_config(self):
        await self.start(CONFIG.replace('advert = { permission = "admin" }', 'advert = { permission = "public" }'))
        await self.radio.dm(STRANGER, "advert")
        self.assertEqual(self.radio.adverts, [False])

    async def test_bad_permissions_stop_startup_before_connecting(self):
        await self.main_exits(CONFIG.replace('wx = { permission = "public" }', 'wx = { permission = "everyone" }'),
                              USERS, r"\[commands.wx\] has unknown permission 'everyone'")

    # --- new contacts announced to admins

    AUTO_ADD = '\n[contacts]\nauto_add = ["chat"]\n'

    async def settle(self):
        """Let background notice tasks finish."""
        for _ in range(10):
            await asyncio.sleep(0)

    async def test_new_contact_announced_to_admins(self):
        await self.start(CONFIG + self.AUTO_ADD)
        self.assertIn("New contacts are announced to 1 admin(s).", self.out.getvalue())
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact("a1a1a1a1a1a1", "Alice", 1))
        await self.settle()
        self.assertEqual(self.radio.sent, [("Admin", "New contact: Alice (a1a1a1a1a1a1, chat)")])
        self.assertIn(f"(new-contact notice to {ADMIN_KEY} delivered)", self.out.getvalue())

    async def test_every_admin_told_once(self):
        users = USERS.replace(f'keys = ["{full_key(ADMIN_KEY)}"]',
                              f'keys = ["{full_key(ADMIN_KEY)}", "{full_key(DANA)}"]')
        await self.start(CONFIG + self.AUTO_ADD, users=users)
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact("a1a1a1a1a1a1", "", 1))
        await self.settle()
        self.assertEqual(sorted(self.radio.sent), [("Admin", "New contact: ? (a1a1a1a1a1a1, chat)"),
                                                   ("Dana", "New contact: ? (a1a1a1a1a1a1, chat)")])

    async def test_skipped_node_not_announced(self):
        await self.start(CONFIG + self.AUTO_ADD)
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact("b2b2b2b2b2b2", "Hilltop", 2))
        await self.settle()
        self.assertEqual(self.radio.sent, [])

    async def test_announcements_can_be_turned_off(self):
        await self.start(CONFIG + self.AUTO_ADD + "notify_admins = false\n")
        self.assertNotIn("announced", self.out.getvalue())
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact("a1a1a1a1a1a1", "Alice", 1))
        await self.settle()
        self.assertEqual(self.radio.added[0]["adv_name"], "Alice")  # still added
        self.assertEqual(self.radio.sent, [])

    async def test_admin_not_in_contacts(self):
        await self.start(CONFIG + self.AUTO_ADD, contacts={DANA: "Dana"})
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact("a1a1a1a1a1a1", "Alice", 1))
        await self.settle()
        self.assertEqual(self.radio.sent, [])
        self.assertIn(f"(no contact {ADMIN_KEY} to send new-contact notice to", self.out.getvalue())

    async def test_lookalike_blocked_and_admins_told(self):
        await self.start(CONFIG + self.AUTO_ADD + "notify_admins = false\n")  # alerts are sent anyway
        await self.radio.deliver(EventType.NEW_CONTACT, make_contact(DANA + "11" * 26, "Dana", 1))
        await self.settle()
        self.assertEqual(self.radio.added, [])
        self.assertEqual(self.radio.sent, [
            ("Admin", "Blocked d0d0d0d0d0d0 Dana: posing as Dana (same key prefix, different key)")])

    async def test_messages_never_overlap(self):
        await self.start(CONFIG + self.AUTO_ADD)
        active, peak = 0, 0
        original = self.radio.commands.send_msg_with_retry

        async def slow_send(contact, text):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return await original(contact, text)

        self.radio.commands.send_msg_with_retry = slow_send
        for key in ("a1a1a1a1a1a1", "a2a2a2a2a2a2", "a3a3a3a3a3a3"):
            await self.radio.deliver(EventType.NEW_CONTACT, make_contact(key, "N", 1))
        await self.radio.dm(STRANGER, "hello")  # a reply while notices are going out
        while len(self.radio.sent) < 4:
            await asyncio.sleep(0.01)
        self.assertEqual(peak, 1)

    async def test_shutdown_disconnects(self):
        await self.start()
        await self.stop()
        self.assertTrue(self.radio.disconnected)

    async def test_no_serial_port(self):
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-c", "/nonexistent.toml"]))
        self.enterContext(mock.patch("mesh_contingency.bot.find_serial_port", return_value=None))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        with self.assertRaisesRegex(SystemExit, "No serial device found"):
            await bot.main()

    async def test_connect_failure(self):
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", "/nonexistent.toml"]))
        self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial", mock.AsyncMock(return_value=None)))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        with self.assertRaisesRegex(SystemExit, "Could not connect"):
            await bot.main()

    # --- the users file, reloaded while running

    FAST_RELOAD = "\n[directory]\nreload_seconds = 0.01\n"

    async def wait_for_output(self, text):
        for _ in range(300):
            if text in self.out.getvalue():
                return
            await asyncio.sleep(0.01)
        self.fail(f"never printed {text!r}")

    def edit_users(self, text):
        self.users_file.write_text(text)
        stat = self.users_file.stat()  # make sure the change is seen as one
        os.utime(self.users_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))

    async def test_user_added_without_restart(self):
        await self.start(CONFIG + self.FAST_RELOAD)
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(STRANGER, "qm hi")
            send_email.assert_not_called()
            self.edit_users(USERS + f'[users.{full_key(STRANGER)}]\nname = "Stranger"\nqm = "s@example.com"\n')
            await self.wait_for_output("users.toml reloaded: added Stranger")
            await self.radio.dm(STRANGER, "qm hi")
        self.assertEqual(send_email.call_args.args[0], ["s@example.com"])

    async def test_user_removed_without_restart(self):
        await self.start(CONFIG + self.FAST_RELOAD)
        self.edit_users(USERS.split("[users.")[0])
        await self.wait_for_output("users.toml reloaded: removed Dana")
        self.assertIn("Warning: no user has qm addresses in users.toml.", self.out.getvalue())
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm hi")
        send_email.assert_not_called()

    async def test_bad_edit_keeps_users_and_tells_admins(self):
        await self.start(CONFIG + self.FAST_RELOAD)
        self.edit_users(USERS + "[users.d0d0]\n")
        await self.wait_for_output("Warning: users.toml not reloaded: ")
        await self.settle()
        self.assertEqual(self.radio.sent, [
            ("Admin", "Node problem: users.toml not reloaded: [users]: 'd0d0' is not a full public key "
                      "(64 hex characters)")])
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm hi")
        send_email.assert_called_once()  # Dana is still a user
        self.edit_users(USERS)
        await self.wait_for_output("users.toml reloaded")
        await self.wait_for_output("Watch: Node ok again: users.toml reloaded")

    async def test_bad_edit_without_the_watch(self):
        await self.start(CONFIG + self.FAST_RELOAD + "[watch]\nenabled = false\n")
        self.edit_users(USERS + "[users.d0d0]\n")
        await self.wait_for_output("Warning: users.toml not reloaded: ")
        await self.settle()
        self.assertEqual(self.radio.sent, [
            ("Admin", "users.toml not reloaded: [users]: 'd0d0' is not a full public key (64 hex characters)")])

    async def test_reload_command(self):
        await self.start()  # polls every 5s, so only the command reloads in time
        self.edit_users(USERS.replace('name = "Dana"', 'name = "Dee"'))
        await self.radio.dm(DANA, "reload")
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])  # admins only
        await self.radio.dm(ADMIN_KEY, "reload")
        self.assertEqual(self.radio.sent[-1], ("Admin", "reload: changed Dee"))
        self.assertIn("users.toml reloaded: changed Dee", self.out.getvalue())

    async def test_sighup_reloads(self):
        await self.start(CONFIG + "\n[directory]\nreload_seconds = 0\n")
        self.assertIn("(checked on reload or SIGHUP only)", self.out.getvalue())
        self.edit_users(USERS.replace('name = "Dana"', 'name = "Dee"'))
        os.kill(os.getpid(), signal.SIGHUP)
        await self.wait_for_output("users.toml reloaded: changed Dee")

    async def test_a_lost_radio_stops_the_bot_with_an_error(self):
        await self.start()
        await self.radio.deliver(EventType.DISCONNECTED, {"reason": "reconnect_failed"})
        self.assertEqual(await self.task, 1)
        self.assertIn("Lost the radio (reconnect_failed); stopping.", self.out.getvalue())
        self.assertNotIn("Stopped.", self.out.getvalue())
        self.assertTrue(self.radio.disconnected)
        # Kept for the next start, which tells the admins how long it was gone.
        lost = json.loads((self.users_file.parent / "watch.json").read_text())["lost"]
        self.assertEqual(lost["reason"], "reconnect_failed")

    async def restart_hook(self):
        """Start the bot, and return the state.restart it sets."""
        states = []
        real_state = bot.State

        def keep(*args, **kwargs):
            states.append(real_state(*args, **kwargs))
            return states[-1]

        self.enterContext(mock.patch("mesh_contingency.bot.State", keep))
        self.enterContext(mock.patch("mesh_contingency.bot.RESTART_SECONDS", 0))
        await self.start()
        return states[0].restart

    async def test_a_restart_asked_for_stops_the_bot_with_an_error(self):
        restart = await self.restart_hook()
        restart("the radio was rebooted from the console")
        self.assertEqual(await self.task, 1)  # so the service starts it again
        self.assertIn("Restarting: the radio was rebooted from the console.", self.out.getvalue())
        watch = self.users_file.parent / "watch.json"
        self.assertNotIn("lost", json.loads(watch.read_text()) if watch.exists() else {})  # not told to the admins

    async def test_the_radio_dropping_during_a_restart_isnt_a_lost_radio(self):
        restart = await self.restart_hook()
        with mock.patch("mesh_contingency.bot.RESTART_SECONDS", 60):  # the drop comes first
            restart("the radio was rebooted from the console")
        await self.radio.deliver(EventType.DISCONNECTED, {"reason": "reconnect_failed"})
        self.assertEqual(await self.task, 1)
        self.assertNotIn("Lost the radio", self.out.getvalue())
        watch = self.users_file.parent / "watch.json"
        self.assertNotIn("lost", json.loads(watch.read_text()) if watch.exists() else {})

    async def test_our_own_disconnect_isnt_a_lost_radio(self):
        await self.start()
        await self.radio.deliver(EventType.DISCONNECTED, {"reason": "manual_disconnect"})
        await asyncio.sleep(0)
        self.assertFalse(self.task.done())

    async def test_mesh_text_is_printed_with_control_codes_escaped(self):
        self.radio = FakeMeshCore({DANA: "Dana\x1b]0;owned\x07", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        await self.start(radio=self.radio)
        await self.radio.dm(DANA, "wx \x1b[2J\x1b[31m33101")
        out = self.out.getvalue()
        self.assertNotIn("\x1b", out)
        self.assertIn("[d0d0d0d0d0d0 Dana\\x1b]0;owned\\x07] wx \\x1b[2J\\x1b[31m33101", out)

    async def test_files_others_can_read_are_warned_about(self):
        config_file = self.write_files(CONFIG, USERS)
        self.users_file.chmod(0o644)
        self.mailrc.write_text("set mta=smtps://secret\n")
        self.mailrc.chmod(0o640)
        await self.start(config_file=config_file)
        out = self.out.getvalue()
        self.assertIn(f"Warning: {self.users_file} can be read or changed by other accounts (mode 644); "
                      f"fix with: chmod 600 {self.users_file}", out)
        self.assertIn(f"Warning: {self.mailrc} can be read or changed by other accounts (mode 640)", out)
        self.assertNotIn(f"Warning: {config_file} ", out)

    async def test_no_warning_for_private_files(self):
        await self.start()
        self.assertNotIn("other accounts", self.out.getvalue())

    async def test_sigterm_stops_cleanly(self):
        await self.start()
        os.kill(os.getpid(), signal.SIGTERM)
        self.assertEqual(await self.task, 0)
        self.assertTrue(self.out.getvalue().endswith("Stopped.\n"))
        self.assertTrue(self.radio.disconnected)

    async def test_sigusr1_sends_a_flood_advert(self):
        await self.start()
        os.kill(os.getpid(), signal.SIGUSR1)
        await self.wait_for_output("Sent flood advert (SIGUSR1)")
        self.assertEqual(self.radio.adverts, [True])

    async def test_advert_at_startup_counts_toward_the_schedule(self):
        await self.start(CONFIG + "\n[advert]\nat_startup = true\nevery_hours = 12\nflood = false\n")
        self.assertEqual(self.radio.adverts, [False])
        out = self.out.getvalue()
        self.assertIn("Sent zero-hop advert (at startup)", out)
        self.assertIn("Sending a zero-hop advert every 12 hour(s); next in 12 h.", out)
        self.assertIn("last_zero_hop", (self.users_file.parent / "adverts.json").read_text())

    async def test_advert_command_counts_toward_the_schedule(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "advert flood")
        self.assertIn("last_flood", (self.users_file.parent / "adverts.json").read_text())

    async def test_first_scheduled_advert_goes_out_at_once(self):
        await self.start(CONFIG + "\n[advert]\nevery_hours = 12\n")
        self.assertIn("Sending a flood advert every 12 hour(s); next now.", self.out.getvalue())
        await self.wait_for_output("Sent flood advert (scheduled)")
        self.assertEqual(self.radio.adverts, [True])

    async def test_no_adverts_unless_configured(self):
        await self.start()
        self.assertEqual(self.radio.adverts, [])
        self.assertNotIn("advert every", self.out.getvalue())

    async def test_bad_advert_section_stops_startup(self):
        await self.main_exits(CONFIG + "\n[advert]\nevery_hours = -1\n", USERS, "every_hours must be")

    async def test_missing_users_file(self):
        await self.start(users=None)
        out = self.out.getvalue()
        self.assertIn(f"Warning: {self.users_file} not found; no users or admins until it is created.", out)
        self.assertIn("user commands (0 user(s))", out)
        await self.radio.dm(ADMIN_KEY, "advert")
        self.assertEqual(self.radio.adverts, [])

    async def test_invalid_users_file_stops_startup_before_connecting(self):
        await self.main_exits(CONFIG, '[admin]\nkeys = "x"\n', r"users.toml: \[admin\] keys must be a list")

    async def test_users_left_in_config_toml(self):
        await self.main_exits(CONFIG + USERS, None, r"\[users\] and \[admin\] now go in their own file")

    # --- console logging

    async def test_logs_sender_key_and_name(self):
        await self.start()
        await self.radio.dm(DANA, "hi there")
        await self.radio.dm("123456789abc", "who am i")
        out = self.out.getvalue()
        self.assertIn(f"[{DANA} Dana] hi there", out)
        self.assertIn("[123456789abc] who am i", out)
        self.assertNotIn(full_key(DANA), out)  # only the prefix is logged

    # --- unrecognized messages and the cooldown

    async def test_unrecognized_message_gets_reply(self):
        await self.start()
        await self.radio.dm(STRANGER, "hello")
        self.assertEqual(self.radio.sent, [("Stranger", bot.UNRECOGNIZED_REPLY)])

    async def test_blank_message_gets_no_reply(self):
        await self.start()
        await self.radio.dm(STRANGER, "   ")
        self.assertEqual(self.radio.sent, [])

    async def test_unrecognized_cooldown_per_sender(self):
        await self.start()
        await self.radio.dm(STRANGER, "hello")
        await self.radio.dm(STRANGER, "anyone?")
        await self.radio.dm(STRANGER, "advert")  # denials share the same cooldown
        await self.radio.dm(DANA, "foo")  # a different sender is unaffected
        self.assertEqual(self.radio.sent, [("Stranger", bot.UNRECOGNIZED_REPLY),
                                           ("Dana", bot.UNRECOGNIZED_REPLY)])
        self.assertIn("not replying (replied within 300s)", self.out.getvalue())

        self.clock += bot.UNRECOGNIZED_COOLDOWN
        await self.radio.dm(STRANGER, "hello again")
        self.assertEqual(self.radio.sent[-1], ("Stranger", bot.UNRECOGNIZED_REPLY))

    # --- suggestions for mistyped commands

    async def test_a_user_is_told_the_nearest_command(self):
        await self.start()
        await self.radio.dm(DANA, "inbx")
        await self.radio.dm(DANA, "Quickim running late")  # its old name
        await self.radio.dm(ADMIN_KEY, "resetpassword Dana")
        self.assertEqual(self.radio.sent, [
            ("Dana", "unknown command inbx; did you mean inbox? help lists yours"),
            ("Dana", "unknown command Quickim; did you mean qm? help lists yours"),
            ("Admin", "unknown command resetpassword; did you mean resetpass? help lists yours")])
        self.assertIn("unrecognized command; suggesting inbox", self.out.getvalue())

    async def test_suggestions_have_no_cooldown(self):
        await self.start()
        await self.radio.dm(DANA, "inbx")
        await self.radio.dm(DANA, "inbx")
        self.assertEqual(len(self.radio.sent), 2)

    async def test_only_commands_the_sender_may_run_are_suggested(self):
        await self.start()
        await self.radio.dm(DANA, "adver")  # advert is for admins
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])
        await self.radio.dm(ADMIN_KEY, "adver")
        self.assertEqual(self.radio.sent[-1], ("Admin", "unknown command adver; did you mean advert? help lists yours"))

    async def test_strangers_get_no_suggestion(self):
        await self.start()
        await self.radio.dm(STRANGER, "hepl")
        self.assertEqual(self.radio.sent, [("Stranger", bot.UNRECOGNIZED_REPLY)])

    async def test_nothing_close_gets_the_usual_reply(self):
        await self.start()
        await self.radio.dm(DANA, "good morning everyone")
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])

    async def test_a_suggestion_repeats_only_the_first_word(self):
        await self.start()
        await self.radio.dm(DANA, "setpas correct horse battery")
        self.assertEqual(self.replies(), ["unknown command setpas; did you mean setpass? help lists yours"])
        self.assertNotIn("horse", self.replies()[0])

    # --- permissions

    async def test_user_command_denied_to_non_user(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(STRANGER, "qm hi")
            await self.radio.dm(ADMIN_KEY, "qm hi")
        send_email.assert_not_called()
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY] * 2)
        self.assertIn("qm denied: sender not approved", self.out.getvalue())

    async def test_user_command_allowed_for_user(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "QM running late")
        self.assertEqual(send_email.call_args.args[0], ["partner@example.com"])
        self.assertEqual(self.radio.sent, [("Dana", "qm: sent")])

    async def test_failed_email_says_why(self):
        # Without the watch, which may tell the admin "email failing" too.
        await self.start(CONFIG + "[watch]\nenabled = false\n")
        failure = SendError("`mail` failed: msmtp: cannot connect to smtp.example.com, port 587: "
                            "Network is unreachable", NO_INTERNET)
        with mock.patch("mesh_contingency.commands.mail.send_email", side_effect=failure):
            await self.radio.dm(DANA, "qm running late")
        self.assertEqual(self.radio.sent, [("Dana", "qm: not sent, no internet at the node; try again later")])
        self.assertIn("qm failed: `mail` failed: msmtp: cannot connect to smtp.example.com", self.out.getvalue())

    async def test_admin_command(self):
        await self.start()
        await self.radio.dm(DANA, "advert")
        self.assertEqual(self.radio.adverts, [])
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])
        await self.radio.dm(ADMIN_KEY, "advert flood")
        self.assertEqual(self.radio.adverts, [True])
        self.assertEqual(self.radio.sent[-1], ("Admin", "advert: flood sent"))

    async def test_rights_need_the_full_key_in_the_config(self):
        # A contact whose key shares the user's prefix but differs after it.
        lookalike = DANA + "11" * 26
        await self.start(contacts={lookalike: "Dana", ADMIN_KEY: "Admin"})
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm hi")
        send_email.assert_not_called()
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])

    async def test_shared_prefix_identifies_nobody(self):
        # An impostor with the user's prefix: neither contact gets rights,
        # whichever of them sent the message.
        impostor = DANA + "11" * 26
        await self.start(contacts={DANA: "Dana", impostor: "Dana"})
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm hi")
        send_email.assert_not_called()
        self.assertIn(f"(2 contacts share key prefix {DANA}; sender not identified)", self.out.getvalue())
        self.assertIn("qm denied: sender not approved", self.out.getvalue())

    async def test_shared_prefix_reported_to_admins_once(self):
        impostor = DANA + "11" * 26
        await self.start(contacts={DANA: "Dana", impostor: "Dana", ADMIN_KEY: "Admin"})
        await self.settle()
        alert = ("Admin", f"2 contacts share Dana's key prefix {DANA}: remove the impostor from the radio")
        self.assertEqual(self.radio.sent, [alert])
        self.assertIn(f"Warning: 2 contacts share Dana's key prefix {DANA}", self.out.getvalue())
        await self.radio.dm(DANA, "hello")
        await self.settle()
        self.assertEqual(self.radio.sent.count(alert), 1)

    async def test_shared_prefix_checked_after_reload(self):
        await self.start(contacts={STRANGER: "Stranger", STRANGER + "11" * 26: "Copy", ADMIN_KEY: "Admin"},
                         config=CONFIG)
        await self.settle()
        self.assertEqual(self.radio.sent, [])  # not a user's prefix: nothing to protect
        self.edit_users(USERS + f'[users.{full_key(STRANGER)}]\nname = "Sam"\n')
        await self.radio.dm(ADMIN_KEY, "reload")
        await self.settle()
        self.assertIn(("Admin", f"2 contacts share Sam's key prefix {STRANGER}: remove the impostor from the radio"),
                      self.radio.sent)

    async def test_reply_goes_to_the_full_key(self):
        await self.start()
        sent_to = []
        original = self.radio.commands.send_msg_with_retry

        async def record(contact, text):
            sent_to.append(contact["public_key"])
            return await original(contact, text)

        self.radio.commands.send_msg_with_retry = record
        await self.radio.dm(ADMIN_KEY, "advert")
        self.assertEqual(sent_to, [full_key(ADMIN_KEY)])

    async def test_new_contact_gets_rights_without_restart(self):
        # Messages from a node the bot hasn't loaded yet: refresh, then match.
        await self.start(contacts={ADMIN_KEY: "Admin"})
        self.radio.stored[full_key(DANA)] = "Dana"
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm hi")
        send_email.assert_called_once()

    async def test_public_command_for_anyone(self):
        await self.start()
        data = {"zipcode": "10001", "place": "New York City, NY", "station": "Central Park",
                "obs": None, "pop": 0, "alerts": []}
        with mock.patch("mesh_contingency.commands.wx.fetch_weather", return_value=data):
            await self.radio.dm(STRANGER, "wx 10001")
        self.assertEqual(self.radio.sent, [("Stranger", "10001 0% precip 6h | no current obs")])

    async def test_multi_part_reply_sent_in_order(self):
        await self.start()
        result = CommandResult(console="full text", reply=["(1/2) first", "(2/2) second"])
        with mock.patch("mesh_contingency.commands.verse.VerseCommand.execute", mock.AsyncMock(return_value=result)):
            await self.radio.dm(STRANGER, "verse john 3:16")
        self.assertEqual(self.radio.sent, [("Stranger", "(1/2) first"), ("Stranger", "(2/2) second")])
        out = self.out.getvalue()
        self.assertIn("full text", out)
        self.assertIn("-> replied (11 chars): (1/2) first", out)
        self.assertIn("-> replied (12 chars): (2/2) second", out)

    async def test_verse_end_to_end(self):
        await self.start()
        await self.radio.dm(STRANGER, "verse phil 4:13")
        self.assertEqual(self.replies(), ["Philippians 4:13 I can do all things through Christ who gives me strength."])

    # --- third-party commands, help and reply limits

    PLUGINS = """
[commands.echo]
handler = "tests.test_bot:echo"
permission = "public"
prefix = "> "

[commands.slow]
handler = "tests.test_bot:slow"
permission = "public"
timeout = 0.01

[commands.secret]
handler = "tests.test_bot:echo"
permission = "admin"

[commands.missing]
handler = "no_such_module_xyz:thing"
permission = "public"
"""

    async def test_plugin_from_config(self):
        await self.start(CONFIG + self.PLUGINS)
        out = self.out.getvalue()
        self.assertIn("public commands (anyone): help, wx, verse, ok, status, join, echo, slow", out)
        self.assertIn("Warning: Could not load missing (no_such_module_xyz:thing)", out)
        await self.radio.dm(STRANGER, "echo hi there")
        self.assertEqual(self.replies(), ["> hi there"])
        self.assertIn("> hi there", self.out.getvalue())  # str reply also printed

    async def test_plugin_long_text_reply_is_split_and_capped(self):
        await self.start(CONFIG + self.PLUGINS)
        await self.radio.dm(STRANGER, "echo " + "word " * 400)
        replies = self.replies()
        self.assertEqual(len(replies), MAX_PARTS)
        self.assertTrue(replies[0].startswith(f"(1/{MAX_PARTS}) > word"))
        self.assertTrue(replies[-1].endswith("..."))
        self.assertTrue(all(len(r) <= MAX_REPLY_LEN for r in replies))

    async def test_plugin_with_no_reply(self):
        await self.start(CONFIG + self.PLUGINS)
        await self.radio.dm(STRANGER, "echo")
        self.assertEqual(self.radio.sent, [])
        self.assertIn("-> no reply", self.out.getvalue())

    async def test_command_timeout(self):
        await self.start(CONFIG + self.PLUGINS)
        await self.radio.dm(STRANGER, "slow")
        self.assertEqual(self.replies(), ["slow: timed out"])
        self.assertIn("slow timed out after 0.01s", self.out.getvalue())

    async def test_help_lists_only_allowed_commands(self):
        await self.start(CONFIG + self.PLUGINS)
        await self.radio.dm(STRANGER, "help")
        await self.radio.dm(ADMIN_KEY, "help")
        await self.radio.dm(STRANGER, "help wx")
        await self.radio.dm(STRANGER, "help secret")
        replies = self.replies()
        self.assertEqual(replies[0], "commands: help, wx, verse, ok, status, join, echo, slow. "
                                     "Send help <command> for usage")
        # Too long for one message, so it comes in parts.
        parts = split_reply("commands: help, wx, verse, advert, contacts, contact, radio, reload, ok, status, "
                            "clearstatus, checkins, health, history, alert, alertmap, testalert, comm, backup, join, "
                            "approve, deny, users, whois, remove, resetpass, echo, slow, secret. Send help <command> "
                            "for usage")
        self.assertGreater(len(parts), 1)
        self.assertEqual(replies[1:1 + len(parts)], parts)
        self.assertEqual(replies[1 + len(parts):], ["wx <zipcode> - Weather, precipitation and alerts for a US zipcode",
                                                    "help: no command secret"])

    # --- check-ins, roster and mailbox

    async def test_roster_lists_everyone_who_messaged(self):
        await self.start(contacts={DANA: "Dana-T1000", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        await self.radio.dm(STRANGER, "hello")  # not a command: still counted
        await self.radio.dm("123456789abc", "help")  # not in contacts: shown by key prefix
        await self.radio.dm(DANA, "roster")
        self.assertRegex(self.replies()[-1], r"^roster since .* \(3\): Dana-T1000, 123456789abc, Stranger$")
        sent = len(self.radio.sent)
        await self.radio.dm(STRANGER, "roster")
        self.assertEqual(len(self.radio.sent), sent)  # users only (and Stranger already got the reply)
        self.assertIn("roster denied: sender not approved", self.out.getvalue())

    async def test_check_in_and_mailbox_saved_next_to_the_config(self):
        await self.start()
        await self.radio.dm(STRANGER, "ok at the shelter")
        await self.radio.dm(DANA, "status stranger")
        self.assertEqual(self.replies()[-1], "Stranger: at the shelter (just now)")
        await self.radio.dm(DANA, "msg Dana note to self")
        self.assertEqual(self.replies()[-1], "msg: saved for Dana (1 in their inbox)")
        folder = self.users_file.parent
        self.assertEqual({p.name for p in folder.iterdir()}, {"config.toml", "users.toml", "status.json",
                                                              "mailbox.json", "watch.json"})
        self.assertNotIn(full_key(STRANGER)[:12] + "\n", self.out.getvalue())
        self.assertNotIn(full_key(STRANGER), self.out.getvalue())  # full keys are only in the files
        await self.radio.dm(DANA, "inbox")
        self.assertEqual(self.replies()[-1], "Dana just now: note to self")
        await self.radio.dm(DANA, "clearinbox")
        self.assertEqual(self.replies()[-1], "clearinbox: deleted 1 message(s)")

    async def test_rate_limit_replies_once_then_stays_silent(self):
        await self.start(CONFIG + '\n[limits]\npublic_rate = "2/hour"\n')
        for _ in range(4):
            await self.radio.dm(STRANGER, "help")
        replies = self.replies()
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[2], "help: limit reached, try again in 60 min")
        out = self.out.getvalue()
        self.assertIn("  -> help limit reached (2/hour); replying once\n", out)
        self.assertIn("  -> help limit reached; not replying\n", out)
        await self.radio.dm(DANA, "help")  # others aren't limited
        self.assertIn("commands:", self.replies()[3])

    async def test_private_commands_keep_text_off_the_console(self):
        await self.start()
        await self.radio.dm(DANA, "setpass blue-canoe-42x")
        await self.radio.dm(DANA, "msg Dana the code is 4711")
        await self.radio.dm(DANA, "inbox blue-canoe-42y")
        self.assertEqual(self.replies()[-1], "inbox: wrong passphrase")
        await self.radio.dm(DANA, "inbox blue-canoe-42x")
        self.assertEqual(self.replies()[-1], "Dana just now: the code is 4711")
        out = self.out.getvalue()
        for secret in ("4711", "blue-canoe"):
            self.assertNotIn(secret, out)
            self.assertNotIn(secret, (self.users_file.parent / "mailbox.json").read_text())
        self.assertIn(f"[{DANA} Dana] msg (private)\n  -> running msg\n", out)
        self.assertIn("  inbox: refused\n", out)
        self.assertIn("  -> replied (31 chars)\n", out)
        await self.radio.dm(DANA, "clearinbox")
        self.assertIn(f"[{DANA} Dana] clearinbox\n", self.out.getvalue())  # not private

    # --- joining and users' own settings

    async def test_join_approve_and_use(self):
        await self.start(contacts={DANA: "Dana", ADMIN_KEY: "Admin", STRANGER: "Sam T-Deck"})
        await self.radio.dm(STRANGER, "join")
        await self.settle()
        # The reply and the background notice may go out in either order.
        self.assertCountEqual(self.radio.sent, [
            ("Sam T-Deck", "join: request sent to the admins as Sam T-Deck"),
            ("Admin", "Join request: Sam T-Deck (ffeeddccbbaa). Reply approve ffeeddccbbaa or deny ffeeddccbbaa")])
        self.radio.sent.clear()
        await self.radio.dm(ADMIN_KEY, "approve (Sam T-Deck)")
        await self.settle()
        self.assertCountEqual(self.radio.sent, [
            ("Admin", "approve: Sam T-Deck added to users.toml"),
            ("Sam T-Deck", "Welcome, Sam T-Deck: you're now a user. Send help for your commands.")])
        self.assertIn("users.toml reloaded: added Sam T-Deck", self.out.getvalue())
        self.assertIn(f'[users.{full_key(STRANGER)}]\nname = "Sam T-Deck"\n', self.users_file.read_text())
        await self.radio.dm(DANA, "msg Sam T-Deck see you at noon")
        self.assertEqual(self.replies()[-1], "msg: saved for Sam T-Deck (1 in their inbox)")
        self.assertNotIn(full_key(STRANGER), self.out.getvalue())
        await self.radio.dm(STRANGER, "setqm sam.home@example.com")
        self.assertEqual(self.replies()[-1], "qm now sends to sam.home@example.com")
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(STRANGER, "qm hello")
        self.assertEqual(send_email.call_args.args[0], ["sam.home@example.com"])

    # --- quickim, renamed qm

    async def test_an_old_config_and_users_file_are_converted(self):
        config = CONFIG.replace('qm = { permission = "user" }', 'quickim = { permission = "user" }')
        await self.start(config=config, users=USERS.replace('qm = "partner@example.com"',
                                                            'quickim = "partner@example.com"'))
        out = self.out.getvalue()
        self.assertIn("quickim is now called qm; rename [commands.quickim] to [commands.qm]", out)
        self.assertIn("users.toml: quickim is now qm for 1 user(s)", out)
        self.assertNotIn("no user has qm addresses", out)
        self.assertEqual(tomllib.loads(self.users_file.read_text())["users"][full_key(DANA)],
                         {"name": "Dana", "qm": "partner@example.com"})
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "qm running late")
        self.assertEqual(send_email.call_args.args[0], ["partner@example.com"])

    async def test_quickim_typed_into_the_users_file_later_is_converted(self):
        await self.start(CONFIG + self.FAST_RELOAD)
        self.edit_users(USERS + f'[users.{full_key(STRANGER)}]\nname = "Stranger"\nquickim = "s@example.com"\n')
        await self.radio.dm(ADMIN_KEY, "reload")
        self.assertEqual(tomllib.loads(self.users_file.read_text())["users"][full_key(STRANGER)],
                         {"name": "Stranger", "qm": "s@example.com"})

    # --- names come from the radios

    async def test_names_are_set_from_the_radios_at_startup(self):
        await self.start(contacts={DANA: "Ridge Base 1", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        self.assertIn("Dana (d0d0d0d0d0d0) is now Ridge Base 1, the radio's name", self.out.getvalue())
        self.assertEqual(tomllib.loads(self.users_file.read_text())["users"][full_key(DANA)],
                         {"name": "Ridge Base 1", "qm": "partner@example.com"})
        self.assertEqual(len(list((self.users_file.parent / "backups").glob("users-*.toml"))), 1)
        await self.radio.dm(ADMIN_KEY, "history")
        self.assertIn("radio: Dana (d0d0d0d0d0d0) is now Ridge Base 1", self.replies()[-1])

    async def test_a_new_radio_name_is_picked_up_from_a_message(self):
        await self.start()
        self.radio.known[DANA] = "Dana's T-Deck"
        await self.radio.dm(DANA, "whoami")
        self.assertTrue(self.replies()[-1].startswith("Dana's T-Deck (d0d0d0d0d0d0)"), self.replies()[-1])
        self.assertIn('name = "Dana\'s T-Deck"', self.users_file.read_text())

    async def test_a_radio_name_that_cant_be_used_is_not_taken(self):
        await self.start()
        self.radio.known[DANA] = "Big Ass"
        await self.radio.dm(DANA, "whoami")
        await self.radio.dm(DANA, "whoami")
        warning = "Warning: Dana's radio is now called 'Big Ass', which can't be used; keeping Dana"
        self.assertEqual(self.out.getvalue().count(warning), 1)
        self.assertIn('name = "Dana"', self.users_file.read_text())

    async def test_a_config_still_listing_rename_starts_with_a_warning(self):
        await self.start(config=CONFIG + 'rename = { permission = "admin" }\n')
        self.assertIn("rename no longer exists (names are now the radios' names, kept up to date by the bot); "
                      "remove [commands.rename] from the config.", self.out.getvalue())

    # --- command failures

    async def test_command_error_is_sent_back(self):
        await self.start()
        await self.radio.dm(STRANGER, "wx")
        self.assertEqual(self.replies(), ["usage: wx <zipcode>"])

    async def test_unexpected_error_sends_generic_failure(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.wx.fetch_weather", side_effect=OSError("network down")):
            await self.radio.dm(STRANGER, "wx 10001")
        self.assertEqual(self.replies(), ["wx: failed"])
        self.assertIn("wx failed: network down", self.out.getvalue())

    async def test_long_reply_is_truncated(self):
        await self.start()
        await self.radio.dm(STRANGER, "wx " + "9" * 200)
        (reply,) = self.replies()
        self.assertEqual(len(reply), MAX_REPLY_LEN)
        self.assertTrue(reply.startswith("wx: invalid zipcode"))
        self.assertTrue(reply.endswith("..."))

    # --- reply delivery

    async def test_reply_delivered_is_logged(self):
        await self.start()
        await self.radio.dm(STRANGER, "hello")
        self.assertIn(f"(reply to {STRANGER} delivered)", self.out.getvalue())

    async def test_watch_hears_of_undelivered_messages(self):
        states = []  # the bot's State, to look inside

        def new_state(*args):
            states.append(State(*args))
            return states[-1]

        self.enterContext(mock.patch.object(bot, "State", side_effect=new_state))
        await self.start()
        self.assertIn("Watching the node every 5 min: battery below 3.5V, radio restarts, 5 undelivered in a row, "
                      "email failing, 3 errors in 30 min, users.toml not reloading, backups failing; "
                      "problems go to 1 admin(s).",
                      self.out.getvalue())
        (state,) = states
        self.radio.ack_result = None
        for _ in range(5):
            await self.radio.dm(STRANGER, "help")
        self.assertEqual(state.undelivered_in_row, 5)
        state.watch.wake.set()
        await self.wait_for_output("Watch: Node problem: 5 messages in a row not delivered")
        await self.settle()
        self.assertIn(("Admin", "Node problem: 5 messages in a row not delivered"), self.radio.sent)
        self.radio.ack_result = event(EventType.MSG_SENT)
        await self.radio.dm(STRANGER, "help")
        self.assertEqual(state.undelivered_in_row, 0)

    async def test_watch_off(self):
        await self.start(CONFIG + "[watch]\nenabled = false\n")
        self.assertNotIn("Watching the node", self.out.getvalue())

    async def test_reply_not_acknowledged_is_logged(self):
        await self.start()
        self.radio.ack_result = None
        await self.radio.dm(STRANGER, "hello")
        self.assertIn(f"(reply to {STRANGER} not acknowledged after retries)", self.out.getvalue())

    async def test_refreshes_contacts_for_unknown_sender(self):
        await self.start()
        self.radio.stored["c0ffeec0ffee"] = "LateNode"  # radio learned it after startup
        await self.radio.dm("c0ffeec0ffee", "hello")
        self.assertEqual(self.radio.get_contacts_calls, 1)
        self.assertEqual(self.radio.sent, [("LateNode", bot.UNRECOGNIZED_REPLY)])

    async def test_no_contact_to_reply_to(self):
        await self.start()
        await self.radio.dm("c0ffeec0ffee", "hello")
        self.assertEqual(self.radio.sent, [])
        self.assertIn("(no contact c0ffeec0ffee to send reply to", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
