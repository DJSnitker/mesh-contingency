"""mesh-contingency-console: it opens the link in the running bot's
console.url, and says why when it can't."""

import asyncio
import contextlib
import io
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.testing import make_context
from mesh_contingency.web import URL_FILE, aiohttp_missing
from mesh_contingency.web.launch import main

KEY = "Kq3_x-9ZpL0aB7cDeFgHiJ"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LaunchTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config = self.folder / "config.toml"
        self.config.write_text("[console]\nenabled = true\n")
        self.opened = []
        self.enterContext(mock.patch("webbrowser.open", side_effect=lambda uri: self.opened.append(uri) or True))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))

    def write_url(self, url):
        (self.folder / URL_FILE).write_text(url + "\n")

    def fails(self, pattern):
        with self.assertRaisesRegex(SystemExit, pattern):
            main(["-c", str(self.config)])
        self.assertEqual(self.opened, [])


class MistakesTest(LaunchTestCase):
    def test_console_off(self):
        self.config.write_text("[console]\nenabled = false\n")
        self.fails(r"^The web console is off: set enabled = true under \[console\]")

    def test_no_config_is_off(self):
        self.config.unlink()
        self.fails("The web console is off")

    def test_bot_not_running(self):
        self.fails(rf"^No .*{URL_FILE}: the bot isn't running.*systemctl --user status mesh-contingency")

    def test_not_a_console_link(self):
        for url in ["https://example.com/?key=x", "http://192.168.1.5:8737/?key=abc", "http://127.0.0.1:8737/",
                    "http://127.0.0.1:8737/?key=a b", "file:///etc/passwd"]:
            with self.subTest(url=url):
                self.write_url(url)
                self.fails("doesn't hold a console link; restart the bot")

    def test_nothing_answers(self):
        self.write_url(f"http://127.0.0.1:{free_port()}/?key={KEY}")
        self.fails(r"^Nothing answers at http://127\.0\.0\.1:\d+/: the bot isn't running")


@unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp: pip install -e .[console]")
class OpenTest(LaunchTestCase, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import web

        from mesh_contingency.web.server import make_app

        self.port = free_port()
        app = make_app(make_context("console"), KEY, self.port, static=self.folder / "static")
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", self.port).start()
        self.addAsyncCleanup(self.runner.cleanup)
        self.url = f"http://127.0.0.1:{self.port}/?key={KEY}"
        self.write_url(self.url)

    async def launch(self, *args):
        # The command blocks, so it runs beside the server, not in its loop.
        return await asyncio.to_thread(main, ["-c", str(self.config), *args])

    async def test_opens_the_link(self):
        await self.launch()
        self.assertEqual(self.opened, [self.url])
        self.assertIn(f"Opened the web console (http://127.0.0.1:{self.port}/)", self.out.getvalue())

    async def test_an_old_key(self):
        self.write_url(f"http://127.0.0.1:{self.port}/?key=old-key")
        with self.assertRaisesRegex(SystemExit, "didn't take the key in console.url; restart the bot"):
            await self.launch()
        self.assertEqual(self.opened, [])

    async def test_no_browser(self):
        with mock.patch("webbrowser.open", return_value=False), \
                self.assertRaisesRegex(SystemExit, f"No browser to open here.*{URL_FILE}"):
            await self.launch()


if __name__ == "__main__":
    unittest.main()
