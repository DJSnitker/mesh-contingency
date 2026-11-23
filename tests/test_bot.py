import asyncio
import contextlib
import io
import os
import signal
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mesh_commands import MAX_PARTS, MAX_REPLY_LEN, Command, CommandError
from mesh_commands.dispatch import UNRECOGNIZED_COOLDOWN, UNRECOGNIZED_REPLY
from mesh_commands.testing import FakeMeshCore, event, full_key, make_contact
from meshcore import EventType

from mesh_contingency import bot


async def echo(text, sender, ctx):
    """A plugin command for the tests: replies with its text, or nothing."""
    return f"{ctx.options.get('prefix', '')}{text}" if text else None


async def slow(text, sender, ctx):
    await asyncio.sleep(10)


async def long_error(text, sender, ctx):
    raise CommandError("nope " * 60)


class BrokenStart(Command):
    """A plugin command whose startup fails."""

    async def start(self):
        raise RuntimeError("radio said no")

    async def execute(self, text, sender):
        return "still works"


# Key prefixes, as direct messages carry them; the config holds full_key(prefix).
ADMIN_KEY = "adadadadadad"  # an admin
DANA = "d0d0d0d0d0d0"  # in contacts, not an admin
STRANGER = "ffeeddccbbaa"  # in contacts, not an admin

ADMINS = f'[admins]\nkeys = ["{full_key(ADMIN_KEY)}"]\n'
COMMANDS = """
[commands]
help = { permission = "admin" }
alert = { permission = "admin" }
testalert = { permission = "admin" }
"""
CONFIG = ADMINS + COMMANDS


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


