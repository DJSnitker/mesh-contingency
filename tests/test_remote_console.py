"""The remote console: who may reach it, logging in, sessions and lockout,
console users from the browser, its certificate, and starting it."""

import contextlib
import io
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.directory import Directory
from mesh_contingency.output import SafeOutput
from mesh_contingency.registry import Registry
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, make_context
from mesh_contingency.web import ConsoleSettings, aiohttp_missing, remote, tls
from mesh_contingency.web import console_users as store
from mesh_contingency.web.launch import main as launch_main
from mesh_contingency.web.remote import LOCK_SECONDS, Logins, private_address

FAST_N = 2**10
GOOD = "correct horse battery"
BOB = "b0" * 32
ADMIN = "ad" * 32
EXAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "config.example.toml"
needs_aiohttp = unittest.skipIf(aiohttp_missing(), "the web console needs aiohttp: pip install -e .[console]")
needs_cryptography = unittest.skipIf(tls.cryptography_missing(), "needs cryptography: pip install -e .[console]")


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class PrivateAddressTest(unittest.TestCase):
    def test_the_local_network(self):
        for address in ("10.1.2.3", "172.16.0.9", "172.31.255.1", "192.168.1.20", "169.254.3.4", "100.64.1.1",
                        "127.0.0.1", "::1", "fd12:3456::1", "fe80::1%eth0", "::ffff:192.168.1.5"):
            with self.subTest(address=address):
                self.assertTrue(private_address(address))

    def test_the_internet_and_junk(self):
        for address in ("8.8.8.8", "172.32.0.1", "100.128.0.1", "2001:4860::8888", "::ffff:8.8.8.8", "", None,
                        "not an address", "192.168.1"):
            with self.subTest(address=address):
                self.assertFalse(private_address(address))


class LoginsTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / store.USERS_FILE
        self.enterContext(mock.patch.object(store, "SCRYPT_N", FAST_N))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.add("sam")
        self.clock = Clock()
        self.logins = Logins(self.path, clock=self.clock)

    def add(self, name, password=GOOD):
        with store.changing(self.path) as users:
            users[name] = store.new_user(name, password)

    def new_password(self, name, password="a whole new password"):
        with store.changing(self.path) as users:
            store.set_password(users[name], password)

    async def refused(self, status, name="sam", password="wrong password", address="192.168.1.20"):
        with self.assertRaises(remote.LoginRefused) as caught:
            await self.logins.log_in(name, password, address)
        self.assertEqual(caught.exception.status, status)
        return caught.exception.text


class LoginTest(LoginsTestCase):
    async def test_a_good_login(self):
        session_id, name = await self.logins.log_in(" Sam ", GOOD, "192.168.1.20")
        self.assertEqual(name, "sam")
        self.assertGreaterEqual(len(session_id), 40)
        self.assertEqual(self.logins.session(session_id).name, "sam")
        self.assertIn("Console login: sam from 192.168.1.20", self.out.getvalue())
        self.assertNotIn(GOOD, self.out.getvalue())
        self.assertEqual(store.load(self.path)["sam"]["last_login"], int(self.clock.now))

    async def test_wrong_name_or_password_get_the_same_answer(self):
        wrong_password = await self.refused(401)
        wrong_name = await self.refused(401, name="nobody", password=GOOD)
        not_a_name = await self.refused(401, name="Robert'); DROP", password=GOOD)
        self.assertEqual({wrong_password, wrong_name, not_a_name}, {"Wrong name or password."})
        log = self.out.getvalue()
        self.assertIn("Console login failed: sam from 192.168.1.20", log)
        self.assertIn("Console login failed: nobody from", log)
        self.assertIn("Console login failed: (not a name) from", log)
        self.assertNotIn("wrong password", log)
        self.assertNotIn("DROP", log)

    async def test_an_unknown_name_still_checks_a_password(self):
        with mock.patch.object(store, "verify_password", wraps=store.verify_password) as verify:
            await self.refused(401, name="nobody")
        verify.assert_called_once()

    async def test_junk_logins_are_wrong_not_errors(self):
        for name, password in ((None, GOOD), ("sam", None), (5, []), ("sam", "x" * 10_000)):
            with self.subTest(name=name):
                self.assertEqual(await self.refused(401, name=name, password=password), "Wrong name or password.")
                self.logins.locked_until.clear()
                self.logins.failures.clear()


