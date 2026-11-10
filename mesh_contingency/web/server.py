"""The console's web server, and the checks every request passes.

Listening on 127.0.0.1 keeps other computers out, but not two things on this
one:

- Web pages in the admin's own browser, which can send requests to
  127.0.0.1 and, with DNS rebinding, read the answers. So only requests whose
  Host is 127.0.0.1:<port> or localhost:<port> are answered, and anything but
  GET needs a matching Origin too.
- Other accounts on the computer. So every request needs the key the bot made
  at startup: the first visit brings it in the link (?key=...), which sets a
  cookie (HttpOnly, SameSite=Strict) and is sent on to the same address
  without it. After that the cookie is enough.

A request that passes is the admin "console" (api.CONSOLE): request[SENDER]
says so, and the API acts as it.

The remote console (remote = true) is a second app on its own port, on every
address, over HTTPS (tls.py), with its own guard (make_remote_app): the
source address must be private, anything but GET needs the Origin
https://<its Host>, and the API needs a console user's login (remote.py).
The app's own files are served without one, so it can show its login page.

Past the checks it serves the API (api.py) and the app: the Angular build in
static/, made by npm run build in console/ and shipped in the package. Every
response says the page may load only its own files and not be framed.
"""

import asyncio
import os
import re
import secrets
import socket
from pathlib import Path

from aiohttp import web

from ..api import CONSOLE, console_user
from ..limits import RateLimiter
from . import HOSTS, URL_FILE, accounts, tls
from .accounts import LOGINS, REMOTE_INFO, SESSION, USERS_PATH
from .api import CTX, LIMITER, LOG_STREAMS, OUTPUT, SENDER, routes
from .console_users import USERS_FILE
from .remote import SESSION_COOKIE, Logins, private_address

COOKIE = "mesh_console"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
NOT_LOGGED_IN = ("Open the console with mesh-contingency-console, or the link in console.url next to "
                 "config.toml (also printed when the bot starts). A restart of the bot makes a new link.\n")
NO_APP = "The web console's API is running, but its app isn't built: in console/, run npm ci and npm run build.\n"
# The app's build (console/ builds into it).
STATIC = Path(__file__).resolve().parent / "static"
# Built files whose name carries a hash of their content, which never change.
HASHED_RE = re.compile(r"-[A-Z0-9]{8}\.(js|css|woff2?)$")
# Sent with every response. Styles may be inline (Angular's components add
# theirs as <style> elements); scripts may not.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
                               "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# Sent with every response of the remote console, as well: browsers then use
# only HTTPS for it.
HSTS = {"Strict-Transport-Security": "max-age=31536000"}
NOT_LOCAL = "This console answers only the local network.\n"
# Seconds a stopping bot waits for requests still being answered.
SHUTDOWN_SECONDS = 3
STATIC_DIR = web.AppKey("static", Path)  # where the app's files are


def make_app(ctx, key, port, limiter=None, output=None, static=STATIC, users_path=None, remote_info=None):
    """The aiohttp application: the checks, then the API and the app (from
    static). Commands are rate limited with limiter (the radio's, so a
    command's rate counts both); output is the bot's SafeOutput, for the live
    log; users_path is console_users.json; remote_info is what the remote
    console says about itself, once it's up."""
    allowed = {f"{host}:{port}" for host in HOSTS}

    @web.middleware
    async def guard(request, handler):
        if request.host not in allowed:
            return web.Response(status=403, text="Wrong host.\n")
        if request.method not in SAFE_METHODS and request.headers.get("Origin") != f"http://{request.host}":
            return web.Response(status=403, text="Wrong origin.\n")
        given = request.query.get("key")
        if given is not None:
            if not secrets.compare_digest(given, key):
                return web.Response(status=403, text="Wrong key. " + NOT_LOGGED_IN)
            # The key leaves the address bar (and the browser's history).
            rest = request.rel_url.with_query([(k, v) for k, v in request.query.items() if k != "key"])
            response = web.Response(status=302, headers={"Location": str(rest)})
            response.set_cookie(COOKIE, key, httponly=True, samesite="Strict", path="/")
            return response
        if not secrets.compare_digest(request.cookies.get(COOKIE, ""), key):
            return web.Response(status=401, text=NOT_LOGGED_IN)
        request[SENDER] = CONSOLE  # the key is the node's own computer
        return await handler(request)

    return _build(guard, ctx, limiter, output, static, users_path, None, remote_info)


