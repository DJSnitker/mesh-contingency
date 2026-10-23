"""Test helpers for commands, built in or third party.

    from mesh_contingency.testing import FakeMeshCore, make_context

    cmd = MyCommand(make_context("mine", options={"station": "x"}, radio=FakeMeshCore()))
    result = await cmd.execute("some text", Sender("Dana", "d0" * 32))
"""

import asyncio
import hashlib
from types import SimpleNamespace

from meshcore import EventType

from .alerts import PUBLIC_SECRET
from .api import Context
from .directory import Directory
from .limits import Limits
from .state import State

# The well-known key of MeshCore's default Public channel.
PUBLIC_CHANNEL_SECRET = PUBLIC_SECRET.hex()


def make_context(name, options=None, users=None, admins=None, radio=None, commands=None, directory=None,
                 state=None, sent=None, limits=None):
    """A Context like the one the bot creates a command with. Pass users and
    admins, or a Directory to change them during a test. Commands that share
    data need the same State; without a data_dir it is kept in memory. Direct
    messages the command sends with ctx.send are added to the `sent` list as
    (public key, text). limits replaces the default [limits] settings."""
    sent = sent if sent is not None else []
    return Context(name=name, options=options or {}, directory=directory or Directory(users, admins),
                   radio=radio, commands=commands if commands is not None else {}, state=state or State(),
                   send=lambda key, text: sent.append((key, text)), limits=limits or Limits())


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

    async def remove_contact(self, key):
        self.radio.removed.append(key)
        if self.radio.remove_contact_result.type != EventType.ERROR:
            for known in (self.radio.known, self.radio.stored):
                for k in [k for k in known if full_key(k) == key]:
                    del known[k]
        return self.radio.remove_contact_result

    async def reset_path(self, key):
        self.radio.paths_reset.append(key)
        return self.radio.reset_path_result

    async def send_advert(self, flood=False):
        self.radio.adverts.append(flood)
        return self.radio.advert_result

    async def send_device_query(self):
        return event(EventType.DEVICE_INFO, {"max_channels": len(self.radio.channels), **self.radio.device_info})

    async def get_bat(self):
        return self.radio.battery_result

    async def get_stats_core(self):
        return self.radio.stats_result

    async def get_channel(self, channel_idx):
        if channel_idx >= len(self.radio.channels):
            return event(EventType.ERROR, {"reason": "not found"})
        name, secret = self.radio.channels[channel_idx]
        return event(EventType.CHANNEL_INFO, {"channel_idx": channel_idx, "channel_name": name,
                                              "channel_secret": secret})

    async def set_channel(self, channel_idx, channel_name, channel_secret=None):
        if channel_secret is None:  # like the library: a key from the name
            channel_secret = hashlib.sha256(channel_name.encode("utf-8")).digest()[:16]
        self.radio.channels[channel_idx] = (channel_name, channel_secret)
        return event(EventType.OK)

    async def send_chan_msg(self, chan, msg):
        self.radio.channel_sent.append((chan, msg))
        return self.radio.channel_result


class FakeMeshCore:
    """Records what the bot asks of the radio and lets tests deliver events."""

    def __init__(self, contacts=None, manual_add_contacts=False):
        # Contacts as {prefix or full public key: name}; a prefix gets full_key(prefix).
        self.known = dict(contacts or {})  # as cached by the library
        # More of a contact's record than its name, by full key, e.g.
        # {"type": 2, "out_path_len": 1, "last_advert": ...}.
        self.details = {}
        self.stored = dict(self.known)  # what the radio itself holds
        self.self_info = {"name": "test-node", "manual_add_contacts": manual_add_contacts}
        self.auto_update_contacts = False
        self.commands = FakeCommands(self)
        self.handlers = {}
        # Channel slots as (name, 16-byte secret); slot 0 is the usual Public
        # channel and the rest are empty.
        self.channels = [("Public", bytes.fromhex(PUBLIC_CHANNEL_SECRET))] + [("", bytes(16))] * 7
        self.listening = asyncio.Event()
        self.disconnected = False
        # Recorded calls
        self.sent = []
        self.added = []
        self.adverts = []
        self.manual_add_calls = []
        self.channel_sent = []  # (slot, text)
        self.removed = []  # keys
        self.paths_reset = []  # keys
        self.get_contacts_calls = 0
        # Results the radio returns
        self.ack_result = event(EventType.MSG_SENT)
        self.manual_add_result = event(EventType.OK)
        self.add_contact_result = event(EventType.OK)
        self.advert_result = event(EventType.OK)
        self.remove_contact_result = event(EventType.OK)
        self.reset_path_result = event(EventType.OK)
        self.channel_result = event(EventType.OK)
        self.device_info = {"max_contacts": 350, "model": "Test Board", "ver": "v1.9"}
        self.battery_result = event(EventType.BATTERY, {"level": 4050})
        self.stats_result = event(EventType.STATS_CORE, {"battery_mv": 4050, "uptime_secs": 93780, "errors": 0,
                                                         "queue_len": 0})

    @property
    def contacts(self):
        return {full_key(k): {**make_contact(k, name), **self.details.get(full_key(k), {})}
                for k, name in self.known.items()}

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