class MainTest(unittest.IsolatedAsyncioTestCase):
    """Runs bot.main() against a fake radio and drives it with messages."""

    async def start(self, config=CONFIG, contacts=None, radio=None, users=None, config_file=None):
        """Start the bot with config.toml (and an old users.toml, if users
        is given) in a temporary folder, or with config_file from write_files."""
        self.radio = radio or FakeMeshCore(contacts if contacts is not None else
                                           {DANA: "Dana", ADMIN_KEY: "Admin", STRANGER: "Stranger"})
        config_file = config_file or self.write_files(config, users)

        self.clock = 1000.0
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        clock = SimpleNamespace(monotonic=lambda: self.clock, time=time.time)
        self.enterContext(mock.patch("mesh_contingency.bot.time", clock))
        self.enterContext(mock.patch("mesh_commands.dispatch.time", clock))
        self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial",
                                     mock.AsyncMock(return_value=self.radio)))
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", str(config_file)]))

        self.task = asyncio.create_task(bot.main())
        listening = asyncio.create_task(self.radio.listening.wait())
        await asyncio.wait({self.task, listening}, return_when=asyncio.FIRST_COMPLETED)
        listening.cancel()
        if self.task.done():
            self.task.result()  # re-raise a startup failure
        self.addAsyncCleanup(self.stop)

    def write_files(self, config, users=None):
        """Write config.toml (and users.toml, if given) to a temporary folder
        and return the config's path."""
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        config_file = self.folder / "config.toml"
        config_file.write_text(config)
        config_file.chmod(0o600)
        if users is not None:
            (self.folder / "users.toml").write_text(users)
        return config_file

    async def main_exits(self, config, error):
        """Check bot.main() stops with this error before connecting."""
        config_file = self.write_files(config)
        self.enterContext(mock.patch("sys.argv", ["mesh-contingency", "-p", "/dev/fake", "-c", str(config_file)]))
        connect = self.enterContext(mock.patch("mesh_contingency.bot.MeshCore.create_serial", mock.AsyncMock()))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        with self.assertRaisesRegex(SystemExit, error):
            await bot.main()
        connect.assert_not_called()

    async def stop(self):
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task

    def replies(self):
        return [text for _, text in self.radio.sent]

    async def wait_for_output(self, text):
        for _ in range(300):
            if text in self.out.getvalue():
                return
            await asyncio.sleep(0.01)
        self.fail(f"never printed {text!r}")

    # --- startup and shutdown

    async def test_startup(self):
        await self.start()
        # Direct messages only: no channel messages.
        self.assertEqual(set(self.radio.handlers), {EventType.CONTACT_MSG_RECV, EventType.DISCONNECTED})
        self.assertTrue(self.radio.auto_update_contacts)
        out = self.out.getvalue()
        self.assertIn("  admin commands (1 admin(s)): help, alert, testalert\n", out)
        self.assertIn("  disabled commands (nobody): none\n", out)
        self.assertNotIn("public commands", out)
        self.assertIn("Rate limits per sender and command: public 10/hour, user 30/hour, admin none", out)
        self.assertIn("Warning: no counties in [alerts] counties in config.toml, so no weather alerts will be "
                      "posted.", out)
        self.assertIn("Listening for direct messages", out)
        self.assertNotIn("Warning: config.toml has settings", out)
        self.assertEqual(self.radio.manual_add_calls, [])  # the radio's own setting is left alone

    async def test_counties_start_the_alert_watcher(self):
        self.enterContext(mock.patch("mesh_contingency.bot.AlertWatcher.run", mock.AsyncMock()))
        await self.start(CONFIG + '\n[alerts]\ncounties = ["Taylor, TX"]\n')
        out = self.out.getvalue()
        self.assertIn("Watching NWS alerts for 1 county (Taylor, TX) every 10 min to Public.", out)
        self.assertNotIn("no counties", out)

    async def test_weekly_test_is_scheduled(self):
        self.enterContext(mock.patch("mesh_contingency.bot.AlertTest.run", mock.AsyncMock()))
        await self.start(CONFIG + '\n[alert_test]\nweekly = "Wed 17:00"\ntimezone = "America/Chicago"\n')
        self.assertIn("Weekly alert test: Wednesday 17:00 America/Chicago to Public", self.out.getvalue())

    async def test_channel_messages_are_ignored(self):
        await self.start()
        self.assertNotIn(EventType.CHANNEL_MSG_RECV, self.radio.handlers)

    async def test_a_right_clock_is_left_alone(self):
        await self.start()
        self.assertEqual([c for c, _ in self.radio.settings_calls], [])
        self.assertNotIn("radio's clock", self.out.getvalue())

    async def test_the_radios_clock_is_set_at_startup(self):
        radio = FakeMeshCore({ADMIN_KEY: "Admin"})
        radio.clock = time.time() - 4 * 3600 - 125  # after a reboot: it keeps no time
        await self.start(radio=radio)
        [(call, (when,))] = self.radio.settings_calls
        self.assertEqual(call, "set_time")
        self.assertAlmostEqual(when, time.time(), delta=5)
        self.assertIn("Set the radio's clock from the computer's: it was 4h 2m behind.\n", self.out.getvalue())

    async def test_a_clock_the_radio_wont_take_is_a_warning(self):
        radio = FakeMeshCore({ADMIN_KEY: "Admin"})
        radio.clock = 1000.0
        radio.settings_result = event(EventType.ERROR, {})
        await self.start(radio=radio)
        self.assertIn("Warning: couldn't set the radio's clock.\n", self.out.getvalue())
        self.assertFalse(self.task.done())  # it runs on

    async def test_public_is_found_at_startup(self):
        await self.start()
        self.assertIn("Alerts go to the Public channel (slot 0).", self.out.getvalue())
        self.assertEqual(self.radio.channels[1:], [("", bytes(16))] * 7)  # nothing added

    async def test_public_in_another_slot(self):
        radio = FakeMeshCore({ADMIN_KEY: "Admin"})
        radio.channels[0], radio.channels[3] = radio.channels[3], radio.channels[0]
        await self.start(radio=radio)
        self.assertIn("Alerts go to the Public channel (slot 3).", self.out.getvalue())
        await radio.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(radio.channel_sent, [(3, "hi")])

    async def test_no_public_channel_is_a_warning_not_a_stop(self):
        radio = FakeMeshCore({ADMIN_KEY: "Admin"})
        radio.channels[0] = ("", bytes(16))
        await self.start(radio=radio)
        out = self.out.getvalue()
        self.assertIn("Warning: No Public channel on the radio, so no alerts can be posted: add MeshCore's Public "
                      "channel back in the radio's app.", out)
        self.assertIn("Listening for direct messages", out)
        self.assertEqual(radio.channels, [("", bytes(16))] * 8)  # nothing added
        await radio.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(radio.channel_sent, [])
        self.assertEqual(radio.sent[-1][1], "alert: no Public channel on the radio; add MeshCore's Public channel "
                                            "back in its app; nothing posted")

    async def test_an_old_channel_setting_is_a_warning(self):
        await self.start(CONFIG.replace('alert = { permission = "admin" }',
                                        'alert = { permission = "admin", channel = "#district7-wx" }')
                         + '\n[alerts]\nchannel = "#district7-wx"\n')
        self.assertIn("Warning: config.toml sets [alerts] channel, [commands.alert] channel, which is no longer "
                      "used: the alerts always go to the Public channel. Remove it.", self.out.getvalue())
        await self.radio.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(self.radio.channel_sent, [(0, "hi")])

    async def test_failed_start_is_a_warning(self):
        await self.start(CONFIG + '[commands.broken]\nhandler = "tests.test_bot:BrokenStart"\npermission = "public"\n')
        self.assertIn("Warning: broken could not get ready: radio said no", self.out.getvalue())
        await self.radio.dm(STRANGER, "broken")
        self.assertEqual(self.replies(), ["still works"])

    async def test_commands_missing_from_config_are_disabled(self):
        await self.start(CONFIG.replace('testalert = { permission = "admin" }\n', ""))
        out = self.out.getvalue()
        self.assertIn("disabled commands (nobody): testalert", out)
        self.assertIn("Warning: testalert has no [commands.testalert] section; disabled.", out)
        await self.radio.dm(ADMIN_KEY, "testalert")
        self.assertEqual(self.radio.channel_sent, [])
        self.assertEqual(self.replies(), [UNRECOGNIZED_REPLY])

    async def test_bad_permissions_stop_startup_before_connecting(self):
        await self.main_exits(CONFIG.replace('alert = { permission = "admin" }', 'alert = { permission = "boss" }'),
                              r"\[commands.alert\] has unknown permission 'boss'")

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

    async def test_a_lost_radio_stops_the_bot_with_an_error(self):
        await self.start()
        await self.radio.deliver(EventType.DISCONNECTED, {"reason": "reconnect_failed"})
        self.assertEqual(await self.task, 1)  # so the service starts it again
        self.assertIn("Lost the radio (reconnect_failed); stopping.", self.out.getvalue())
        self.assertNotIn("Stopped.", self.out.getvalue())
        self.assertTrue(self.radio.disconnected)

    async def test_our_own_disconnect_isnt_a_lost_radio(self):
        await self.start()
        await self.radio.deliver(EventType.DISCONNECTED, {"reason": "manual_disconnect"})
        await asyncio.sleep(0)
        self.assertFalse(self.task.done())

    async def test_sigterm_stops_cleanly(self):
        await self.start()
        os.kill(os.getpid(), signal.SIGTERM)
        self.assertEqual(await self.task, 0)
        self.assertTrue(self.out.getvalue().endswith("Stopped.\n"))
        self.assertTrue(self.radio.disconnected)

    async def test_mesh_text_is_printed_with_control_codes_escaped(self):
        self.radio = FakeMeshCore({ADMIN_KEY: "Admin\x1b]0;owned\x07"})
        await self.start(radio=self.radio)
        await self.radio.dm(ADMIN_KEY, "help \x1b[2J")
        out = self.out.getvalue()
        self.assertNotIn("\x1b", out)
        self.assertIn("[adadadadadad Admin\\x1b]0;owned\\x07] help\n", out)

    async def test_a_config_others_can_change_is_warned_about(self):
        config_file = self.write_files(CONFIG)
        config_file.chmod(0o644)
        await self.start(config_file=config_file)
        self.assertIn(f"Warning: {config_file} can be read or changed by other accounts (mode 644); "
                      f"fix with: chmod 600 {config_file}", self.out.getvalue())

    async def test_no_warning_for_a_private_config(self):
        await self.start()
        self.assertNotIn("other accounts", self.out.getvalue())

    # --- adverts

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
        self.assertIn("last_zero_hop", (self.folder / "adverts.json").read_text())

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
        await self.main_exits(CONFIG + "\n[advert]\nevery_hours = -1\n", "every_hours must be")

    # --- admins, and what older versions had

    async def test_no_admins(self):
        await self.start(COMMANDS)
        out = self.out.getvalue()
        self.assertIn("  admin commands (0 admin(s)): help, alert, testalert\n", out)
        self.assertIn("Note: no admins in [admins] keys in config.toml, so nobody can use the admin commands.", out)
        await self.radio.dm(ADMIN_KEY, "alert hello")
        self.assertEqual(self.radio.channel_sent, [])

    async def test_bad_admin_key_stops_startup(self):
        await self.main_exits('[admins]\nkeys = ["d0d0"]\n' + COMMANDS, r"\[admins\] keys: 'd0d0'\.\.\. is not a full")

    async def test_admins_from_an_old_users_file(self):
        await self.start(COMMANDS, users=f'[admin]\nkeys = ["{full_key(ADMIN_KEY)}"]\n\n[users.{full_key(DANA)}]\n'
                                         'name = "Dana"\n')
        self.assertIn("Warning: admins read from users.toml, which is otherwise no longer used: move them to "
                      "[admins] keys in config.toml.", self.out.getvalue())
        await self.radio.dm(ADMIN_KEY, "help")
        self.assertEqual(self.replies(), ["commands: help, alert, testalert. Send help <command> for usage"])

    async def test_an_old_users_file_beside_admins(self):
        await self.start(users='[admin]\nkeys = []\n')
        self.assertIn("Warning: users.toml is no longer used; delete it once [admins] has every admin.",
                      self.out.getvalue())

    async def test_an_old_config_still_starts(self):
        old = CONFIG.replace("[commands]\n", '[commands]\nwx = { permission = "public" }\n'
                             'msg = { permission = "user" }\n') + (
            '\n[backup]\nto = "x"\n\n[watch]\nenabled = true\n\n[console]\nenabled = true\n\n'
            '[contacts]\nauto_add = ["chat"]\n\n[limits]\npublic_rate = "10/hour"\nemails_per_day = 50\n')
        await self.start(old)
        out = self.out.getvalue()
        self.assertIn("Warning: config.toml has settings for removed features, ignored: [backup], [console], "
                      "[contacts], [watch], [limits] emails_per_day. Remove them (see config.example.toml).", out)
        self.assertIn("Warning: [commands] lists commands that no longer exist, ignored: wx, msg.", out)
        self.assertEqual(self.radio.manual_add_calls, [])  # [contacts] no longer changes the radio
        self.assertIn("Listening for direct messages", out)

    async def test_a_manual_add_radio_adds_the_admins(self):
        radio = FakeMeshCore({}, manual_add_contacts=True)
        await self.start(radio=radio)
        self.assertIn("adding the admins' radios when they advert", self.out.getvalue())
        await radio.deliver(EventType.NEW_CONTACT, make_contact(STRANGER, "Stranger"))
        await radio.deliver(EventType.NEW_CONTACT, make_contact(ADMIN_KEY, "Admin"))
        self.assertEqual([c["public_key"] for c in radio.added], [full_key(ADMIN_KEY)])
        await radio.dm(ADMIN_KEY, "help")
        self.assertEqual(radio.sent[-1][0], "Admin")

    # --- console logging

    async def test_logs_sender_key_and_name(self):
        await self.start()
        await self.radio.dm(DANA, "hi there")
        await self.radio.dm("123456789abc", "who am i")
        out = self.out.getvalue()
        self.assertIn(f"[{DANA} Dana] not a command", out)
        self.assertIn("[123456789abc] not a command", out)
        self.assertNotIn("hi there", out)  # what was sent isn't printed
        self.assertNotIn("who am i", out)
        self.assertNotIn(full_key(DANA), out)  # only the prefix is logged

    async def test_an_alerts_text_is_not_printed(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "alert Shelter open at the school")
        self.assertEqual(self.replies(), ["alert: posted to Public"])
        out = self.out.getvalue()
        self.assertIn(f"[{ADMIN_KEY} Admin] alert\n  -> running alert\n", out)
        self.assertNotIn("Shelter", out)
        self.assertNotIn("posted to", out)

    # --- unrecognized messages and the cooldown

    async def test_unrecognized_message_gets_reply(self):
        await self.start()
        await self.radio.dm(STRANGER, "hello")
        self.assertEqual(self.radio.sent, [("Stranger", UNRECOGNIZED_REPLY)])

    async def test_blank_message_gets_no_reply(self):
        await self.start()
        await self.radio.dm(STRANGER, "   ")
        self.assertEqual(self.radio.sent, [])

    async def test_unrecognized_cooldown_per_sender(self):
        await self.start()
        await self.radio.dm(STRANGER, "hello")
        await self.radio.dm(STRANGER, "anyone?")
        await self.radio.dm(STRANGER, "alert hi")  # denials share the same cooldown
        await self.radio.dm(DANA, "foo")  # a different sender is unaffected
        self.assertEqual(self.radio.sent, [("Stranger", UNRECOGNIZED_REPLY),
                                           ("Dana", UNRECOGNIZED_REPLY)])
        self.assertIn("not replying (replied within 300s)", self.out.getvalue())

        self.clock += UNRECOGNIZED_COOLDOWN
        await self.radio.dm(STRANGER, "hello again")
        self.assertEqual(self.radio.sent[-1], ("Stranger", UNRECOGNIZED_REPLY))

    # --- suggestions for mistyped commands

    async def test_an_admin_is_told_the_nearest_command(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "alret shelter open")
        await self.radio.dm(ADMIN_KEY, "alret shelter open")  # no cooldown on suggestions
        suggestion = ("Admin", "unknown command alret; did you mean alert? help lists yours")
        self.assertEqual(self.radio.sent, [suggestion] * 2)
        self.assertIn("unrecognized command; suggesting alert", self.out.getvalue())
        self.assertNotIn("shelter", self.replies()[0])  # only the first word is repeated

    async def test_others_get_no_suggestion(self):
        await self.start()
        await self.radio.dm(STRANGER, "hepl")
        self.assertEqual(self.radio.sent, [("Stranger", UNRECOGNIZED_REPLY)])

    async def test_nothing_close_gets_the_usual_reply(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "good morning everyone")
        self.assertEqual(self.replies(), [UNRECOGNIZED_REPLY])

    # --- permissions

    async def test_admin_commands_are_for_admins(self):
        await self.start()
        await self.radio.dm(STRANGER, "alert hi")
        self.assertEqual(self.radio.channel_sent, [])
        self.assertEqual(self.replies(), [UNRECOGNIZED_REPLY])
        self.assertIn("alert denied: sender not approved", self.out.getvalue())
        await self.radio.dm(ADMIN_KEY, "alert Shelter open")
        self.assertEqual(self.radio.channel_sent, [(0, "Shelter open")])
        self.assertEqual(self.radio.sent[-1], ("Admin", "alert: posted to Public"))

    async def test_testalert_posts_the_test_message(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "testalert")
        self.assertEqual(self.radio.channel_sent,
                         [(0, "TEST: this is a test of the weather alerts on this channel. No action needed.")])
        self.assertEqual(self.replies(), ["testalert: posted to Public"])

    async def test_rights_need_the_full_key_in_the_config(self):
        # A contact whose key shares the admin's prefix but differs after it.
        lookalike = ADMIN_KEY + "11" * 26
        await self.start(contacts={lookalike: "Admin"})
        await self.radio.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(self.radio.channel_sent, [])
        self.assertEqual(self.replies(), [UNRECOGNIZED_REPLY])

    async def test_shared_prefix_identifies_nobody(self):
        # An impostor with the admin's prefix: neither contact gets rights,
        # whichever of them sent the message.
        impostor = ADMIN_KEY + "11" * 26
        await self.start(contacts={ADMIN_KEY: "Admin", impostor: "Admin"})
        await self.radio.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(self.radio.channel_sent, [])
        out = self.out.getvalue()
        self.assertIn(f"(2 contacts share key prefix {ADMIN_KEY}; sender not identified; one is an admin, so "
                      "remove the impostor from the radio)", out)
        self.assertIn("alert denied: sender not approved", out)

    async def test_reply_goes_to_the_full_key(self):
        await self.start()
        sent_to = []
        original = self.radio.commands.send_msg_with_retry

        async def record(contact, text):
            sent_to.append(contact["public_key"])
            return await original(contact, text)

        self.radio.commands.send_msg_with_retry = record
        await self.radio.dm(ADMIN_KEY, "help")
        self.assertEqual(sent_to, [full_key(ADMIN_KEY)])

    async def test_a_new_contact_gets_rights_without_restart(self):
        # Messages from a node the bot hasn't loaded yet: refresh, then match.
        await self.start(contacts={})
        self.radio.stored[full_key(ADMIN_KEY)] = "Admin"
        await self.radio.dm(ADMIN_KEY, "help")
        self.assertEqual(self.replies(), ["commands: help, alert, testalert. Send help <command> for usage"])

    async def test_rate_limit_replies_once_then_stays_silent(self):
        await self.start(CONFIG + '\n[limits]\nadmin_rate = "2/hour"\n')
        for _ in range(4):
            await self.radio.dm(ADMIN_KEY, "help")
        replies = self.replies()
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[2], "help: limit reached, try again in 60 min")
        out = self.out.getvalue()
        self.assertIn("  -> help limit reached (2/hour); replying once\n", out)
        self.assertIn("  -> help limit reached; not replying\n", out)

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

