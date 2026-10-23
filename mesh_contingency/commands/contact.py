"""contact remove|path <name or key>: manage one of the radio's contacts.

remove takes it off the radio, which holds only so many (health shows how
many of how many): it asks first, and says if it's a user or an admin, who
can't be messaged until they advert again. A node whose type [contacts]
auto_add adds comes back by itself when it next adverts. path resets the
route the radio keeps to a contact, for one whose messages stopped getting
through: the next message floods to find a new one.
"""

from meshcore import EventType

from ..api import CONFIRM_SECONDS, Command, CommandError, CommandResult, Confirmations
from ..contacts import ContactNotFound, find_contact

ACTIONS = ("remove", "path")


class ContactCommand(Command):
    args = "remove|path <name or key>"
    summary = "Remove one of the radio's contacts, or reset the path to it"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance
        self.confirmations = Confirmations()

    def find(self, text):
        try:
            return find_contact(self.radio, text)
        except ContactNotFound as e:
            raise CommandError(f"{self.name}: {e}") from None

    def who(self, key):
        """", a user" or ", an admin", for one of the node's people."""
        if key in self.ctx.admins:
            return ", an admin"
        return ", a user" if key in self.ctx.users else ""

    async def execute(self, text, sender):
        action, _, rest = text.strip().partition(" ")
        action = action.lower()
        if action not in ACTIONS or not rest.strip():
            raise CommandError(f"usage: {self.usage}")
        contact = self.find(rest)
        key = contact["public_key"].lower()
        name = contact.get("adv_name") or key[:12]
        by = self.ctx.name_of(sender)
        if action == "remove":
            who = self.who(key)
            them = " They can't be messaged until they advert again." if who else ""
            if not self.confirmations.confirmed(sender.public_key, ("remove", key)):
                question = (f"{self.name}: this removes {name} ({key[:12]}{who}) from the radio.{them} Send it "
                            f"again within {CONFIRM_SECONDS // 60} min to confirm.")
                return CommandResult(console="", reply=question, asks=True)
            result = await self.radio.commands.remove_contact(key)
            if result.type == EventType.ERROR:
                raise CommandError(f"{self.name}: the radio didn't remove {name}: {result.payload}")
            # The library keeps its own copy of the radio's contacts, and only
            # ever adds to it.
            self.radio.contacts.pop(contact["public_key"], None)
            reply = f"{self.name}: {name} ({key[:12]}) removed from the radio"
            self.ctx.state.record(by, f"removed contact {name} ({key[:12]}) from the radio")
        else:
            result = await self.radio.commands.reset_path(key)
            if result.type == EventType.ERROR:
                raise CommandError(f"{self.name}: the radio didn't reset the path to {name}: {result.payload}")
            reply = f"{self.name}: path to {name} ({key[:12]}) reset; the next message to it floods"
            self.ctx.state.record(by, f"reset the path to contact {name} ({key[:12]})")
        return CommandResult(console=f"{by}: {reply}", reply=reply)
