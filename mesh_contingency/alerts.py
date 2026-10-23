"""Weather alerts on a public channel: shared by the alert command and the
automatic alert watcher.

The bot takes no commands from channels; it only sends to one (it keeps what
it hears on them only for the web console, channel_log.py). The channel is a
hashtag channel (#name), which anyone can join by adding the same name. If the radio
doesn't have it, it is added to the first empty channel slot.

The watcher ([alerts] in config.toml) watches counties. It looks up each
county's NWS code once (kept until an admin sends alertmap), then every few
minutes asks the National Weather Service for the alerts in all the counties
in a single request, and posts each alert it hasn't posted before, once, even
if several counties share it. The codes and what it has posted are kept in
alerts.json next to config.toml, so a restart doesn't post anything again.
Right after the computer starts the network may not be up yet, so the first
round waits (up to NETWORK_WAIT) until the NWS's name can be looked up.

[alert_test] posts a test message to the same channel every week, and the
testalert command posts it on request, so people know the channel works.
"""

import asyncio
import datetime
import socket
import time
import urllib.parse
import zoneinfo
from dataclasses import dataclass
from hashlib import sha256

from meshcore import EventType

from .api import MAX_PARTS, MAX_REPLY_LEN, fit_reply, pack
from .weather import NWS_API, STATE_FIPS, alert_counties, county_alerts, county_code

DEFAULT_CHANNEL = "#contingency-wx"
# Channel slots to look through if the radio doesn't say how many it has.
DEFAULT_SLOTS = 8
# The key of MeshCore's usual Public channel, the same on every radio.
PUBLIC_SECRET = bytes.fromhex("8b3387e9c5cdea6ac9e5edbaa115cd72")
ALERTS_FILE = "alerts.json"
ALERTS_KEYS = {"counties", "every_minutes", "channel"}
DEFAULT_EVERY_MINUTES = 10
# api.weather.gov asks clients not to poll too often.
MIN_EVERY_MINUTES = 5
# Seconds between channel messages, so a burst doesn't crowd the mesh.
SEND_GAP = 1
# How long a posted alert is remembered after it ends, if the NWS doesn't
# say when (seconds), and after its end time once it is no longer active.
REMEMBER_SECONDS = 24 * 3600
KEEP_AFTER_END_SECONDS = 6 * 3600
# Before the first round: how long to wait for the network (seconds), and how
# often to look while waiting.
NETWORK_WAIT = 120
NETWORK_POLL = 5


class NoChannelSlot(Exception):
    """The radio has no empty channel slot for the alert channel."""


def check_channel(channel):
    """The channel name if it is a usable hashtag channel; raises ValueError."""
    if not (isinstance(channel, str) and channel.startswith("#") and len(channel) > 1
            and len(channel.encode("utf-8")) <= 31):
        raise ValueError(f"channel must be a hashtag channel name such as {DEFAULT_CHANNEL!r}, "
                         f"up to 31 bytes, not {channel!r}")
    return channel


def hashtag_secret(name):
    """The key of a hashtag channel, which anyone can work out from its name."""
    return sha256(name.encode("utf-8")).digest()[:16]


def short_time(iso):
    """"Tue 6:00PM" for an NWS time such as 2026-10-20T18:00:00-05:00, in
    the alert's own time zone; the text as given if it isn't a time."""
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{t:%a} {t.hour % 12 or 12}:{t:%M}{'AM' if t.hour < 12 else 'PM'}"


def format_alerts(place, alerts, limit=MAX_REPLY_LEN):
    """One channel message per distinct alert for a place (a zipcode or a
    county), most important information first, at most MAX_PARTS messages."""
    messages = []
    seen = set()
    for a in alerts:
        ends = a.get("ends") or a.get("expires")
        if (a.get("event"), ends) in seen:  # NWS often repeats an alert for several zones
            continue
        seen.add((a.get("event"), ends))
        sections = [a.get("event") or "Alert"]
        if ends:
            sections.append(f"until {short_time(ends)}")
        if a.get("areaDesc"):
            sections.append(a["areaDesc"])
        messages.append(fit_reply(f"{place} ALERT:", sections, limit))
    if len(messages) > MAX_PARTS:
        more = len(messages) - (MAX_PARTS - 1)
        messages = messages[:MAX_PARTS - 1] + [f"{place}: {more} more alerts; check wx or weather.gov"]
    return messages


