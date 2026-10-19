import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from commands.base import USER, CommandError, Sender
from commands.notify_default import BODY, DISCLAIMER, SUBJECT, NotifyDefaultCommand, send_email
from commands.notify_email import ADDRESS_RE, NotifyEmailCommand
from commands.notify_group import NotifyGroupCommand

DANA = Sender("Dana", "d0d0d0d0d0d0")
BOB = Sender("Bob", "b0b0b0b0b0b0")
USERS = {
    "d0d0d0d0d0d0": {"notify_default": "partner@example.com",
                     "notify_group": ["a@example.com", "b@example.com"]},
    "b0b0b0b0b0b0": {"notify_default": ["bob1@example.com", "bob2@example.com"]},
    "c0c0c0c0c0c0": {"name": "No addresses"},
}


def completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class SendEmailTest(unittest.TestCase):
    def send(self, to=("a@example.com",), subject="Subject", body="Body", result=None):
        with mock.patch("commands.notify_default.subprocess.run", return_value=result or completed()) as run:
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
        with mock.patch("commands.notify_default.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                send_email(["a@example.com"], "s", "b")

    def test_mail_timeout(self):
        with mock.patch("commands.notify_default.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("mail", 30)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                send_email(["a@example.com"], "s", "b")


class NotifyCommandTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch("commands.notify_default.send_email")
        self.send_email = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_sent(self, to, text, sender_name="Dana"):
        self.send_email.assert_called_once_with(
            to, SUBJECT.format(sender=sender_name), BODY.format(text=text, disclaimer=DISCLAIMER))


class NotifyDefaultTest(NotifyCommandTestCase):
    def test_requires_user_permission(self):
        for cls in (NotifyDefaultCommand, NotifyGroupCommand, NotifyEmailCommand):
            self.assertEqual(cls.permission, USER)

    def test_recipients_per_user_accept_string_or_list(self):
        cmd = NotifyDefaultCommand(USERS)
        self.assertEqual(cmd.recipients, {
            "d0d0d0d0d0d0": ["partner@example.com"],
            "b0b0b0b0b0b0": ["bob1@example.com", "bob2@example.com"],
        })
        self.assertTrue(cmd.enabled)
        self.assertFalse(NotifyDefaultCommand({}).enabled)

    async def test_sends_to_senders_own_addresses(self):
        result = await NotifyDefaultCommand(USERS).execute("Running late", DANA)
        self.assert_sent(["partner@example.com"], "Running late")
        self.assertEqual(result.reply, "notify_default: sent")
        self.assertIn("partner@example.com", result.console)

    async def test_other_user_gets_their_own_addresses(self):
        await NotifyDefaultCommand(USERS).execute("hi", BOB)
        self.assert_sent(["bob1@example.com", "bob2@example.com"], "hi", "Bob")

    async def test_usage_and_not_configured(self):
        cmd = NotifyDefaultCommand(USERS)
        with self.assertRaisesRegex(CommandError, "usage: notify_default <message>"):
            await cmd.execute("", DANA)
        with self.assertRaisesRegex(CommandError, "notify_default: not configured for you"):
            await cmd.execute("hi", Sender("Nobody", "c0c0c0c0c0c0"))
        self.send_email.assert_not_called()

    async def test_mail_failure_propagates(self):
        self.send_email.side_effect = RuntimeError("`mail` failed")
        with self.assertRaises(RuntimeError):
            await NotifyDefaultCommand(USERS).execute("hi", DANA)

    def test_body_ends_with_disclaimer(self):
        body = BODY.format(text="msg", disclaimer=DISCLAIMER)
        self.assertEqual(body, "msg\n\n" + DISCLAIMER)
        self.assertTrue(DISCLAIMER.startswith("This message was triggered from an external relayed radio signal"))


class NotifyGroupTest(NotifyCommandTestCase):
    async def test_uses_group_list(self):
        cmd = NotifyGroupCommand(USERS)
        self.assertEqual(cmd.name, "notify_group")
        self.assertEqual(cmd.recipients, {"d0d0d0d0d0d0": ["a@example.com", "b@example.com"]})
        result = await cmd.execute("Meeting moved", DANA)
        self.assert_sent(["a@example.com", "b@example.com"], "Meeting moved")
        self.assertEqual(result.reply, "notify_group: sent")

    async def test_user_without_group(self):
        with self.assertRaisesRegex(CommandError, "notify_group: not configured for you"):
            await NotifyGroupCommand(USERS).execute("hi", BOB)


class NotifyEmailTest(NotifyCommandTestCase):
    def test_always_enabled(self):
        self.assertTrue(NotifyEmailCommand().enabled)

    async def test_sends_to_address_in_message(self):
        result = await NotifyEmailCommand().execute("friend@example.org  Hello   there ", DANA)
        self.assert_sent(["friend@example.org"], "Hello   there")
        self.assertEqual(result.reply, "notify_email: sent")

    async def test_usage(self):
        for text in ("", "friend@example.org"):
            with self.assertRaisesRegex(CommandError, "usage: notify_email <address> <message>"):
                await NotifyEmailCommand().execute(text, DANA)

    async def test_rejects_unsafe_addresses(self):
        for bad in ("-oProxyCommand=x@y.com", "|touch@x.com", "/etc/passwd", "user@localhost",
                    "a@b.com,c@d.com", "not-an-email", "a@b.c"):
            with self.assertRaisesRegex(CommandError, "notify_email: invalid address"):
                await NotifyEmailCommand().execute(f"{bad} hi", DANA)
        self.send_email.assert_not_called()

    def test_address_pattern_accepts_normal_addresses(self):
        for good in ("a@example.com", "first.last+tag@mail.example.co.uk", "x_y%z@sub-domain.example.org"):
            self.assertTrue(ADDRESS_RE.fullmatch(good), good)


if __name__ == "__main__":
    unittest.main()
