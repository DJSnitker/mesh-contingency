"""Check-ins: ok [status] records how the sender is doing, status <name or key>
looks it up, clearstatus empties the list.

Statuses are kept in status.json next to config.toml, so they survive a
restart, one per node.
"""

import re
import time

from ..api import Command, CommandError, CommandResult
from ..directory import unquote
from ..state import ago

FILENAME = "status.json"
DEFAULT_STATUS = "ok"
# A key prefix typed into status: at least 4 hex characters.
KEY_PREFIX_RE = re.compile(r"[0-9a-f]{4,64}")


class StatusBase(Command):
    """Commands that share the statuses in status.json."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(FILENAME)  # fails at startup if the file is unreadable

    @property
    def statuses(self):
        """{public key: {"name", "status", "time"}}"""
        return self.store.data


class OkCommand(StatusBase):
    args = "[status]"
    summary = "Check in: tell others you're ok, or how you are"

    async def execute(self, text, sender):
        if sender.public_key is None:
            raise CommandError(f"{self.name}: can't tell who you are; send an advert and try again")
        name = self.ctx.name_of(sender)
        status = text or DEFAULT_STATUS
        self.statuses[sender.public_key] = {"name": name, "status": status, "time": time.time()}
        self.store.save()
        return CommandResult(console=f"Status for {name}: {status}", reply=f"{self.name}: saved for {name}")


class StatusCommand(StatusBase):
    args = "<name or key>"
    summary = "Show someone's last check-in"

    def find(self, text):
        """Keys of the statuses whose name matches text (exactly, or else as
        part of the name), or else whose key starts with it. The name may be
        in ( )."""
        quoted = unquote(text)
        wanted = (quoted[0] if quoted and not quoted[1] else text).lower()
        for match in (lambda key, entry: entry["name"].lower() == wanted,
                      lambda key, entry: wanted in entry["name"].lower(),
                      lambda key, entry: KEY_PREFIX_RE.fullmatch(wanted) and key.startswith(wanted)):
            keys = [key for key, entry in self.statuses.items() if match(key, entry)]
            if keys:
                return keys
        return []

    async def execute(self, text, sender):
        if not text:
            if sender.public_key not in self.statuses:
                raise CommandError(f"usage: {self.usage}")
            keys = [sender.public_key]
        else:
            keys = self.find(text)
        if not keys:
            raise CommandError(f"{self.name}: no status for {text}")
        names = [self.statuses[key]["name"] for key in keys]
        lines = []
        for key in sorted(keys, key=lambda k: -self.statuses[k]["time"]):
            entry = self.statuses[key]
            # The key prefix tells apart people with the same name.
            who = f"{entry['name']} ({key[:12]})" if names.count(entry["name"]) > 1 else entry["name"]
            lines.append(f"{who}: {entry['status']} ({ago(entry['time'])})")
        reply = "; ".join(lines)
        return CommandResult(console=reply, reply=reply)


class ClearStatusCommand(StatusBase):
    summary = "Delete every check-in"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        count = len(self.statuses)
        self.statuses.clear()
        self.store.save()
        reply = f"{self.name}: cleared {count} status{'' if count == 1 else 'es'}"
        self.ctx.state.record(self.ctx.name_of(sender), f"cleared {count} check-in(s)")
        return CommandResult(console=reply, reply=reply)


class CheckinsCommand(StatusBase):
    args = "[page <n>]"
    summary = "Roll call of all check-ins (paginated)"

    def get_page_size(self):
        """Number of checkins per page (tuned for mesh message limits)."""
        return 5

    def get_all_users(self):
        """Return list of all users from directory, sorted by name."""
        return sorted(self.ctx.directory.users.items(), key=lambda item: item[1].get("name", "").lower())

    def get_checked_in(self):
        """Return dict of users who have checked in: {public_key: {"name", "status", "time"}}"""
        return self.statuses

    def get_page_data(self, page_num):
        """Return (total_pages, page_entries) where page_entries is a list of dicts.
        Each entry has: {name, status, time_ago, checked_in}"""
        all_users = self.get_all_users()
        checked_in = self.get_checked_in()
        page_size = self.get_page_size()
        total_pages = max(1, (len(all_users) + page_size - 1) // page_size)

        # Validate page number
        if page_num < 1 or page_num > total_pages:
            raise CommandError(f"checkins: page {page_num} out of range (1-{total_pages})")

        # Build list of all users with their status
        entries = []
        for key, user_info in all_users:
            if key in checked_in:
                status_info = checked_in[key]
                entries.append({
                    "name": status_info["name"],
                    "status": status_info["status"],
                    "time_ago": ago(status_info["time"]),
                    "checked_in": True,
                })
            else:
                entries.append({
                    "name": user_info.get("name", key[:12]),
                    "status": None,
                    "time_ago": None,
                    "checked_in": False,
                })

        # Return requested page
        start = (page_num - 1) * page_size
        end = start + page_size
        return total_pages, entries[start:end]

    async def execute(self, text, sender):
        # Parse arguments for pagination
        page_num = 1
        if text:
            parts = text.strip().split()
            if len(parts) == 2 and parts[0].lower() == "page":
                try:
                    page_num = int(parts[1])
                except ValueError:
                    raise CommandError(f"usage: {self.usage}") from None
            else:
                raise CommandError(f"usage: {self.usage}")

        total_pages, page_entries = self.get_page_data(page_num)

        # Format output
        lines = ["Roll Call:"]
        checked_in_count = 0
        missing_count = 0

        for entry in page_entries:
            if entry["checked_in"]:
                lines.append(f"✓ {entry['name']}: {entry['status']} ({entry['time_ago']})")
                checked_in_count += 1
            else:
                lines.append(f"✗ {entry['name']}: missing")
                missing_count += 1

        # Summary line
        total_users = len(self.get_all_users())
        total_checked_in = len(self.get_checked_in())
        summary = f"\n{total_checked_in}/{total_users} checked in. Page {page_num}/{total_pages}."
        if total_pages > 1:
            summary += " Use 'checkins page <n>' to see other pages."

        console_output = "\n".join(lines) + summary
        reply = console_output

        return CommandResult(console=console_output, reply=reply)
