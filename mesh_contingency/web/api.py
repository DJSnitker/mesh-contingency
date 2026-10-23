"""The web console's API, as JSON.

Reading: the same things health, whois, checkins, inbox and history show
over the radio, as tables instead of 140-character pages. Times are
time.time() seconds; keys are full public keys. A sealed message's text, a
user's sealing key and message text in general never leave the node this
way: the inbox lists who has mail, from whom and when, as inbox does without
a passphrase.

Doing: /api/run runs a command as the admin "console" (api.CONSOLE), through
the same run_command as a direct message, so its checks, confirmations and
history entries (by console) are the radio's. It offers the admin and public
commands that don't act on the sender's own records (Command.own), since the
console has none, and user commands that only leave something for someone
else (Command.sends: msg, from "console").

Watching: /api/log sends the lines the bot prints, as server-sent events.
"""

import asyncio
import json
import time

from aiohttp import web

from ..alerts import message_limit
from ..api import ADMIN, CONSOLE, PUBLIC, USER, is_authorized
from ..commands.health import activity_items, people_items, radio_items
from ..commands.join import FILENAME as REQUESTS
from ..commands.mailbox import FILENAME as MAILBOX
from ..commands.mailbox import INBOX_KEY
from ..commands.status import FILENAME as STATUSES
from ..limits import wait_text
from ..running import run_command
from ..state import HISTORY_FILE
from ..watch import LABELS

routes = web.RouteTableDef()
# Settings of a user that are about them, not for the console to show.
HIDDEN_SETTINGS = {"name", INBOX_KEY}
# The longest text /api/run takes: more than a direct message can hold.
MAX_TEXT = 500
# Seconds between keep-alives on a quiet log, so the connection stays open.
KEEPALIVE_SECONDS = 15


def _ctx(request):
    return request.app["ctx"]


@routes.get("/api/overview")
async def overview(request):
    """The health items, and the numbers behind them."""
    ctx = _ctx(request)
    state = ctx.state
    boxes = state.store(MAILBOX).data
    watch = state.watch
    backups = state.backups
    return web.json_response({
        "node": ctx.radio.self_info.get("name") if ctx.radio else None,
        # The longest channel post (alert, comm) from this node.
        "channel_limit": message_limit(ctx.radio) if ctx.radio else None,
        "started": state.started,
        "now": time.time(),
        "health": [*await radio_items(ctx), *people_items(ctx), *activity_items(ctx)],
        "users": len(ctx.users),
        "admins": len(ctx.admins),
        "requests": len(state.store(REQUESTS).data),
        "checkins": len(state.store(STATUSES).data),
        "waiting": sum(len(box) for box in boxes.values()),
        "counts": {name: state.counts[name] for name in ("messages", "sent", "undelivered", "errors")},
        "watch": [LABELS[problem] for problem in watch.active] if watch else None,
        "backup": {"last": backups.last, "failing": backups.failing} if backups else None,
    })


@routes.get("/api/users")
async def users(request):
    """Users and admins (an admin needn't be a user), by name."""
    ctx = _ctx(request)
    statuses = ctx.state.store(STATUSES).data
    boxes = ctx.state.store(MAILBOX).data
    found = []
    for key in sorted(ctx.users.keys() | ctx.admins, key=lambda k: (ctx.users.get(k, {}).get("name") or k).lower()):
        settings = ctx.users.get(key)
        seen = ctx.state.seen.get(key)
        box = boxes.get(key, [])
        found.append({
            "key": key,
            "name": (settings or {}).get("name") or (seen[0] if seen else None),
            "user": settings is not None,
            "admin": key in ctx.admins,
            "passphrase": bool((settings or {}).get(INBOX_KEY)),
            "settings": {k: v for k, v in (settings or {}).items() if k not in HIDDEN_SETTINGS},
            "last_seen": seen[1] if seen else None,
            "checkin": {"status": statuses[key]["status"], "time": statuses[key]["time"]} if key in statuses
                       else None,
            "messages": len(box),
            "unread": sum(not entry.get("read") for entry in box),
        })
    return web.json_response(found)


@routes.get("/api/requests")
async def requests(request):
    """Join requests waiting, oldest first."""
    waiting = _ctx(request).state.store(REQUESTS).data
    return web.json_response([{"key": key, "name": r["name"], "time": r["time"]}
                              for key, r in sorted(waiting.items(), key=lambda item: item[1]["time"])])


