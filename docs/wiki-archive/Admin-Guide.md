# Admin Guide

How to run the node day to day. Each task lists the commands to send, as
**direct messages** to the node from an admin radio, with what comes back.
Every command is described in full on **[Commands (A–Z)](Commands)**.

Admins are the people whose full public keys are in `[admin] keys` in the
node's `users.toml`. That list can only be changed by editing the file, never
over the mesh, so a lost admin radio can't make more admins. Admin commands
have no rate limit. Setting up a new node, and making yourself its first
admin, is on **[Set Up a Node](Set-Up-a-Node)**.

- [Add a new user](#add-a-new-user)
- [Check the node's health](#check-the-nodes-health)
- [Get told about problems](#get-told-about-problems)
- [See who's on the node](#see-whos-on-the-node)
- [Names, and removing a user](#names-and-removing-a-user)
- [Help someone who forgot their passphrase](#help-someone-who-forgot-their-passphrase)
- [Set someone's email addresses](#set-someones-email-addresses)
- [Keep the node reachable](#keep-the-node-reachable)
- [Warn people about the weather](#warn-people-about-the-weather)
- [Test the alert channel every week](#test-the-alert-channel-every-week)
- [Post news for everyone](#post-news-for-everyone)
- [Check on people](#check-on-people)
- [See what admins have done](#see-what-admins-have-done)
- [Edit the users file by hand](#edit-the-users-file-by-hand)
- [Undo a change to the users file](#undo-a-change-to-the-users-file)
- [Back up the node's data](#back-up-the-nodes-data)
- [Use the web console](#use-the-web-console)
- [Use the console from other computers](#use-the-console-from-other-computers)
- [Change the radio's settings](#change-the-radios-settings)
- [From the node's computer](#from-the-nodes-computer)
- [Set up a node](Set-Up-a-Node)
- [Running as a service](Running-as-a-systemd-Service-on-Linux)
- [When something doesn't work](#when-something-doesnt-work)

---

## Add a new user

Two radios can only message each other once each has heard the other's
**advert**, so first make sure the node and the new person know each other.

1. **Ask them to advert** from their MeshCore app. The node adds their radio
   when it hears it, and you get a notice:
   ```
   → New contact: Sam T-Deck (5a3e1c7b9d20, chat)
   ```
2. **Advert the node** so their radio learns it:
   ```
   advert            (they're in direct range)
   advert flood      (they're further away; use sparingly)
   ```
3. **Check the node has them:**
   ```
   contacts sam
   → contacts matching sam (1): Sam T-Deck 5a3e1c7b9d20
   ```
4. **They ask to join**, and you get a notice:
   ```
   (they send)  join
   → Join request: Sam T-Deck (5a3e1c7b9d20). Reply approve 5a3e1c7b9d20 or deny 5a3e1c7b9d20
   ```
5. **Approve them** (or `deny`; they aren't told):
   ```
   approve
   → requests: Sam T-Deck (5a3e1c7b9d20) 5m ago

   approve (Sam T-Deck)
   → approve: Sam T-Deck added to users.toml
   ```
   They join under their radio's name, so ask them to set the name they want
   people to see on the radio before they send `join` (a short name others
   will recognise, like `Ridge Base 1`, works well). The name is typed as it is
   (`approve sam t-deck`) or in parentheses, or use the key (`approve 5a3e`).
   They get a welcome message and can use every user command straight away.
   Point them at the **[User Guide](User-Guide)**.

## Check the node's health

Send `health` for a summary of the radio, the people and what the bot has been
doing:

```
health
→ health: up 5h 20m; radio Hilltop Node (Heltec V3 v1.18.0); radio up 2d 4h; battery 4.17V; contacts 8/350; users 2 (1 admin)
→ join requests 0; inbox 3 message(s) for 2 user(s); check-ins 1; since start 14 message(s) in, 17 out (1 undelivered); errors none
→ emails 24h 2/200 address(es); auto alerts 2 counties, checked 4m ago; last flood advert 2h ago; users.toml loaded 5h ago
```

What to look for:

- **`battery`** dropping toward 3.5 V: the radio is running down. Check its
  power.
- **`radio up`** much shorter than you expect: the radio has restarted (a power
  blip, its USB cable unplugged, or a crash). Restarting the bot doesn't
  restart the radio (tested on a Heltec V3: opening its USB port leaves it
  running), so `radio up` shorter than `up` always means a real radio restart.
- **`up`** short: the bot restarted. As a service, check why with
  `journalctl --user -u mesh-contingency -b`.
- **`contacts`** near its limit: the radio can't add new nodes. Remove old
  ones with `contact remove <name>`, or in the web console's Contacts page, on its Contacts tab.
- **`undelivered`** climbing: replies aren't getting through, often a weak link
  or a radio that's left the mesh.
- **`errors`**: the last failed or timed-out command is named. `wx timed out`
  usually means the weather service or the internet is slow.
- **`emails 24h`** near the cap: emails will be refused until older ones pass
  24 hours.
- **`last email failed`**: when an email last couldn't be sent, and why. The
  console has the full reason from `mail`; see the table under
  [When something doesn't work](#when-something-doesnt-work).
- **`users.toml NOT reloaded`**: the last edit has a mistake. The previous
  version is still in use; fix the file (see
  [Edit the users file by hand](#edit-the-users-file-by-hand)).

Every part is explained in [Commands: health](Commands#health). On an existing
node, turn the command on by adding `health = { permission = "admin" }` under
`[commands]` in `config.toml` and restarting the bot.

## Get told about problems

You don't have to send `health` to find out something's wrong. Every 5
minutes the bot checks the node, and each admin gets a direct message when a
problem starts and another when it's over:

```
→ Node problem: battery low, 3.42V (below 3.50V)
→ Node ok again: battery 3.65V
```

| Notice | What to do |
|---|---|
| `battery low, 3.42V (below 3.50V)` | Check the radio's power. Ok again once it's 0.1 V above the limit. |
| `the radio restarted 3m ago (power, USB or a crash)` | Check its power and USB cable. Restarting the bot never restarts the radio, so this is a real restart. |
| `Node restarted: the computer started 1m ago, and the radio with it` | Not a problem with the radio: the computer restarted (a power cut, an update, someone rebooting it), and a radio powered by its USB restarts with it. Worth knowing if nobody meant to reboot it. Linux only; elsewhere it's the restart notice above. |
| `the radio was disconnected for 7m (reconnect_failed); back now` | The bot lost the radio (usually the USB cable) and stopped; this is sent once it's back, since nobody could be told meanwhile. A radio with a battery keeps running, so there's no restart notice. Check the cable. |
| `5 messages in a row not delivered` | Replies aren't getting through: a weak link, a radio that's left the mesh, or the node's antenna. Ok again when one is delivered. |
| `email failing: no internet at the node` | Emails can't go out (or `the node's email login was refused`, ...). Ok again when one is sent. |
| `3 command errors in 30 min, last wx timed out` | Often the internet is down. `health` shows the error count. |
| `users.toml not reloaded: ...` | The last edit of the users file has a mistake; the old version is still in use. Ok again once it's fixed. |
| `backup to ... failing: No such file or directory` | The bot couldn't back up its data: the backup disk isn't mounted, or is full. It tries again every hour; ok again once a backup works. See [Back up the node's data](#back-up-the-nodes-data). |
| `12 failed console logins in 15 min, from 192.168.1.50` | Someone on the network is guessing console passwords, or a console user forgot theirs. Only with the [remote console](#use-the-console-from-other-computers) on. Check who uses that device; the journal has each try (`Console login failed: ...`). Ok again after 15 minutes without that many. |

Each problem is announced at most once an hour, so something going back and
forth can't flood the mesh. A restart of the bot doesn't repeat a problem
you've already been told about, and doesn't end one either: "ok again" comes
only when there's evidence (an email sent, a message delivered, a backup
made; for command errors and failed console logins, the time they're
counted over). `health` ends with `watch: no problems` or
the current ones (`watch: battery low, email failing`).

The limits are set in `[watch]` in `config.toml`; these are the defaults:

```toml
[watch]
enabled = true
every_minutes = 5        # how often to check; at least 1
battery_volts = 3.5      # warn below this; 0 for no battery check
undelivered_in_row = 5   # messages in a row not delivered; 0 for no check
errors = 3               # commands failed or timed out within 30 min; 0 for no check
failed_logins = 10       # failed remote console logins within 15 min; 0 for no check
```

With `enabled = false` only the users-file notice is sent, as it was before.

## See who's on the node

| To see | Send |
|---|---|
| Every user and what they've set | `users` (`users 2` for more) |
| One user in detail | `whois sam t-deck`, `whois 5a3e` |
| Every contact on the radio | `contacts` (`contacts 2` for more) |
| Contacts matching a name or key | `contacts sam`, `contacts 5a3e` |
| Who has messaged the node since it started | `roster` |
| Waiting join requests | `approve` |

```
users
→ users (2): Alex Base a1e2c3d4b5f6 (admin, qm) Sam T-Deck 5a3e1c7b9d20 (pass, qm, emailall)

whois alex base
→ Alex Base (a1e2c3d4b5f6); admin; no passphrase; qm alex@example.com; 1 message(s), 1 unread
```

In `users`, `pass` means they've set a passphrase. In `contacts`, `(user)` and
`(admin)` mark people in the users file, and repeaters, rooms and sensors are
labelled.

To manage one contact, name it by its name, the start of its name, or 4 or
more characters of its key:

| To | Send |
|---|---|
| Take a contact off the radio (it asks first; send it again to confirm) | `contact remove hilltop` |
| Reset the path to one whose messages stopped getting through | `contact path 5a3e` |

A user or admin you remove can't be messaged until they advert again; a node
your `auto_add` takes comes back by itself when it next adverts. If your
`config.toml` is older than this command, add
`contact = { permission = "admin" }` under `[commands]` first.

## Names, and removing a user

A user's name is always **their radio's name**, so it matches what everyone
sees on their own radios. There's no command to change it: the user renames
their radio, and the bot writes the new name to `users.toml` the next time it
hears from them (or at its next start), logging and recording it:

```
history
→ history (1): 3m ago radio: Sam T-Deck (5a3e1c7b9d20) is now Ridge Base 1
```

`join` refuses a radio with no name, one with control characters or
parentheses in it, or a profane one, and the bot won't take such a name when a radio is
renamed later either (it logs a warning and keeps the old name). The
profanity list catches the obvious; you still approve every join, so turn
down anything it misses with `deny`. If two users' radios have the same
name, commands ask for the key prefix instead.

Removing someone deletes their section of the users file and their messages.
It asks first:

```
remove (Sam T-Deck)
→ remove: this removes Sam T-Deck (5a3e1c7b9d20) and their 1 message(s). Send it again within 5 min to confirm.

remove (Sam T-Deck)
→ remove: Sam T-Deck removed, 1 message(s) deleted
```

Users can also take themselves out with `leave`. Removing someone doesn't take
their radio out of the node's contacts, and an admin keeps admin rights until
`[admin] keys` is edited.

## Help someone who forgot their passphrase

Sealed messages can't be opened without the passphrase, by anyone, so all you
can do is clear it. That deletes the messages sealed with it, and tells them:

```
resetpass alex base
→ resetpass: this clears Alex Base's passphrase and deletes 2 sealed message(s). Send it again within 5 min to confirm.

resetpass alex base
→ resetpass: Alex Base's passphrase cleared, 2 sealed message(s) deleted
```

New messages to them are kept unsealed until they send `setpass` again.

## Set someone's email addresses

Users set their own `qm` address and `emailall` group, but you can set them
for someone (setting it up for them, or fixing a typo) with `setemail`. Give
`qm`, `group`, or both; a part with no address clears it, and a group you give
replaces the old one:

```
setemail (Sam T-Deck) qm partner@example.com group mom@example.com dad@example.com
→ setemail: Sam T-Deck's qm partner@example.com; emailall mom@example.com, dad@example.com

setemail (Sam T-Deck) group
→ setemail: Sam T-Deck's emailall cleared
```

They're told what changed, and it's recorded in `history`. In the web
console, it's **Edit emails** on the **Users** page. If your `config.toml` is
older than this command, add `setemail = { permission = "admin" }` under
`[commands]` first.

## Keep the node reachable

New radios only find the node by hearing its advert.

- **Now:** `advert` (direct range) or `advert flood` (across the mesh).
- **Automatically:** the node's `config.toml` can advert on a schedule:
  ```toml
  [advert]
  every_hours = 12
  flood = true
  ```
  Each scheduled advert goes out 12 hours after the last flood advert, whether
  the schedule sent it or someone did by hand, and restarts don't reset the
  clock.
- **New contacts are capped** at 20 an hour (users and admins always get in),
  and you get at most 5 new-contact notices an hour, then one summary.

## Warn people about the weather

`alert` posts your message, exactly as typed, to the public hashtag channel
`#contingency-wx`, which anyone can follow by adding it in their app:

```
alert Tornado warning until 6pm. Shelter open at First Baptist on 5th St
→ alert: posted to #contingency-wx
```

It must fit in one channel message: 133 characters, less the node's name.
Anyone can look up a zipcode's or county's weather and alerts with `wx`:

```
wx 79601
→ 79601 ALERT: Severe Thunderstorm Warning | 60% precip 6h | 88F S12mph G25

wx Taylor, TX
→ Taylor, TX ALERT: Severe Thunderstorm Warning | 60% precip 6h | 88F S12mph G25
```

To have the bot post new National Weather Service alerts by itself, list the
counties to watch in `config.toml` and restart it:

```toml
[alerts]
counties = ["Taylor, TX", "Jones, TX"]
every_minutes = 10
```

When it starts, it looks up each county's NWS code and keeps it. Then every
10 minutes it asks the NWS for the alerts in all of the counties at once (one
request, however many counties) and posts any alert it hasn't posted before,
once, to the same channel, named by county:

```
Taylor, TX ALERT: Severe Thunderstorm Warning | until Tue 6:00PM | Taylor; Jones
```

Write each county as its name and state; `Taylor County, TX` works too. A
restart doesn't repost anything. The console shows each post and anything it
couldn't look up; `history` lists the posts as by "auto"; `health` shows when
it last checked. `alertmap` looks the codes up again:

```
alertmap
→ alertmap: 2 looked up: Taylor, Jones
```

With many counties the list takes as few messages as it needs, numbered
`(1/2)`, `(2/2)`. Any county that couldn't be looked up is listed after
`not looked up:` with the reason. The codes themselves are in the console.

On an existing node, turn the command on by adding
`alertmap = { permission = "admin" }` under `[commands]` in `config.toml`.

## Test the alert channel every week

A weekly test tells people the alert channel works and reminds them to keep
it on their radios. Set the day and time in `config.toml` and restart:

```toml
[alert_test]
weekly = "Wednesday 17:00"     # or "Wed 5:00PM"; empty (the default) for no weekly test
timezone = "America/Chicago"   # defaults to the computer's time zone
# message = "TEST: this is a test of the #contingency-wx alert channel. No action needed."
```

Every Wednesday at 5PM Central time (CDT in summer, CST in winter) the bot
posts the message to the alert channel, followed by the counties it watches
for alerts:

```
TEST: this is a test of the #contingency-wx alert channel. No action needed.
Counties watched for alerts: Taylor, Jones
```

`testalert` posts it straight away:

```
testalert
→ testalert: posted to #contingency-wx; next weekly test Wed 5:00PM CDT
```

If the bot isn't running at the time, that week's test is skipped rather than
sent late. `health` shows `next alert test Wed 5:00PM CDT`, and `history`
lists each test (as "auto" when scheduled). On an existing node, turn the
command on with `testalert = { permission = "admin" }` under `[commands]`.

## Post news for everyone

`comm` posts your message, exactly as typed, to the public hashtag channel
`#contingency-comm`, so everyone who follows it sees it at once (one channel
message costs far less airtime than a direct message to each person):

```
comm Shelter open at the high school gym, bring bedding
→ comm: posted to #contingency-comm
```

It must fit in one channel message: 133 characters, less the node's name. The
bot adds the channel to its radio when it starts (the startup log shows
`comm: #contingency-comm is channel slot 2.`), and `history` lists each post.
Ask people to add `#contingency-comm` in their app; anyone with it can post
there from their own radio as well. Keep weather on `#contingency-wx` with
`alert`.

On an existing node, turn the command on by adding
`comm = { permission = "admin" }` under `[commands]` in `config.toml`.

## Check on people

Anyone can check in with `ok` and look others up with `status`:

```
status sam
→ Sam T-Deck: at the shelter on 5th st (2h ago)

clearstatus
→ clearstatus: cleared 4 statuses
```

To see everyone at once, and who hasn't checked in, use `checkins`:

```
checkins
→ Roll Call:
  ✗ Alex Base: missing
  ✓ Sam T-Deck: at the shelter on 5th st (2h ago)
  1/2 checked in. Page 1/1.
```

It lists five users to a page; send `checkins page 2` and so on for more. On
an existing node, turn it on with `checkins = { permission = "admin" }` under
`[commands]`.

Use `clearstatus` after an event, so old check-ins don't mislead anyone.

## See what admins have done

With more than one admin, or after a busy day, `history` shows who approved,
turned down, removed or reset whom, who cleared the check-ins or posted to the
alert or communications channel (and what), who left, which radios changed their name, and the
weather alerts the bot posted by itself (as "auto"), newest first:

```
history
→ history (3): 5m ago Doug: approved Sam T-Deck (5a3e1c7b9d20); 2h ago radio: Al (a1e2c3d4b5f6) is now Alex Base; 1d ago Alex Base: left the users (a1e2c3d4b5f6)
```

The newest 200 are kept, across restarts. Send `history 2` and so on for older
ones. Edits made by hand to `users.toml` aren't in it; the bot's console or
journal shows those as `users.toml reloaded: ...`.

On an existing node, turn the command on by adding
`history = { permission = "admin" }` under `[commands]` in `config.toml` and
restarting the bot.

## Edit the users file by hand

`users.toml` sits next to `config.toml` on the node's computer. The bot checks
it every few seconds and uses a change once the file stops changing. To apply
an edit at once:

```
reload
→ reload: added Sam T-Deck; changed Alex Base
```

If the edit has a mistake, the bot keeps the previous version and tells every
admin why (`Node problem: users.toml not reloaded: ...`), then `Node ok again:
users.toml reloaded` once it's fixed. Edit by hand to add or remove admins,
or to fix a section the bot can't rewrite. A `name` you type is replaced by the
user's radio name the next time the bot sees their radio.


## Undo a change to the users file

Every time the bot changes `users.toml` (`approve`, `remove`, `resetpass`, `setemail`,
`leave`, a radio's new name, and users' own `setpass`, `setqm`, `addgroup`,
`cleargroup`), it first saves the file as it was in a `backups` folder next to
it, named by date and time. The newest 5 are kept.

```
backups/users-20261020-214502.toml
backups/users-20261020-221500.toml
```

To go back to one, on the node's computer, in the folder with `users.toml`:

1. Find the version you want; `diff` shows what changed since:
   ```sh
   ls -l backups/
   diff backups/users-20261020-221500.toml users.toml
   ```
2. Copy it back:
   ```sh
   cp backups/users-20261020-221500.toml users.toml
   ```
3. The bot picks it up within a few seconds (or send `reload`). Check the
   console or journal for `users.toml reloaded: ...`.

Backups hold the same email addresses and keys as `users.toml`, and are just
as private (readable only by you).

## Back up the node's data

If the node's disk dies, the users, messages, check-ins and history go with
it. So once a day the bot copies everything it keeps into a new folder, named
for the date and time, in its backup folder. Send `backup` to make one now:

```
backup
→ backup: 12 file(s) saved in ~/MeshContingencyBackups/20261022-091340; newest 7 kept
```

Each folder holds `config.toml`, `users.toml`, the state files (check-ins,
mailbox, history, join requests...) and the users file's `backups` folder.
The newest 7 are kept. Set it in `config.toml`:

```toml
[backup]
to = "~/MeshContingencyBackups"   # e.g. "/mnt/usb/MeshContingencyBackups"
every_hours = 24                  # 0 for only with the backup command
keep = 7                          # newest backups kept
```

> **Put the backups on a separate disk if you can**: a USB stick, a second
> drive, or a network share mounted on the node's computer, e.g.
> `to = "/mnt/usb/MeshContingencyBackups"`. A backup on the same disk as the
> bot is lost along with it when that disk fails. The default,
> `~/MeshContingencyBackups`, only protects against mistakes, and the bot says
> so when it starts:
> `Note: ~/MeshContingencyBackups is on the same disk as the bot's data; ...`

The copies hold email addresses, keys and messages (sealed messages stay
sealed). They keep their permissions and the folders are readable only by
you; keep the disk private too. Your mail client's config, with the email
password, isn't included.

`health` shows `last backup 3h ago`, and `history` lists every backup. If one
fails (the USB stick isn't plugged in, or the disk is full), the bot tries
again an hour later and the admins get `Node problem: backup to ... failing`
until one works; see [Get told about problems](#get-told-about-problems).

**To restore**, on the node's computer:

1. Stop the bot: `systemctl --user stop mesh-contingency`.
2. Copy the files from the backup folder you want back into the folder with
   `config.toml` (and `users.toml` and its `backups` folder to where they
   were, if that's somewhere else):
   ```sh
   cp -p ~/MeshContingencyBackups/20261022-091340/* ~/mesh-contingency/
   cp -p ~/MeshContingencyBackups/20261022-091340/backups/* ~/mesh-contingency/backups/
   ```
3. Start it again: `systemctl --user start mesh-contingency`.

On an existing node, turn the command on by adding
`backup = { permission = "admin" }` under `[commands]` in `config.toml`.
Backups themselves run without it.

## Use the web console

Everything on this page can also be done from a browser on the node's own
computer: no radio in hand, no 133-character replies, and the whole node on
one screen. It's off until you turn it on (new in 0.7.0).

<p align="center">
  <img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-dashboard.png" alt="The web console's dashboard" width="720">
  <img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-dashboard-phone.png" alt="The dashboard on a phone-sized window" width="180">
</p>
<p align="center"><em>The dashboard, wide and phone-sized (made-up demo data).</em></p>

**Turn it on**, once, on the node's computer, in the project folder:

```sh
.venv/bin/pip install -e ".[console]"
cd console && npm ci && npm run build && cd ..     # needs Node.js 22.22+ or 24.15+
```

Then add to `config.toml`:

```toml
[console]
enabled = true
```

and restart the bot (`systemctl --user restart mesh-contingency` as a
service). It prints the link to open:

```
Web console: http://127.0.0.1:8737/?key=... (also in .../console.url)
```

**Open it** on that computer, in the project folder:

```sh
.venv/bin/mesh-contingency-console
```

It opens the console in your browser. If it can't, it says
why: the console is off, the bot isn't running, or the link is old. Or open
the link yourself: it's printed in the journal, and in `console.url`
(`cat console.url`).

The key in the link is what lets you in; it leaves the address bar once
you're in. **Each restart of the bot makes a new key**, so after a restart the
page says *Open the console's link*: run `mesh-contingency-console` again.

**What's on it**, in the order of the menu: the Dashboard, then what
people do (Mailbox to Bible), then what only admins look after (Radio,
Users, Console users, History), grouped as the phone app's screens are; who
you are is at the foot of the menu (**Account**). In a window as
narrow as a phone, the menu becomes a tab bar along the bottom: Dashboard,
Mailbox, Contacts, Weather and **More** for the rest.

| Page | What you see | What you can do |
|---|---|---|
| **Dashboard** | Users, join requests, check-ins, messages waiting, the weather alerts out now (with their counties, in orange), the node watch, the last backup, `health`, and the live log | Click a tile to go to its page, or the alerts to go to Weather |
| **Mailbox** | Who has messages waiting, from whom, read or sealed, never what they say (that stays private, read with `inbox` over the radio) | **Leave a message** for a user (`msg`, from console) |
| **Check-ins** | Who has checked in, newest first, and who hasn't | **Look up a check-in** (`status`); **Clear check-ins** (it asks first) |
| **Contacts** | Two tabs. **Channels:** the radio's channels in use, each Public, hashtag or private, what the bot posts there (never a key), and how many messages are unread. Open one to read what was said on it since the bot started. **Contacts:** the radio's contacts, each one's type, whether it's a user or admin, its path and when it was last heard, with a filter | Post to any channel as the node; **Reset path** and **Remove** a contact |
| **Weather** | A card for each county in `[alerts]`: the weather now from the nearest NWS station, the next three forecast periods, and any alert out for it. Updated every 15 min; if the internet's down, a card says how old it is and why | Star (☆) the counties you care about to show them first, the rest under **Show more**; **Weather anywhere** (`wx`, any zipcode or county); **Post alert test** (it asks first: it goes out on the air), **Look up counties again** |
| **Bible** | The verse of the day | **Look up a verse** (`verse`) |
| **Radio** | The radio's settings: name, frequency, TX power, position, clock and firmware | **Advert**, **Flood advert**, **Back up now**; [change the radio's settings](#change-the-radios-settings) |
| **Users** | Each user and admin: settings, last seen, check-in, messages | **Whois**, **Edit emails**, **Reset passphrase**, **Remove**; **Approve** or **Deny** join requests; **Reload users file** after editing it |
| **Console users** | Who can log in to the console from other computers (see [below](#use-the-console-from-other-computers)): when each was made and by whom, and their last login | **Add** one, give one a **New password**, **Remove** one (it asks first) |
| **History** | What admins have done, newest first | Filter it: a name, `approved`, `alert`... |
| **Account** | Who you are, and how History names you | On the remote console: **Change password**, **Log out** |

<details>
<summary><b>See each page</b> (made-up demo data; click one for full size)</summary>

<table>
<tr><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-mailbox.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-mailbox.png" alt="The Mailbox page" width="400"></a><br><b>Mailbox</b></td><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-checkins.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-checkins.png" alt="The Check-ins page" width="400"></a><br><b>Check-ins</b></td></tr>
<tr><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-channels.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-channels.png" alt="The Contacts page: Channels tab" width="400"></a><br><b>Contacts: Channels</b></td><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-channel.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-channel.png" alt="A channel's messages" width="400"></a><br><b>Contacts: a channel</b></td></tr>
<tr><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-contacts.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-contacts.png" alt="The Contacts page: Contacts tab" width="400"></a><br><b>Contacts: Contacts</b></td><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-weather.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-weather.png" alt="The Weather page" width="400"></a><br><b>Weather</b></td></tr>
<tr><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-bible.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-bible.png" alt="The Bible page" width="400"></a><br><b>Bible</b></td><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-radio.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-radio.png" alt="The Radio page" width="400"></a><br><b>Radio</b></td></tr>
<tr><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-users.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-users.png" alt="The Users page" width="400"></a><br><b>Users</b></td><td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-history.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-history.png" alt="The History page" width="400"></a><br><b>History</b></td></tr>
</table>
</details>

Every button runs the same command you'd send over the radio, as an admin
called **console**, so the same rules apply: `remove` and `resetpass` ask
first (press **Confirm**), `history` shows `by console`, and a message you
leave arrives *from console* (they get the usual notice). A post must fit in
one channel message; the count under the box says how much room is left.
If the bot turns something down (*no user ...*, *inbox is full*), the reply
says why and your text stays in the box.

**Channel messages** are kept while the console is on: the last 200 of each
channel, since the bot started, in its memory only. A restart forgets them,
and none are written to disk. A post to a channel is recorded in `history`
(*posted to Family: ...*, by console). Each channel counts the messages
heard since you last opened it, and so do the Channels tab and Contacts in
the menu; the counts are kept in your browser, and start again when the bot
restarts.

**It doesn't chat with people directly.** People talk through `msg` and the
channels, and a direct message to the node is always a command. The bot
takes no commands from channels.

**Who can use it:** someone on the node's computer, with your account,
through the link; and, if you turn it on, [console users on other
computers](#use-the-console-from-other-computers), each with their own
name and password. Other web pages in the browser can't use it. It can't
read sealed messages or change `config.toml`.

## Use the console from other computers

In an Emergency Operations Center the node's computer may be in a closet or
another room, and the people running it work from whatever laptop, tablet
or phone is at hand. The same console can answer them over the local
network, over HTTPS, once each has a **console user**: a name and a
password. *New after 0.11.0, in the next release.*

**Console users aren't radio users.** They're kept apart from `users.toml`:
a console user needs no radio, a radio (even an admin's) is never a console
user and gives no way in, and console users can't send commands over the
mesh. A console user can do everything the console does (approve people,
post alerts, change the radio's settings) and manage the other console
users. Your admin radio still works as always; the two are separate ways in.

**Make the first console user** on the node's computer, in the project
folder. It asks for the password twice, 12 characters or more, and doesn't
show it:

```sh
.venv/bin/mesh-contingency-console user add sam
```

```sh
.venv/bin/mesh-contingency-console user list           # who there is
.venv/bin/mesh-contingency-console user password sam   # a new password (it also ends a lockout)
.venv/bin/mesh-contingency-console user remove sam     # asks first
```

These work whether or not the bot is running: they're the way back in if
everyone has forgotten their password or is locked out. Console users are
kept in `console_users.json` next to `config.toml`: names and password
*hashes* only, readable only by your account, and not in backups (after
restoring a backup, make them again).

**Turn it on** in `config.toml`, then restart the bot:

```toml
[console]
enabled = true
remote = true
# remote_port = 8738
```

The first time, the bot makes its own HTTPS certificate (in `console_tls/`
next to `config.toml`), and each start it prints where to open it and the
certificate's fingerprint:

```
Remote console: https://node.local:8738/ (certificate SHA-256 30:2B:D9:...:C1:57)
  also https://192.168.1.20:8738/
Watching the remote console's logins: 10 failed console logins in 15 min go to the admins.
```

If the node's computer has a firewall, let the local network reach that
port, for example with ufw (use your own network's addresses):

```sh
sudo ufw allow from 192.168.1.0/24 to any port 8738 proto tcp
```

**Log in from another device:** open one of those addresses in its
browser. The first time, the browser warns that the certificate isn't
trusted: that's expected, since the bot made it itself. Open the warning's
certificate details and check the **SHA-256 fingerprint** is the one the
bot printed (it's also on the Dashboard's **Remote** row); if it is, go on.
Then log in with the console user's name and password. Your name is at the
foot of the menu, with **Log out**.

**What console users do is theirs:** History says *by sam (console)*, a
message left from Mailbox comes *from sam (console)*, and rate limits and
**Confirm** questions are each person's own (alex can't confirm a removal
sam started). On the node's own computer, the console is still *console*.

**More console users:** on the **Console users** page, **Add** one with a
name and a password; tell them the password in person, and they can change
it on **Account** (it asks for the current one first). **New password**
gives someone a new one and logs them out; **Remove** asks first. Nobody can
remove themselves there, so there's always one left; the command on the
node's computer can remove anyone. Each change is in History.

**How long a login lasts:** until 30 minutes without using it (a page left
open, refreshing itself, doesn't count, so a laptop left on a desk logs
out), 12 hours at most, **Log out**, or a restart of the bot (which logs
everyone out). A removed console user, or one given a new password, is
logged out at their next click, and the Dashboard's live log stops within
15 seconds.

**Wrong passwords:** the answer is the same for a wrong name or a wrong
password. After 5 wrong tries for one name, or 10 from one device, within
15 minutes, that name or device waits 15 minutes; `user password` on the
node's computer lets that name in again at once. Each login, failure and
lockout is in the bot's journal (never a password), and a burst of 10
failed logins in 15 minutes is a [node problem](#get-told-about-problems):
every admin radio is told, with the devices it came from.

**Who can reach it:** only the local network. Requests from internet
addresses are refused before the login page, so a port forward on the
router doesn't put it on the internet. Use long passwords: there's no
second step to logging in.

**The certificate:** `mesh-contingency-console cert show` prints its
fingerprint. If the computer's address changes, `cert renew` makes a new
one, used from the next restart, and each browser warns once again. To use
your own certificate instead, set `cert` and `key` under `[console]` to its
files.

## Change the radio's settings

Send `radio` to see the radio's own settings:

```
radio
→ radio: Hilltop Base; 910.525 MHz BW62.5 SF7 CR5 (Canada, USA); TX 22/22 dBm; no position; clock right; firmware Heltec V3 v1.9.1
```

Over the mesh, that's all it does. **Every change is made from the web
console**, on the Radio page's **Settings** panel (turn on
`radio = { permission = "admin" }` under `[commands]` in `config.toml`).
The console reaches the radio over USB, so a setting that cuts the node off
from the mesh can't cut off the console: you can always set it back.

- **Name:** others see the new one after the node's next advert.
- **TX power:** from 1 dBm up to what the radio can do.
- **Position:** latitude and longitude. Whether adverts carry it is the
  radio's own setting.
- **Set clock:** from the computer's. The bot also does this each time it
  starts, if the clock is off: the radio loses the time when it reboots or
  loses power.
- **Reboot radio:** it asks first. The bot restarts with it, and is back in
  about a minute; then run `mesh-contingency-console` again, as the link
  changes (on another computer, log in again). You aren't sent a *Node
  problem* message for it.
- **Frequency, bandwidth, SF and CR:** pick one of MeshCore's regional
  presets, or **Other values…**. Every radio on a mesh must use the same
  frequency, bandwidth and spreading factor, so the button waits for you to
  type the node's name, and the bot then asks again and says what to set to
  go back. The radio reboots, and the bot with it.

<a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-radio.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/console-radio.png" alt="The Radio page, with its settings" width="600"></a>

## From the node's computer

Without using the mesh, while the bot keeps running:

| To | Do |
|---|---|
| Advert in direct range | Type `advert` in the bot's terminal |
| Advert across the mesh | Type `advert flood`, or run `kill -USR1 <pid>` from another shell |
| List the radio's contacts | Type `contacts` or `contacts <name>` |
| See the console commands | Type `help` |
| Re-read the users file | `kill -HUP <pid>` |
| Stop the bot | Ctrl+C |

The console shows each message and reply, except for `msg`, `inbox` and
`setpass`, where it shows only the command and who sent it.

**Running as a service?** There's no terminal to type in, and the output goes
to the journal. Use these instead (full details in
[Running as a systemd Service on Linux](Running-as-a-systemd-Service-on-Linux)):

| To | Run |
|---|---|
| Advert across the mesh | `systemctl --user kill --kill-whom=main -s USR1 mesh-contingency` |
| Re-read the users file | `systemctl --user kill --kill-whom=main -s HUP mesh-contingency` |
| Restart after changing `config.toml` | `systemctl --user restart mesh-contingency` |
| Watch what it's doing | `journalctl --user -u mesh-contingency -f` |
| Stop it to use the MeshCore app | `systemctl --user stop mesh-contingency` (then `start`) |

## When something doesn't work

| What you see | Why, and what to do |
|---|---|
| No reply at all | The radios may not know each other. Advert, then check with `contacts`. |
| `unrecognized user or function` | The command doesn't exist, or that person isn't allowed to use it. Check with `whois`. It's sent at most once every 5 minutes. Users and admins who mistype a command get `unknown command ...; did you mean ...?` instead, naming only commands they may run. |
| `<command>: limit reached, try again in 23 min` | That person used the command too often. Limits are set in `[limits]` in `config.toml`. |
| `... daily email limit ...` | The sender or the whole node reached the daily email cap. |
| `qm: not sent, no internet at the node; try again later` | `mail` couldn't reach the email server (no internet, or no DNS). Nothing is kept to send later; the sender sends it again once the internet is back. |
| `... not sent, the node's email login was refused; tell an admin` | The email server turned down the node's login: the app password in the mail client's config (e.g. `~/.msmtprc`) is wrong or was revoked. The console has the server's own words. |
| `... not sent, an address was refused; check the address` | The email server wouldn't accept one of the addresses. For `qm` and `emailall` it's one of the sender's preset addresses (`setqm`, `addgroup`). |
| `... not sent, email isn't set up on the node` or `email error at the node` | `mail` isn't installed, or failed for another reason; the console line ``<command> failed: `mail` failed: ...`` says what. Test on the node's computer with `echo test \| mail -s test you@example.com`. |
| `... can't be changed automatically; edit ... section by hand` | That user's section of `users.toml` has a layout the bot won't rewrite. Edit it by hand. |
| `Warning: ... can be read or changed by other accounts (mode 644); fix with: chmod 600 ...` | A file holding email addresses, keys or your SMTP password is readable by other accounts on the node's computer. Run the `chmod 600` command shown (on the node's computer, not over the mesh). |
| `rename no longer exists (...); remove [commands.rename] from the config.` | Names now come from the radios, so the command is gone. Delete the `rename = ...` line from `[commands]` in `config.toml`; the bot runs fine meanwhile. |
| `msg: no user ...` or the wrong person picked | Use the whole radio name, or put it in parentheses: `msg (Sam T-Deck) hi`. The start of their key always works (`msg 5a3e hi`). |
| `... 2 users are called ...; use the key prefix: ...` | Two users' radios have the same name. Use one of the key prefixes it lists, and ask one of them to rename their radio. |
| `Warning: ...'s radio is now called '...', which can't be used; keeping ...` | A user renamed their radio to a name `join` would refuse. Ask them to pick another. |
| `quickim is now called qm; rename [commands.quickim] to [commands.qm] in the config. Using it for qm meanwhile.` (or the same for `setquickim`) | The commands were renamed `qm` and `setqm`. In `config.toml`, change `quickim =` to `qm =` and `setquickim =` to `setqm =` under `[commands]`, and restart. Users' `quickim` addresses in `users.toml` are renamed `qm` by the bot itself (`users.toml: quickim is now qm for 2 user(s)`). |
| `alert: too long for one channel message (150 characters; at most 119); nothing posted` | A channel message has room for 133 characters, less the node's name and ": " (119 for a node called "Hilltop Node"). Shorten it and send it again. |
| `Auto alerts: couldn't look up the NWS code of Tailor, TX (the NWS has no county 'Tailor' in TX)` | A county in `[alerts]` is misspelled. Fix it in `config.toml` and restart. The other counties are still watched. |
| `Auto alerts: couldn't check for alerts (...)` or `health` says `last check failed` | The node can't reach api.weather.gov (no internet, or the NWS is down). It tries again every round and says `checking for alerts again` when it works. Right after the computer starts, the bot waits up to 2 minutes for the network before its first check (`Auto alerts: no network yet; waiting up to 2 min before the first check`, then `network up after 15s`), so this only shows if the network takes longer. |
| `[alerts] counties: 'Taylor' isn't a county and state, e.g. "Taylor, TX"` (the bot won't start) | Each county needs its state's two letters: `"Taylor, TX"`. |
| `[alerts] may only set channel, counties, every_minutes.` (the bot won't start) | `[alerts]` has a setting it doesn't know, such as `zipcodes`. Alerts are watched by county: use `counties = ["Taylor, TX"]`. |
| `[alert_test] weekly: 'Wed' isn't a day and time, e.g. "Wednesday 17:00" or "Wed 5:00PM"` (the bot won't start) | `weekly` needs a day and a time: `"Wednesday 17:00"`. |
| `[alert_test] timezone 'Central' isn't a time zone, e.g. "America/Chicago"` (the bot won't start) | Use a name from the time zone database: `America/Chicago`, `America/Denver`, `America/New_York`. |
| `Weekly alert test failed: ...` | The radio didn't take the message, or has no free channel slot. The next week's test still goes out; send `testalert` to try now. |
| The web console says *Open the console's link* | The bot restarted, which makes a new key. Run `.venv/bin/mesh-contingency-console` again, or open the link in `console.url` (or from the journal's `Web console:` line). |
| `mesh-contingency-console` says *Nothing answers* or *No console.url*, or the link doesn't load (*can't connect*) | The bot isn't running, `[console] enabled` isn't `true`, or the port was taken: the journal says `Warning: web console not started: port 8737 can't be used`; set another `port` under `[console]` and restart. Open it on the node's computer: other computers can't reach it. |
| On another device, the console says *Wrong name or password.* | The name or password is wrong (names don't care about capitals). Another console user can give them a **New password**, or on the node's computer: `mesh-contingency-console user password NAME`. |
| *Too many failed logins: try again in 15 minutes.* | 5 wrong passwords for that name, or 10 from that device, within 15 minutes. Wait, or set a new password on the node's computer (`user password NAME`), which lets that name in at once. |
| Another device can't connect to `https://...:8738/` at all | `remote = true` isn't under `[console]`, the bot hasn't restarted since, or a firewall on the node's computer blocks the port (see [Use the console from other computers](#use-the-console-from-other-computers)). The journal's `Remote console:` line says it's on; `Warning: remote console not started: ...` says why not. |
| The console on another device says *Open the console's link* | It's an old copy of the console's app in that browser: reload the page. |
| The browser warns the certificate isn't trusted | Expected: the bot made the certificate itself. Check its SHA-256 fingerprint matches the journal's `Remote console:` line or the Dashboard's Remote row, then go on. If it doesn't match, don't log in: something else is answering. |
| `Remote console: no console users yet; add one with mesh-contingency-console user add NAME` | Nobody can log in yet: make a console user on the node's computer. |
| The web console shows only *its app isn't built* | Build it: `cd console && npm ci && npm run build`, then restart the bot. Do it again after an update that changes `console/`. |
| A user's radio has a new key | Put the new key in `users.toml`; the node adds the radio when it next adverts. |
