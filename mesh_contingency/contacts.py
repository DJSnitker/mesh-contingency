"""The radio's contacts: adding the admins, and listing them for the terminal.

A direct message carries only the sender's key prefix, so the bot needs the
sender in the radio's contacts to know who it is and to reply. A radio in
manual-add mode (a setting stored on the radio; older versions of this bot
turned it on) reports each new node it hears instead of adding it: the bot
adds the admins' radios and no others, so nothing else fills the contact
table. In the radio's usual mode it adds every node itself, the admins too,
and the bot leaves that alone.

A node whose key prefix matches an admin's but whose full key doesn't is
never added: it could pass itself off as them.
"""

from meshcore import EventType

# MeshCore advert types, as in a contact's "type" field.
NODE_TYPES = {"chat": 1, "repeater": 2, "room": 3, "sensor": 4}
TYPE_NAMES = {v: k for k, v in NODE_TYPES.items()}


async def add_admins(mc, admins):
    """If the radio is in manual-add mode, add each admin's radio when it
    adverts. Returns a line to print, or None in the radio's usual mode."""
    if not mc.self_info.get("manual_add_contacts"):
        return None

    warned = set()  # lookalikes already reported, so repeated adverts stay quiet

    async def on_new_contact(event):
        c = event.payload
        key = c["public_key"].lower()
        label = f"{key[:12]} {c.get('adv_name') or '?'}"
        if key not in admins:
            if key not in warned and any(admin[:12] == key[:12] for admin in admins):
                warned.add(key)
                print(f"! not adding {label}: same key prefix as an admin, different key", flush=True)
            return
        res = await mc.commands.add_contact(c)
        if res.type == EventType.ERROR:
            # Most likely the radio's contact table is full.
            print(f"  (could not add admin {label}: {res.payload})", flush=True)
            return
        # Refresh our copy so the admin can be named and replied to.
        await mc.commands.get_contacts()
        print(f"+ admin contact {label}", flush=True)

    mc.subscribe(EventType.NEW_CONTACT, on_new_contact)
    return "The radio adds new contacts only when told: adding the admins' radios when they advert."


def contact_rows(mc, wanted=""):
    """[(name, full public key, type name)] for the radio's contacts, sorted
    by name; with `wanted`, only those whose name or key starts with it."""
    wanted = wanted.lower()
    rows = sorted(((c.get("adv_name") or "?", c["public_key"].lower(), TYPE_NAMES.get(c.get("type"), ""))
                   for c in mc.contacts.values()), key=lambda row: (row[0].lower(), row[1]))
    return [row for row in rows if not wanted or row[0].lower().startswith(wanted) or row[1].startswith(wanted)]
