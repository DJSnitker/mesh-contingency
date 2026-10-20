import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from meshcore import EventType

from mesh_contingency import bot
from mesh_contingency.api import ADMIN, DISABLED, MAX_PARTS, MAX_REPLY_LEN, PUBLIC, USER, CommandResult, Sender
from mesh_contingency.testing import FakeMeshCore


async def echo(text, sender, ctx):
    """A plugin command for the tests: replies with its text, or nothing."""
    return f"{ctx.options.get('prefix', '')}{text}" if text else None


async def slow(text, sender, ctx):
    await asyncio.sleep(10)


DANA = "d0d0d0d0d0d0"  # user
ADMIN_KEY = "adadadadadad"  # admin only
STRANGER = "ffeeddccbbaa"  # in contacts, but neither user nor admin

CONFIG = f"""
[commands]
help = {{ permission = "public" }}
wx = {{ permission = "public" }}
verse = {{ permission = "public" }}
quickim = {{ permission = "user" }}
emailall = {{ permission = "user" }}
email = {{ permission = "user" }}
advert = {{ permission = "admin" }}

[admin]
keys = ["{ADMIN_KEY}"]

[users.{DANA}]
quickim = "partner@example.com"
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
        return bot.is_authorized(command, Sender("x", key), users={DANA: {}}, admins={ADMIN_KEY})

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
        with mock.patch("mesh_contingency.bot.main", mock.AsyncMock()) as main:
            bot.run()
        main.assert_awaited_once()

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


class MainTest(unittest.IsolatedAsyncioTestCase):
    """Runs bot.main() against a fake radio and drives it with messages."""

    async def start(self, config=CONFIG, contacts=None, argv=None, radio=None):
        self.radio = radio or FakeMeshCore(contacts if contacts is not None else
                                           {DANA: "Dana", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(config)
        self.addCleanup(os.unlink, f.name)

        self.clock = 1000.0
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.enterContext(mock.patch("mesh_contingency.bot.time", SimpleNamespace(monotonic=lambda: self.clock)))
        self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial",
                                     mock.AsyncMock(return_value=self.radio)))
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", f.name] + (argv or [])))

        self.task = asyncio.create_task(bot.main())
        listening = asyncio.create_task(self.radio.listening.wait())
        await asyncio.wait({self.task, listening}, return_when=asyncio.FIRST_COMPLETED)
        listening.cancel()
        if self.task.done():
            self.task.result()  # re-raise a startup failure
        self.addAsyncCleanup(self.stop)

    async def stop(self):
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task

    def replies(self):
        return [text for _, text in self.radio.sent]

    # --- startup and shutdown

    async def test_startup(self):
        await self.start()
        self.assertEqual(set(self.radio.handlers), {EventType.CONTACT_MSG_RECV})  # no channel messages
        self.assertTrue(self.radio.auto_update_contacts)
        out = self.out.getvalue()
        self.assertIn("public commands (anyone): help, wx, verse", out)
        self.assertIn("user commands (1 user(s)): quickim, emailall, email", out)
        self.assertIn("admin commands (1 admin(s)): advert", out)
        self.assertIn("disabled commands (nobody): none", out)
        self.assertNotIn("Warning: quickim", out)
        self.assertIn("emailall command disabled", out)
        self.assertNotIn("quickim command disabled", out)
        self.assertEqual(self.radio.manual_add_calls, [])  # no [contacts] section

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
        self.assertNotIn("emailall command disabled.\nWarning: no user", out)
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
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(CONFIG.replace('wx = { permission = "public" }', 'wx = { permission = "everyone" }'))
        self.addCleanup(os.unlink, f.name)
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", f.name]))
        connect = self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial", mock.AsyncMock()))
        with self.assertRaisesRegex(SystemExit, r"\[commands.wx\] has unknown permission 'everyone'"):
            await bot.main()
        connect.assert_not_called()

    async def test_shutdown_disconnects(self):
        await self.start()
        await self.stop()
        self.assertTrue(self.radio.disconnected)

    async def test_no_serial_port(self):
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-c", "/nonexistent.toml"]))
        self.enterContext(mock.patch("mesh_contingency.bot.find_serial_port", return_value=None))
        with self.assertRaisesRegex(SystemExit, "No serial device found"):
            await bot.main()

    async def test_connect_failure(self):
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", "/nonexistent.toml"]))
        self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial", mock.AsyncMock(return_value=None)))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        with self.assertRaisesRegex(SystemExit, "Could not connect"):
            await bot.main()

    # --- console logging

    async def test_logs_sender_key_and_name(self):
        await self.start()
        await self.radio.dm(DANA, "hi there")
        await self.radio.dm("123456789abc", "who am i")
        out = self.out.getvalue()
        self.assertIn(f"[{DANA} Dana] hi there", out)
        self.assertIn("[123456789abc] who am i", out)

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

    # --- permissions

    async def test_user_command_denied_to_non_user(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(STRANGER, "quickim hi")
            await self.radio.dm(ADMIN_KEY, "quickim hi")
        send_email.assert_not_called()
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY] * 2)
        self.assertIn("quickim denied: sender not approved", self.out.getvalue())

    async def test_user_command_allowed_for_user(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            await self.radio.dm(DANA, "QUICKIM running late")
        self.assertEqual(send_email.call_args.args[0], ["partner@example.com"])
        self.assertEqual(self.radio.sent, [("Dana", "quickim: sent")])

    async def test_admin_command(self):
        await self.start()
        await self.radio.dm(DANA, "advert")
        self.assertEqual(self.radio.adverts, [])
        self.assertEqual(self.replies(), [bot.UNRECOGNIZED_REPLY])
        await self.radio.dm(ADMIN_KEY, "advert flood")
        self.assertEqual(self.radio.adverts, [True])
        self.assertEqual(self.radio.sent[-1], ("Admin", "advert: flood sent"))

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
        self.assertIn("public commands (anyone): help, wx, verse, echo, slow", out)
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
        self.assertEqual(replies[0], "commands: help, wx, verse, echo, slow. Send help <command> for usage")
        self.assertEqual(replies[1], "commands: help, wx, verse, advert, echo, slow, secret. "
                                     "Send help <command> for usage")
        self.assertEqual(replies[2], "wx <zipcode> - Weather, precipitation and alerts for a US zipcode")
        self.assertEqual(replies[3], "help: no command secret")

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
        self.assertIn("(no contact c0ffeec0ffee to reply to", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
