"""The web console's API, as JSON.

Reading: the same things health, whois, checkins, inbox, history and
contacts show over the radio, as tables instead of 140-character pages, and
the radio's channel slots (not their keys) and settings.
Times are time.time() seconds; keys are full public keys. A sealed message's text, a
user's sealing key and message text in general never leave the node this
way: the inbox lists who has mail, from whom and when, as inbox does without
a passphrase.

Doing: /api/run runs a command as the admin "console" (api.CONSOLE), through
the same run_command as a direct message, so its checks, confirmations and
history entries (by console) are the radio's. It offers the admin and public
commands that don't act on the sender's own records (Command.own), since the
console has none, and user commands that only leave something for someone
else (Command.sends: msg, from "console").

Posting: POST /api/channels/{slot}/messages posts to any of the radio's
channels as this node, as alert and comm do to theirs: one message, held to
what fits after the node's name, recorded in history by console.

Messaging: POST /api/contacts/{key}/messages sends a contact a direct
message as this node; /api/conversations and /api/contacts/{key}/messages
show the console's conversations, only its own messages and the replies to
them (conversations.py), never commands sent to the node.

Watching: /api/log sends the lines the bot prints, as server-sent events.
"""

import asyncio
import json
import time

from aiohttp import web
from meshcore import EventType

from ..alerts import PUBLIC_SECRET, hashtag_secret, is_empty, message_limit, post, read_channels
from ..api import ADMIN, CONSOLE, MAX_REPLY_LEN, PUBLIC, USER, is_authorized
from ..area_weather import EVERY_MINUTES
from ..commands.health import RADIO_SECONDS, activity_items, people_items, radio_items
from ..commands.join import FILENAME as REQUESTS
from ..commands.mailbox import FILENAME as MAILBOX
from ..commands.mailbox import INBOX_KEY
from ..commands.radio import BANDWIDTHS, matching_presets
from ..commands.status import FILENAME as STATUSES
from ..contacts import TYPE_NAMES
from ..limits import wait_text
from ..radio_presets import PRESETS
from ..radio_presets import TAKEN as PRESETS_TAKEN
from ..running import run_command
from ..state import HISTORY_FILE
from ..watch import LABELS, ask_radio

routes = web.RouteTableDef()
# What the app holds for the handlers (server.make_app sets them).
CTX = web.AppKey("ctx", object)  # the console's Context
LIMITER = web.AppKey("limiter", object)  # the RateLimiter, shared with the radio
OUTPUT = web.AppKey("output", object)  # the bot's SafeOutput, or None: no live log
LOG_STREAMS = web.AppKey("log_streams", set)  # the queues of open live logs
# Settings of a user that are about them, not for the console to show.
HIDDEN_SETTINGS = {"name", INBOX_KEY}
# The longest text /api/run takes: more than a direct message can hold.
MAX_TEXT = 500
# Seconds between keep-alives on a quiet log, so the connection stays open.
KEEPALIVE_SECONDS = 15


def _ctx(request):
    return request.app[CTX]


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
        "alerts": active_alerts(state.alert_watcher),
    })


def active_alerts(watcher):
    """The alerts out for the watched counties at the alert watcher's last
    check, each event once with the counties it covers, in [alerts] order:
    {"active": [{"event", "counties"}], "checked", "problem"}; None without
    counties in [alerts]."""
    if watcher is None:
        return None
    active = {}
    for county in watcher.settings.counties:
        for alert in watcher.current.get(county, []):
            counties = active.setdefault(alert["event"] or "Alert", [])
            if county not in counties:
                counties.append(county)
    return {"active": [{"event": event, "counties": counties} for event, counties in active.items()],
            "checked": watcher.last_check, "problem": watcher.problem}


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


@routes.get("/api/weather")
async def weather(request):
    """The weather now in each county [alerts] watches (area_weather.py), and
    when the alerts were last checked. areas is null if there's none: no
    counties in [alerts]."""
    state = _ctx(request).state
    area, watcher = state.area_weather, state.alert_watcher
    return web.json_response({
        "now": time.time(),
        "every_minutes": EVERY_MINUTES,
        "areas": area.areas() if area else None,
        "alerts_checked": watcher.last_check if watcher else None,
        "alerts_problem": watcher.problem if watcher else None,
    })


