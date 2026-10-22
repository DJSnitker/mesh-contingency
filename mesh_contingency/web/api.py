"""What the web console can read, as JSON: the same things health, whois,
checkins, inbox and history show over the radio, as tables instead of
140-character pages.

Times are time.time() seconds. Keys are full public keys. Nothing here
changes anything, and a sealed message's text, a user's sealing key and
message text in general never leave the node this way: the inbox lists who
has mail, from whom and when, as inbox does without a passphrase.
"""

import time

from aiohttp import web

from ..commands.health import activity_items, people_items, radio_items
from ..commands.join import FILENAME as REQUESTS
from ..commands.mailbox import FILENAME as MAILBOX
from ..commands.mailbox import INBOX_KEY
from ..commands.status import FILENAME as STATUSES
from ..state import HISTORY_FILE
from ..watch import LABELS

routes = web.RouteTableDef()
# Settings of a user that are about them, not for the console to show.
HIDDEN_SETTINGS = {"name", INBOX_KEY}


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
