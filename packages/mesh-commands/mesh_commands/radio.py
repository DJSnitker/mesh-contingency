"""The MeshCore side: who sent a direct message, and sending replies.

This is the only module that talks to a meshcore.MeshCore radio.

    link = MeshLink(mc, roles)
    commands = registry.build(mc, roles, send=link.send_later)
    link.listen(Dispatcher(commands, roles, link.send, registry.disabled))
"""

import asyncio

from meshcore import EventType

from .command import Sender
from .replies import MAX_REPLY_LEN


class MeshLink:
    """Direct messages through one connected radio: sending (one at a time,
    since the radio matches each ack to the message it just sent) and
    working out who each message is from."""

    def __init__(self, mc, roles=None):
        self.mc = mc
        self.roles = roles  # only to say when a shared key prefix is an admin's
        self._lock = asyncio.Lock()
        self._background = set()  # running background tasks, kept so they aren't garbage collected

    async def send(self, key, text, what="reply"):
        """Send a direct message to a contact by public key (or, for a sender
        we couldn't identify, the prefix they wrote from), retrying until the
        radio reports an ack, and print whether it was delivered."""
        if len(text) > MAX_REPLY_LEN:
            # Error text can echo the sender's input; never exceed the mesh limit.
            text = text[: MAX_REPLY_LEN - 3] + "..."
        prefix = key[:12]  # printed instead of the full key
        contact = self.mc.get_contact_by_key_prefix(key)
        if contact is None:
            # The radio may have learned this node after we loaded contacts.
            await self.mc.commands.get_contacts()
            contact = self.mc.get_contact_by_key_prefix(key)
        if contact is None:
            print(f"  (no contact {prefix} to send {what} to; is it in the radio's contacts?)", flush=True)
            return
        async with self._lock:
            result = await self.mc.commands.send_msg_with_retry(contact, text)
        if result is None:
            print(f"  ({what} to {prefix} not acknowledged after retries)", flush=True)
        else:
            print(f"  ({what} to {prefix} delivered)", flush=True)

    def in_background(self, coro):
        """Run a coroutine as a background task, kept until it finishes."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def send_later(self, key, text, what="notice"):
        """Send a direct message in the background, without holding up the
        radio's event handling (or a command's reply) while it goes out."""
        self.in_background(self.send(key, text, what=what))

    def _with_prefix(self, prefix):
        return [c for c in self.mc.contacts.values() if prefix and c.get("public_key", "").lower().startswith(prefix)]

    async def sender_of(self, prefix):
        """Return the Sender of a direct message that came with this key prefix.

        A message carries only the sender's key prefix, so it is matched to
        the radio's contacts for the full public key that permissions use. If
        no contact or more than one has the prefix, the sender is unidentified
        (public_key None): a node with a copied prefix never gets rights.
        """
        matches = self._with_prefix(prefix)
        if not matches:
            # The radio may have learned this node after we loaded contacts.
            await self.mc.commands.get_contacts()
            matches = self._with_prefix(prefix)
        if len(matches) != 1:
            if matches:
                admin = self.roles is not None and any(self.roles.is_admin(c["public_key"].lower()) for c in matches)
                print(f"  ({len(matches)} contacts share key prefix {prefix}; sender not identified"
                      f"{'; one is an admin, so remove the impostor from the radio' if admin else ''})", flush=True)
            return Sender(prefix, None)
        contact = matches[0]
        return Sender(contact.get("adv_name") or prefix, contact["public_key"].lower())

    def listen(self, dispatcher):
        """Hand every direct message the radio receives to dispatcher.handle.
        Channel messages are not listened to. Call the radio's
        start_auto_message_fetching() afterwards."""

        async def on_message(event):
            msg = event.payload
            prefix = msg.get("pubkey_prefix", "").lower()
            await dispatcher.handle(prefix, await self.sender_of(prefix), msg.get("text", ""))

        self.mc.subscribe(EventType.CONTACT_MSG_RECV, on_message)