class LockoutTest(LoginsTestCase):
    async def test_a_name_is_locked_after_5_failures(self):
        for i in range(5):
            await self.refused(401, address=f"192.168.1.{i + 1}")
        self.assertIn("sam locked out for 15 minutes after 5 failed", self.out.getvalue())
        text = await self.refused(429, password=GOOD, address="192.168.1.99")  # even the right one
        self.assertEqual(text, "Too many failed logins: try again in 15 minutes.")
        self.clock.now += LOCK_SECONDS + 1
        session_id, _ = await self.logins.log_in("sam", GOOD, "192.168.1.99")
        self.assertIsNotNone(self.logins.session(session_id))

    async def test_failures_older_than_15_minutes_dont_count(self):
        for _ in range(4):
            await self.refused(401)
        self.clock.now += 15 * 60 + 1
        await self.refused(401)
        await self.logins.log_in("sam", GOOD, "192.168.1.20")  # not locked

    async def test_a_good_login_clears_the_names_failures(self):
        for _ in range(4):
            await self.refused(401)
        await self.logins.log_in("sam", GOOD, "192.168.1.20")
        for _ in range(4):
            await self.refused(401)
        await self.logins.log_in("sam", GOOD, "192.168.1.20")

    async def test_an_address_is_locked_after_10_failures(self):
        for i in range(10):
            await self.refused(401, name=f"guess{i}", address="192.168.1.50")
        self.assertIn("192.168.1.50 locked out for 15 minutes after 10", self.out.getvalue())
        await self.refused(429, password=GOOD, address="192.168.1.50")
        await self.logins.log_in("sam", GOOD, "192.168.1.51")  # another address may

    async def test_a_new_password_on_the_node_unlocks_the_name(self):
        for _ in range(5):
            await self.refused(401)
        self.new_password("sam")
        self.logins.users.users()  # the bot notices the file changed
        await self.logins.log_in("sam", "a whole new password", "192.168.1.20")
        self.assertIn("sam may log in again (a new password)", self.out.getvalue())

    async def test_failures_counted_for_the_node_watch(self):
        for _ in range(3):
            await self.refused(401)
        self.assertEqual(self.logins.recent_failures(), 3)
        self.clock.now += 15 * 60 + 1
        self.assertEqual(self.logins.recent_failures(), 0)


class SessionTest(LoginsTestCase):
    async def asyncSetUp(self):
        self.session_id, _ = await self.logins.log_in("sam", GOOD, "192.168.1.20")

    def test_unknown_and_missing_ids(self):
        for session_id in (None, "", "made-up"):
            self.assertIsNone(self.logins.session(session_id))

    def test_ends_after_30_idle_minutes(self):
        self.clock.now += 29 * 60
        self.assertIsNotNone(self.logins.session(self.session_id))  # and that request counts
        self.clock.now += 29 * 60
        self.assertIsNotNone(self.logins.session(self.session_id))
        self.clock.now += 31 * 60
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertIn("Console logout: sam (30 minutes without a request)", self.out.getvalue())

    def test_ends_12_hours_after_login_however_busy(self):
        for _ in range(12 * 4):
            self.clock.now += 15 * 60
            found = self.logins.session(self.session_id)
        self.assertIsNotNone(found)
        self.clock.now += 1
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertIn("(12 hours since logging in)", self.out.getvalue())

    def test_a_removed_user_is_logged_out(self):
        with store.changing(self.path) as users:
            del users["sam"]
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertIn("Console logout: sam (no longer a console user)", self.out.getvalue())

    def test_a_new_password_logs_them_out(self):
        self.new_password("sam")
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertIn("(a new password)", self.out.getvalue())

    def test_a_broken_file_lets_nobody_in(self):
        self.path.write_text("{")
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertEqual(self.out.getvalue().count("no console user can log in until it's fixed"), 1)

    def test_logging_out(self):
        self.assertEqual(self.logins.log_out(self.session_id).name, "sam")
        self.assertIsNone(self.logins.session(self.session_id))
        self.assertIsNone(self.logins.log_out(self.session_id))
        self.assertIn("Console logout: sam\n", self.out.getvalue())