[commands.long_error]
handler = "tests.test_bot:long_error"
permission = "public"

[commands.missing]
handler = "no_such_module_xyz:thing"
permission = "public"
"""

    async def test_plugin_from_config(self):
        await self.start(CONFIG + self.PLUGINS)
        out = self.out.getvalue()
        self.assertIn("  public commands (anyone): echo, slow, long_error\n", out)
        self.assertIn("Warning: Could not load missing (no_such_module_xyz:thing)", out)
        await self.radio.dm(STRANGER, "echo hi there")
        self.assertEqual(self.replies(), ["> hi there"])
        self.assertNotIn("hi there", self.out.getvalue())  # neither the text nor the reply

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
        await self.start(CONFIG.replace('help = { permission = "admin" }', 'help = { permission = "public" }')
                         + self.PLUGINS)
        await self.radio.dm(STRANGER, "help")
        await self.radio.dm(ADMIN_KEY, "help")
        await self.radio.dm(STRANGER, "help alert")
        self.assertEqual(self.replies(), [
            "commands: help, echo, slow, long_error. Send help <command> for usage",
            "commands: help, alert, testalert, echo, slow, long_error. Send help <command> for usage",
            "help: no command alert"])

    # --- command failures

    async def test_command_error_is_sent_back(self):
        await self.start()
        await self.radio.dm(ADMIN_KEY, "alert")
        self.assertEqual(self.replies(), ["usage: alert <message>"])
        self.assertIn("  alert: refused\n", self.out.getvalue())

    async def test_unexpected_error_sends_generic_failure(self):
        await self.start()
        with mock.patch("mesh_contingency.commands.alert.AlertCommand.execute",
                        mock.AsyncMock(side_effect=OSError("radio gone"))):
            await self.radio.dm(ADMIN_KEY, "alert Shelter open")
        self.assertEqual(self.replies(), ["alert: failed"])
        self.assertIn("alert failed: OSError\n", self.out.getvalue())
        self.assertNotIn("radio gone", self.out.getvalue())

    async def test_long_reply_is_truncated(self):
        await self.start(CONFIG + self.PLUGINS)
        await self.radio.dm(STRANGER, "long_error")
        (reply,) = self.replies()
        self.assertEqual(len(reply), MAX_REPLY_LEN)
        self.assertTrue(reply.startswith("nope nope"))
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
        self.assertEqual(self.radio.sent, [("LateNode", UNRECOGNIZED_REPLY)])

    async def test_no_contact_to_reply_to(self):
        await self.start()
        await self.radio.dm("c0ffeec0ffee", "hello")
        self.assertEqual(self.radio.sent, [])
        self.assertIn("(no contact c0ffeec0ffee to send reply to", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
