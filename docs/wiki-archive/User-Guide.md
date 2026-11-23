# User Guide

How to use the node from your MeshCore radio. Send every command as a
**direct message** to the node (not in a channel). Each task lists what to
send and what comes back. Every command is described in full on
**[Commands (A–Z)](Commands)**.

- [Get connected](#get-connected)
- [Use the app (phone or computer)](#use-the-app-phone-or-computer)
- [Become a user](#become-a-user)
- [Let people know you're ok](#let-people-know-youre-ok)
- [Leave someone a message](#leave-someone-a-message)
- [Read and clear your messages](#read-and-clear-your-messages)
- [Keep your messages private](#keep-your-messages-private)
- [Get a message out by email](#get-a-message-out-by-email)
- [Weather and Bible verses](#weather-and-bible-verses)
- [See your settings, or leave](#see-your-settings-or-leave)
- [If there's no reply](#if-theres-no-reply)

---

## Get connected

Your radio and the node can only message each other once each has heard the
other's **advert**.

1. In your MeshCore app, send an advert (a flood advert if you're not close by).
2. Wait for the node to appear in your contacts. It adverts by itself every so
   often, or ask one of its admins to advert.
3. Send `help`. If the node answers, you're connected:
   ```
   help
   → commands: help, wx, verse, ok, status, join. Send help <command> for usage
   ```

## Use the app (phone or computer)

Instead of typing commands, you can use the **Mesh Contingency app**. It
talks to your own MeshCore radio and sends the node the same commands for
you: the mailbox, check-ins, chat, weather, the Bible and email. It runs on
Android phones and on Windows, Mac and Linux computers.

The **[User App Guide](User-App-Guide)** covers installing it, connecting your radio,
and every screen.

## Become a user

Anyone can use `help`, `wx`, `verse`, `ok`, `status` and `join`. Everything else
needs you to be a user.

```
join                  (from a radio named "Sam T-Deck")
→ join: request sent to the admins as Sam T-Deck
```

You're known by **your radio's name**, exactly as your radio shows it, so set
the name you want people to see on the radio first (in the MeshCore app's
settings), then send an advert and `join`. A short name others will
recognise, like `Ridge Base 1`, works well. To change it later, just rename the
radio: the node picks up the new name the next time it hears from you.

A radio with no name, one with parentheses in its name, or a profane one is
refused; rename it and try again.

When an admin approves you:

```
→ Welcome, Sam T-Deck: you're now a user. Send help for your commands.
```

You aren't told if a request is turned down.

## Let people know you're ok

Anyone can check in, and anyone can look a check-in up, so keep it to what you'd
say on an open channel.

```
ok
→ ok: saved for Sam T-Deck

ok at the shelter on 5th st, all 4 of us fine
→ ok: saved for Sam T-Deck

status alex
→ Alex Base: heading north on 83 (25m ago)

status
→ Sam T-Deck: at the shelter on 5th st, all 4 of us fine (just now)
```

Each check-in replaces your last one.

## Leave someone a message

Messages wait on the node until the other person reads them, even if their
radio is off. Use their radio's name, as it shows on your radio, or the start of
their key (4 or more characters).

```
msg Alex Base water is out on the east side, we're ok
→ msg: saved for Alex Base (1 in their inbox)
```

If the wrong person gets picked, or the name has odd punctuation, put the name
in parentheses:

```
msg (Alex Base) water is out on the east side, we're ok
```

Alex gets a short notice that something is waiting (never the text). Up to 20
messages wait per person, for up to 30 days.

## Read and clear your messages

```
inbox
→ Alex Base 5m ago: on my way, 20 minutes out
```

Messages stay until you clear them, so you can read them again if a reply gets
lost. More than fit in one reply? Send `inbox 2`, `inbox 3`, and so on.

```
clearinbox
→ clearinbox: deleted 1 message(s)
```

`clearinbox` deletes only what `inbox` has shown you, so nothing that arrived
since is lost. `clearinbox all` deletes everything.

## Keep your messages private

Messages are kept on the node's computer. With a passphrase, new messages to you
are **sealed**: the node keeps only who sent each one and when, and nobody can
read them without your passphrase, the node's owner included.

```
setpass blue-canoe-42x
→ setpass: passphrase set; new messages to you will be sealed.
→ A forgotten passphrase can't be recovered, and messages sealed with it are lost.
```

- Passphrases are **12 to 16 characters, with no spaces**.
- To read your messages, add the passphrase:
  ```
  inbox
  → inbox: 1 message(s) from Alex Base 5m ago. Send inbox <passphrase> to read.

  inbox blue-canoe-42x
  → Alex Base 5m ago: on my way, 20 minutes out
  ```
- **Don't forget it.** Nobody can recover it. If you do, an admin can clear it
  with `resetpass`, but the messages sealed with it are deleted.
- To change it, send `setpass` with the new one. If sealed messages are
  waiting, it warns they'll be deleted and asks you to send it again; read them
  first with your old passphrase.

The node still sees each message briefly as it arrives and as it's delivered;
sealing protects what's stored.

## Get a message out by email

The node can email your message to people off the mesh. They can't reply over
the mesh.

**One regular contact** (a partner, a family member):

```
setqm partner@example.com
→ qm now sends to partner@example.com

qm made it home safe, phone is dead
→ qm: sent
```

**A group** (up to 10 addresses, sent as one email):

```
addgroup mom@example.com
→ addgroup: mom@example.com added (1 in the group)

addgroup dad@example.com
→ addgroup: dad@example.com added (2 in the group)

emailall roads closed, staying put tonight
→ emailall: sent
```

`addgroup` on its own lists the group; `cleargroup` empties it. An admin can
also set your `qm` address and group for you; the bot tells you when they do.

**Anyone else:**

```
email friend@example.com power is back on here
→ email: sent
```

There's a daily limit on emails per person; the reply says when you've reached
it.

If the node can't send an email, for example with the internet down, it isn't
kept to send later. The reply says why, and you can send it again later:

```
qm made it home safe, phone is dead
→ qm: not sent, no internet at the node; try again later
```

## Weather and Bible verses

```
wx 79601
→ 79601 Mostly Cloudy, 20% precip 6h | 82F E14mph G18

wx Taylor, TX
→ Taylor, TX Mostly Cloudy, 20% precip 6h | 82F E14mph G18

verse
→ (the verse of the day)

verse john 3:16
verse ps 23:1-3
```

Weather alerts come first when there are any. To get the alerts and news the
node posts for everyone, add two hashtag channels in your app:
`#contingency-wx` for weather alerts, and `#contingency-comm` for news and
updates (you can post there too).

## See your settings, or leave

```
whoami
→ Sam T-Deck (5a3e1c7b9d20); passphrase set; qm partner@example.com; emailall 2 address(es); 1 message(s), 1 unread
```

To stop being a user (this deletes your messages):

```
leave
→ leave: this removes you from the users and deletes your 1 message(s). Send it again within 5 min to confirm.

leave
→ leave: you're no longer a user; send join to ask again.
```

## If there's no reply

| What you see | What to do |
|---|---|
| Nothing at all | Your radios may not know each other: advert from your app and try again in a minute. |
| `unknown command inbx; did you mean inbox? help lists yours` | A typo: send it again with the suggested command. |
| `unrecognized user or function` | The command is misspelled, or not one you can use. Send `help` for yours. This reply comes at most once every 5 minutes. |
| `usage: ...` | Something is missing; the reply shows the right form. |
| `<command>: limit reached, try again in 23 min` | You've used that command a lot; wait and try again. |
| `inbox: wrong passphrase` | Check the passphrase; it's case-sensitive. |
| A reply starting `(1/3)` | Long replies come in numbered parts; wait for the rest. |