@needs_cryptography
class CertificateTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory())) / tls.TLS_FOLDER

    def test_made_privately_and_usable(self):
        cert = tls.make_certificate(self.folder)
        for path in (cert, self.folder / tls.KEY_FILE):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        tls.ssl_context(cert, self.folder / tls.KEY_FILE)
        self.assertRegex(tls.fingerprint(cert), r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")

    def test_names_this_computer(self):
        from cryptography import x509

        cert = x509.load_pem_x509_certificate(tls.make_certificate(self.folder).read_bytes())
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dns = names.get_values_for_type(x509.DNSName)
        self.assertIn("localhost", dns)
        self.assertTrue(any(n.endswith(".local") for n in dns))
        self.assertIn("127.0.0.1", [str(a) for a in names.get_values_for_type(x509.IPAddress)])
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        self.assertGreaterEqual(days, 3649)

    def test_renewing_makes_another(self):
        first = tls.fingerprint(tls.make_certificate(self.folder))
        self.assertNotEqual(first, tls.fingerprint(tls.make_certificate(self.folder)))

    def test_made_once_then_kept(self):
        settings = ConsoleSettings(remote=True)
        cert, _ = tls.certificate_files(settings, self.folder.parent)
        first = tls.fingerprint(cert)
        tls.certificate_files(settings, self.folder.parent)
        self.assertEqual(tls.fingerprint(cert), first)

    def test_your_own_must_be_there(self):
        settings = ConsoleSettings(remote=True, cert="/nowhere/cert.pem", key="/nowhere/key.pem")
        with self.assertRaisesRegex(tls.CertificateError, r"no file /nowhere/cert\.pem \(\[console\] cert\)"):
            tls.certificate_files(settings, self.folder.parent)

    def test_a_mismatched_key(self):
        cert = tls.make_certificate(self.folder)
        other = self.folder.parent / "other"
        tls.make_certificate(other)
        with self.assertRaisesRegex(tls.CertificateError, "can't use the certificate"):
            tls.ssl_context(cert, other / tls.KEY_FILE)

    def test_cert_command(self):
        config = self.folder.parent / "config.toml"
        config.write_text("")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaisesRegex(SystemExit, "No certificate yet"):
            launch_main(["-c", str(config), "cert", "show"])
        with contextlib.redirect_stdout(out):
            launch_main(["-c", str(config), "cert", "renew"])
            launch_main(["-c", str(config), "cert", "show"])
        self.assertIn("Made a new certificate", out.getvalue())
        self.assertEqual(out.getvalue().count(f"SHA-256 {tls.fingerprint(self.folder / tls.CERT_FILE)}"), 2)
        config.write_text('[console]\ncert = "/c.pem"\nkey = "/k.pem"\n')
        with self.assertRaisesRegex(SystemExit, "names your own certificate"):
            launch_main(["-c", str(config), "cert", "renew"])


@needs_aiohttp
@needs_cryptography
class RemoteAppTestCase(unittest.IsolatedAsyncioTestCase):
    """The remote console's app over HTTPS, as a browser on the network uses it."""

    async def asyncSetUp(self):
        import aiohttp
        from aiohttp.test_utils import TestClient, TestServer

        from mesh_contingency.web.server import make_remote_app

        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(store, "SCRYPT_N", FAST_N))
        self.state = State(self.folder)
        self.radio = FakeMeshCore()
        self.directory = Directory({BOB: {"name": "Bob"}}, {ADMIN})
        with open(EXAMPLE_CONFIG, "rb") as f:
            self.commands = Registry(tomllib.load(f)).build(self.directory, self.radio, self.state)
        self.ctx = make_context("console", directory=self.directory, state=self.state, radio=self.radio,
                                commands=self.commands)
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(SafeOutput(self.out, keep=50)))
        self.path = self.folder / store.USERS_FILE
        for name in ("sam", "alex"):
            with store.changing(self.path) as users:
                users[name] = store.new_user(name, GOOD)
        self.static = self.folder / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<p>the app</p>")
        cert = tls.make_certificate(self.folder / tls.TLS_FOLDER)
        context = tls.ssl_context(cert, self.folder / tls.TLS_FOLDER / tls.KEY_FILE)
        self.logins = Logins(self.path)
        self.app = make_remote_app(self.ctx, self.logins, static=self.static,
                                   remote_info={"urls": ["https://node.local:8738/"], "fingerprint": "AB:CD"})
        server = TestServer(self.app, host="127.0.0.1")
        await server.start_server(ssl=context)
        # Secure cookies on an IP address: unsafe=True, as browsers keep them anyway.
        self.client = TestClient(server, cookie_jar=aiohttp.CookieJar(unsafe=True),
                                 connector=aiohttp.TCPConnector(ssl=False))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.origin = {"Origin": f"https://127.0.0.1:{server.port}"}

    async def call(self, method, path, body=None, status=200, origin=True):
        response = await self.client.request(method, path, json=body, headers=self.origin if origin else {})
        found = await response.json() if response.content_type == "application/json" else await response.text()
        self.assertEqual(response.status, status, found)
        return found

    async def log_in(self, name="sam", password=GOOD, status=200):
        return await self.call("POST", "/api/login", {"name": name, "password": password}, status=status)

    def last_history(self):
        return self.state.store(HISTORY_FILE).data["entries"][-1]