def message_limit(radio):
    """A channel message goes out as "<node name>: <text>", within the usual limit."""
    return MAX_REPLY_LEN - len(radio.self_info.get("name", "")) - 2


async def read_channels(radio):
    """The radio's channel slots in order, as [(name, 16-byte key)], with
    ("", 16 zero bytes) for an empty one; as far as the radio answers."""
    info = await radio.commands.send_device_query()
    slots = DEFAULT_SLOTS if info.type == EventType.ERROR else info.payload.get("max_channels", DEFAULT_SLOTS)
    found = []
    for slot in range(slots):
        res = await radio.commands.get_channel(slot)
        if res.type == EventType.ERROR:
            break
        found.append((res.payload.get("channel_name", ""), res.payload.get("channel_secret", bytes(16))))
    return found


def is_empty(name, secret):
    return not name and not any(secret)


async def channel_slot(radio, channel):
    """Return (slot, added): the radio's slot for the channel, adding it to
    the first empty slot if it isn't there. Raises NoChannelSlot if there is
    no room, or RuntimeError if the radio refuses."""
    secret = hashtag_secret(channel)
    slots = await read_channels(radio)
    for slot, (_, key) in enumerate(slots):
        if key == secret:
            return slot, False
    empty = next((slot for slot, (name, key) in enumerate(slots) if is_empty(name, key)), None)
    if empty is None:
        raise NoChannelSlot(f"no free channel slot on the radio for {channel}")
    res = await radio.commands.set_channel(empty, channel)
    if res.type == EventType.ERROR:
        raise RuntimeError(f"radio rejected adding {channel} to slot {empty}: {res.payload}")
    return empty, True


async def post(radio, slot, messages, log=None):
    """Send messages to a channel slot, a little apart, adding each one sent
    to log (the ChannelLog, if any)."""
    for i, message in enumerate(messages):
        if i:
            await asyncio.sleep(SEND_GAP)
        res = await radio.commands.send_chan_msg(slot, message)
        if res.type == EventType.ERROR:
            raise RuntimeError(f"radio rejected channel message {i + 1} of {len(messages)}: {res.payload}")
        if log:
            log.sent(slot, radio.self_info.get("name"), message)


def parse_county(text):
    """"Taylor, TX" from "Taylor, TX", "taylor tx" or "Taylor County, TX":
    the county's name and its state's two letters. Raises ValueError."""
    words = text.replace(",", " ").split()
    if len(words) < 2 or words[-1].upper() not in STATE_FIPS:
        raise ValueError(f"{text.strip()!r} isn't a county and state, e.g. \"Taylor, TX\"")
    name = words[:-1]
    if len(name) > 1 and name[-1].lower() in ("county", "parish", "borough"):
        name = name[:-1]
    return f"{' '.join(name)}, {words[-1].upper()}"


def county_name(county):
    """"Taylor" from "Taylor, TX"."""
    return county.rsplit(", ", 1)[0]


def county_lines(counties, limit, intro="Counties watched for alerts: "):
    """The county names (no states) in as few channel messages as fit in
    limit, numbered if more than one, without splitting a name."""
    names = [county_name(c) for c in counties]
    if not names:
        return []
    lines = pack([intro + names[0]] + names[1:], limit, ", ")
    if len(lines) > 1:  # channel messages can arrive out of order
        lines = pack([intro + names[0]] + names[1:], limit - len(f"({len(lines)}/{len(lines)}) ") - 1, ", ")
        lines = [f"({i}/{len(lines)}) {line}" for i, line in enumerate(lines, 1)]
    return lines


def plural_counties(n):
    return f"{n} {'county' if n == 1 else 'counties'}"


