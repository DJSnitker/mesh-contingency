import contextlib
import io
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path

from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, make_context
from mesh_contingency.web import ConsoleSettings, aiohttp_missing, load_console

ALICE = "a1" * 32
BOB = "b0" * 32
ADMIN = "ad" * 32
KEY = "the-key"


class LoadConsoleTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_console({}), ConsoleSettings(False, 8737, "127.0.0.1"))

    def test_settings(self):
        self.assertEqual(load_console({"console": {"enabled": True, "port": 9000, "host": "localhost"}}),
                         ConsoleSettings(True, 9000, "localhost"))

    def test_mistakes(self):
        for section, message in [
            ({"listen": "0.0.0.0"}, r"^\[console\] may only set enabled, host, port\.$"),
            ({"enabled": "yes"}, r"enabled must be true or false"),
            ({"port": 80}, r"port must be a whole number from 1024 to 65535"),
            ({"port": True}, r"port must be a whole number"),
            ({"host": "0.0.0.0"}, r"host may only be 127\.0\.0\.1 or localhost"),
            ({"host": "192.168.1.5"}, r"host may only be 127\.0\.0\.1 or localhost"),
        ]:
            with self.assertRaisesRegex(SystemExit, message):
                load_console({"console": section})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp: pip install -e .[console]")
class ConsoleTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import CookieJar
        from aiohttp.test_utils import TestClient, TestServer

        from mesh_contingency.web.server import make_app

        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = State(self.folder)
        users = {ALICE: {"name": "Alice", "qm": "alice@example.com", "inbox_key": "secret"},
                 BOB: {"name": "Bob"}}
        self.radio = FakeMeshCore()
        self.ctx = make_context("console", users=users, admins={ADMIN}, state=self.state, radio=self.radio)
        self.port = free_port()
        self.host = f"127.0.0.1:{self.port}"
        server = TestServer(make_app(self.ctx, KEY, self.port), host="127.0.0.1", port=self.port)
        # A cookie for an IP address needs unsafe=True; browsers keep it anyway.
        self.client = TestClient(server, cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def log_in(self):
        response = await self.client.get(f"/?key={KEY}", allow_redirects=False)
        self.assertEqual(response.status, 302)
        return response

    async def get_json(self, path):
        response = await self.client.get(path)
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()


class GuardTest(ConsoleTestCase):
    async def test_nothing_without_the_key(self):
        for path in ("/", "/api/overview", "/api/users", "/nowhere"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 401, path)
            self.assertIn("console.url", await response.text())

    async def test_the_key_sets_a_cookie_and_leaves_the_address(self):
        response = await self.client.get(f"/api/history?key={KEY}&x=1", allow_redirects=False)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers["Location"], "/api/history?x=1")
        cookie = response.cookies["mesh_console"]
        self.assertEqual(cookie.value, KEY)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(await self.get_json("/api/history"), [])

    async def test_a_wrong_key(self):
        response = await self.client.get("/?key=guess", allow_redirects=False)
        self.assertEqual(response.status, 403)
        self.assertNotIn("mesh_console", response.cookies)
        response = await self.client.get("/api/overview", cookies={"mesh_console": "guess"})
        self.assertEqual(response.status, 401)

    async def test_only_this_computers_names_for_the_host(self):
        await self.log_in()
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", f"127.0.0.1:{self.port + 1}",
                     f"192.168.1.5:{self.port}"):
            response = await self.client.get("/api/overview", headers={"Host": host})
            self.assertEqual(response.status, 403, host)
            self.assertEqual(await response.text(), "Wrong host.\n")
        # The key is refused from a wrong host too: no cookie for a rebinding page.
        response = await self.client.get(f"/?key={KEY}", headers={"Host": "evil.example"}, allow_redirects=False)
        self.assertEqual(response.status, 403)
        response = await self.client.get("/api/history", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(response.status, 200)

    async def test_changes_need_this_origin(self):
        await self.log_in()
        for origin in (None, "http://evil.example", f"http://evil.example:{self.port}", "null"):
            headers = {"Origin": origin} if origin else {}
            response = await self.client.post("/api/history", headers=headers)
            self.assertEqual(response.status, 403, origin)
            self.assertEqual(await response.text(), "Wrong origin.\n")
        # Past the checks, there's nothing to post to (yet).
        response = await self.client.post("/api/history", headers={"Origin": f"http://{self.host}"})
        self.assertEqual(response.status, 405)

    async def test_the_page_without_the_app(self):
        await self.log_in()
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("app isn't built yet", await response.text())


class ReadTest(ConsoleTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.log_in()

    async def test_overview(self):
        self.state.counts["messages"] = 3
        self.state.store("requests.json").data[BOB[:2] * 32] = {"name": "Carol", "time": 5.0}
        found = await self.get_json("/api/overview")
        self.assertEqual(found["node"], self.radio.self_info.get("name"))
        self.assertEqual((found["users"], found["admins"], found["requests"]), (2, 1, 1))
        self.assertEqual(found["counts"], {"messages": 3, "sent": 0, "undelivered": 0, "errors": 0})
        self.assertIn("users 2 (1 admin)", found["health"])
        self.assertIn("join requests 1", found["health"])
        self.assertIsNone(found["watch"])

    async def test_users_without_secrets(self):
        self.state.saw(ADMIN, "Admin's Radio")
        self.state.store("status.json").data[BOB] = {"name": "Bob", "status": "ok", "time": 7.0}
        self.state.store("mailbox.json").data[ALICE] = [{"from": "Bob", "time": 1.0, "read": True, "text": "hi"},
                                                        {"from": "Bob", "time": 2.0, "read": False, "sealed": "x"}]
        found = await self.get_json("/api/users")
        self.assertEqual([(u["name"], u["user"], u["admin"]) for u in found],
                         [("Admin's Radio", False, True), ("Alice", True, False), ("Bob", True, False)])
        alice = found[1]
        self.assertEqual(alice["settings"], {"qm": "alice@example.com"})
        self.assertTrue(alice["passphrase"])
        self.assertEqual((alice["messages"], alice["unread"]), (2, 1))
        self.assertEqual(found[2]["checkin"], {"status": "ok", "time": 7.0})
        self.assertIsNotNone(found[0]["last_seen"])
        text = str(found)
        self.assertNotIn("secret", text)
        self.assertNotIn("inbox_key", text)

    async def test_requests_oldest_first(self):
        requests = self.state.store("requests.json").data
        requests["c" * 64] = {"name": "Carol", "time": 9.0}
        requests["d" * 64] = {"name": "Dan", "time": 3.0}
        found = await self.get_json("/api/requests")
        self.assertEqual([r["name"] for r in found], ["Dan", "Carol"])

    async def test_checkins_and_who_is_missing(self):
        statuses = self.state.store("status.json").data
        statuses[ALICE] = {"name": "Alice", "status": "ok", "time": 1.0}
        statuses[ADMIN] = {"name": "Admin", "status": "fine", "time": 2.0}
        found = await self.get_json("/api/checkins")
        self.assertEqual([c["name"] for c in found["checkins"]], ["Admin", "Alice"])
        self.assertEqual(found["missing"], [{"key": BOB, "name": "Bob"}])

    async def test_inbox_never_has_the_text(self):
        self.state.store("mailbox.json").data.update({
            ALICE: [{"from": "Bob", "time": 1.0, "read": False, "text": "meet at the church"},
                    {"from": "Dan", "time": 2.0, "read": True, "sealed": "c2VhbGVk"}],
            BOB: [],
        })
        found = await self.get_json("/api/inbox")
        self.assertEqual(found, [{"key": ALICE, "name": "Alice", "messages": [
            {"from": "Bob", "time": 1.0, "read": False, "sealed": False},
            {"from": "Dan", "time": 2.0, "read": True, "sealed": True}]}])

    async def test_history_newest_first(self):
        self.state.record("Admin", "approved Alice")
        self.state.record("Alice", "left")
        found = await self.get_json("/api/history")
        self.assertEqual([(e["by"], e["what"]) for e in found], [("Alice", "left"), ("Admin", "approved Alice")])
        self.assertEqual(len(self.state.store(HISTORY_FILE).data["entries"]), 2)


@unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp: pip install -e .[console]")
class ConsoleServerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))

    def server(self, port):
        from mesh_contingency.web.server import ConsoleServer

        return ConsoleServer(ConsoleSettings(True, port), make_context("console"), self.folder)

    async def test_start_writes_the_link_and_stop_removes_it(self):
        server = self.server(free_port())
        self.assertTrue(await server.start())
        url_file = self.folder / "console.url"
        self.assertEqual(url_file.read_text(), server.url + "\n")
        self.assertIn(f"?key={server.key}", server.url)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(url_file.stat().st_mode), 0o600)
        self.assertIn(f"Web console: {server.url}", self.out.getvalue())
        await server.stop()
        self.assertFalse(url_file.exists())

    async def test_a_new_key_each_start(self):
        self.assertNotEqual(self.server(1).key, self.server(1).key)

    async def test_a_port_in_use_leaves_the_bot_running(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            server = self.server(taken.getsockname()[1])
            self.assertFalse(await server.start())
        self.assertIn("Warning: web console not started: port", self.out.getvalue())
        self.assertFalse((self.folder / "console.url").exists())
        await server.stop()


if __name__ == "__main__":
    unittest.main()