class RemoteGuardTest(RemoteAppTestCase):
    async def test_the_api_needs_a_login(self):
        found = await self.call("GET", "/api/overview", status=401)
        self.assertEqual(found, {"error": "log in first", "login": True})
        await self.call("POST", "/api/run", {"command": "health"}, status=401)

    async def test_the_app_itself_needs_none(self):
        self.assertEqual(await self.call("GET", "/users"), "<p>the app</p>")

    async def test_only_the_local_network(self):
        with mock.patch("mesh_contingency.web.server.private_address", return_value=False):
            response = await self.client.get("/")
            self.assertEqual(response.status, 403)
            self.assertEqual(await response.text(), "This console answers only the local network.\n")
            await self.call("POST", "/api/login", {"name": "sam", "password": GOOD}, status=403)
        self.assertNotIn("Console login", self.out.getvalue())

    async def test_changes_need_this_https_origin(self):
        await self.call("POST", "/api/login", {"name": "sam", "password": GOOD}, status=403, origin=False)
        response = await self.client.post("/api/login", json={"name": "sam", "password": GOOD},
                                          headers={"Origin": self.origin["Origin"].replace("https", "http")})
        self.assertEqual(response.status, 403)
        await self.log_in()
        response = await self.client.post("/api/run", json={"command": "health"},
                                          headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status, 403)

    async def test_https_only_and_the_usual_headers(self):
        response = await self.client.get("/")
        self.assertEqual(response.headers["Strict-Transport-Security"], "max-age=31536000")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])


class RemoteLoginTest(RemoteAppTestCase):
    async def test_log_in_then_use_the_console_as_yourself(self):
        self.assertEqual(await self.log_in("Sam"), {"name": "sam"})
        me = await self.call("GET", "/api/me")
        self.assertEqual(me, {"name": "sam (console)", "user": "sam", "remote": True,
                              "remote_console": {"urls": ["https://node.local:8738/"], "fingerprint": "AB:CD"}})
        found = await self.call("POST", "/api/run", {"command": "health"})
        self.assertTrue(found["ok"])
        self.assertIn("[sam (console)] health", self.out.getvalue())

    async def test_the_cookie(self):
        response = await self.client.post("/api/login", json={"name": "sam", "password": GOOD}, headers=self.origin)
        cookie = response.cookies[remote.SESSION_COOKIE]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/")

    async def test_a_wrong_password(self):
        found = await self.log_in(password="not the password", status=401)
        self.assertEqual(found, {"error": "Wrong name or password."})
        await self.call("GET", "/api/me", status=401)

    async def test_locked_out(self):
        for _ in range(5):
            await self.log_in(password="not the password", status=401)
        found = await self.log_in(status=429)
        self.assertIn("try again in 15 minutes", found["error"])

    async def test_bad_requests(self):
        response = await self.client.post("/api/login", data="not json", headers=self.origin)
        self.assertEqual(response.status, 400)
        await self.call("POST", "/api/login", {"name": "sam"}, status=400)

    async def test_log_out(self):
        await self.log_in()
        await self.call("POST", "/api/logout")
        await self.call("GET", "/api/me", status=401)
        self.assertIn("Console logout: sam", self.out.getvalue())

    async def test_removed_on_the_node_is_logged_out(self):
        await self.log_in()
        with store.changing(self.path) as users:
            del users["sam"]
        await self.call("GET", "/api/me", status=401)


