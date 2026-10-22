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
"""

import os
import secrets
from pathlib import Path

from aiohttp import web

from . import HOSTS
from .api import routes

URL_FILE = "console.url"
COOKIE = "mesh_console"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
NOT_LOGGED_IN = ("Open the console with the link in console.url, next to config.toml (also printed when the "
                 "bot starts). A restart of the bot makes a new link.\n")
NO_APP = "The web console's API is running; the app isn't built yet.\n"


def make_app(ctx, key, port):
    """The aiohttp application: the checks, then the API."""
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
    app["ctx"] = ctx
    app.add_routes(routes)
    app.router.add_get("/", no_app)
    return app


async def no_app(request):
    return web.Response(text=NO_APP)


def write_url(path, url):
    """Write the console's link to path, readable only by this account."""
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    os.replace(temp, path)


class ConsoleServer:
    """The web console, started and stopped with the bot."""

    def __init__(self, settings, ctx, folder):
        self.settings = settings
        self.ctx = ctx
        self.url_file = Path(folder) / URL_FILE
        self.key = secrets.token_urlsafe(32)
        self.runner = None

    @property
    def url(self):
        return f"http://{self.settings.host}:{self.settings.port}/?key={self.key}"

    async def start(self):
        """Start listening, write console.url and say where. Returns False
        (having said why) if the port can't be used; the bot runs on."""
        self.runner = web.AppRunner(make_app(self.ctx, self.key, self.settings.port), access_log=None)
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
        return True

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        self.url_file.unlink(missing_ok=True)  # its key is no longer valid