def make_remote_app(ctx, logins, limiter=None, output=None, static=STATIC, remote_info=None):
    """The remote console's application: its guard, then the same API and
    app as the local one, as the logged-in console user, and logging in and
    out. logins is a remote.Logins."""

    @web.middleware
    async def guard(request, handler):
        if not private_address(request.remote):
            return web.Response(status=403, text=NOT_LOCAL)
        if request.method not in SAFE_METHODS and request.headers.get("Origin") != f"https://{request.host}":
            return web.Response(status=403, text="Wrong origin.\n")
        path = request.path
        if path in ("/api/login", "/api/logout"):
            return await handler(request)
        session_id = request.cookies.get(SESSION_COOKIE)
        session = logins.session(session_id)
        if session is not None:
            request[SENDER] = console_user(session.name)
            request[SESSION] = session_id
        elif path == "/api" or path.startswith("/api/"):
            return web.json_response({"error": "log in first", "login": True}, status=401)
        return await handler(request)  # the app's files: its login page needs them

    app = _build(guard, ctx, limiter, output, static, logins.users.path, logins, remote_info)
    app.on_response_prepare.append(add_hsts)
    app.add_routes(accounts.remote_routes)
    return app


def _build(guard, ctx, limiter, output, static, users_path, logins, remote_info):
    app = web.Application(middlewares=[guard])
    app.on_response_prepare.append(add_security_headers)
    app[CTX] = ctx
    app[STATIC_DIR] = Path(static).resolve()
    app[LIMITER] = limiter or RateLimiter()
    app[OUTPUT] = output
    app[LOG_STREAMS] = set()
    app[USERS_PATH] = users_path
    app[LOGINS] = logins
    app[REMOTE_INFO] = remote_info if remote_info is not None else {}
    app.on_shutdown.append(end_logs)
    app.add_routes(accounts.routes)  # before routes: /api/me/password isn't a page
    app.add_routes(routes)
    app.router.add_get("/{path:.*}", page)
    return app


async def add_security_headers(request, response):
    response.headers.update(SECURITY_HEADERS)


async def add_hsts(request, response):
    response.headers.update(HSTS)


def built(static):
    return (static / "index.html").is_file()


async def page(request):
    """A file of the app, or the app itself for any other address (its
    pages are its own: /users is the app at /users)."""
    static, path = request.app[STATIC_DIR], request.match_info["path"]
    if path == "api" or path.startswith("api/"):
        return web.json_response({"error": f"no such API: /{path[:60]}"}, status=404)
    if not built(static):
        return web.Response(text=NO_APP)
    target = (static / path).resolve()
    if path and target.is_relative_to(static) and target.is_file():
        cache = "max-age=31536000, immutable" if HASHED_RE.search(target.name) else "no-cache"
        return web.FileResponse(target, headers={"Cache-Control": cache})
    if "." in path.rsplit("/", 1)[-1]:  # a file that isn't there
        return web.Response(status=404, text="Not found.\n")
    return web.FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})


async def end_logs(app):
    """End the open live logs, which would otherwise hold up stopping."""
    for queue in app[LOG_STREAMS]:
        queue.put_nowait(None)


def write_url(path, url):
    """Write the console's link to path, readable only by this account."""
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    os.replace(temp, path)