class ConsoleUsersApiTest(RemoteAppTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.log_in()

    async def test_list_has_no_passwords(self):
        found = await self.call("GET", "/api/console-users")
        self.assertEqual([u["name"] for u in found], ["alex", "sam"])
        self.assertEqual(set(found[0]), {"name", "created", "created_by", "changed", "last_login"})
        self.assertIsNotNone(next(u for u in found if u["name"] == "sam")["last_login"])
        self.assertNotIn("scrypt", str(found))

    async def test_add(self):
        found = await self.call("POST", "/api/console-users", {"name": "Jo", "password": GOOD}, status=201)
        self.assertEqual((found["name"], found["created_by"]), ("jo", "sam"))
        self.assertTrue(store.verify_password(GOOD, store.load(self.path)["jo"]["password"]))
        self.assertEqual(self.last_history()["by"], "sam (console)")
        self.assertEqual(self.last_history()["what"], "added console user jo")
        self.assertNotIn(GOOD, str(self.state.store(HISTORY_FILE).data))
        await self.call("POST", "/api/console-users", {"name": "jo", "password": GOOD}, status=409)
        found = await self.call("POST", "/api/console-users", {"name": "bad name", "password": GOOD}, status=400)
        self.assertIn("letters, digits", found["error"])
        found = await self.call("POST", "/api/console-users", {"name": "kim", "password": "short"}, status=400)
        self.assertIn("12 to 128", found["error"])

    async def test_set_someone_elses_password_logs_them_out(self):
        other = await self.second_client("alex")
        await self.call("POST", "/api/console-users/alex/password", {"password": "alex's new one!"})
        self.assertTrue(store.verify_password("alex's new one!", store.load(self.path)["alex"]["password"]))
        self.assertEqual(self.last_history()["what"], "set console user alex's password")
        response = await other.get("/api/me")
        self.assertEqual(response.status, 401)
        await self.call("POST", "/api/console-users/nobody/password", {"password": GOOD}, status=404)

    async def test_not_your_own_that_way(self):
        found = await self.call("POST", "/api/console-users/sam/password", {"password": "whatever it is"},
                                status=400)
        self.assertIn("Change password", found["error"])

    async def test_remove_someone_else_but_not_yourself(self):
        await self.call("DELETE", "/api/console-users/alex")
        self.assertEqual(list(store.load(self.path)), ["sam"])
        self.assertEqual(self.last_history()["what"], "removed console user alex")
        await self.call("DELETE", "/api/console-users/alex", status=404)
        found = await self.call("DELETE", "/api/console-users/sam", status=400)
        self.assertIn("can't remove yourself", found["error"])
        self.assertEqual(list(store.load(self.path)), ["sam"])

    async def test_change_your_own_password(self):
        found = await self.call("POST", "/api/me/password", {"current": "not it", "password": "my new password"},
                                status=403)
        self.assertIn("isn't your current password", found["error"])
        await self.call("POST", "/api/me/password", {"current": GOOD, "password": "short"}, status=400)
        await self.call("POST", "/api/me/password", {"current": GOOD, "password": "my new password"})
        self.assertTrue(store.verify_password("my new password", store.load(self.path)["sam"]["password"]))
        await self.call("GET", "/api/me")  # this session stays
        self.assertEqual(self.last_history()["what"], "changed their console password")

    async def test_wrong_current_passwords_count_toward_lockout(self):
        for _ in range(5):
            await self.call("POST", "/api/me/password", {"current": "not it", "password": "my new password"},
                            status=403)
        await self.call("POST", "/api/me/password", {"current": GOOD, "password": "my new password"}, status=429)

    async def second_client(self, name):
        import aiohttp
        from aiohttp.test_utils import TestClient

        other = TestClient(self.client.server, cookie_jar=aiohttp.CookieJar(unsafe=True),
                           connector=aiohttp.TCPConnector(ssl=False))
        self.addAsyncCleanup(other.close)
        response = await other.post("/api/login", json={"name": name, "password": GOOD}, headers=self.origin)
        self.assertEqual(response.status, 200)
        return other


@needs_aiohttp
class LocalAccountsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import socket

        import aiohttp
        from aiohttp.test_utils import TestClient, TestServer

        from mesh_contingency.web.server import make_app

        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(store, "SCRYPT_N", FAST_N))
        self.state = State(self.folder)
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.path = self.folder / store.USERS_FILE
        app = make_app(make_context("console", state=self.state), "the-key", port, static=self.folder,
                       users_path=self.path)
        self.client = TestClient(TestServer(app, host="127.0.0.1", port=port),
                                 cookie_jar=aiohttp.CookieJar(unsafe=True))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.origin = {"Origin": f"http://127.0.0.1:{port}"}
        response = await self.client.get("/?key=the-key", allow_redirects=False)
        self.assertEqual(response.status, 302)

    async def test_who_and_no_login(self):
        response = await self.client.get("/api/me")
        self.assertEqual(await response.json(), {"name": "console", "user": None, "remote": False,
                                                 "remote_console": None})
        response = await self.client.post("/api/login", json={"name": "sam", "password": GOOD}, headers=self.origin)
        self.assertEqual(response.status, 405)  # there's no logging in here
        response = await self.client.post("/api/me/password", json={"current": "x", "password": GOOD},
                                          headers=self.origin)
        self.assertEqual(response.status, 400)

    async def test_add_and_remove_console_users(self):
        response = await self.client.post("/api/console-users", json={"name": "sam", "password": GOOD},
                                          headers=self.origin)
        self.assertEqual(response.status, 201)
        self.assertEqual(store.load(self.path)["sam"]["created_by"], "console")
        self.assertEqual(self.state.store(HISTORY_FILE).data["entries"][-1]["by"], "console")
        response = await self.client.delete("/api/console-users/sam", headers=self.origin)
        self.assertEqual(response.status, 200)  # the last one, from the node's own computer
        self.assertEqual(store.load(self.path), {})


