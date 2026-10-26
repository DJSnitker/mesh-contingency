import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from mesh_contingency.api import ADMIN, PUBLIC, USER, CommandError, Sender
from mesh_contingency.commands.email import EmailCommand
from mesh_contingency.commands.emailall import EmailAllCommand
from mesh_contingency.commands.mail import (
    ADDRESS_RE,
    BODY,
    DISCLAIMER,
    LOGIN_REFUSED,
    NO_INTERNET,
    SUBJECT,
    SendError,
    reason_for,
    send_email,
)
from mesh_contingency.commands.qm import QmCommand
from mesh_contingency.directory import Directory
from mesh_contingency.limits import Limits
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0" * 32)
BOB = Sender("Bob", "b0" * 32)
USERS = {
    "d0" * 32: {"qm": "partner@example.com",
                     "emailall": ["a@example.com", "b@example.com"]},
    "b0" * 32: {"qm": ["bob1@example.com", "bob2@example.com"]},
    "c0" * 32: {"name": "No addresses"},
}


def completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class SendEmailTest(unittest.TestCase):
    def send(self, to=("a@example.com",), subject="Subject", body="Body", result=None):
        with mock.patch("mesh_contingency.commands.mail.subprocess.run", return_value=result or completed()) as run:
            send_email(list(to), subject, body)
        return run

    def test_runs_mail_without_shell(self):
        run = self.send(to=["a@example.com", "b@example.com"], subject="Hi", body="line1\nline2")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["mail", "-s", "Hi", "a@example.com", "b@example.com"])
        self.assertEqual(kwargs["input"], "line1\nline2\n")
        self.assertTrue(kwargs["text"])
        self.assertNotIn("shell", kwargs)

    def test_strips_control_characters_from_subject(self):
        run = self.send(subject="From: Eve\nBcc: x@evil.com\r\t")
        self.assertEqual(run.call_args.args[0][2], "From: EveBcc: x@evil.com")

    def test_indents_tilde_lines(self):
        run = self.send(body="~!rm -rf /\nok\n~v")
        self.assertEqual(run.call_args.kwargs["input"], " ~!rm -rf /\nok\n ~v\n")

    def test_failure_exit_status(self):
        with self.assertRaisesRegex(SendError, "`mail` failed: no sendmail"):
            self.send(result=completed(1, stderr="no sendmail\n"))
        with self.assertRaisesRegex(SendError, "exit status 2"):
            self.send(result=completed(2))

    def test_failure_is_one_line_with_a_reason(self):
        stderr = ("msmtp: cannot locate host smtp.example.com: Name or service not known\n"
                  "msmtp: could not send mail\n/home/node/dead.letter 8/146\n... message not sent\n")
        with self.assertRaises(SendError) as caught:
            self.send(result=completed(4, stderr=stderr))
        self.assertEqual(str(caught.exception), "`mail` failed: " + " ".join(stderr.split()))
        self.assertEqual(caught.exception.reason, NO_INTERNET)

    def test_unsent_message_is_not_saved(self):
        run = self.send()
        self.assertEqual(run.call_args.kwargs["env"]["DEAD"], "/dev/null")

    def test_mail_missing(self):
        with mock.patch("mesh_contingency.commands.mail.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(SendError, "not found") as caught:
                send_email(["a@example.com"], "s", "b")
        self.assertEqual(caught.exception.reason, ("email isn't set up on the node", "tell an admin"))

    def test_mail_timeout(self):
        with mock.patch("mesh_contingency.commands.mail.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("mail", 30)):
            with self.assertRaisesRegex(SendError, "timed out") as caught:
                send_email(["a@example.com"], "s", "b")
        self.assertEqual(caught.exception.reason, ("email timed out", "try again later"))


class ReasonTest(unittest.TestCase):
    """msmtp's own wording, as mail passes it on."""

    def test_no_internet(self):
        for output in ["msmtp: cannot locate host smtp.gmail.com: Temporary failure in name resolution",
                       "msmtp: cannot connect to smtp.gmail.com, port 587: Network is unreachable",
                       "msmtp: cannot connect to smtp.gmail.com, port 587: Connection refused",
                       "msmtp: network read error: The operation timed out"]:
            self.assertEqual(reason_for(output), NO_INTERNET, output)

    def test_login_refused(self):
        self.assertEqual(reason_for("msmtp: server message: 535-5.7.8 Username and Password not accepted.\n"
                                    "msmtp: authentication failed (method PLAIN)"), LOGIN_REFUSED)

    def test_address_refused(self):
        self.assertEqual(reason_for("msmtp: recipient address x@example.com not accepted by the server"),
                         ("an address was refused", "check the address"))

    def test_anything_else(self):
        self.assertEqual(reason_for("... message not sent"), ("email error at the node", "tell an admin"))
        self.assertEqual(reason_for(""), ("email error at the node", "tell an admin"))


class MailCommandTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch("mesh_contingency.commands.mail.send_email")
        self.send_email = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_sent(self, to, text, sender_name="Dana"):
        self.send_email.assert_called_once_with(
            to, SUBJECT.format(sender=sender_name), BODY.format(text=text, disclaimer=DISCLAIMER))


class QmTest(MailCommandTestCase):
    def test_recipients_per_user_accept_string_or_list(self):
        cmd = QmCommand(make_context("qm", users=USERS))
        self.assertEqual(cmd.recipients, {
            "d0" * 32: ["partner@example.com"],
            "b0" * 32: ["bob1@example.com", "bob2@example.com"],
        })
        self.assertTrue(cmd.enabled)
        self.assertFalse(QmCommand(make_context("qm")).enabled)

    async def test_addresses_read_when_sending(self):
        # The users file can change while the bot runs.
        directory = Directory(USERS)
        cmd = QmCommand(make_context("qm", directory=directory))
        directory._users = {DANA.public_key: {"qm": "new@example.com"}}
        await cmd.execute("hi", DANA)
        self.assert_sent(["new@example.com"], "hi")
        directory._users = {}
        self.assertFalse(cmd.enabled)
        with self.assertRaisesRegex(CommandError, "qm: not configured for you"):
            await cmd.execute("hi", DANA)

    async def test_sends_to_senders_own_addresses(self):
        result = await QmCommand(make_context("qm", users=USERS)).execute("Running late", DANA)
        self.assert_sent(["partner@example.com"], "Running late")
        self.assertEqual(result.reply, "qm: sent")
        self.assertEqual(result.console, "Sent email to 1 address(es)")  # not to whom, nor what
        self.assertTrue(QmCommand.private)

    async def test_other_user_gets_their_own_addresses(self):
        await QmCommand(make_context("qm", users=USERS)).execute("hi", BOB)
        self.assert_sent(["bob1@example.com", "bob2@example.com"], "hi", "Bob")

    async def test_usage_and_not_configured(self):
        cmd = QmCommand(make_context("qm", users=USERS))
        with self.assertRaisesRegex(CommandError, "usage: qm <message>"):
            await cmd.execute("", DANA)
        with self.assertRaisesRegex(CommandError, "qm: not configured for you"):
            await cmd.execute("hi", Sender("Nobody", "c0" * 32))
        self.send_email.assert_not_called()

    async def test_mail_failure_says_why(self):
        self.send_email.side_effect = SendError("`mail` failed: msmtp: cannot connect", NO_INTERNET)
        state = State()
        with mock.patch("mesh_contingency.commands.mail.time.time", return_value=500.0):
            with self.assertRaises(SendError) as caught:
                await QmCommand(make_context("qm", users=USERS, state=state)).execute("hi", DANA)
        self.assertEqual(caught.exception.reply, "qm: not sent, no internet at the node; try again later")
        self.assertEqual(state.emails.last_failure, (500.0, "no internet at the node"))

    async def test_message_starting_with_an_address_is_refused(self):
        commands = {}
        ctx = make_context("qm", users=USERS, commands=commands)
        qm = commands["qm"] = QmCommand(ctx)
        email = EmailCommand(make_context("email", users=USERS, commands=commands))
        with self.assertRaisesRegex(CommandError, "^qm: message starts with an address; send just the message$"):
            await qm.execute("bob@example.com hi", DANA)  # no email command loaded
        commands["email"] = email
        email.permission = USER
        with self.assertRaisesRegex(CommandError, "to email it, use email <address> <message>$"):
            await qm.execute("bob@example.com hi", DANA)
        email.permission = ADMIN  # Dana may not use it, so don't suggest it
        with self.assertRaisesRegex(CommandError, "send just the message$"):
            await qm.execute("bob@example.com hi", DANA)
        email.permission = PUBLIC
        with self.assertRaisesRegex(CommandError, "to email it, use email"):
            await qm.execute("bob@example.com hi", BOB)
        self.send_email.assert_not_called()
        await qm.execute("hi bob@example.com", DANA)  # an address later on is fine
        self.assert_sent(["partner@example.com"], "hi bob@example.com")

    def test_body_ends_with_disclaimer(self):
        body = BODY.format(text="msg", disclaimer=DISCLAIMER)
        self.assertEqual(body, "msg\n\n" + DISCLAIMER)
        self.assertTrue(DISCLAIMER.startswith("This message was triggered from an external relayed radio signal"))


class EmailAllTest(MailCommandTestCase):
    async def test_uses_group_list(self):
        cmd = EmailAllCommand(make_context("emailall", users=USERS))
        self.assertEqual(cmd.name, "emailall")
        self.assertEqual(cmd.recipients, {"d0" * 32: ["a@example.com", "b@example.com"]})
        result = await cmd.execute("Meeting moved", DANA)
        self.assert_sent(["a@example.com", "b@example.com"], "Meeting moved")
        self.assertEqual(result.reply, "emailall: sent")

    async def test_refuses_address_first_too(self):
        with self.assertRaisesRegex(CommandError, "emailall: message starts with an address"):
            await EmailAllCommand(make_context("emailall", users=USERS)).execute("a@example.com hi", DANA)

    async def test_user_without_group(self):
        with self.assertRaisesRegex(CommandError, "emailall: not configured for you"):
            await EmailAllCommand(make_context("emailall", users=USERS)).execute("hi", BOB)


class EmailTest(MailCommandTestCase):
    def test_always_enabled(self):
        self.assertTrue(EmailCommand(make_context("email")).enabled)  # needs no addresses

    async def test_sends_to_address_in_message(self):
        result = await EmailCommand(make_context("email")).execute("friend@example.org  Hello   there ", DANA)
        self.assert_sent(["friend@example.org"], "Hello   there")
        self.assertEqual(result.reply, "email: sent")

    async def test_usage(self):
        for text in ("", "friend@example.org"):
            with self.assertRaisesRegex(CommandError, "usage: email <address> <message>"):
                await EmailCommand(make_context("email")).execute(text, DANA)

    async def test_rejects_unsafe_addresses(self):
        for bad in ("-oProxyCommand=x@y.com", "|touch@x.com", "/etc/passwd", "user@localhost",
                    "a@b.com,c@d.com", "not-an-email", "a@b.c"):
            with self.assertRaisesRegex(CommandError, "email: invalid address"):
                await EmailCommand(make_context("email")).execute(f"{bad} hi", DANA)
        self.send_email.assert_not_called()

    def test_address_pattern_accepts_normal_addresses(self):
        for good in ("a@example.com", "first.last+tag@mail.example.co.uk", "x_y%z@sub-domain.example.org"):
            self.assertTrue(ADDRESS_RE.fullmatch(good), good)

    def test_address_must_start_with_a_letter_or_digit(self):
        for bad in ("+tag@example.com", "%x@example.com", ".dot@example.com", "_x@example.com"):
            self.assertIsNone(ADDRESS_RE.fullmatch(bad), bad)
        self.assertTrue(ADDRESS_RE.fullmatch("7days@example.com"))


class EmailCapsTest(MailCommandTestCase):
    def setUp(self):
        super().setUp()
        self.now = 1_000_000.0
        self.enterContext(mock.patch("mesh_contingency.limits.time.time", lambda: self.now))
        state = State()
        self.limits = Limits(emails_per_day=3, emails_per_day_total=5)
        directory = Directory(USERS)
        self.email, self.emailall = (
            cls(make_context(name, directory=directory, state=state, limits=self.limits))
            for cls, name in [(EmailCommand, "email"), (EmailAllCommand, "emailall")])

    async def test_per_sender_cap_counts_commands(self):
        self.limits.emails_per_day_total = 0
        await self.emailall.execute("hi all", DANA)  # 2 addresses, but one email
        await self.email.execute("x@example.com hi", DANA)
        await self.emailall.execute("hi again", DANA)
        with self.assertRaisesRegex(CommandError, r"^email: you've reached your daily email limit \(3\); "
                                                  r"try again later$"):
            await self.email.execute("x@example.com again", DANA)
        await self.email.execute("x@example.com from bob", BOB)  # others aren't affected
        self.now += 86401  # a day later it frees up
        await self.email.execute("x@example.com next day", DANA)

    async def test_total_cap_counts_addresses(self):
        await self.emailall.execute("hi", DANA)  # 2
        await self.email.execute("x@example.com hi", BOB)  # 3
        await self.email.execute("x@example.com hi", BOB)  # 4
        with self.assertRaisesRegex(CommandError, "^emailall: the node's daily email limit is reached"):
            await self.emailall.execute("hi again", DANA)  # 2 more would make 6
        await self.email.execute("x@example.com hi", DANA)  # 1 more fits
        self.assertEqual(self.send_email.call_count, 4)

    async def test_failed_send_is_not_counted(self):
        self.send_email.side_effect = SendError("down", NO_INTERNET)
        for _ in range(4):
            with self.assertRaises(SendError):
                await self.email.execute("x@example.com hi", DANA)
        self.send_email.side_effect = None
        await self.email.execute("x@example.com hi", DANA)

    async def test_zero_means_no_cap(self):
        self.limits.emails_per_day = self.limits.emails_per_day_total = 0
        for _ in range(10):
            await self.email.execute("x@example.com hi", DANA)

if __name__ == "__main__":
    unittest.main()
