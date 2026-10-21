"""health: how the node is doing, for admins.

The radio (battery, its own uptime, contact capacity), the people (users, join
requests, messages waiting, check-ins), what the bot has done since it started
(messages, replies, undelivered replies, errors), emails in the last 24 hours,
the last flood advert and the users file. Anything the radio doesn't answer
within RADIO_SECONDS is left out.
"""

import asyncio
import time

from meshcore import EventType

from ..alerts import plural_counties, when_text
from ..api import Command, CommandError, CommandResult, pack
from ..console import ADVERTS_FILE
from ..state import ago
from .join import FILENAME as REQUESTS
from .mailbox import FILENAME as MAILBOX
from .status import FILENAME as STATUSES

RADIO_SECONDS = 5


def duration(seconds):
    """A length of time in its two largest units: "2d 3h", "3h 5m", "12m"."""
    seconds = int(seconds)
    days, hours, minutes = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class HealthCommand(Command):
    summary = "How the node is doing: radio, battery, users, messages, errors"

    async def ask(self, request, wanted):
        """The payload of a radio request, or None if it fails, is refused or
        takes too long."""
        try:
            result = await asyncio.wait_for(request(), RADIO_SECONDS)
        except Exception:
            return None
        return result.payload if result is not None and result.type == wanted else None

    async def radio_items(self):
        radio = self.ctx.radio
        if radio is None:
            return ["no radio"]
        info = await self.ask(radio.commands.send_device_query, EventType.DEVICE_INFO) or {}
        stats = await self.ask(radio.commands.get_stats_core, EventType.STATS_CORE) or {}
        battery = await self.ask(radio.commands.get_bat, EventType.BATTERY) or {}
        model = " ".join(part for part in (info.get("model"), info.get("ver")) if part)
        items = [f"radio {radio.self_info.get('name', '?')}" + (f" ({model})" if model else "")]
        if "uptime_secs" in stats:
            items.append(f"radio up {duration(stats['uptime_secs'])}")
        millivolts = battery.get("level") or stats.get("battery_mv")
        if millivolts:
            items.append(f"battery {millivolts / 1000:.2f}V")
        contacts = len(radio.contacts)
        items.append(f"contacts {contacts}/{info['max_contacts']}" if info.get("max_contacts")
                     else f"contacts {contacts}")
        return items

    def people_items(self):
        state = self.ctx.state
        boxes = state.store(MAILBOX).data
        waiting = sum(len(box) for box in boxes.values())
        return [
            f"users {len(self.ctx.users)} ({len(self.ctx.admins)} admin)",
            f"join requests {len(state.store(REQUESTS).data)}",
            f"inbox {waiting} message(s) for {sum(1 for box in boxes.values() if box)} user(s)",
            f"check-ins {len(state.store(STATUSES).data)}",
        ]

    def activity_items(self):
        state, counts = self.ctx.state, self.ctx.state.counts
        items = [f"since start {counts['messages']} message(s) in, {counts['sent']} out "
                 f"({counts['undelivered']} undelivered)"]
        if state.last_error:
            when, what = state.last_error
            items.append(f"errors {counts['errors']}, last {what} {ago(when)}")
        else:
            items.append("errors none")
        cap = self.ctx.limits.emails_per_day_total
        items.append(f"emails 24h {state.emails.addresses()}" + (f"/{cap}" if cap else "") + " address(es)")
        watcher = state.alert_watcher
        if watcher:
            checked = f"checked {ago(watcher.last_check)}" if watcher.last_check else "not checked yet"
            if watcher.problem:
                checked += ", last check failed"
            if watcher.unmapped:
                checked += f", not looked up: {'; '.join(watcher.unmapped)}"
            items.append(f"auto alerts {plural_counties(len(watcher.settings.counties))}, {checked}")
        test = state.alert_test
        if test and test.settings.weekly:
            items.append(f"next alert test {when_text(test.next_time(), test.settings.zone)}")
        last = state.store(ADVERTS_FILE).data.get("last_flood")
        items.append(f"last flood advert {ago(last)}" if last else "no flood advert yet")
        directory = self.ctx.directory
        if directory.problem:
            when, why = directory.problem
            items.append(f"{directory.name} NOT reloaded {ago(when)}: {why}")
        elif directory.loaded:
            items.append(f"{directory.name} loaded {ago(directory.loaded)}")
        return items

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        up = duration(time.time() - self.ctx.state.started)
        items = [f"{self.name}: up {up}", *await self.radio_items(), *self.people_items(), *self.activity_items()]
        return CommandResult(console="; ".join(items), reply=pack(items))
