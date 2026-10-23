"""scripts/demo_console.py: its made-up node reads as a real one through the
console's API, and its buttons work."""

import contextlib
import importlib.util
import io
import socket
import tempfile
import unittest
from pathlib import Path

from mesh_contingency.web import aiohttp_missing

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "demo_console.py"


def load_demo():
    spec = importlib.util.spec_from_file_location("demo_console", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp: pip install -e .[console]")
class DemoConsoleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import CookieJar
        from aiohttp.test_utils import TestClient, TestServer

        from mesh_contingency.web.server import make_app

        self.demo = load_demo()
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        ctx, output = self.demo.demo_context(self.folder)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.client = TestClient(TestServer(make_app(ctx, self.demo.KEY, port, output=output, static=self.folder),
                                            host="127.0.0.1", port=port),
                                 cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.client.session.headers.update({"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
        response = await self.client.get(f"/?key={self.demo.KEY}", allow_redirects=False)
        self.assertEqual(response.status, 302)

    async def get(self, path):
        response = await self.client.get(path)
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def test_every_page_has_something(self):
        overview = await self.get("/api/overview")
        self.assertEqual(overview["node"], "Ridgeview Relay")
        self.assertEqual((overview["users"], overview["admins"], overview["requests"]), (6, 1, 1))
        self.assertEqual(overview["watch"], [])
        self.assertIsNotNone(overview["backup"]["last"])
        self.assertIn("auto alerts 4 counties, checked 3m ago", overview["health"])
        self.assertEqual(len(await self.get("/api/users")), 7)
        self.assertEqual(len((await self.get("/api/checkins"))["missing"]), 3)
        self.assertEqual(len(await self.get("/api/inbox")), 3)
        self.assertEqual((await self.get("/api/history"))[0]["by"], "console")
        areas = (await self.get("/api/weather"))["areas"]
        self.assertEqual([a["county"] for a in areas], ["Boone, MO", "Callaway, MO", "Cole, MO", "Howard, MO"])
        self.assertEqual([a["event"] for a in areas[1]["alerts"]], ["Wind Advisory"])
        self.assertEqual(areas[3]["problem"], "HTTP Error 503: Service Unavailable")
        contacts = await self.get("/api/contacts")
        self.assertEqual((len(contacts["contacts"]), contacts["max"]), (12, 350))
        channels = [(c["name"], c["kind"], c["uses"]) for c in await self.get("/api/channels")][:4]
        self.assertEqual(channels, [("Public", "public", []),
                                    ("#contingency-wx", "hashtag", ["alert", "automatic alerts"]),
                                    ("#contingency-comm", "hashtag", ["comm"]),
                                    ("Ridgeview ARES", "private", [])])
        said = (await self.get("/api/channels/2/messages"))["messages"]
        self.assertEqual([(m["sender"], m["own"]) for m in said],
                         [("priya-hh", False), ("james-hh", False), ("Ridgeview Relay", True)])

    async def test_only_made_up_addresses(self):
        users = str(await self.get("/api/users"))
        self.assertNotIn("@", users.replace("@example.com", "").replace("@example.org", "")
                         .replace("@example.net", ""))

    async def test_back_up_now_writes_into_its_folder(self):
        response = await self.client.post("/api/run", json={"command": "backup", "text": ""})
        found = await response.json()
        self.assertTrue(found["ok"], found)
        self.assertTrue(any((self.folder / "backups").iterdir()))
