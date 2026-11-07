# Encryption notes: how private are messages over MeshCore?

Short answer: **encrypted against casual listening, not secure against a
determined adversary, and who is talking to whom is visible.** How much risk
there is depends on the kind of message and on who you're worried about.

These notes describe MeshCore as understood from its design and public
documentation; MeshCore has not, as far as we know, had a formal outside
security review. Check the [MeshCore project](https://github.com/meshcore-dev/MeshCore)
for its current behavior.

## 1. Channel messages: assume anyone can read them

- **Hashtag channels have no secret.** Their key is worked out from the
  name. Mesh Contingency does the same thing in
  `mesh_contingency/alerts.py` (`hashtag_secret`: the first 16 bytes of
  `sha256(name)`). Anyone who knows or guesses `#contingency-wx` or
  `#contingency-comm` can read them.
- **The Public channel's key is the same on every radio.**
- **Private channels** (a random key shared by hand) are only as private as
  everyone you've given the key to, and there's no way to revoke it except
  making a new channel.

The alert and comm channels are meant to be public, so that's fine. Never
put anything sensitive on a channel.

## 2. Direct messages: encrypted over the air, with real limits

Each direct message between two radios is encrypted with a key that only
those two radios share, worked out from each radio's long-term key pair. A
listener who records the traffic can't read the text without one of the
two radios' private keys.

The limits:

- **No forward secrecy.** Each radio keeps the same keys for good. If one is
  captured and its private key read off the board, every direct message
  to or from it that someone recorded can be decrypted afterwards.
- **The devices are the weak point.** Most boards don't encrypt their
  storage, and messages also sit on the paired phone. The Bluetooth pairing
  PIN matters: many radios ship with a well-known default (often `123456`).
- **Who is talking isn't hidden, only what's said.**
  - Adverts broadcast each radio's name, public key and, if it's set, its
    position.
  - Each packet carries short hints of who it's from and to, and the path
    of repeaters it took.
  - Anyone listening can map who talks to whom, when, and roughly where,
    without reading a word.
- **Small, little-reviewed cryptography.** The message checks are short and
  the design hasn't had wide outside review. It's fine for everyday
  privacy; don't rely on it against a well-funded adversary.

## 3. What Mesh Contingency itself can see

The node is one end of every conversation with it, so it sees every command
in plain text.

- **`msg` messages are kept on the node's disk** in `mailbox.json`, readable
  only by the node's account. They're sealed only if the recipient set a
  passphrase with `setpass` (see *Sealed messages* in the README).
- **Sealed mailboxes have their own weak spot.** The passphrase travels inside
  an encrypted direct message, but the node sees it for a moment during
  `setpass` and `inbox`. Anyone with copies of `mailbox.json` and the users
  file can try guessing passphrases offline; scrypt slows each guess down,
  and the 12-character minimum keeps the number of guesses large.
- **`email`, `qm` and `emailall` leave the mesh as ordinary email** through
  the node's SMTP provider, so the email provider and the recipient's
  provider can read them.
- **Check-ins are public by design.** Anyone who can reach the node can read
  anyone's status with `status <name>`.
- **The log keeps no message text**, only which command was run and by whom.
  **Backups do**, `mailbox.json` included: keep them as private as the node.

## 4. A legal point, not a technical one

MeshCore's encryption is why groups run it license-free under FCC Part 15
rather than as amateur traffic: §97.113 bars messages encoded to hide their
meaning. If these messages were ever carried over an amateur link such as
Winlink (see *Not built yet: email over Winlink* in the README), that part
of the trip would have to be in the clear, and anyone could read it.

## What to do about it

**Node operators:**

- Change every radio's Bluetooth PIN from the default.
- Leave position out of adverts unless it's needed.
- Keep the node's computer, `config.toml`, the users file, its state files
  and its backups readable only by the node's account (the README's
  *Security notes* list them).
- Make a channel public on purpose, never by accident: a hashtag name is
  not a password.

**People given a radio:**

- A direct message is about as private as a text message. A channel post is
  a public broadcast.
- Don't rely on the mesh for anything truly secret or for sensitive personal
  details (medical information, the exact location of someone at risk).
- If a radio or phone is lost, tell the node's admin; anyone holding it can
  read its stored messages and send as its owner.

**When describing it to others:** "encrypted against casual listening, not
secure against a determined adversary, and who is talking to whom is
visible."
