"""Weather alerts on a public channel: shared by the alert command and the
automatic alert watcher.

The bot never reads channels; it only sends to one. The channel is a hashtag
channel (#name), which anyone can join by adding the same name. If the radio
doesn't have it, it is added to the first empty channel slot.

The watcher ([alerts] in config.toml) watches counties. It looks up each
county's NWS code once (kept until an admin sends alertmap), then every few
minutes asks the National Weather Service for the alerts in all the counties
in a single request, and posts each alert it hasn't posted before, once, even
if several counties share it. The codes and what it has posted are kept in
alerts.json next to config.toml, so a restart doesn't post anything again.
"""

import asyncio
import datetime
import time
from dataclasses import dataclass
from hashlib import sha256

from meshcore import EventType

from .api import MAX_PARTS, MAX_REPLY_LEN, fit_reply
from .weather import STATE_FIPS, alert_counties, county_alerts, county_code

DEFAULT_CHANNEL = "#contingency-wx"
# Channel slots to look through if the radio doesn't say how many it has.
DEFAULT_SLOTS = 8
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


async def channel_slot(radio, channel):
    """Return (slot, added): the radio's slot for the channel, adding it to
    the first empty slot if it isn't there. Raises NoChannelSlot if there is
    no room, or RuntimeError if the radio refuses."""
    secret = hashtag_secret(channel)
    info = await radio.commands.send_device_query()
    slots = DEFAULT_SLOTS if info.type == EventType.ERROR else info.payload.get("max_channels", DEFAULT_SLOTS)
    empty = None
    for slot in range(slots):
        res = await radio.commands.get_channel(slot)
        if res.type == EventType.ERROR:
            break
        if res.payload.get("channel_secret") == secret:
            return slot, False
        unused = not res.payload.get("channel_name") and not any(res.payload.get("channel_secret", b""))
        if empty is None and unused:
            empty = slot
    if empty is None:
        raise NoChannelSlot(f"no free channel slot on the radio for {channel}")
    res = await radio.commands.set_channel(empty, channel)
    if res.type == EventType.ERROR:
        raise RuntimeError(f"radio rejected adding {channel} to slot {empty}: {res.payload}")
    return empty, True


async def post(radio, slot, messages):
    """Send messages to a channel slot, a little apart."""
    for i, message in enumerate(messages):
        if i:
            await asyncio.sleep(SEND_GAP)
        res = await radio.commands.send_chan_msg(slot, message)
        if res.type == EventType.ERROR:
            raise RuntimeError(f"radio rejected channel message {i + 1} of {len(messages)}: {res.payload}")


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


class AlertWatcher:
    """Posts new NWS alerts for the watched counties to the alert channel."""

    def __init__(self, radio, settings, state, lookup=None, fetch=None):
        self.radio = radio
        self.settings = settings
        self.state = state
        self.lookup = lookup or county_code  # (name, state) -> NWS code, e.g. "TXC441"
        self.fetch = fetch or county_alerts  # [NWS codes] -> active alerts
        # {"counties": {"Taylor, TX": {"code", "time"}}, "posted": {key: time to forget it}}
        self.store = state.store(ALERTS_FILE)
        self.store.data.pop("zones", None)  # from a test version that watched zipcodes
        self.unmapped = {}  # county -> why its code couldn't be looked up
        self.problem = None  # why the last request for alerts failed, until one works
        self.last_check = None  # time.time() of the last request for alerts that worked
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
        covered = alert_counties(alert)
        return next((c for c in mapped if self.codes[c]["code"] in covered), mapped[0])

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
        for alert in alerts:
            key = _key(alert)
            if key in active:
                continue
            active.add(key)
            until = self.remember_until(alert, now)
            if key in self.posted:
                self.posted[key] = max(self.posted[key], until)
            else:
                new.setdefault(self.county_for(alert, mapped), []).append((key, until, alert))
        sent = 0
        try:
            if new:
                slot, added = await channel_slot(self.radio, self.settings.channel)
                if added:
                    print(f"Auto alerts: added {self.settings.channel} to channel slot {slot}", flush=True)
            for county, entries in new.items():
                messages = format_alerts(county, [alert for _, _, alert in entries], message_limit(self.radio))
                await post(self.radio, slot, messages)
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

    async def run(self):
        """Check every every_minutes until cancelled; a failed round is logged
        and tried again next time, never stopping the bot."""
        while True:
            try:
                await self.check()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # e.g. no free channel slot, or the radio refused a message
                print(f"Auto alerts: {e}; trying again in {self.settings.every_minutes:g} min", flush=True)
                self.state.error("auto alerts failed")
            await asyncio.sleep(self.settings.every_minutes * 60)
