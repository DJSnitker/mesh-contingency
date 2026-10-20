"""Test helpers for commands, built in or third party.

    from mesh_contingency.testing import FakeMeshCore, make_context

    cmd = MyCommand(make_context("mine", options={"station": "x"}, radio=FakeMeshCore()))
    result = await cmd.execute("some text", Sender("Dana", "d0" * 32))
"""

import asyncio
from types import SimpleNamespace

from meshcore import EventType

from .api import Context
from .directory import Directory


def make_context(name, options=None, users=None, admins=None, radio=None, commands=None, directory=None):
    """A Context like the one the bot creates a command with. Pass users and
    admins, or a Directory to change them during a test."""
    return Context(name=name, options=options or {}, directory=directory or Directory(users, admins),
                   radio=radio, commands=commands if commands is not None else {})


def event(event_type, payload=None):
    """A minimal stand-in for meshcore.Event."""
    return SimpleNamespace(type=event_type, payload=payload if payload is not None else {})


def full_key(prefix):
    """The full 64-hex public key the fakes give a contact with this prefix
    (or the key itself, if already full)."""
    return prefix if len(prefix) == 64 else prefix + "00" * 26


def make_contact(prefix, name, node_type=1):
    """A contact record shaped like the ones MeshCore reports."""
    return {
        "public_key": full_key(prefix),
        "type": node_type,
        "flags": 0,
        "out_path_len": -1,
        "out_path_hash_mode": -1,
        "out_path": "",
        "adv_name": name,
        "last_advert": 0,
        "adv_lat": 0.0,
        "adv_lon": 0.0,
        "lastmod": 0,
    }


class FakeCommands:
    def __init__(self, radio):
        self.radio = radio

    async def send_msg_with_retry(self, contact, text):
        self.radio.sent.append((contact["adv_name"], text))
        return self.radio.ack_result

    async def get_contacts(self, lastmod=0):
        self.radio.get_contacts_calls += 1
        # A refresh picks up anything the radio has stored since we last looked.
        self.radio.known.update(self.radio.stored)

    async def set_manual_add_contacts(self, value):
        self.radio.manual_add_calls.append(value)
        if self.radio.manual_add_result.type != EventType.ERROR:
            self.radio.self_info["manual_add_contacts"] = value
        return self.radio.manual_add_result

    async def add_contact(self, contact):
        self.radio.added.append(contact)
        if self.radio.add_contact_result.type != EventType.ERROR:
            self.radio.stored[contact["public_key"]] = contact["adv_name"]
        return self.radio.add_contact_result

    async def send_advert(self, flood=False):
        self.radio.adverts.append(flood)
        return self.radio.advert_result


class FakeMeshCore:
    """Records what the bot asks of the radio and lets tests deliver events."""

    def __init__(self, contacts=None, manual_add_contacts=False):
        # Contacts as {prefix or full public key: name}; a prefix gets full_key(prefix).
        self.known = dict(contacts or {})  # as cached by the library
        self.stored = dict(self.known)  # what the radio itself holds
        self.self_info = {"name": "test-node", "manual_add_contacts": manual_add_contacts}
        self.auto_update_contacts = False
        self.commands = FakeCommands(self)
        self.handlers = {}
        self.listening = asyncio.Event()
        self.disconnected = False
        # Recorded calls
        self.sent = []
        self.added = []
        self.adverts = []
        self.manual_add_calls = []
        self.get_contacts_calls = 0
        # Results the radio returns
        self.ack_result = event(EventType.MSG_SENT)
        self.manual_add_result = event(EventType.OK)
        self.add_contact_result = event(EventType.OK)
        self.advert_result = event(EventType.OK)

    @property
    def contacts(self):
        return {full_key(k): {"public_key": full_key(k), "adv_name": name} for k, name in self.known.items()}

    def get_contact_by_key_prefix(self, prefix):
        # Like the library: the first contact whose key starts with prefix.
        if not prefix:
            return None
        return next((c for key, c in self.contacts.items() if key.startswith(prefix.lower())), None)

    def subscribe(self, event_type, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    async def deliver(self, event_type, payload):
        for handler in self.handlers.get(event_type, []):
            await handler(event(event_type, payload))

    async def dm(self, prefix, text):
        """Deliver a direct message from the given pubkey prefix."""
        await self.deliver(EventType.CONTACT_MSG_RECV, {"type": "PRIV", "pubkey_prefix": prefix, "text": text})

    async def ensure_contacts(self):
        pass

    async def start_auto_message_fetching(self):
        self.listening.set()

    async def stop_auto_message_fetching(self):
        pass

    async def disconnect(self):
        self.disconnected = True