class ConsoleServer:
    """The web console, started and stopped with the bot."""

    def __init__(self, settings, ctx, folder, limiter=None, output=None):
        self.settings = settings
        self.ctx = ctx
        self.limiter = limiter
        self.output = output
        self.folder = Path(folder)
        self.url_file = self.folder / URL_FILE
        self.key = secrets.token_urlsafe(32)
        self.runner = None
        self.remote_runner = None
        self.logins = None
        self.remote_info = {}  # filled in once the remote console is up

    @property
    def url(self):
        return f"http://{self.settings.host}:{self.settings.port}/?key={self.key}"

    async def start(self):
        """Start listening, write console.url and say where. Returns False
        (having said why) if the port can't be used; the bot runs on."""
        app = make_app(self.ctx, self.key, self.settings.port, self.limiter, self.output,
                       users_path=self.folder / USERS_FILE, remote_info=self.remote_info)
        self.runner = web.AppRunner(app, access_log=None, shutdown_timeout=SHUTDOWN_SECONDS)
        await self.runner.setup()
        try:
            await web.TCPSite(self.runner, self.settings.host, self.settings.port).start()
        except OSError as e:
            await self.runner.cleanup()
            self.runner = None
            print(f"Warning: web console not started: port {self.settings.port} can't be used ({e.strerror or e}); "
                  "set [console] port to another.", flush=True)
            return False
        write_url(self.url_file, self.url)
        print(f"Web console: {self.url} (also in {self.url_file})", flush=True)
        if not built(STATIC):
            print("Note: the web console's app isn't built, so only its API answers: in console/, run npm ci and "
                  "npm run build.", flush=True)
        if self.settings.remote:
            await self.start_remote()
        return True

    async def start_remote(self):
        """Start the remote console (HTTPS, every address) and say where.
        Returns False (having said why) if it can't start; the local console
        and the bot run on."""
        port = self.settings.remote_port
        try:
            cert, key = await asyncio.to_thread(tls.certificate_files, self.settings, self.folder)
            context = tls.ssl_context(cert, key)
            fingerprint = tls.fingerprint(cert)
        except tls.CertificateError as e:
            print(f"Warning: remote console not started: {e}.", flush=True)
            return False
        self.logins = await asyncio.to_thread(Logins, self.folder / USERS_FILE)
        app = make_remote_app(self.ctx, self.logins, self.limiter, self.output, remote_info=self.remote_info)
        self.remote_runner = web.AppRunner(app, access_log=None, shutdown_timeout=SHUTDOWN_SECONDS)
        await self.remote_runner.setup()
        try:
            await web.TCPSite(self.remote_runner, None, port, ssl_context=context).start()
        except OSError as e:
            await self.remote_runner.cleanup()
            self.remote_runner = None
            print(f"Warning: remote console not started: port {port} can't be used ({e.strerror or e}); set "
                  "[console] remote_port to another.", flush=True)
            return False
        urls = remote_urls(port)
        self.remote_info.update(urls=urls, fingerprint=fingerprint, own_certificate=bool(self.settings.cert))
        print(f"Remote console: {urls[0]} (certificate SHA-256 {fingerprint})", flush=True)
        if len(urls) > 1:
            print(f"  also {', '.join(urls[1:])}", flush=True)
        if not self.logins.users.users():
            print("Remote console: no console users yet; add one with mesh-contingency-console user add NAME",
                  flush=True)
        return True

    async def stop(self):
        if self.remote_runner:
            await self.remote_runner.cleanup()
            self.remote_runner = None
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        self.url_file.unlink(missing_ok=True)  # its key is no longer valid


def remote_urls(port):
    """The addresses other computers may open the remote console at:
    <hostname>.local, then this computer's own addresses."""
    host = socket.gethostname().split(".", 1)[0]
    urls = [f"https://{host}.local:{port}/"] if host else []
    for address in tls.own_addresses():
        if private_address(str(address)):
            shown = f"[{address}]" if address.version == 6 else str(address)
            urls.append(f"https://{shown}:{port}/")
    return urls or [f"https://localhost:{port}/"]
