"""Auto-accept adverts from new nodes, filtered by node type.

The radio is put in manual-add mode, so instead of storing every node it
hears it reports each new one as a NEW_CONTACT event; we add only the types
listed in config. This keeps repeaters, rooms and sensors from filling the
radio's contact table, which would block new people from messaging us.
Each node added can be announced to the admins.

So a burst of adverts can't fill the contact table or swamp the admins, at
most max_new_per_hour nodes are added (users and admins always are), and at
most notices_per_hour are announced one by one; the rest are summed up in one
message when the hour is up.

A node whose key prefix matches a user or admin but whose full key doesn't
is never added: messages carry only the prefix, so it could pass itself off
as them (see the bot's sender check).
"""

import time
from collections import deque

from meshcore import EventType

# MeshCore advert types, as in a contact's "type" field.
NODE_TYPES = {"chat": 1, "repeater": 2, "room": 3, "sensor": 4}
TYPE_NAMES = {v: k for k, v in NODE_TYPES.items()}
DEFAULT_MAX_NEW_PER_HOUR = 20
DEFAULT_NOTICES_PER_HOUR = 5
HOUR = 3600


def load_auto_add(config):
    """Return the set of node type numbers to auto-add, or None if [contacts]
    is not configured (leave the radio's own behavior alone)."""
    contacts = config.get("contacts")
    if contacts is None or "auto_add" not in contacts:
        return None
    unknown = [t for t in contacts["auto_add"] if t not in NODE_TYPES]
    if unknown:
        raise SystemExit(f"[contacts] auto_add: unknown type(s) {unknown}; use {list(NODE_TYPES)}")
    return {NODE_TYPES[t] for t in contacts["auto_add"]}


def load_notify_admins(config):
    """Return whether new contacts should be announced to the admins
    ([contacts] notify_admins, default true)."""
    value = config.get("contacts", {}).get("notify_admins", True)
    if not isinstance(value, bool):
        raise SystemExit(f"[contacts] notify_admins must be true or false, not {value!r}")
    return value


def load_contact_limits(config):
    """Return ([contacts] max_new_per_hour, notices_per_hour), 0 meaning no limit."""
    section = config.get("contacts", {})
    values = []
    for key, default in [("max_new_per_hour", DEFAULT_MAX_NEW_PER_HOUR),
                         ("notices_per_hour", DEFAULT_NOTICES_PER_HOUR)]:
        value = section.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SystemExit(f"[contacts] {key} must be a whole number, or 0 for no limit, not {value!r}")
        values.append(value)
    return tuple(values)


class NoticeBatcher:
    """Lets the first `per_hour` new-contact notices of each hour through and
    counts the rest, along with nodes skipped by the cap, for one summary."""

    def __init__(self, per_hour):
        self.per_hour = per_hour
        self._start = None  # time.monotonic() the current hour began
        self._sent = self._held = self._skipped = 0

    def _now(self):
        now = time.monotonic()
        if self._start is None:
            self._start = now
        return now

    def allow(self):
        """True if a notice may go out now; otherwise it is counted."""
        self._now()
        if not self.per_hour or self._sent < self.per_hour:
            self._sent += 1
            return True
        self._held += 1
        return False

    def skipped(self):
        """Count a node not added because of the cap."""
        self._now()
        self._skipped += 1

    def summary(self):
        """Once the hour is up, start a new one and return the summary of what
        wasn't announced, or None if there is nothing to say yet."""
        if self._start is None or time.monotonic() - self._start < HOUR:
            return None
        held, skipped = self._held, self._skipped
        self._start, self._sent, self._held, self._skipped = None, 0, 0, 0
        parts = ([f"{held} more new contact(s)"] if held else []) + (
            [f"{skipped} new node(s) not added (over max_new_per_hour)"] if skipped else [])
        return f"In the last hour: {'; '.join(parts)}" if parts else None


def contact_rows(mc, wanted=""):
    """[(name, full public key, type name)] for the radio's contacts, sorted
    by name; with `wanted`, only those whose name or key starts with it."""
    wanted = wanted.lower()
    rows = sorted(((c.get("adv_name") or "?", c["public_key"].lower(), TYPE_NAMES.get(c.get("type"), ""))
                   for c in mc.contacts.values()), key=lambda row: (row[0].lower(), row[1]))
    return [row for row in rows if not wanted or row[0].lower().startswith(wanted) or row[1].startswith(wanted)]