@routes.get("/api/contacts")
async def contacts(request):
    """The radio's contacts by name, and how many it can hold (max, null if
    it doesn't say). hops is the length of the path the radio keeps to one,
    null if it has none (a message to it floods); last_advert is the radio's
    time it last heard from it, null if never."""
    ctx = _ctx(request)
    radio = ctx.radio
    if radio is None:
        return web.json_response({"max": None, "contacts": []})
    info = await ask_radio(radio.commands.send_device_query, EventType.DEVICE_INFO, RADIO_SECONDS) or {}
    found = []
    for contact in radio.contacts.values():
        key = contact["public_key"].lower()
        hops = contact.get("out_path_len", -1)
        found.append({
            "key": key,
            "name": contact.get("adv_name") or None,
            "type": TYPE_NAMES.get(contact.get("type"), "unknown"),
            "user": key in ctx.users,
            "admin": key in ctx.admins,
            "hops": hops if hops is not None and hops >= 0 else None,
            "last_advert": contact.get("last_advert") or None,
        })
    found.sort(key=lambda c: ((c["name"] or "").lower(), c["key"]))
    return web.json_response({"max": info.get("max_contacts"), "contacts": found})


def channel_kind(name, secret):
    """public (the usual Public channel), hashtag (its key is worked out from
    its #name, so anyone can join), private (any other key) or empty."""
    if is_empty(name, secret):
        return "empty"
    if secret == PUBLIC_SECRET:
        return "public"
    return "hashtag" if name.startswith("#") and secret == hashtag_secret(name) else "private"


@routes.get("/api/channels")
async def channels(request):
    """The radio's channel slots: each one's name, kind (channel_kind), what
    the bot posts to it (uses: the alert and comm commands, testalert, the
    automatic alerts and the weekly test), and how many of its messages are
    kept since the bot started (messages; null if none are), when the
    newest came (last) and how many others' messages were heard on it since
    the bot started (heard, for unread counts; null if none are kept). Never
    a channel's key: with it anyone could read and post on a private
    channel."""
    ctx = _ctx(request)
    if ctx.radio is None:
        return web.json_response([])
    state = ctx.state
    uses = [(name, getattr(command, "channel", None)) for name, command in sorted(ctx.commands.items())]
    if state.alert_test:
        test = state.alert_test.settings
        uses += [("testalert", test.channel)] if "testalert" in ctx.commands else []
        uses += [("weekly test", test.channel)] if test.weekly else []
    if state.alert_watcher:
        uses.append(("automatic alerts", state.alert_watcher.settings.channel))
    posting = {}
    for use, channel in uses:
        if channel:
            posting.setdefault(hashtag_secret(channel), []).append(use)
    try:
        slots = await asyncio.wait_for(read_channels(ctx.radio), RADIO_SECONDS * 2)
    except Exception as e:  # the radio didn't answer, or answered nonsense
        return _error(502, f"can't read the radio's channels: {str(e) or type(e).__name__}")
    log = state.channel_log
    found = []
    for slot, (name, secret) in enumerate(slots):
        kept, last = log.summary(slot) if log else (None, None)
        found.append({"slot": slot, "name": name, "kind": channel_kind(name, secret),
                      "uses": [] if is_empty(name, secret) else posting.get(secret, []),
                      "messages": kept, "last": last, "heard": log.heard_count(slot) if log else None})
    return web.json_response(found)


@routes.get("/api/channels/{slot}/messages")
async def channel_messages(request):
    """A channel slot's messages since the bot started, newest first: when
    each came, who sent it (null if it didn't say), the text, the hops it came
    over and the signal (null for this node's own posts), and own: whether
    this node posted it. messages is null if they aren't kept; heard is as
    /api/channels says."""
    log = _ctx(request).state.channel_log
    try:
        slot = int(request.match_info["slot"])
    except ValueError:
        return _error(404, "no such channel slot")
    return web.json_response({"slot": slot, "keep": log.keep if log else None,
                              "messages": log.messages(slot) if log else None,
                              "heard": log.heard_count(slot) if log else None})


