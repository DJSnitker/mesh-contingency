"""health: how the node is doing, for admins.

The radio (battery, its own uptime, contact capacity), the people (users, join
requests, messages waiting, check-ins), what the bot has done since it started
(messages, replies, undelivered replies, errors), emails in the last 24 hours
and the last one that failed, the last flood advert and the users file.
Anything the radio doesn't answer within RADIO_SECONDS is left out.
"""

import time

from meshcore import EventType

from ..alerts import plural_counties, when_text
from ..api import Command, CommandError, CommandResult, pack
from ..console import ADVERTS_FILE
from ..state import ago, duration
from ..watch import LABELS, ask_radio
from .join import FILENAME as REQUESTS
from .mailbox import FILENAME as MAILBOX
from .status import FILENAME as STATUSES

RADIO_SECONDS = 5


class HealthCommand(Command):
    summary = "How the node is doing: radio, battery, users, messages, errors"

    async def radio_items(self):
        radio = self.ctx.radio
        if radio is None:
            return ["no radio"]
        info = await ask_radio(radio.commands.send_device_query, EventType.DEVICE_INFO, RADIO_SECONDS) or {}
        stats = await ask_radio(radio.commands.get_stats_core, EventType.STATS_CORE, RADIO_SECONDS) or {}
        battery = await ask_radio(radio.commands.get_bat, EventType.BATTERY, RADIO_SECONDS) or {}
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
        if state.emails.last_failure:
            when, cause = state.emails.last_failure
            items.append(f"last email failed {ago(when)}: {cause}")
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
        backups = state.backups
        if backups:
            if backups.failing:
                items.append(f"backup failing: {backups.failing}")
            else:
                items.append(f"last backup {ago(backups.last)}" if backups.last else "no backup yet")
        if state.watch:
            items.append(f"watch: {', '.join(LABELS[p] for p in state.watch.active) or 'no problems'}")
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
