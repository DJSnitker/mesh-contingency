import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from mesh_contingency.api import ADMIN, PUBLIC, USER, CommandError, Sender
from mesh_contingency.commands.email import EmailCommand
from mesh_contingency.commands.emailall import EmailAllCommand
from mesh_contingency.commands.mail import ADDRESS_RE, BODY, DISCLAIMER, SUBJECT, send_email
from mesh_contingency.commands.quickim import QuickImCommand
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0d0d0d0d0d0")
BOB = Sender("Bob", "b0b0b0b0b0b0")
USERS = {
    "d0d0d0d0d0d0": {"quickim": "partner@example.com",
                     "emailall": ["a@example.com", "b@example.com"]},
    "b0b0b0b0b0b0": {"quickim": ["bob1@example.com", "bob2@example.com"]},
    "c0c0c0c0c0c0": {"name": "No addresses"},
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
        with self.assertRaisesRegex(RuntimeError, "`mail` failed: no sendmail"):
            self.send(result=completed(1, stderr="no sendmail\n"))
        with self.assertRaisesRegex(RuntimeError, "exit status 2"):
            self.send(result=completed(2))

    def test_mail_missing(self):
        with mock.patch("mesh_contingency.commands.mail.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                send_email(["a@example.com"], "s", "b")

    def test_mail_timeout(self):
        with mock.patch("mesh_contingency.commands.mail.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("mail", 30)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                send_email(["a@example.com"], "s", "b")


class MailCommandTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch("mesh_contingency.commands.mail.send_email")
        self.send_email = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_sent(self, to, text, sender_name="Dana"):
        self.send_email.assert_called_once_with(
            to, SUBJECT.format(sender=sender_name), BODY.format(text=text, disclaimer=DISCLAIMER))


class QuickImTest(MailCommandTestCase):
    def test_recipients_per_user_accept_string_or_list(self):
        cmd = QuickImCommand(make_context("quickim", users=USERS))
        self.assertEqual(cmd.recipients, {
            "d0d0d0d0d0d0": ["partner@example.com"],
            "b0b0b0b0b0b0": ["bob1@example.com", "bob2@example.com"],
        })
        self.assertTrue(cmd.enabled)
        self.assertFalse(QuickImCommand(make_context("quickim")).enabled)

    async def test_sends_to_senders_own_addresses(self):
        result = await QuickImCommand(make_context("quickim", users=USERS)).execute("Running late", DANA)
        self.assert_sent(["partner@example.com"], "Running late")
        self.assertEqual(result.reply, "quickim: sent")
        self.assertIn("partner@example.com", result.console)

    async def test_other_user_gets_their_own_addresses(self):
        await QuickImCommand(make_context("quickim", users=USERS)).execute("hi", BOB)
        self.assert_sent(["bob1@example.com", "bob2@example.com"], "hi", "Bob")

    async def test_usage_and_not_configured(self):
        cmd = QuickImCommand(make_context("quickim", users=USERS))
        with self.assertRaisesRegex(CommandError, "usage: quickim <message>"):
            await cmd.execute("", DANA)
        with self.assertRaisesRegex(CommandError, "quickim: not configured for you"):
            await cmd.execute("hi", Sender("Nobody", "c0c0c0c0c0c0"))
        self.send_email.assert_not_called()

    async def test_mail_failure_propagates(self):
        self.send_email.side_effect = RuntimeError("`mail` failed")
        with self.assertRaises(RuntimeError):
            await QuickImCommand(make_context("quickim", users=USERS)).execute("hi", DANA)

    async def test_message_starting_with_an_address_is_refused(self):
        commands = {}
        ctx = make_context("quickim", users=USERS, commands=commands)
        quickim = commands["quickim"] = QuickImCommand(ctx)
        email = EmailCommand(make_context("email", users=USERS, commands=commands))
        with self.assertRaisesRegex(CommandError, "^quickim: message starts with an address; send just the message$"):
            await quickim.execute("bob@example.com hi", DANA)  # no email command loaded
        commands["email"] = email
        email.permission = USER
        with self.assertRaisesRegex(CommandError, "to email it, use email <address> <message>$"):
            await quickim.execute("bob@example.com hi", DANA)
        email.permission = ADMIN  # Dana may not use it, so don't suggest it
        with self.assertRaisesRegex(CommandError, "send just the message$"):
            await quickim.execute("bob@example.com hi", DANA)
        email.permission = PUBLIC
        with self.assertRaisesRegex(CommandError, "to email it, use email"):
            await quickim.execute("bob@example.com hi", BOB)
        self.send_email.assert_not_called()
        await quickim.execute("hi bob@example.com", DANA)  # an address later on is fine
        self.assert_sent(["partner@example.com"], "hi bob@example.com")

    def test_body_ends_with_disclaimer(self):
        body = BODY.format(text="msg", disclaimer=DISCLAIMER)
        self.assertEqual(body, "msg\n\n" + DISCLAIMER)
        self.assertTrue(DISCLAIMER.startswith("This message was triggered from an external relayed radio signal"))


class EmailAllTest(MailCommandTestCase):
    async def test_uses_group_list(self):
        cmd = EmailAllCommand(make_context("emailall", users=USERS))
        self.assertEqual(cmd.name, "emailall")
        self.assertEqual(cmd.recipients, {"d0d0d0d0d0d0": ["a@example.com", "b@example.com"]})
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


if __name__ == "__main__":
    unittest.main()