@dataclass(frozen=True)
class AlertSettings:
    counties: tuple = ()  # "Taylor, TX", ...
    every_minutes: float = DEFAULT_EVERY_MINUTES
    channel: str = DEFAULT_CHANNEL


def load_alerts(config):
    """AlertSettings from [alerts] in config.toml. The channel defaults to the
    alert command's. Exits on a mistake."""
    section = config.get("alerts", {})
    if not isinstance(section, dict) or set(section) - ALERTS_KEYS:
        raise SystemExit(f"[alerts] may only set {', '.join(sorted(ALERTS_KEYS))}.")
    counties = section.get("counties", [])
    if isinstance(counties, str):
        counties = [counties]
    if not isinstance(counties, list) or not all(isinstance(c, str) for c in counties):
        raise SystemExit('[alerts] counties must be a list of counties, e.g. ["Taylor, TX", "Jones, TX"].')
    unique = {}  # each county once, however it's written
    for text in counties:
        try:
            county = parse_county(text)
        except ValueError as e:
            raise SystemExit(f"[alerts] counties: {e}.") from None
        unique.setdefault(county.lower(), county)
    counties = tuple(unique.values())
    every = section.get("every_minutes", DEFAULT_EVERY_MINUTES)
    if isinstance(every, bool) or not isinstance(every, (int, float)) or every < MIN_EVERY_MINUTES:
        raise SystemExit(f"[alerts] every_minutes must be a number of minutes, at least {MIN_EVERY_MINUTES}.")
    alert_command = config.get("commands", {}).get("alert", {})
    default = alert_command.get("channel", DEFAULT_CHANNEL) if isinstance(alert_command, dict) else DEFAULT_CHANNEL
    try:
        channel = check_channel(section.get("channel", default))
    except ValueError as e:
        raise SystemExit(f"[alerts] {e}.") from None
    return AlertSettings(counties, every, channel)


def _timestamp(iso):
    try:
        return datetime.datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


def _key(alert):
    """What identifies an alert: the NWS id, or what it says if it has none."""
    return alert.get("id") or f"{alert.get('event')}|{alert.get('ends') or alert.get('expires')}|" \
                               f"{alert.get('areaDesc')}"


def summary(alert):
    """What the web console shows of an alert (its properties): {"event",
    "severity", "headline", "ends" (time.time(), or None)}."""
    ends = _timestamp(alert.get("ends")) or _timestamp(alert.get("expires"))
    return {"event": alert.get("event"), "severity": alert.get("severity"), "headline": alert.get("headline"),
            "ends": ends}


def nws_reachable():
    """True if the NWS's name can be looked up, i.e. there's a network."""
    try:
        socket.getaddrinfo(urllib.parse.urlsplit(NWS_API).hostname, 443)
    except OSError:
        return False
    return True


