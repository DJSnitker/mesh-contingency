# Plan: keeping mailbox messages private

Status: built on `feature/private-mailbox` · Requested 2026-10-20 · Decided 2026-10-20

## Goal

Messages left with `msg` should not be readable in plain text on the bot's
computer: not in `mailbox.json`, and not in the console output.

## What can't be done

True end-to-end encryption, where only the recipient's device can read a
message, isn't possible with MeshCore as it stands:

- A `msg` arrives as a direct message to the bot's node. The radio decrypts it
  and hands the bot plain text.
- To deliver it, the bot gives its radio plain text, which the radio encrypts
  for the recipient. The MeshCore apps can't decrypt anything extra the bot
  adds, so the bot can't pass on ciphertext for the recipient to open.

So the bot always sees each message briefly, as it arrives and as it's
delivered. The plan limits what is **kept** and **shown**.

## Chosen approach: passphrase inbox

Sealing is opt-in per user. A user who sets a passphrase gets sealed messages;
everyone else's mailbox works unsealed, exactly as it does today.

### How it works

- **`setpass <passphrase>`** (new user command): the bot derives a key pair from
  the passphrase (scrypt, then X25519) and stores only the public half, as
  `inbox_key = { public, salt, n }` in the user's section of `users.toml`. The passphrase and the
  private half are never stored. Users never see or handle keys; the passphrase
  is all they type.
- **`msg <name> <message>`**: the bot finds the recipient by the public key of
  their radio (the `[users.<radio public key>]` section of `users.toml`, the
  same key that identifies them everywhere else).
  - If that section has an `inbox_key`, the message text is sealed to it and
    only the sealed form is stored. Once sealed, the bot can't read it.
  - If not, the message is stored unsealed, as today.
  - Nothing changes for the sender either way.
- **`inbox <passphrase>`**: the bot re-derives the private key, opens the
  messages, sends them and forgets the key.
- **`inbox`** with no passphrase:
  - Passphrase set: replies with how many messages are waiting, who they're
    from and when, plus a reminder to use `inbox <passphrase>`. No text, not
    even of messages left unsealed before `setpass`.
  - No passphrase set: shows the messages, as today.

Sealing a message needs only the public half, so `msg` works without the
recipient's passphrase. For each message the bot makes a throwaway key pair,
combines its private half with the recipient's `inbox_key` (X25519) to get a
shared secret, encrypts the text with that (AES-GCM), and stores the ciphertext
with the throwaway public half. The throwaway private half and the secret are
then discarded. Opening combines the passphrase-derived private key with the
stored throwaway public half, which gives the same secret.

### Two keys, not the same thing

| Key | What it is | Used for |
|---|---|---|
| Radio public key | The MeshCore identity of the recipient's radio (64 hex) | Finding the recipient's section of `users.toml`, and where the radio delivers the message |
| `inbox_key` | Derived from the recipient's passphrase, stored in that section | Sealing the stored message |

Messages can't be sealed to the radio key, or to a key made from it: the radio
key is public (it's in `users.toml`, the bot's contacts and every advert), so
anyone could open them.

### Example

```
Alice → bot:  setpass blue-canoe-42x
bot → Alice:  setpass: passphrase set; new messages to you will be sealed.
bot → Alice:  A forgotten passphrase can't be recovered, and messages
              sealed with it are lost.

Bob → bot:    msg Alice meet at the shelter at 6
bot → Bob:    Message for Alice saved.

Alice → bot:  inbox
bot → Alice:  inbox: 1 message(s) from Bob 5m ago. Send inbox <passphrase>
              to read.

Alice → bot:  inbox blue-canoe-42x
bot → Alice:  Bob 6m ago: meet at the shelter at 6
```

### Rules

- **Passphrase length:** 12 to 16 characters, no spaces (so `inbox
  <passphrase> <page>` can't be misread). `setpass` refuses anything else and
  says why.
- **`setpass` warning:** every `setpass` reply warns that a forgotten
  passphrase can't be recovered. If sealed messages are already waiting under
  an old passphrase, it also warns that those won't open with the new one and
  will be deleted, and asks the user to send the same `setpass` again within 5
  minutes to confirm. Until then nothing changes, so they can still read them
  with the old passphrase. Setting the current passphrase again changes
  nothing.
- **Wrong passphrase:** `inbox: wrong passphrase`. Nothing is opened or changed.
- **Unsealed messages left from before `setpass`** are not sealed after the
  fact; `inbox <passphrase>` shows them with the rest.

### Limits

- The passphrase crosses the mesh to the bot inside an encrypted direct
  message, and the bot sees it while handling `setpass` and `inbox`.
- Someone with a copy of `mailbox.json` and `users.toml` can try guessing
  passphrases offline. The 12-character minimum and costly scrypt settings
  make this slow; a 16-character cap means a long passphrase can't be chosen
  for extra strength.
- A forgotten passphrase means the sealed messages are lost. `setpass` again
  starts a new key; older sealed messages can't be opened.
- Sender names and times stay readable in `mailbox.json` so plain `inbox` can
  show them.

## Keep message text out of the console

Today the console shows message text in two places:
- the incoming line, `[prefix name] msg <name> ...`
- the `msg` command's own output, `Message for X from Y: ...`

Commands can mark themselves private (e.g. `private = True`). For those
commands, the bot logs only the command name and who sent it, and never logs
the text or the reply. `msg`, `inbox` and `setpass` are private, so neither
message text nor passphrases reach the console. Phase 5 of the security plan
(safe console output) is a good time to do this.

## Implementation notes

- pycryptodome (already installed as a dependency of `meshcore`) provides
  scrypt, X25519 (`Crypto.Protocol.DH.key_agreement`) and AES-GCM. List it as a
  direct dependency in `pyproject.toml` rather than relying on it through
  `meshcore`.
- scrypt needs a salt: a random one is kept in `inbox_key` with the scrypt
  cost (`n`, 2**16), so the same passphrase gives different keys for different
  users and the cost can be raised later without breaking existing keys.
- The crypto lives in `sealing.py`; scrypt runs in a worker thread so the
  radio isn't held up.
- `mailbox.json` stays keyed by the recipient's radio public key, as it is
  today. A sealed message is `{"from", "time", "read", "sealed": {"epk",
  "nonce", "ct"}}`; an unsealed one keeps today's shape.
- `setpass` writes through `Directory.save_user`, like `setquickim`.

## Tests

- A sealed message opens with the right passphrase and not with a wrong one.
- Nothing in `mailbox.json` or the console contains sealed message text or a
  passphrase.
- A restart keeps messages sealed and openable.
- Plain `inbox` with a passphrase set shows count, senders and times, but no
  text.
- Users without a passphrase: messages stored unsealed and shown by `inbox`.
- Passphrases of 12 and 16 characters are accepted; 11 and 17 are refused.
- `setpass` warns, and asks for confirmation when sealed messages are waiting.
- Unsealed messages from before `setpass` stay readable.

## Considered and not chosen

- **Bot key file:** `mailbox.json` encrypted with a random key kept next to
  `config.toml`. Protects a copy of `mailbox.json` on its own, but anyone who
  can read the bot's files can read the messages.
- **Key from the recipient's radio public key:** the key is public, so this
  hides nothing.
- **Console only:** no encryption; its console change is included above.
