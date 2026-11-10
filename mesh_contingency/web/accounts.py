"""The console's own accounts, as JSON: who is logged in, the console users,
and (on the remote console) logging in and out.

On both listeners (routes):
- GET /api/me: who this is ({"name", "user": the console user or null for
  the console on the node's computer, "remote"}), and the remote console's
  addresses and certificate fingerprint for the Dashboard.
- GET /api/console-users: name, made when and by whom, password set, last
  login. Never a password or its hash.
- POST /api/console-users {"name", "password"}: add one.
- POST /api/console-users/{name}/password {"password"}: set someone else's
  (their sessions end; your own is below).
- DELETE /api/console-users/{name}: remove one (the app asks first). Not
  yourself, so the browser can't remove the last one; the node's command can.
- POST /api/me/password {"current", "password"}: a console user's own,
  with the current one first. This session stays; their others end.

Each change goes in history, by whoever made it, never the password.

On the remote console only (remote_routes): POST /api/login {"name",
"password"} and POST /api/logout.
"""

import asyncio

from aiohttp import web

from ..api import CONSOLE_USER_PREFIX
from . import console_users as store
from .api import CTX, SENDER
from .remote import SESSION_COOKIE, LoginRefused

routes = web.RouteTableDef()
remote_routes = web.RouteTableDef()

USERS_PATH = web.AppKey("console_users_path", object)  # console_users.json
LOGINS = web.AppKey("logins", object)  # remote.Logins, or None on the local console
REMOTE_INFO = web.AppKey("remote_info", object)  # {"urls", "fingerprint"} once the remote console is up, or None
SESSION = "mesh_console_session"  # the request's session id, on the remote console


def _error(status, text):
    return web.json_response({"error": text}, status=status)


def user_of(sender):
    """The console user sender is, or None (the console on the node)."""
    key = sender.public_key or ""
    return key[len(CONSOLE_USER_PREFIX):] if key.startswith(CONSOLE_USER_PREFIX) else None


async def _body(request, *fields):
    try:
        asked = await request.json()
    except ValueError:
        asked = None
    if not isinstance(asked, dict) or not all(isinstance(asked.get(f), str) for f in fields):
        raise web.HTTPBadRequest(text=f'{{"error": "send JSON: {", ".join(fields)}"}}',
                                 content_type="application/json")
    return asked


def _record(request, what):
    ctx, sender = request.app[CTX], request[SENDER]
    ctx.state.record(ctx.name_of(sender), what)
    print(f"[{sender.name}] {what}", flush=True)


def _changing(request):
    return store.changing(request.app[USERS_PATH])


def _shown(user):
    return {"name": user["name"], "created": user["created"], "created_by": user["created_by"],
            "changed": user["changed"], "last_login": user.get("last_login")}


@routes.get("/api/me")
async def me(request):
    sender = request[SENDER]
    return web.json_response({"name": sender.name, "user": user_of(sender),
                              "remote": request.app[LOGINS] is not None,
                              "remote_console": request.app[REMOTE_INFO] or None})


@routes.get("/api/console-users")
async def list_users(request):
    try:
        users = await asyncio.to_thread(store.load, request.app[USERS_PATH])
    except store.ConsoleUsersError as e:
        return _error(500, f"{store.USERS_FILE}: {e}")
    return web.json_response([_shown(users[name]) for name in sorted(users)])


@routes.post("/api/console-users")
async def add_user(request):
    asked = await _body(request, "name", "password")
    name = store.normal_name(asked["name"])
    problem = store.check_name(name) or store.check_password(asked["password"])
    if problem:
        return _error(400, problem)
    by = user_of(request[SENDER]) or "console"
    entry = await asyncio.to_thread(store.new_user, name, asked["password"], by)

    def save():
        with _changing(request) as users:
            if name in users:
                return False
            users[name] = entry
            return True
    try:
        if not await asyncio.to_thread(save):
            return _error(409, f"there is already a console user called {name}")
    except store.ConsoleUsersError as e:
        return _error(500, f"{store.USERS_FILE}: {e}")
    _record(request, f"added console user {name}")
    return web.json_response(_shown(entry), status=201)


@routes.post("/api/console-users/{name}/password")
async def set_password(request):
    name = store.normal_name(request.match_info["name"])
    if name == user_of(request[SENDER]):
        return _error(400, "for your own password, use Change password (it asks for the current one)")
    asked = await _body(request, "password")
    problem = store.check_password(asked["password"])
    if problem:
        return _error(400, problem)

    def save():
        with _changing(request) as users:
            if name not in users:
                return False
            store.set_password(users[name], asked["password"])
            return True
    try:
        if not await asyncio.to_thread(save):
            return _error(404, f"no console user called {name}")
    except store.ConsoleUsersError as e:
        return _error(500, f"{store.USERS_FILE}: {e}")
    _record(request, f"set console user {name}'s password")
    return web.json_response({"name": name})


@routes.delete("/api/console-users/{name}")
async def remove_user(request):
    name = store.normal_name(request.match_info["name"])
    if name == user_of(request[SENDER]):
        return _error(400, "you can't remove yourself; another console user, or the node's "
                           "mesh-contingency-console user remove, can")

    def save():
        with _changing(request) as users:
            return users.pop(name, None) is not None
    try:
        if not await asyncio.to_thread(save):
            return _error(404, f"no console user called {name}")
    except store.ConsoleUsersError as e:
        return _error(500, f"{store.USERS_FILE}: {e}")
    _record(request, f"removed console user {name}")
    return web.json_response({"name": name})


@routes.post("/api/me/password")
async def own_password(request):
    name = user_of(request[SENDER])
    logins = request.app[LOGINS]
    if name is None or logins is None:
        return _error(400, "the console on the node's computer has no password")
    asked = await _body(request, "current", "password")
    address = request.remote or ""
    wait = logins.locked(name, address)
    if wait:
        return _error(429, "too many failed tries: try again later")
    user = logins.users.get(name)
    if user is None or not await asyncio.to_thread(store.verify_password, asked["current"][:store.PASSWORD_MAX],
                                                   user["password"]):
        logins.failed(name, address, name)
        return _error(403, "that isn't your current password")
    problem = store.check_password(asked["password"])
    if problem:
        return _error(400, problem)

    def save():
        with _changing(request) as users:
            if name not in users:
                return None
            store.set_password(users[name], asked["password"])
            return users[name]["changed"]
    changed = await asyncio.to_thread(save)
    if changed is None:
        return _error(404, "you're no longer a console user")
    logins.keep_after_new_password(request[SESSION], changed)
    _record(request, "changed their console password")
    return web.json_response({"name": name})


@remote_routes.post("/api/login")
async def log_in(request):
    logins = request.app[LOGINS]
    asked = await _body(request, "name", "password")
    try:
        session_id, name = await logins.log_in(asked["name"], asked["password"], request.remote or "")
    except LoginRefused as e:
        return _error(e.status, e.text)
    response = web.json_response({"name": name})
    response.set_cookie(SESSION_COOKIE, session_id, secure=True, httponly=True, samesite="Strict", path="/")
    return response


@remote_routes.post("/api/logout")
async def log_out(request):
    request.app[LOGINS].log_out(request.cookies.get(SESSION_COOKIE))
    response = web.json_response({"ok": True})
    response.del_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="Strict")
    return response