@routes.post("/api/channels/{slot}/messages")
async def post_to_channel(request):
    """{"text": the message} -> {"channel": its name}: post it to the slot's
    channel as this node. One channel message, at most what fits after the
    node's name; recorded in history (by console) and kept with the
    channel's messages."""
    ctx = _ctx(request)
    try:
        slot = int(request.match_info["slot"])
        asked = await request.json()
    except ValueError:
        return _error(400, "send JSON to a slot: {\"text\": ...}")
    text = asked.get("text") if isinstance(asked, dict) else None
    if not isinstance(text, str) or not text.strip():
        return _error(400, "text must be a message")
    text = text.strip()
    if ctx.radio is None:
        return _error(503, "no radio")
    limit = message_limit(ctx.radio)
    if len(text) > limit:
        return _error(400, f"too long for one channel message ({len(text)} characters; at most {limit})")
    try:
        slots = await asyncio.wait_for(read_channels(ctx.radio), RADIO_SECONDS * 2)
    except Exception as e:
        return _error(502, f"can't read the radio's channels: {str(e) or type(e).__name__}")
    if not 0 <= slot < len(slots) or is_empty(*slots[slot]):
        return _error(404, f"no channel in slot {slot}")
    name = slots[slot][0] or f"slot {slot}"
    try:
        await post(ctx.radio, slot, [text], ctx.state.channel_log)
    except RuntimeError as e:
        return _error(502, str(e))
    print(f"[{CONSOLE.name}] posted to {name} ({len(text)} chars)", flush=True)
    ctx.state.record(CONSOLE.name, f"posted to {name}: {text}")
    return web.json_response({"channel": name})


def _contact_name(ctx, key):
    """A contact's name: in the users file, else as the radio has it, else None."""
    contact = ctx.radio.contacts.get(key) if ctx.radio is not None else None
    if contact is None and ctx.radio is not None:
        contact = next((c for c in ctx.radio.contacts.values() if c["public_key"].lower() == key), None)
    return ctx.users.get(key, {}).get("name") or (contact or {}).get("adv_name") or None


def _contact_key(request):
    """The route's full public key, lowercase, or None if it isn't one."""
    key = request.match_info["key"].lower()
    return key if len(key) == 64 and all(c in "0123456789abcdef" for c in key) else None


@routes.get("/api/conversations")
async def conversations(request):
    """The console's conversations, the most recent first: each contact's
    key and name, how many messages are kept, the newest (time, text, own,
    status) and how many replies were heard since the bot started (heard,
    for unread). null if the console's messages aren't kept."""
    ctx = _ctx(request)
    kept = ctx.state.conversations
    if kept is None:
        return web.json_response(None)
    return web.json_response([
        {"key": key, "name": _contact_name(ctx, key), "messages": len(kept.messages(key)),
         "last": kept.last(key), "heard": kept.heard_count(key)}
        for key in kept.keys()])


@routes.get("/api/contacts/{key}/messages")
async def contact_messages(request):
    """The console's conversation with a contact, newest first: its
    messages (the console's, own, with sending, delivered or not delivered,
    and the contact's replies, with hops and snr as heard), how many are
    kept (keep) and heard as /api/conversations says. messages is null if
    they aren't kept."""
    ctx = _ctx(request)
    key = _contact_key(request)
    if key is None:
        return _error(404, "not a contact's key")
    kept = ctx.state.conversations
    return web.json_response({"key": key, "name": _contact_name(ctx, key), "keep": kept.keep if kept else None,
                              "messages": kept.messages(key) if kept else None,
                              "heard": kept.heard_count(key) if kept else None})


_sending = set()  # direct messages going out, kept until they're delivered or not


