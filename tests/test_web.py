import asyncio
import contextlib
import io
import json
import os
import socket
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.alerts import message_limit
from mesh_contingency.api import ADMIN as ADMIN_LEVEL
from mesh_contingency.api import DISABLED, Command, CommandResult
from mesh_contingency.directory import Directory
from mesh_contingency.output import SafeOutput
from mesh_contingency.registry import Registry
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, make_context
from mesh_contingency.web import ConsoleSettings, aiohttp_missing, load_console

ALICE = "a1" * 32
BOB = "b0" * 32
ADMIN = "ad" * 32
KEY = "the-key"
EXAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "config.example.toml"


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
        self.directory = Directory(users, {ADMIN})
        # The built-in commands, with the permissions config.example.toml gives them.
        with open(EXAMPLE_CONFIG, "rb") as f:
            self.commands = Registry(tomllib.load(f)).build(self.directory, self.radio, self.state)
        self.ctx = make_context("console", directory=self.directory, state=self.state, radio=self.radio,
                                commands=self.commands)
        self.out = io.StringIO()
        self.output = SafeOutput(self.out, keep=50)
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.port = free_port()
        self.host = f"127.0.0.1:{self.port}"
        self.static = self.folder / "static"  # no app built, unless a test builds one
        self.app = make_app(self.ctx, KEY, self.port, output=self.output, static=self.static)
        server = TestServer(self.app, host="127.0.0.1", port=self.port)
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
        # Past the checks, history can't be posted to.
        response = await self.client.post("/api/history", headers={"Origin": f"http://{self.host}"})
        self.assertEqual(response.status, 405)

    async def test_the_page_without_the_app(self):
        await self.log_in()
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("app isn't built: in console/, run npm ci and npm run build", await response.text())

    async def test_every_response_says_what_the_page_may_load(self):
        for path in ("/", "/api/overview"):  # refused, and not
            for cookies in ({}, {"mesh_console": KEY}):
                response = await self.client.get(path, cookies=cookies)
                policy = response.headers["Content-Security-Policy"]
                self.assertIn("script-src 'self';", policy)
                self.assertIn("frame-ancestors 'none'", policy)
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")