class ContactNotFound(Exception):
    """No contact, or more than one, matches; the message says which."""


def find_contact(mc, text):
    """The one radio contact that text names: a name (any case), a key or the
    start of one (at least 4 hex digits), or the start of a name. Raises
    ContactNotFound, saying why, if none or several match."""
    wanted = text.strip().lower()
    if not wanted:
        raise ContactNotFound("give a name or key")
    contacts = list(mc.contacts.values())
    tries = [[c for c in contacts if (c.get("adv_name") or "").lower() == wanted]]
    if len(wanted) >= 4 and all(ch in "0123456789abcdef" for ch in wanted):
        tries.append([c for c in contacts if c["public_key"].lower().startswith(wanted)])
    tries.append([c for c in contacts if (c.get("adv_name") or "").lower().startswith(wanted)])
    for found in tries:
        if len(found) == 1:
            return found[0]
        if found:
            raise ContactNotFound(f"{len(found)} contacts match {text.strip()}; give more of the key")
    raise ContactNotFound(f"no contact {text.strip()}")


def lookalike_of(public_key, protected):
    """Return the key in `protected` that public_key shares a 12-hex prefix
    with but doesn't equal, or None."""
    public_key = public_key.lower()
    return next((key for key in sorted(protected) if key[:12] == public_key[:12] and key != public_key), None)


async def setup_auto_add(mc, types, on_added=None, protected=None, on_blocked=None, max_new_per_hour=0,
                         on_skipped=None):
    """Switch the radio to manual-add mode and add new nodes of the given types.

    on_added(key, name, type_name), if given, is called for each node added.
    protected(), if given, returns the full public keys of the users and admins as they
    are now; a node that shares one's prefix but not its key is not added, and
    on_blocked(key, name, protected_key), if given, is called the first time
    each such node is heard. Beyond max_new_per_hour nodes added in the last
    hour (0 for no limit), others than users and admins are skipped, calling
    on_skipped() if given.
    """
    if not mc.self_info.get("manual_add_contacts"):
        res = await mc.commands.set_manual_add_contacts(True)
        if res.type == EventType.ERROR:
            raise SystemExit(f"Could not enable manual contact adding on the radio: {res.payload}")
        print("Radio setting changed: manual_add_contacts on (stored on the radio; "
              "it no longer adds every node it hears by itself).")

    names = ", ".join(sorted(TYPE_NAMES[t] for t in types)) or "none"
    print(f"Auto-adding new contacts of type: {names}")

    blocked = set()  # full keys already reported, so repeated adverts stay quiet
    recent = deque()  # time.monotonic() of each node added in the last hour

    async def on_new_contact(event):
        c = event.payload
        label = f"{c['public_key'][:12]} {c.get('adv_name') or '?'} ({TYPE_NAMES.get(c['type'], c['type'])})"
        if c["type"] not in types:
            print(f"  (skipped new contact {label})", flush=True)
            return
        target = lookalike_of(c["public_key"], protected() if protected else ())
        if target is not None:
            if c["public_key"] not in blocked:
                blocked.add(c["public_key"])
                print(f"! blocked new contact {label}: same key prefix as a user or admin, different key", flush=True)
                if on_blocked is not None:
                    on_blocked(c["public_key"][:12], c.get("adv_name") or "", target)
            return
        now = time.monotonic()
        while recent and now - recent[0] >= HOUR:
            recent.popleft()
        is_protected = protected is not None and c["public_key"].lower() in protected()
        if max_new_per_hour and len(recent) >= max_new_per_hour and not is_protected:
            print(f"  (skipped new contact {label}: {max_new_per_hour} already added this hour)", flush=True)
            if on_skipped is not None:
                on_skipped()
            return
        res = await mc.commands.add_contact(c)
        if res.type == EventType.ERROR:
            # Most likely the radio's contact table is full.
            print(f"  (could not add contact {label}: {res.payload})", flush=True)
            return
        recent.append(now)
        # Refresh our copy so the new contact can be named and replied to.
        await mc.commands.get_contacts()
        print(f"+ contact {label}", flush=True)
        if on_added is not None:
            on_added(c["public_key"][:12], c.get("adv_name") or "", TYPE_NAMES.get(c["type"], str(c["type"])))

    mc.subscribe(EventType.NEW_CONTACT, on_new_contact)