@routes.post("/api/contacts/{key}/messages")
async def message_contact(request):
    """{"text": the message} -> {"message": it, sending}: send a companion
    contact a direct message as this node, retried until the radio has an
    ack, as replies are. One message, at most MAX_REPLY_LEN characters.
    Kept in the conversation, where its status becomes delivered or not
    delivered; history records who was messaged (by console), not what."""
    ctx = _ctx(request)
    key = _contact_key(request)
    if key is None:
        return _error(404, "not a contact's key")
    try:
        asked = await request.json()
    except ValueError:
        return _error(400, 'send JSON: {"text": ...}')
    text = asked.get("text") if isinstance(asked, dict) else None
    if not isinstance(text, str) or not text.strip():
        return _error(400, "text must be a message")
    text = text.strip()
    if len(text) > MAX_REPLY_LEN:
        return _error(400, f"too long for one direct message ({len(text)} characters; at most {MAX_REPLY_LEN})")
    kept, send = ctx.state.conversations, ctx.state.send_direct
    if ctx.radio is None or kept is None or send is None:
        return _error(503, "no radio")
    contact = next((c for c in ctx.radio.contacts.values() if c["public_key"].lower() == key), None)
    if contact is None:
        return _error(404, "the radio has no such contact")
    if TYPE_NAMES.get(contact.get("type")) != "chat":
        return _error(400, "only a companion (chat) contact can be messaged")
    name = _contact_name(ctx, key) or key[:12]
    entry = kept.sent(key, text)

    async def deliver():
        try:
            kept.delivered(entry, await send(key, text, what="console's message") is True)
        except Exception as e:
            kept.delivered(entry, False)
            print(f"  console's message to {key[:12]} failed: {type(e).__name__}", flush=True)

    task = asyncio.create_task(deliver())
    _sending.add(task)
    task.add_done_callback(_sending.discard)
    print(f"[{CONSOLE.name}] message to {name} ({len(text)} chars)", flush=True)
    ctx.state.record(CONSOLE.name, f"messaged {name}")
    return web.json_response({"message": dict(entry)})


@routes.get("/api/radio")
async def radio(request):
    """The radio's own settings, as radio shows them, and MeshCore's presets
    for the console to offer. clock_offset is the radio's clock minus the
    computer's, in seconds (null if it didn't say). Never its Bluetooth PIN."""
    radio = _ctx(request).radio
    if radio is None:
        return web.json_response(None)
    info = radio.self_info
    device = await ask_radio(radio.commands.send_device_query, EventType.DEVICE_INFO, RADIO_SECONDS) or {}
    clock = await ask_radio(radio.commands.get_time, EventType.CURRENT_TIME, RADIO_SECONDS) or {}
    four = [info.get(k) for k in ("radio_freq", "radio_bw", "radio_sf", "radio_cr")]
    return web.json_response({
        "name": info.get("name"),
        "freq": four[0], "bw": four[1], "sf": four[2], "cr": four[3],
        "presets_matching": matching_presets(*four) if None not in four else [],
        "tx_power": info.get("tx_power"), "max_tx_power": info.get("max_tx_power"),
        "lat": info.get("adv_lat"), "lon": info.get("adv_lon"),
        "shares_position": bool(info.get("adv_loc_policy")),
        "clock_offset": clock["time"] - time.time() if clock.get("time") else None,
        "model": device.get("model"), "version": device.get("ver"), "build": device.get("fw_build"),
        "path_hash_mode": device.get("path_hash_mode"),
        "manual_add_contacts": info.get("manual_add_contacts"),
        "bandwidths": list(BANDWIDTHS),
        "presets": [{"title": title, "freq": freq, "bw": bw, "sf": sf, "cr": cr, "path_hash_size": size}
                    for title, freq, bw, sf, cr, size in PRESETS],
        "presets_taken": PRESETS_TAKEN,
    })


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
    print(f"[{CONSOLE.name}] {name}", flush=True)  # as over the radio: never the text
    wait, _ = request.app[LIMITER].check(CONSOLE.public_key, command.name, command.rate)
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
    output = request.app[OUTPUT]
    if output is None:
        return _error(404, "no log kept")
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await response.prepare(request)
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def listener(when, line):  # may be called from another thread
        loop.call_soon_threadsafe(queue.put_nowait, (when, line))

    streams = request.app[LOG_STREAMS]
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
