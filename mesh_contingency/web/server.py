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

Past the checks it serves the API (api.py) and the app: the Angular build in
static/, made by npm run build in console/ and shipped in the package. Every
response says the page may load only its own files and not be framed.
"""

import os
import re
import secrets
from pathlib import Path

from aiohttp import web

from ..limits import RateLimiter
from . import HOSTS, URL_FILE
from .api import CTX, LIMITER, LOG_STREAMS, OUTPUT, routes

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
# Seconds a stopping bot waits for requests still being answered.
SHUTDOWN_SECONDS = 3
STATIC_DIR = web.AppKey("static", Path)  # where the app's files are


def make_app(ctx, key, port, limiter=None, output=None, static=STATIC):
    """The aiohttp application: the checks, then the API and the app (from
    static). Commands are rate limited with limiter (the radio's, so a
    command's rate counts both); output is the bot's SafeOutput, for the live
    log."""
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
        return await handler(request)

    app = web.Application(middlewares=[guard])
    app.on_response_prepare.append(add_security_headers)
    app[CTX] = ctx
    app[STATIC_DIR] = Path(static).resolve()
    app[LIMITER] = limiter or RateLimiter()
    app[OUTPUT] = output
    app[LOG_STREAMS] = set()
    app.on_shutdown.append(end_logs)
    app.add_routes(routes)
    app.router.add_get("/{path:.*}", page)
    return app


async def add_security_headers(request, response):
    response.headers.update(SECURITY_HEADERS)


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
        self.url_file = Path(folder) / URL_FILE
        self.key = secrets.token_urlsafe(32)
        self.runner = None

    @property
    def url(self):
        return f"http://{self.settings.host}:{self.settings.port}/?key={self.key}"

    async def start(self):
        """Start listening, write console.url and say where. Returns False
        (having said why) if the port can't be used; the bot runs on."""
        app = make_app(self.ctx, self.key, self.settings.port, self.limiter, self.output)
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
        return True

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        self.url_file.unlink(missing_ok=True)  # its key is no longer valid