@routes.get("/api/checkins")
async def checkins(request):
    """Check-ins, newest first, and the users who haven't checked in."""
    ctx = _ctx(request)
    statuses = ctx.state.store(STATUSES).data
    return web.json_response({
        "checkins": [{"key": key, "name": s["name"], "status": s["status"], "time": s["time"]}
                     for key, s in sorted(statuses.items(), key=lambda item: -item[1]["time"])],
        "missing": [{"key": key, "name": user.get("name")}
                    for key, user in sorted(ctx.users.items(), key=lambda item: (item[1].get("name") or "").lower())
                    if key not in statuses],
    })


@routes.get("/api/inbox")
async def inbox(request):
    """Who has messages waiting: from whom, when, read or not, sealed or
    not. Never the text."""
    ctx = _ctx(request)
    boxes = ctx.state.store(MAILBOX).data
    return web.json_response([
        {"key": key, "name": ctx.users.get(key, {}).get("name"),
         "messages": [{"from": entry["from"], "time": entry["time"], "read": bool(entry.get("read")),
                       "sealed": "sealed" in entry} for entry in box]}
        for key, box in boxes.items() if box
    ])


@routes.get("/api/history")
async def history(request):
    """Admin actions (and users leaving), newest first."""
    entries = _ctx(request).state.store(HISTORY_FILE).data.get("entries", [])
    return web.json_response([{"time": e["time"], "by": e["by"], "what": e["what"]} for e in reversed(entries)])


def offered(ctx):
    """{name: command} the console may run."""
    def may(command):
        if command.own:
            return False
        if command.permission == USER:
            return command.sends
        return command.permission in (ADMIN, PUBLIC) and is_authorized(command, CONSOLE, ctx.users, ctx.admins)
    return {name: command for name, command in ctx.commands.items() if may(command)}


@routes.get("/api/commands")
async def commands(request):
    """What /api/run can run, by name, and where a channel command posts."""
    return web.json_response([
        {"name": name, "permission": command.permission, "usage": command.usage, "summary": command.summary,
         "channel": getattr(command, "channel", None)}
        for name, command in sorted(offered(_ctx(request)).items())
    ])


def _error(status, text):
    return web.json_response({"error": text}, status=status)


@routes.post("/api/run")
async def run(request):
    """{"command": name, "text": what follows it} -> {"messages": the reply,
    "asks": whether it only asks to send the same again to confirm, "ok":
    False if it refused, failed or timed out}."""
    ctx = _ctx(request)
    try:
        asked = await request.json()
    except ValueError:
        return _error(400, "send JSON: {\"command\": ..., \"text\": ...}")
    if not isinstance(asked, dict) or not isinstance(asked.get("command"), str) \
            or not isinstance(asked.get("text", ""), str):
        return _error(400, "command and text must be strings")
    name, text = asked["command"].strip().lower(), asked.get("text", "").strip()
    command = offered(ctx).get(name)
    if command is None:
        return _error(404, f"no command {name[:30]} for the console")
    if len(text) > MAX_TEXT:
        return _error(400, f"text too long ({len(text)} characters; at most {MAX_TEXT})")
    print(f"[{CONSOLE.name}] {name + ' (private)' if command.private else (name + ' ' + text).strip()}", flush=True)
    wait, _ = request.app["limiter"].check(CONSOLE.public_key, command.name, command.rate)
    if wait:
        print(f"  -> {command.name} limit reached", flush=True)
        return _error(429, f"{command.name}: limit reached, try again in {wait_text(wait)}")
    answer = await run_command(command, text, CONSOLE, ctx.state)
    if answer.messages:
        print(f"  -> answered the console ({len(answer.messages)} message(s))", flush=True)
    return web.json_response({"command": command.name, "messages": answer.messages, "asks": answer.asks,
                              "ok": answer.ok})


@routes.get("/api/log")
async def log(request):
    """The lines kept so far, then each new one as it's printed, as
    server-sent events: data: {"time", "line"}."""
    output = request.app["output"]
    if output is None:
        return _error(404, "no log kept")
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await response.prepare(request)
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def listener(when, line):  # may be called from another thread
        loop.call_soon_threadsafe(queue.put_nowait, (when, line))

    streams = request.app["log_streams"]
    streams.add(queue)
    try:
        for when, line in output.listen(listener):
            await response.write(_event(when, line))
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                await response.write(b": keep-alive\n\n")
                continue
            if entry is None:  # the bot is stopping
                break
            await response.write(_event(*entry))
    except ConnectionError:  # the page was closed
        pass
    finally:
        output.unlisten(listener)
        streams.discard(queue)
    return response


def _event(when, line):
    return f"data: {json.dumps({'time': when, 'line': line}, ensure_ascii=False)}\n\n".encode()