class AlertWatcher:
    """Posts new NWS alerts for the watched counties to the alert channel."""

    def __init__(self, radio, settings, state, lookup=None, fetch=None, reachable=None):
        self.radio = radio
        self.settings = settings
        self.state = state
        self.lookup = lookup or county_code  # (name, state) -> NWS code, e.g. "TXC441"
        self.fetch = fetch or county_alerts  # [NWS codes] -> active alerts
        self.reachable = reachable or nws_reachable  # () -> True once there's a network
        # {"counties": {"Taylor, TX": {"code", "time"}}, "posted": {key: time to forget it}}
        self.store = state.store(ALERTS_FILE)
        self.store.data.pop("zones", None)  # from a test version that watched zipcodes
        self.unmapped = {}  # county -> why its code couldn't be looked up
        self.problem = None  # why the last request for alerts failed, until one works
        self.last_check = None  # time.time() of the last request for alerts that worked
        self.current = {}  # county -> [the alerts active for it at the last check], for the web console
        for county in [c for c in self.codes if c not in settings.counties]:
            del self.codes[county]  # no longer watched

    @property
    def codes(self):
        return self.store.data.setdefault("counties", {})

    @property
    def posted(self):
        return self.store.data.setdefault("posted", {})

    def describe(self):
        """For startup."""
        return (f"{plural_counties(len(self.settings.counties))} ({'; '.join(self.settings.counties)}) every "
                f"{self.settings.every_minutes:g} min to {self.settings.channel}")

    async def map_counties(self, counties=None):
        """Look up and keep the NWS codes of these counties (all the watched
        ones by default). Returns [(county, code, None)], or (county, None,
        reason) for a county that couldn't be looked up."""
        results = []
        for county in counties or self.settings.counties:
            name, state = county.rsplit(", ", 1)
            try:
                code = await asyncio.to_thread(self.lookup, name, state)
            except Exception as e:  # the network or the NWS, or no such county
                if county not in self.unmapped:
                    print(f"Auto alerts: couldn't look up the NWS code of {county} ({e}); trying again "
                          f"every {self.settings.every_minutes:g} min", flush=True)
                self.unmapped[county] = str(e)
                results.append((county, None, str(e)))
                continue
            self.unmapped.pop(county, None)
            self.codes[county] = {"code": code, "time": time.time()}
            print(f"Auto alerts: {county} is NWS county {code}", flush=True)
            results.append((county, code, None))
        self.store.save()
        return results

    def remember_until(self, alert, now):
        ends = max(filter(None, (_timestamp(alert.get("ends")), _timestamp(alert.get("expires")))), default=None)
        return (ends + KEEP_AFTER_END_SECONDS) if ends else now + REMEMBER_SECONDS

    def county_for(self, alert, mapped):
        """The first watched county the alert covers, to name it by."""
        return self.counties_for(alert, mapped)[0]

    def counties_for(self, alert, mapped):
        """Every watched county the alert covers; the first watched one if
        it names none of them (an alert for a forecast zone)."""
        covered = alert_counties(alert)
        return [c for c in mapped if self.codes[c]["code"] in covered] or mapped[:1]

    async def check(self):
        """One round: look up any counties not looked up yet, ask for the
        alerts of every county in one request, post what's new, and forget
        alerts that have ended. Returns the number of messages posted."""
        missing = [c for c in self.settings.counties if c not in self.codes]
        if missing:
            await self.map_counties(missing)
        mapped = [c for c in self.settings.counties if c in self.codes]
        if not mapped:
            return 0
        try:
            alerts = await asyncio.to_thread(self.fetch, [self.codes[c]["code"] for c in mapped])
        except Exception as e:  # the network or the NWS
            if self.problem is None:
                print(f"Auto alerts: couldn't check for alerts ({e}); trying again every "
                      f"{self.settings.every_minutes:g} min", flush=True)
            self.problem = str(e)
            return 0
        if self.problem is not None:
            print("Auto alerts: checking for alerts again", flush=True)
            self.problem = None
        now = time.time()
        self.last_check = now
        new = {}  # county -> [(key, until, alert)] not posted before
        active = set()
        current = {}
        for alert in alerts:
            key = _key(alert)
            if key in active:
                continue
            active.add(key)
            for county in self.counties_for(alert, mapped):
                current.setdefault(county, []).append(summary(alert))
            until = self.remember_until(alert, now)
            if key in self.posted:
                self.posted[key] = max(self.posted[key], until)
            else:
                new.setdefault(self.county_for(alert, mapped), []).append((key, until, alert))
        self.current = current
        sent = 0
        try:
            if new:
                slot, added = await channel_slot(self.radio, self.settings.channel)
                if added:
                    print(f"Auto alerts: added {self.settings.channel} to channel slot {slot}", flush=True)
            for county, entries in new.items():
                messages = format_alerts(county, [alert for _, _, alert in entries], message_limit(self.radio))
                await post(self.radio, slot, messages, self.state.channel_log)
                # Only now, so alerts that couldn't be posted are tried again next round.
                self.posted.update((key, until) for key, until, _ in entries)
                sent += len(messages)
                print(f"Auto alerts: posted {len(messages)} new alert message(s) for {county} to "
                      f"{self.settings.channel}:", flush=True)
                for message in messages:
                    print(f"  {message}", flush=True)
                self.state.record("auto", f"posted {len(messages)} new {county} alert message(s) to "
                                          f"{self.settings.channel}")
        finally:
            for key in [k for k, until in self.posted.items() if k not in active and until < now]:
                del self.posted[key]
            self.store.save()
        return sent

    async def wait_for_network(self):
        """Wait until there's a network, at most NETWORK_WAIT seconds, so the
        first round right after the computer starts doesn't fail. Returns
        True if there is one."""
        waited = 0
        while not await asyncio.to_thread(self.reachable):
            if waited >= NETWORK_WAIT:
                print(f"Auto alerts: still no network after {NETWORK_WAIT // 60} min; checking anyway",
                      flush=True)
                return False
            if not waited:
                print(f"Auto alerts: no network yet; waiting up to {NETWORK_WAIT // 60} min before the "
                      "first check", flush=True)
            await asyncio.sleep(NETWORK_POLL)
            waited += NETWORK_POLL
        if waited:
            print(f"Auto alerts: network up after {waited}s", flush=True)
        return True

    async def run(self):
        """Check every every_minutes until cancelled, the first time once
        there's a network; a failed round is logged and tried again next
        time, never stopping the bot."""
        await self.wait_for_network()
        while True:
            try:
                await self.check()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # e.g. no free channel slot, or the radio refused a message
                print(f"Auto alerts: {e}; trying again in {self.settings.every_minutes:g} min", flush=True)
                self.state.error("auto alerts failed")
            await asyncio.sleep(self.settings.every_minutes * 60)