@needs_aiohttp
@needs_cryptography
class ConsoleServerRemoteTest(unittest.IsolatedAsyncioTestCase):
    """The bot's ConsoleServer with remote = true: both listeners, and what it says."""

    async def asyncSetUp(self):
        import socket

        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        ports = []
        for _ in range(2):
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                ports.append(s.getsockname()[1])
        self.settings = ConsoleSettings(True, ports[0], "127.0.0.1", remote=True, remote_port=ports[1])

    async def start(self):
        from mesh_contingency.web.server import ConsoleServer

        server = ConsoleServer(self.settings, make_context("console", state=State(self.folder)), self.folder)
        self.assertTrue(await server.start())
        self.addAsyncCleanup(server.stop)
        return server

    async def test_starts_both_and_says_where(self):
        import aiohttp

        server = await self.start()
        log = self.out.getvalue()
        fingerprint = tls.fingerprint(self.folder / tls.TLS_FOLDER / tls.CERT_FILE)
        self.assertIn(f":{self.settings.remote_port}/ (certificate SHA-256 {fingerprint})", log)
        self.assertIn("Remote console: no console users yet; add one with mesh-contingency-console user add",
                      log)
        self.assertEqual(server.remote_info["fingerprint"], fingerprint)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://127.0.0.1:{self.settings.remote_port}/api/me", ssl=False) as response:
                self.assertEqual(response.status, 401)
            with self.assertRaises(aiohttp.ClientError), self.assertLogs("asyncio", "ERROR"):  # HTTPS only
                async with session.get(f"http://127.0.0.1:{self.settings.remote_port}/api/me"):
                    pass
            # Its certificate is its own, so a client that checks certificates refuses it until it's trusted.
            with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                async with session.get(f"https://127.0.0.1:{self.settings.remote_port}/"):
                    pass

    async def test_a_bad_certificate_keeps_the_local_console(self):
        self.settings = ConsoleSettings(True, self.settings.port, "127.0.0.1", remote=True,
                                        remote_port=self.settings.remote_port, cert="/no/cert.pem",
                                        key="/no/key.pem")
        server = await self.start()
        self.assertIn("Warning: remote console not started: no file /no/cert.pem", self.out.getvalue())
        self.assertIsNone(server.remote_runner)
        self.assertIsNotNone(server.runner)

    async def test_off_unless_remote(self):
        self.settings = ConsoleSettings(True, self.settings.port, "127.0.0.1")
        server = await self.start()
        self.assertIsNone(server.remote_runner)
        self.assertNotIn("Remote console", self.out.getvalue())
        self.assertFalse((self.folder / tls.TLS_FOLDER).exists())

