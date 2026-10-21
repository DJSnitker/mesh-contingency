"""history [page]: what admins have done, newest first.

Approvals, refusals, removals, renames, cleared passphrases, cleared
check-ins and posted alerts, and users leaving, as recorded with
State.record in history.json next to config.toml.
"""

from ..api import Command, CommandError, CommandResult, pack, page
from ..state import HISTORY_FILE, ago


class HistoryCommand(Command):
    args = "[page]"
    summary = "What admins have done (approve, remove, rename...), newest first"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(HISTORY_FILE)  # fails at startup if the file is unreadable

    async def execute(self, text, sender):
        if text and not text.isdigit():
            raise CommandError(f"usage: {self.usage}")
        entries = self.store.data.get("entries", [])
        if not entries:
            return CommandResult(console="", reply=f"{self.name}: nothing yet")
        items = [f"{ago(entry['time'])} {entry['by']}: {entry['what']}" for entry in reversed(entries)]
        items[0] = f"{self.name} ({len(entries)}): {items[0]}"
        messages = pack(items)
        reply = page(messages, int(text or 1), self.name)
        return CommandResult(console="\n".join(reply), reply=reply)