TEST_KEYS = {"weekly", "timezone", "message"}
DEFAULT_TEST_MESSAGE = "TEST: this is a test of the {channel} alert channel. No action needed."
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# The longest a scheduled task sleeps before looking at the clock again, so a
# clock change or a suspended computer doesn't throw the time off (seconds).
MAX_SLEEP = 3600


def parse_weekly(text):
    """(weekday 0-6 from Monday, hour, minute) from "Wednesday 17:00",
    "wed 5:00pm" or "Wed 5PM". Raises ValueError."""
    words = text.lower().replace(".", "").split()
    if len(words) == 3 and words[2] in ("am", "pm"):  # "wed 5:00 pm"
        words = [words[0], words[1] + words[2]]
    problem = ValueError(f"{text!r} isn't a day and time, e.g. \"Wednesday 17:00\" or \"Wed 5:00PM\"")
    if len(words) != 2:
        raise problem
    days = [d for d in DAYS if len(words[0]) >= 3 and d.startswith(words[0])]
    if len(days) != 1:
        raise problem
    clock, half = words[1], None
    if clock.endswith(("am", "pm")):
        clock, half = clock[:-2], clock[-2:]
    hour, _, minute = clock.partition(":")
    if not hour.isdigit() or not (minute.isdigit() and len(minute) == 2 or minute == "" and half):
        raise problem
    hour, minute = int(hour), int(minute or 0)
    if half:
        if not 1 <= hour <= 12:
            raise problem
        hour = hour % 12 + (12 if half == "pm" else 0)
    if hour > 23 or minute > 59:
        raise problem
    return DAYS.index(days[0]), hour, minute


@dataclass(frozen=True)
class TestSettings:
    channel: str = DEFAULT_CHANNEL
    message: str = DEFAULT_TEST_MESSAGE.format(channel=DEFAULT_CHANNEL)
    weekly: tuple = None  # (weekday, hour, minute), or None for no weekly test
    zone: zoneinfo.ZoneInfo = None  # None for the computer's own time zone


