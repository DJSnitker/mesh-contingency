"""alert <zipcode>: post the NWS alerts for a zipcode to a public channel.

The bot never reads channels; this only sends to one. The channel is a
hashtag channel (#name), which anyone can join by adding the same name. If the
radio doesn't have it, it is added to the first empty channel slot at startup
(and again when posting, in case it was removed meanwhile).
"""

import asyncio
import datetime
from hashlib import sha256

from meshcore import EventType

from ..api import MAX_PARTS, MAX_REPLY_LEN, Command, CommandError, CommandResult, fit_reply
from ..weather import fetch_alerts

DEFAULT_CHANNEL = "#contingency-wx"
# Channel slots to look through if the radio doesn't say how many it has.
DEFAULT_SLOTS = 8
NO_ALERTS = "No alerts active for {zipcode}"


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


def format_alerts(zipcode, alerts, limit=MAX_REPLY_LEN):
    """One channel message per distinct alert, most important information
    first, at most MAX_PARTS messages."""
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
        messages.append(fit_reply(f"{zipcode} ALERT:", sections, limit))
    if len(messages) > MAX_PARTS:
        more = len(messages) - (MAX_PARTS - 1)
        messages = messages[:MAX_PARTS - 1] + [f"{zipcode}: {more} more alerts; check wx or weather.gov"]
    return messages


class AlertCommand(Command):
    args = "<zipcode>"
    summary = "Post the weather alerts for a zipcode to the public weather channel"
    # Seconds between channel messages, so a burst doesn't crowd the mesh.
    send_gap = 1

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance
        self.channel = ctx.options.get("channel", DEFAULT_CHANNEL)
        if not (isinstance(self.channel, str) and self.channel.startswith("#") and len(self.channel) > 1
                and len(self.channel.encode("utf-8")) <= 31):
            raise ValueError(f"channel must be a hashtag channel name such as {DEFAULT_CHANNEL!r}, "
                             f"up to 31 bytes, not {self.channel!r}")

    async def channel_slot(self):
        """Return (slot, added): the radio's slot for the channel, adding it to
        the first empty slot if it isn't there."""
        secret = hashtag_secret(self.channel)
        info = await self.radio.commands.send_device_query()
        slots = DEFAULT_SLOTS if info.type == EventType.ERROR else info.payload.get("max_channels", DEFAULT_SLOTS)
        empty = None
        for slot in range(slots):
            res = await self.radio.commands.get_channel(slot)
            if res.type == EventType.ERROR:
                break
            if res.payload.get("channel_secret") == secret:
                return slot, False
            unused = not res.payload.get("channel_name") and not any(res.payload.get("channel_secret", b""))
            if empty is None and unused:
                empty = slot
        if empty is None:
            raise CommandError(f"{self.name}: no free channel slot on the radio for {self.channel}")
        res = await self.radio.commands.set_channel(empty, self.channel)
        if res.type == EventType.ERROR:
            raise RuntimeError(f"radio rejected adding {self.channel} to slot {empty}: {res.payload}")
        return empty, True

    async def start(self):
        slot, added = await self.channel_slot()
        return f"{self.name}: {self.channel} is channel slot {slot}{' (added to the radio)' if added else ''}."

    async def execute(self, text, sender):
        args = text.split()
        if len(args) != 1:
            raise CommandError(f"usage: {self.usage}")
        try:
            zipcode, place, alerts = await asyncio.to_thread(fetch_alerts, args[0])
        except ValueError as e:
            raise CommandError(f"{self.name}: {e}") from e
        # A channel message goes out as "<node name>: <text>", within the same limit.
        limit = MAX_REPLY_LEN - len(self.radio.self_info.get("name", "")) - 2
        messages = format_alerts(zipcode, alerts, limit) or [NO_ALERTS.format(zipcode=zipcode)]

        slot, added = await self.channel_slot()
        console = [f"Alerts for {zipcode} ({place}) to {self.channel} (slot {slot}"
                   f"{', added to the radio' if added else ''}):"]
        for i, message in enumerate(messages):
            if i:
                await asyncio.sleep(self.send_gap)
            res = await self.radio.commands.send_chan_msg(slot, message)
            if res.type == EventType.ERROR:
                raise RuntimeError(f"radio rejected channel message {i + 1} of {len(messages)}: {res.payload}")
            console.append(f"  {message}")
        what = f"{len(messages)} alert message(s)" if alerts else f"'{messages[0]}'"
        return CommandResult(console="\n".join(console), reply=f"{self.name}: posted {what} to {self.channel}")
