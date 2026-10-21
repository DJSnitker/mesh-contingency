"""contacts [name or key] [page]: list the radio's contacts over the mesh,
the same list the console's contacts command prints."""

from ..api import Command, CommandResult, pack, page
from ..contacts import contact_rows


class ContactsCommand(Command):
    args = "[name or key] [page]"
    summary = "List the radio's contacts, or those whose name or key starts with name"

    def parse(self, text):
        """Return (filter, page number). A short number at the end is the
        page; anything else filters, so "contacts 37ca" finds a key prefix."""
        words = text.split()
        if words and words[-1].isdigit() and len(words[-1]) <= 2:
            return " ".join(words[:-1]), int(words[-1])
        return " ".join(words), 1

    def entry(self, name, key, kind):
        flags = [kind] if kind not in ("", "chat") else []
        if key in self.ctx.admins:
            flags.append("admin")
        if key in self.ctx.users:
            flags.append("user")
        return f"{name} {key[:12]}" + (f" ({', '.join(flags)})" if flags else "")

    async def execute(self, text, sender):
        wanted, number = self.parse(text)
        rows = contact_rows(self.ctx.radio, wanted)
        matching = f" matching {wanted}" if wanted else ""
        if not rows:
            return CommandResult(console="", reply=f"{self.name}: none{matching}")
        messages = pack([f"{self.name}{matching} ({len(rows)}):"] + [self.entry(*row) for row in rows], separator=" ")
        again = f"{self.name} {wanted}" if wanted else self.name
        reply = page(messages, number, self.name, again)
        return CommandResult(console="\n".join(reply), reply=reply)