def load_alert_test(config, channel):
    """TestSettings from [alert_test] in config.toml, posting to channel (the
    alerts' channel). Exits on a mistake."""
    section = config.get("alert_test", {})
    if not isinstance(section, dict) or set(section) - TEST_KEYS:
        raise SystemExit(f"[alert_test] may only set {', '.join(sorted(TEST_KEYS))}.")
    message = section.get("message", DEFAULT_TEST_MESSAGE.format(channel=channel))
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > MAX_REPLY_LEN:
        raise SystemExit(f"[alert_test] message must be some text, at most {MAX_REPLY_LEN} characters.")
    weekly = section.get("weekly", "")
    if not isinstance(weekly, str):
        raise SystemExit('[alert_test] weekly must be a day and time, e.g. "Wednesday 17:00".')
    try:
        weekly = parse_weekly(weekly) if weekly.strip() else None
    except ValueError as e:
        raise SystemExit(f"[alert_test] weekly: {e}.") from None
    zone = section.get("timezone")
    if zone is not None:
        try:
            zone = zoneinfo.ZoneInfo(zone)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, TypeError):
            raise SystemExit(f"[alert_test] timezone {zone!r} isn't a time zone, e.g. \"America/Chicago\" "
                             "(on Windows, also pip install tzdata).") from None
    return TestSettings(channel, message.strip(), weekly, zone)


def next_weekly(weekly, zone=None, now=None):
    """The time.time() of the next (weekday, hour, minute) after now, in the
    time zone (the computer's own if None), daylight saving included."""
    now = time.time() if now is None else now
    day, hour, minute = weekly
    today = datetime.datetime.fromtimestamp(now, zone).date()
    for ahead in range(8):
        date = today + datetime.timedelta(days=ahead)
        if date.weekday() != day:
            continue
        when = datetime.datetime.combine(date, datetime.time(hour, minute), zone).timestamp()
        if when > now:
            return when
    raise AssertionError("unreachable: a weekday comes round within 8 days")


def when_text(timestamp, zone=None):
    """"Wed 5:00PM CDT" for a time.time()."""
    t = datetime.datetime.fromtimestamp(timestamp, zone).astimezone(zone)
    return f"{t:%a} {t.hour % 12 or 12}:{t:%M}{'AM' if t.hour < 12 else 'PM'} {t:%Z}".strip()


class AlertTest:
    """Posts the test message to the alert channel: on request, and weekly if set."""

    def __init__(self, radio, settings, state, counties=()):
        self.radio = radio
        self.settings = settings
        self.state = state
        self.counties = counties  # the counties [alerts] watches, listed after the message
        self.store = state.store(ALERTS_FILE)  # "last_test": time.time() of the last test

    def problem(self):
        """Why the test message can't go out from this radio, or None."""
        limit = message_limit(self.radio)
        if len(self.settings.message) > limit:
            return (f"[alert_test] message is {len(self.settings.message)} characters; a channel message from "
                    f"this node has room for {limit}")
        return None

    def messages(self):
        """The test message, then the watched counties, as channel messages."""
        return [self.settings.message] + county_lines(self.counties, message_limit(self.radio))

    def next_time(self):
        """time.time() of the next weekly test, or None if there is none."""
        return next_weekly(self.settings.weekly, self.settings.zone) if self.settings.weekly else None

    def describe(self):
        day, hour, minute = self.settings.weekly
        zone = f" {self.settings.zone.key}" if self.settings.zone else ""
        return (f"{DAYS[day].capitalize()} {hour:02d}:{minute:02d}{zone} to {self.settings.channel}; "
                f"next {when_text(self.next_time(), self.settings.zone)}")

    async def send(self, by):
        """Post the test message now; by is who asked ("auto" for the
        schedule). Returns (slot, added, the messages posted)."""
        slot, added = await channel_slot(self.radio, self.settings.channel)
        messages = self.messages()
        await post(self.radio, slot, messages, self.state.channel_log)
        self.store.data["last_test"] = time.time()
        self.store.save()
        self.state.record(by, f"posted the alert test to {self.settings.channel}")
        return slot, added, messages

    async def run(self):
        """Post the test every week until cancelled; a failure is logged and
        the next week's test still goes out."""
        while True:
            due = self.next_time()
            while (wait := due - time.time()) > 0:
                await asyncio.sleep(min(wait, MAX_SLEEP))
            try:
                _, _, messages = await self.send("auto")
                print(f"Weekly alert test posted to {self.settings.channel}:", flush=True)
                for message in messages:
                    print(f"  {message}", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # e.g. no free channel slot, or the radio refused the message
                print(f"Weekly alert test failed: {e}", flush=True)
                self.state.error("weekly alert test failed")