class AppTest(ConsoleTestCase):
    """Serving the Angular build."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.static.mkdir()
        (self.static / "index.html").write_text("<mc-root></mc-root>")
        (self.static / "main-ABCD1234.js").write_text("console.log(1)")
        (self.static / "media").mkdir()
        (self.static / "media" / "inter-latin-400-normal-55WT6UWF.woff2").write_bytes(b"font")
        (self.static / "mesh-contingency-mark.svg").write_text("<svg/>")
        (self.folder / "secret.txt").write_text("not for the web")
        await self.log_in()

    async def test_the_app_and_its_pages(self):
        for path in ("/", "/users", "/inbox/sealed"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200, path)
            self.assertEqual(await response.text(), "<mc-root></mc-root>")
            self.assertEqual(response.headers["Cache-Control"], "no-cache")

    async def test_files_of_the_build(self):
        response = await self.client.get("/main-ABCD1234.js")
        self.assertEqual(await response.text(), "console.log(1)")
        self.assertIn("javascript", response.headers["Content-Type"])
        self.assertEqual(response.headers["Cache-Control"], "max-age=31536000, immutable")
        response = await self.client.get("/media/inter-latin-400-normal-55WT6UWF.woff2")
        self.assertEqual(await response.read(), b"font")
        response = await self.client.get("/mesh-contingency-mark.svg")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")  # no hash in its name

    async def test_a_missing_file_isnt_the_app(self):
        response = await self.client.get("/main-ZZZZ9999.js")
        self.assertEqual(response.status, 404)

    async def test_an_unknown_api_isnt_the_app(self):
        response = await self.client.get("/api/nosuch")
        self.assertEqual(response.status, 404)
        self.assertEqual(await response.json(), {"error": "no such API: /api/nosuch"})

    async def test_nothing_outside_the_build(self):
        from yarl import URL

        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/media/../../secret.txt"):
            response = await self.client.get(URL(path, encoded=True))
            self.assertNotEqual(await response.text(), "not for the web", path)


class ReadTest(ConsoleTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.log_in()

    async def test_overview(self):
        self.state.counts["messages"] = 3
        self.state.store("requests.json").data[BOB[:2] * 32] = {"name": "Carol", "time": 5.0}
        found = await self.get_json("/api/overview")
        self.assertEqual(found["node"], self.radio.self_info.get("name"))
        self.assertEqual(found["channel_limit"], message_limit(self.radio))
        self.assertEqual((found["users"], found["admins"], found["requests"]), (2, 1, 1))
        self.assertEqual(found["counts"], {"messages": 3, "sent": 0, "undelivered": 0, "errors": 0})
        self.assertIn("users 2 (1 admin)", found["health"])
        self.assertIn("join requests 1", found["health"])
        self.assertIsNone(found["watch"])
        self.assertIsNone(found["alerts"])

    async def test_overview_alerts_each_event_once_with_its_counties(self):
        from types import SimpleNamespace

        def alert(event):
            return {"event": event, "severity": None, "headline": None, "ends": None}

        self.state.alert_watcher = SimpleNamespace(
            settings=SimpleNamespace(counties=["Taylor, TX", "Jones, TX", "Brown, TX"]), last_check=5.0,
            problem=None, unmapped={},
            current={"Jones, TX": [alert("Wind Advisory")], "Brown, TX": [alert("Flood Warning")],
                     "Taylor, TX": [alert("Wind Advisory"), alert(None)]})
        found = (await self.get_json("/api/overview"))["alerts"]
        self.assertEqual(found, {"checked": 5.0, "problem": None, "active": [
            {"event": "Wind Advisory", "counties": ["Taylor, TX", "Jones, TX"]},
            {"event": "Alert", "counties": ["Taylor, TX"]},
            {"event": "Flood Warning", "counties": ["Brown, TX"]}]})

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

    async def test_weather_off_without_counties(self):
        found = await self.get_json("/api/weather")
        self.assertEqual((found["areas"], found["alerts_checked"], found["every_minutes"]), (None, None, 15))

    async def test_weather_for_each_county(self):
        from types import SimpleNamespace

        self.state.alert_watcher = SimpleNamespace(last_check=5.0, problem=None, current={})
        self.state.area_weather = SimpleNamespace(areas=lambda: [{"county": "Taylor, TX", "alerts": [],
                                                                  "text": "Clear", "problem": None}])
        found = await self.get_json("/api/weather")
        self.assertEqual(found["areas"], [{"county": "Taylor, TX", "alerts": [], "text": "Clear", "problem": None}])
        self.assertEqual((found["alerts_checked"], found["alerts_problem"]), (5.0, None))

    async def test_history_newest_first(self):
        self.state.record("Admin", "approved Alice")
        self.state.record("Alice", "left")
        found = await self.get_json("/api/history")
        self.assertEqual([(e["by"], e["what"]) for e in found], [("Alice", "left"), ("Admin", "approved Alice")])
        self.assertEqual(len(self.state.store(HISTORY_FILE).data["entries"]), 2)


class Private(Command):
    """An admin command whose text must stay off the log."""
    private = True

    async def execute(self, text, sender):
        return CommandResult(console="", reply=f"kept {len(text)} characters")


class RunTest(ConsoleTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.log_in()

    async def run_command(self, command, text="", status=200):
        response = await self.client.post("/api/run", json={"command": command, "text": text},
                                          headers={"Origin": f"http://{self.host}"})
        found = await response.json()
        self.assertEqual(response.status, status, found)
        return found

    async def test_commands_offered(self):
        names = [c["name"] for c in await self.get_json("/api/commands")]
        for name in ("health", "approve", "remove", "whois", "alert", "help", "wx", "status", "backup", "msg"):
            self.assertIn(name, names)
        # Acting on the sender's own records, which the console doesn't have.
        for name in ("join", "ok", "inbox", "setpass", "whoami", "leave", "qm", "email", "emailall"):
            self.assertNotIn(name, names)
        health = next(c for c in await self.get_json("/api/commands") if c["name"] == "health")
        self.assertEqual(health, {"name": "health", "permission": "admin", "usage": "health",
                                  "summary": self.commands["health"].summary, "channel": None})
        alert = next(c for c in await self.get_json("/api/commands") if c["name"] == "alert")
        self.assertEqual(alert["channel"], "#contingency-wx")

    async def test_run_an_admin_command(self):
        found = await self.run_command("Health")
        self.assertEqual(found["command"], "health")
        self.assertFalse(found["asks"])
        self.assertTrue(found["ok"])
        self.assertTrue(found["messages"][0].startswith("health: up "))
        log = self.out.getvalue()
        self.assertIn("[console] health\n", log)
        self.assertIn("  -> answered the console", log)

    async def test_approve_is_recorded_as_by_console(self):
        carol = "c" * 64
        self.state.store("requests.json").data[carol] = {"name": "Carol", "time": 1.0}
        found = await self.run_command("approve", "Carol")
        self.assertIn("Carol", found["messages"][0])
        self.assertIn(carol, self.directory.users)
        self.assertEqual(self.state.store(HISTORY_FILE).data["entries"][-1]["by"], "console")

    async def test_remove_asks_first_as_over_the_radio(self):
        first = await self.run_command("remove", BOB)  # by key, as the app does
        self.assertIn("this removes Bob", first["messages"][0])
        self.assertTrue(first["asks"])
        self.assertIn(BOB, self.directory.users)
        second = await self.run_command("remove", BOB)
        self.assertIn("Bob removed", second["messages"][0])
        self.assertFalse(second["asks"])
        self.assertNotIn(BOB, self.directory.users)

    async def test_msg_leaves_a_message_from_console(self):
        found = await self.run_command("msg", f"{BOB} the road north is open")
        self.assertEqual(found["messages"], ["msg: saved for Bob (1 in their inbox)"])
        box = self.state.store("mailbox.json").data[BOB]
        self.assertEqual((box[0]["from"], box[0]["text"]), ("console", "the road north is open"))
        self.assertIn("[console] msg (private)", self.out.getvalue())
        self.assertNotIn("road north", self.out.getvalue())

    async def test_msg_not_offered_when_turned_off(self):
        self.commands["msg"].permission = DISABLED
        await self.run_command("msg", f"{BOB} hi", status=404)

    async def test_a_refusal_is_the_reply(self):
        found = await self.run_command("whois", "nobody")
        self.assertEqual(found["messages"], ["whois: no user nobody"])
        self.assertFalse(found["ok"])

    async def test_a_failing_command(self):
        async def broken(text, sender):
            raise RuntimeError("radio on fire")

        self.commands["health"].execute = broken
        found = await self.run_command("health")
        self.assertEqual((found["messages"], found["ok"]), (["health: failed"], False))
        self.assertEqual(self.state.counts["errors"], 1)

    async def test_commands_not_offered(self):
        for name in ("join", "inbox", "nosuch", ""):
            found = await self.run_command(name, status=404)
            self.assertIn("for the console", found["error"])

    async def test_bad_requests(self):
        headers = {"Origin": f"http://{self.host}"}
        response = await self.client.post("/api/run", data="health", headers=headers)
        self.assertEqual(response.status, 400)
        for body in ([], {"text": "x"}, {"command": 3}, {"command": "health", "text": None}):
            response = await self.client.post("/api/run", json=body, headers=headers)
            self.assertEqual(response.status, 400, body)
        found = await self.run_command("whois", "x" * 501, status=400)
        self.assertIn("at most 500", found["error"])

    async def test_a_command_rate(self):
        self.commands["health"].rate = (1, 3600)
        await self.run_command("health")
        found = await self.run_command("health", status=429)
        self.assertIn("health: limit reached, try again in", found["error"])

    async def test_a_private_commands_text_stays_off_the_log(self):
        secret = "correct horse battery staple"
        command = Private(make_context("hush", state=self.state))
        command.permission = ADMIN_LEVEL
        self.commands["hush"] = command
        found = await self.run_command("hush", secret)
        self.assertEqual(found["messages"], ["kept 28 characters"])
        self.assertIn("[console] hush (private)", self.out.getvalue())
        self.assertNotIn(secret, self.out.getvalue())
        self.assertNotIn(secret, json.dumps(list(self.output.lines)))


class LogTest(ConsoleTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.log_in()

    async def events(self, response, count):
        """The next count events from a live log."""
        found = []
        while len(found) < count:
            line = (await asyncio.wait_for(response.content.readline(), 5)).decode()
            if line.startswith("data: "):
                found.append(json.loads(line[6:])["line"])
        return found

    async def test_kept_lines_then_new_ones(self):
        print("before one")
        print("before two")
        response = await self.client.get("/api/log")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        self.assertEqual(await self.events(response, 2), ["before one", "before two"])
        print("after", end="")
        print(" \x1b[2Jdone")  # escaped, as on the terminal
        self.assertEqual(await self.events(response, 1), ["after \\x1b[2Jdone"])
        response.close()

    async def test_stopping_ends_open_logs(self):
        response = await self.client.get("/api/log")
        await self.app.on_shutdown.send(self.app)
        self.assertEqual(await asyncio.wait_for(response.content.read(), 5), b"")

    async def test_no_log_kept(self):
        self.app["output"] = None
        response = await self.client.get("/api/log")
        self.assertEqual(response.status, 404)


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
