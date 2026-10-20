"""Auto-accept adverts from new nodes, filtered by node type.

The radio is put in manual-add mode, so instead of storing every node it
hears it reports each new one as a NEW_CONTACT event; we add only the types
listed in config. This keeps repeaters, rooms and sensors from filling the
radio's contact table, which would block new people from messaging us.
Each node added can be announced to the admins.

A node whose key prefix matches a user or admin but whose full key doesn't
is never added: messages carry only the prefix, so it could pass itself off
as them (see the bot's sender check).
"""

from meshcore import EventType

# MeshCore advert types, as in a contact's "type" field.
NODE_TYPES = {"chat": 1, "repeater": 2, "room": 3, "sensor": 4}
TYPE_NAMES = {v: k for k, v in NODE_TYPES.items()}


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


def lookalike_of(public_key, protected):
    """Return the key in `protected` that public_key shares a 12-hex prefix
    with but doesn't equal, or None."""
    public_key = public_key.lower()
    return next((key for key in sorted(protected) if key[:12] == public_key[:12] and key != public_key), None)


async def setup_auto_add(mc, types, on_added=None, protected=None, on_blocked=None):
    """Switch the radio to manual-add mode and add new nodes of the given types.

    on_added(key, name, type_name), if given, is called for each node added.
    protected(), if given, returns the full public keys of the users and admins as they
    are now; a node that shares one's prefix but not its key is not added, and
    on_blocked(key, name, protected_key), if given, is called the first time
    each such node is heard.
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
        res = await mc.commands.add_contact(c)
        if res.type == EventType.ERROR:
            # Most likely the radio's contact table is full.
            print(f"  (could not add contact {label}: {res.payload})", flush=True)
            return
        # Refresh our copy so the new contact can be named and replied to.
        await mc.commands.get_contacts()
        print(f"+ contact {label}", flush=True)
        if on_added is not None:
            on_added(c["public_key"][:12], c.get("adv_name") or "", TYPE_NAMES.get(c["type"], str(c["type"])))

    mc.subscribe(EventType.NEW_CONTACT, on_new_contact)
