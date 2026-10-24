<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/branding/mesh-contingency-lockup.svg">
    <img src="docs/branding/mesh-contingency-lockup-dark.svg" alt="Mesh Contingency" width="560">
  </picture>
</p>

<p align="center">
  <strong>A contingency link over MeshCore.</strong><br>
  Weather, check-ins, private messages and email, from nothing but a mesh radio.
</p>

<p align="center">
  <a href="https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml"><img src="https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-38BDF8?logo=python&logoColor=white" alt="Python 3.11+">
  <a href="https://github.com/meshcore-dev/MeshCore"><img src="https://img.shields.io/badge/radio-MeshCore-FF5F1F" alt="MeshCore"></a>
  <a href="https://github.com/DJSnitker/mesh-contingency/wiki"><img src="https://img.shields.io/badge/docs-wiki-151B23" alt="Docs: wiki"></a>
</p>

<p align="center">
  <a href="https://github.com/DJSnitker/mesh-contingency/wiki/User-Guide"><b>User Guide</b></a> ·
  <a href="https://github.com/DJSnitker/mesh-contingency/wiki/Admin-Guide"><b>Admin Guide</b></a> ·
  <a href="https://github.com/DJSnitker/mesh-contingency/wiki/Commands"><b>Commands (A–Z)</b></a> ·
  <a href="https://github.com/DJSnitker/mesh-contingency/wiki/Running-as-a-systemd-Service-on-Linux"><b>Run as a service</b></a>
</p>

---

## About

A small bot for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion
radio connected over USB serial. It listens for **direct messages** sent to the
radio, runs simple commands, and replies over the mesh. It is meant as a
contingency link: someone with only a mesh radio can check the weather, read
a Bible verse, check in, leave messages for others, or get a message out by
email. Commands are plugins: anyone can
write one in a separate package and install it (see
[Writing a command](#writing-a-command)).

Channel messages are ignored entirely; only direct messages are acted on. The
one exception is outgoing: `alert` and the automatic weather alerts post to a
public channel.

What changed in each release, and how to upgrade, is in
[CHANGELOG.md](CHANGELOG.md).

## Commands

Full usage, examples and how-to guides are in the
[wiki](https://github.com/DJSnitker/mesh-contingency/wiki):

- [Commands (A–Z)](https://github.com/DJSnitker/mesh-contingency/wiki/Commands): every command with usage, permissions and examples
- [User Guide](https://github.com/DJSnitker/mesh-contingency/wiki/User-Guide): joining, check-ins, messages, passphrases, email
- [Admin Guide](https://github.com/DJSnitker/mesh-contingency/wiki/Admin-Guide): adding and managing users, adverts, alerts, troubleshooting

Grouped by who can run them in the example config (admins, anyone, users),
then A–Z; see [Permissions](#permissions) to change who may run what.

| Command | Who can run it (example config) | What it does |
|---|---|---|
| `advert [flood]` | admins | Make the radio advertise itself (see [While it runs](#while-it-runs)) |
| `alert <message>` | admins | Post a message to the alert channel, `#contingency-wx` |
| `alertmap [county, ST]` | admins | Look up the NWS codes of the [automatically watched](#automatic-weather-alerts) counties again |
| `approve [name or key]` | admins | Approve a join request; alone, list them |
| `backup` | admins | Make a [backup](#backups) of the bot's data now |
| `checkins [page <n>]` | admins | Roll call: every user's check-in, or missing |
| `clearstatus` | admins | Delete every check-in |
| `comm <message>` | admins | Post a message to the [communications channel](#communications-channel), `#contingency-comm` |
| `contact path <name or key>` | admins | Reset the radio's path to a contact whose messages stopped getting through |
| `contact remove <name or key>` | admins | Remove a contact from the radio (it asks first) |
| `contacts [name or key] [page]` | admins | List the radio's contacts |
| `deny <name or key>` | admins | Turn down a join request |
| `health` | admins | How the node is doing: radio, battery, users, messages, errors |
| `history [page]` | admins | What admins have done (approve, remove, resetpass...), newest first |
| `radio` | admins | Show the radio's settings; [change them](#radio-settings) from the web console only |
| `reload` | admins | Re-read the [users file](#users-file) now |
| `remove <name or key>` | admins | Remove a user and their messages |
| `resetpass <name or key>` | admins | Clear a user's forgotten passphrase |
| `roster` | admins | Who has messaged the node since it started |
| `setemail <name or key> qm [address] group [address ...]` | admins | Set a user's qm address and emailall group; a part with no address clears it |
| `testalert` | admins | Post the [test message](#weekly-alert-test) to the alert channel now |
| `users [page]` | admins | List the users and what each has set |
| `whois <name or key>` | admins | What the node knows about a user |
| `help [command]` | anyone | List your commands, or how to use one |
| `join` | anyone | Ask to become a user, under your radio's name |
| `ok [status]` | anyone | Check in: tell others you're ok |
| `status <name or key>` | anyone | See someone's last check-in |
| `verse [book chapter:verse[-verse]]` | anyone | A Bible verse (BSB), or the verse of the day |
| `wx <zipcode>` or `wx <county, ST>` | anyone | Weather and alerts for a US zipcode or county |
| `addgroup <address>` | users | Add an address to your emailall group; alone, list it |
| `cleargroup` | users | Empty your emailall group |
| `clearinbox [all]` | users | Delete the messages you've read, or all of them |
| `email <address> <message>` | users | Email any address |
| `emailall <message>` | users | Email your group |
| `inbox [passphrase] [page]` | users | Read your messages (see [Sealed messages](#sealed-messages)) |
| `leave` | users | Stop being a user |
| `msg <name> <message>` | users | Leave a message for another user |
| `qm <message>` | users | Quick message: email your preset contact |
| `setpass <passphrase>` | users | Seal your messages with a passphrase |
| `setqm <address>` | users | Set your qm address; alone, show it |
| `whoami` | users | What the node knows about you |

Command names are case-insensitive. Everything after the command name is
passed through as typed. Replies too long for one 133-character message are
split into numbered messages (`(1/3) ...`), at most 8 per reply.

Notification emails have the subject
`You have received a MeshCore message from: <sender>`, the message text as the
body, and a fixed disclaimer that replies are not relayed back to the mesh.

Check-ins and mailbox messages are saved in `status.json` and `mailbox.json`
next to `config.toml`, so they survive a restart. Both are git-ignored and
readable only by you. Messages stay until their reader sends `clearinbox`, so
one lost on the air can be read again with `inbox`. The names a check-in or message
shows are from the users file, or the name the node advertises.

### Sealed messages

A user who sends `setpass <passphrase>` gets every new message to them sealed,
so `mailbox.json` holds only who sent it and when. Nobody needs to handle keys:

```
Alice → bot:  setpass blue-canoe-42x
Bob → bot:    msg Alice T-Deck meet at the shelter at 6
Alice → bot:  inbox
bot → Alice:  inbox: 1 message(s) from Bob's Heltec 5m ago. Send inbox <passphrase> to read.
Alice → bot:  inbox blue-canoe-42x
bot → Alice:  Bob's Heltec 6m ago: meet at the shelter at 6
```

- The bot turns the passphrase into a key pair (scrypt, then X25519) and saves
  only the public half, as `inbox_key` in the user's section of the users
  file. That half can seal messages but not open them. The passphrase and the
  private half are never saved; `inbox <passphrase>` rebuilds the private half,
  opens the messages and forgets it again.
- Messages are found by the recipient's radio public key as usual; the
  `inbox_key` is a separate key, made from the passphrase.
- Passphrases are 12 to 16 characters, without spaces.
- **A forgotten passphrase can't be recovered**, and the messages sealed with it
  are lost. `setpass` with a new passphrase starts a new key. If sealed
  messages are waiting, it says they will be deleted and asks for the same
  `setpass` again within 5 minutes to confirm.
- Messages left before `setpass` stay unsealed, and are shown with
  `inbox <passphrase>`. Users who never set a passphrase keep plain messages,
  shown by plain `inbox`.
- The bot still sees each message as it arrives and as it's delivered, since
  the radio hands it plain text both ways. `msg`, `inbox` and `setpass` are
  private commands: the console shows only the command and who sent it, never
  the message, passphrase or reply.

When `msg` saves a message, the recipient gets a direct message such as
`inbox: new message from Bob; send inbox to read`, at most once every 10
minutes, never with the text and never for a message to yourself. Set
`notify = false` in `[commands.msg]` to turn this off. Messages are deleted
after 30 days, read or not; set `keep_days` in `[commands.msg]` to change
that (0 keeps them until cleared).

`remove`, `resetpass` and `leave` can't be undone, so the first time each only
says what it would do, e.g. `remove: this removes Bob (b0b0b0b0b0b0) and their
2 message(s). Send it again within 5 min to confirm.` Users are
named by their radio's name (see [Names](#names)) or a key prefix of at least
4 hex characters. Nobody can be made an admin over the mesh; that takes an
edit of `[admin] keys`, so a lost admin radio can't create more admins.

`approve`, `remove`, `setqm`, `addgroup`, `cleargroup`, `setemail`, `setpass`, `resetpass` and `leave` write to the users file
and reload it at once. They rewrite only that person's `[users.<key>]` section
(comments inside it are dropped); the rest of the file is kept as it is. The
result is checked before it's saved, so if a section can't be rewritten
cleanly (for example one split into sub-tables), nothing is changed and the
command says to edit it by hand. Before each write, the file as it was is
saved in a `backups` folder next to it (e.g.
`backups/users-20261020-221500.toml`, as private as the file); the newest 5
are kept. To undo a change, copy a backup back over `users.toml`.

`approve`, `deny`, `remove`, `resetpass`, `setemail`, `clearstatus`, `alert` and `comm`
(with the message), `alertmap`, `testalert` and `backup` are recorded in `history.json` next to
`config.toml`, with who did them and when, as are a user's `leave`, a radio's
change of name, and the weather alerts, weekly tests and backups the bot makes
by itself (as "auto"); admins read it with `history`. The newest 200 are kept.

Join requests wait in `requests.json` next to
`config.toml` until approved or denied, at most 20 at a time.

`alert <message>` posts the message, exactly as typed, to a hashtag channel,
which anyone can join by adding the same name (`#contingency-wx`) in their
app: `alert Shelter open at First Baptist on 5th St`. It must fit in one
channel message (133 characters, less the node's name and ": ", which the
radio puts in front). The automatic weather alerts below go to the same
channel. When the bot starts, it makes sure the
radio has the channel, adding it to the first empty channel slot if needed
(the console says which slot). If there is no free slot, it warns and keeps
running. To use another channel:

```toml
[commands.alert]
permission = "admin"
channel = "#storm-watch"
```

### Communications channel

`comm <message>` posts an admin's message, exactly as typed, to a second
hashtag channel, `#contingency-comm`, for news and updates everyone should see
at once: `comm Shelter open at the high school gym`. One channel message
costs far less airtime than a direct message to each user. It works like
`alert`: the same one-message limit, the channel is added to the radio at
startup if missing (the console says which slot), and `channel = "..."` under
`[commands.comm]` uses another one. Anyone who adds `#contingency-comm` in
their app can post there from their own radio too. Weather stays on
`#contingency-wx`.

`checkins [page <n>]` is the matching roll call: every user in name order,
with their last check-in (`✓ Sam T-Deck: at the shelter (2h ago)`) or
`✗ Alex Base: missing`, five to a page, then `1/2 checked in. Page 1/1.`

### Automatic weather alerts

The bot can watch the National Weather Service for a list of counties and
post each **new** alert to the channel by itself, with no admin needed:

```toml
[alerts]
counties = ["Taylor, TX", "Jones, TX"]  # empty, the default, turns it off
every_minutes = 10                      # how often to check (at least 5)
# channel = "#storm-watch"              # defaults to [commands.alert] channel
```

Write each county as its name and state (`"Taylor, TX"`; `Taylor County, TX`
works too). The bot looks up each county's NWS code once and keeps it in
`alerts.json`; `alertmap` looks them up again. Each round is then a single
request for the alerts in all the counties, including those the NWS issues
for forecast zones in them. Each alert is posted once, one message per alert,
named by the first watched county it covers:

```
Taylor, TX ALERT: Severe Thunderstorm Warning | until Tue 6:00PM | Taylor; Jones
```

An alert several counties share isn't repeated. What has been posted is kept
in `alerts.json` too, so a restart doesn't post anything again, and alerts
are forgotten some hours after they end. If something can't be looked up (no
internet, or api.weather.gov is down) the console says so once and the bot
keeps trying every round. Each post is in `history` as by "auto", and
`health` shows `auto alerts 2 counties, checked 3m ago`. Posting goes only to
the channel; nobody is sent a direct message. For anyone to look up a
zipcode's or county's alerts themselves, there is `wx <zipcode>` or
`wx Taylor, TX`.

### Weekly alert test

So people know the alert channel works, the bot can post a test message to it
every week, followed by the counties it watches (names only, in as few
messages as fit, numbered `(1/2)` and so on when there are several), and
`testalert` posts it on request:

```toml
[alert_test]
weekly = "Wednesday 17:00"     # or "Wed 5:00PM"; empty (the default) for no weekly test
timezone = "America/Chicago"   # defaults to the computer's time zone
# message = "TEST: this is a test of the #contingency-wx alert channel. No action needed."
```

The time is in the time zone given, daylight saving included: 17:00 in
`America/Chicago` is 5PM CDT in summer and 5PM CST in winter. If the bot isn't
running at that time, that week's test is skipped, not sent late. Each test
is in `history` (as "auto" when scheduled), and `health` shows
`next alert test Wed 5:00PM CDT`. The message must fit in one channel message
from the node; the bot won't start if it doesn't.

### Node watch

Problems with the node shouldn't wait for someone to send `health`. Every few
minutes the bot checks the radio and what it has seen, and sends every admin a
direct message when a problem starts and when it's over:

| Problem | Starts when | Over when |
|---|---|---|
| Battery low | the radio's battery is below `battery_volts` | it's 0.1 V above it |
| Messages not delivered | `undelivered_in_row` direct messages in a row get no acknowledgement | one does |
| Email failing | an email can't be sent for a reason at the node (no internet, login refused...; not a refused address) | one is sent |
| Command errors | `errors` commands fail or time out within 30 minutes | 30 minutes have passed and there are fewer |
| Users file | `users.toml` has a mistake and isn't reloaded | it's reloaded |
| Backup failing | a [backup](#backups) can't be made | one is |

```
Node problem: battery low, 3.42V (below 3.50V)
Node ok again: battery 3.65V
Node problem: the radio restarted 3m ago (power, USB or a crash)
Node problem: the radio was disconnected for 7m (reconnect_failed); back now
Node restarted: the computer started 1m ago, and the radio with it
```

It also says when the radio has restarted (its uptime went backwards).
Restarting the bot doesn't restart the radio, so that's always a real restart,
and it's noticed even when it restarted the bot too. A radio powered by the
computer's USB restarts when the computer does (a power cut, an update,
someone rebooting it); on Linux the bot can tell, and says `Node restarted`
instead, since nothing is wrong with the radio. When the bot stopped
because it lost the radio (an unplugged USB cable), nobody could be told at
the time, so once the radio is back it says for how long it was gone (and
whether the radio restarted meanwhile). A radio with a battery keeps running
while unplugged, so only the disconnect shows. A reboot from the web console
([`radio reboot` or `radio freq`](#radio-settings)) is only logged
(`Watch: the radio restarted just now: ...`): whoever asked for it knows.

Each problem is announced at most once an hour, with one "ok again" after it,
so a value going back and forth can't flood the mesh. "Ok again" needs
evidence the problem is over (an email sent, a message delivered, a backup
made), so a restart of the bot, which forgets what it had seen, doesn't end
a problem by itself. What has been announced is kept in `watch.json`, so a
restart doesn't announce an ongoing problem again either. `health` shows `watch: no problems` or the current ones, and the
console logs every notice. It's on by default:

```toml
[watch]
enabled = true
every_minutes = 5        # how often to check; at least 1
battery_volts = 3.5      # warn below this; 0 for no battery check
undelivered_in_row = 5   # messages in a row not delivered; 0 for no check
errors = 3               # commands failed or timed out within 30 min; 0 for no check
```

With `enabled = false`, a users file that can't be reloaded is still sent to
the admins straight away, as before, but nothing else is.

### Backups

A dead disk would lose the users, messages, check-ins and history, so the bot
backs up its data by itself, once a day by default, and admins can make a
backup at any time with `backup`:

```
backup
→ backup: 9 file(s) saved in ~/MeshContingencyBackups/20261022-031500; newest 7 kept
```

Each backup is a new folder named for the time, inside the `to` folder:
`config.toml`, the users file, every JSON file next to `config.toml`
(check-ins, the mailbox, history, join requests...) and the users file's
`backups` folder. The newest `keep` are kept; other folders in `to` are left
alone. A backup is made `every_hours` after the last one, even across
restarts, so a restart only backs up if one is due.

```toml
[backup]
to = "~/MeshContingencyBackups"   # e.g. "/mnt/usb/MeshContingencyBackups"
every_hours = 24                  # 0 for only with the backup command
keep = 7                          # newest backups kept
```

**Put `to` on a separate disk if you can**: a USB stick, a second drive or a
network share mounted on the node's computer, e.g.
`to = "/mnt/usb/MeshContingencyBackups"`. A backup on the same disk as the
bot's data is lost along with it when that disk fails; the default,
`~/MeshContingencyBackups`, only protects against mistakes. At startup the
bot says so if `to` is on the same disk:
`Note: ~/MeshContingencyBackups is on the same disk as the bot's data; ...`.
A relative `to` is relative to the folder of `config.toml`.

The backups hold everything the bot keeps: email addresses, node keys, check-ins
and messages (sealed messages stay sealed). Files keep their permissions, and
the folders the bot makes are readable only by their owner; keep the disk
private too. Your mail client's own config (with the SMTP password) isn't
included.

`history` lists each backup, `health` shows `last backup 3h ago`, and a backup
that fails (the disk isn't mounted, or is full) is logged with the reason and
tried again an hour later; the [node watch](#node-watch) tells the admins
(`Node problem: backup to /mnt/usb/... failing: No such file or directory`)
until one works. To restore, stop the bot, copy the files from a backup folder
back next to `config.toml` (`users.toml` where it was, and its `backups`
folder next to it), and start the bot again.

Example `wx` reply:

```
33101 ALERT: Rip Current Statement | Mostly Cloudy, 20% precip 6h | 82F E14mph G18
```

(`G18` is wind gusts in mph.)

`wx` also takes a county, written as its name and state (`wx Taylor, TX`,
`wx taylor county tx`) or as its NWS code (`wx TXC441`). The conditions are
from the station nearest the county's middle, and the alerts are the ones the
NWS has issued for the county:

```
Taylor, TX Clear, 0% precip 6h | 81F S11mph
```

### Bible verses

The whole [Berean Standard Bible](https://berean.bible/) is bundled with the
bot (`mesh_contingency/bible/bsb.json.gz`, 1.2 MB), so `verse` never touches the network. The
BSB was dedicated to the public domain in 2023, so verses are sent without a
copyright notice.

References accept full book names, standard abbreviations and any
unambiguous prefix: `john 3:16`, `jn 3:16`, `1 jn 4:8`, `I John 4:8`,
`song 2:4`, `phil 4:13`. Single-chapter books can be cited by verse alone
(`jude 24`). A range within one chapter, `ps 23:1-3`, numbers each verse
after the first.

A reply that doesn't fit in one 133-character message is split between words
into numbered messages, so they can be read in order even if the mesh
delivers them out of sequence:

```
(1/2) John 3:16 For God so loved the world that He gave His one and only Son, that everyone who believes in Him shall not perish but
(2/2) have eternal life.
```

A reply may take at most 8 messages; longer ranges are refused. The verse of
the day comes from a built-in list of 237 well-known verses
(`mesh_contingency/bible/votd.py`), taken in turn by date, so everyone gets the same verse on
the same day. Text is converted to plain ASCII (straight quotes, `--` for
dashes). Verses the BSB omits from the main text, such as Matthew 17:21, are
reported as not in the text.

The bundled file is built from the [Free Use Bible API](https://bible.helloao.org)
with `python -m mesh_contingency.bible.build`. It only needs rebuilding to pick up corrections
to the source text.

### Permissions

Users and admins are listed by their full public key (64 hex characters),
which the MeshCore app shows for your node. A direct message carries only the
first 12 characters (the prefix), so the bot looks the sender up in the
radio's contacts and checks that contact's full key against the
[users file](#users-file). If no
contact, or more than one, has the prefix, the sender is unidentified and may
only run public commands, so a node that copies someone's prefix never gets
their rights. If two contacts share a user's or admin's prefix, admins are told
once (at startup, after a reload, or when such a message arrives) so they can
remove the impostor from the radio. The console prints the prefix and name for each message, e.g.
`[a1b2c3d4e5f6 Alice] wx 10001`.

Who may run each command is set entirely in the config's `[commands]`
table (see [Configuration](#configuration)); the code has no built-in levels.
Each command gets one of:

- **public**: anyone.
- **user**: senders with a `[users.<public key>]` section in the users file.
- **admin**: senders whose public key is in the users file's `[admin] keys`.
- **disabled**: nobody.

An installed command with no entry is disabled, with a warning at startup,
so installing a command never opens it until you allow it. An unknown
command name or level stops the bot before it connects.

The user and admin lists are independent: an admin isn't automatically a
user. Anything else — an unknown command,
or a command the sender isn't allowed to run — gets the reply
`unrecognized user or function`, at most once per sender every 5 minutes so
the bot can't be pulled into a reply loop with another automated node.

A user or admin who mistypes a command is told the nearest one **they** may
run instead, e.g. `unknown command resetpassword; did you mean resetpass?
help lists yours`; an old name (`quickim`) gets its new one (`qm`). Only the
first word is repeated, never the rest (it may be a passphrase), and
strangers still get only `unrecognized user or function`, so they learn
nothing about the commands there are.

Senders must be in the radio's contacts, since direct messages from unknown
nodes can't be decrypted or replied to. See [Contacts](#contacts) for adding
them automatically.

## Requirements

- Python 3.11+
- A MeshCore companion radio on USB serial
- The `mail` command (e.g. s-nail or mailutils) able to send through an SMTP
  server, for the `qm`, `emailall` and `email` commands
- Internet access for `wx` ([api.weather.gov](https://www.weather.gov/documentation/services-web-api)
  and [zippopotam.us](https://zippopotam.us) for zipcode lookup; no API keys).
  `verse` works offline.
- Optional, for the [web console](#web-console): [Node.js](https://nodejs.org)
  22.22+ or 24.15+ with npm, to build its app from this folder (only once per
  update; the bot doesn't need Node.js to run). Its fonts are bundled, so it
  works without the internet.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e .           # installs meshcore and the mesh-contingency command
cp config.example.toml config.toml   # then edit it
cp users.example.toml users.toml     # then add your users and admins
chmod 600 config.toml users.toml     # they hold email addresses and keys
```

The editable install (`-e`) runs the code straight from this folder, so edits
take effect on restart, and `config.toml` and `users.toml` here are found by
default. Re-run the install after pulling changes that add modules or
commands, since commands are registered when the package is installed.

### Configuration

`config.toml` holds the settings that change rarely and are read at startup:
commands, permissions and contacts. People go in the [users file](#users-file),
which can change while the bot runs. Both are git-ignored because they hold
real email addresses and node keys. See `config.example.toml`:

```toml
[commands]
help = { permission = "public" }
wx = { permission = "public" }
verse = { permission = "public" }
qm = { permission = "user" }
emailall = { permission = "user" }
email = { permission = "user" }
advert = { permission = "admin" }
contacts = { permission = "admin" }
contact = { permission = "admin" }
radio = { permission = "admin" }
reload = { permission = "admin" }
ok = { permission = "public" }
status = { permission = "public" }
clearstatus = { permission = "admin" }
checkins = { permission = "admin" }
roster = { permission = "admin" }
health = { permission = "admin" }
history = { permission = "admin" }
msg = { permission = "user" }
inbox = { permission = "user" }
clearinbox = { permission = "user" }
setpass = { permission = "user" }
alert = { permission = "admin" }
alertmap = { permission = "admin" }
testalert = { permission = "admin" }
comm = { permission = "admin" }
backup = { permission = "admin" }
join = { permission = "public" }
approve = { permission = "admin" }
deny = { permission = "admin" }
setqm = { permission = "user" }
addgroup = { permission = "user" }
cleargroup = { permission = "user" }
setemail = { permission = "admin" }
users = { permission = "admin" }
whois = { permission = "admin" }
remove = { permission = "admin" }
resetpass = { permission = "admin" }
whoami = { permission = "user" }
leave = { permission = "user" }
```

Each entry under `[commands]` takes:

| Key | Meaning |
|---|---|
| `permission` | Required: `public`, `user`, `admin` or `disabled`. |
| `timeout` | Seconds before the command is abandoned with a "timed out" reply (default 60). |
| `rate` | Uses allowed per sender, e.g. `"5/hour"` (per `minute`, `hour` or `day`), or `"none"`. Defaults come from [`[limits]`](#limits). |
| `handler` | Code to run, as `"module:attr"`: a `Command` subclass or a function. Only needed for commands that aren't installed as a package, or to run installed code under another name. |
| anything else | Passed to the command as its options. |

A command with options reads more easily as its own section:

```toml
[commands.roll]
permission = "public"
max_dice = 10
```

The same code can run under several names. For example, a second qm
command whose addresses come from each user's `quickfam` key:

```toml
[commands.quickfam]
handler = "mesh_contingency.commands.qm:QmCommand"
permission = "user"
```

Each user's `qm` / `emailall` key may be a single address or a list.

`qm` and `setqm` were called `quickim` and `setquickim` before 0.3. A config
that still uses the old names works, with a warning at startup to rename them,
and the bot renames users' `quickim` addresses in `users.toml` to `qm` by
itself (with a backup), at startup and whenever the file reloads.
A user with no addresses can still use `email`. A `qm` or `emailall`
message that starts with an email address is refused with a pointer to
`email`, so a message meant for someone else isn't sent to the preset
contact by mistake.

### Limits

So no one can tie up the node or its email account, each sender may use each
command only so often:

```toml
[limits]
public_rate = "10/hour"       # default for public commands
user_rate = "30/hour"         # default for user commands
admin_rate = "none"           # default for admin commands
emails_per_day = 50           # emails sent per sender in 24 hours
emails_per_day_total = 200    # addresses emailed by the whole node in 24 hours
```

These are the defaults when `[limits]` is left out. A command's own `rate`
replaces its level's default. A sender who reaches a limit gets one reply,
`wx: limit reached, try again in 23 min`, and no reply to that command after
that until the limit frees up, so the limit itself can't make the node
transmit. `emails_per_day` counts each `qm`, `emailall` or `email` as
one, however many addresses it goes to. `emails_per_day_total` counts
addresses, so an `emailall` to 3 counts 3 there, since that's what the sending
account's own limits count. Set a cap to 0 for no cap.
Counts are kept in memory and start again when the bot restarts.

### Users file

Users and admins are in `users.toml`, next to `config.toml` (see
`users.example.toml`):

```toml
[admin]
keys = ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"]

[users.a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2]
name = "Alice T-Deck"  # the radio's name; the bot keeps it up to date
qm = "someone@example.com"
emailall = ["someone@example.com", "someone.else@example.com"]
```

Keys are full public keys (64 hex characters); the 12-character prefix is not
accepted. Each user's settings are read by the commands: `qm` and
`emailall` take one address or a list.

### Names

A user's `name` is always their radio's name, exactly as the radio advertises
it, spaces and punctuation included (`Ridge Base 1`), so the name in every reply
is the one people see on their own radios. Nobody picks it with a command:

- `join` uses the radio's name. It refuses a radio with no name, one with
  control characters or parentheses in it, or a profane one (see
  `mesh_contingency/names.py` for the list); the person renames the radio and
  sends `join` again.
- The bot keeps the file up to date. At startup it compares each user's name
  with the radio's contacts, and whenever a user's message arrives under a new
  name it writes the new one, logs `Dana (d0d0d0d0d0d0) is now Ridge Base 1, the
  radio's name` and records it in `history`. A new name `join` would refuse
  is logged and not taken.
- A name typed into the file by hand is replaced by the radio's name the next
  time the bot sees the radio.

Commands that name a user take the name as it is, in any case:
`msg ridge base 1 see you at noon`. When the longest matching name is wrong,
or a name ends in something that looks like the rest of the message, put it in
parentheses: `msg (Ridge Base 1) see you at noon`. Every keyboard has them,
including the small ones on mesh devices, which is why radio names can't
contain them. If two users' radios have the same name, the command lists their
key prefixes; use one of those instead.

The bot checks the file every 5 seconds and applies changes without a restart,
logging what changed, e.g. `users.toml reloaded: added Bob; changed Alice`. A
change is used once the file has stopped changing, so it takes effect within
about 10 seconds. To apply it at once, send `reload` as an admin or signal the
bot with `kill -HUP <pid>`.

If an edit is invalid (bad TOML, a short key, a misspelled section), the bot
keeps the users it has, logs the reason and sends it to each admin, e.g.
`users.toml not reloaded: [users]: 'a1b2c3' is not a full public key`. Fix the
file and it is picked up on the next check. A deleted file is reported the
same way. At startup, an invalid file stops the bot; a missing one only
warns, and is picked up once created.

To use another file or interval, add to `config.toml`:

```toml
[directory]
file = "/etc/mesh-contingency/users.toml"   # relative paths are relative to config.toml
reload_seconds = 5                          # 0 = only on reload or SIGHUP
```

Users and admins used to be in `config.toml`; the bot now stops with a message
if they are still there.

### Contacts

By default a MeshCore radio stores every node whose advert it hears, so
repeaters, room servers and sensors can fill its contact table and block new
people from messaging the bot. With a `[contacts]` section the bot takes
over instead:

```toml
[contacts]
auto_add = ["chat"]   # any of: chat, repeater, room, sensor; [] adds none
```

At startup it puts the radio in manual-add mode (`manual_add_contacts`, a
setting stored on the radio that also affects the phone app), then adds each
newly heard node whose type is listed, logging e.g.
`+ contact a1b2c3d4e5f6 Alice (chat)`. Nodes heard while the bot isn't
running are picked up when they advert again. Without a `[contacts]` section
the radio's setting is left as it is.

A new node whose key prefix matches a user or admin but whose full key
differs is never added, since it could pass itself off as them. The admins get
one alert per node, even with `notify_admins = false`:
`Blocked a1b2c3d4e5f6 Alice: posing as Alice (same key prefix, different key)`.
If it really is them on a new device, put the new key in the users file and
the node is added when it next adverts.

Each admin also gets a direct message for every contact added, e.g.
`New contact: Alice (a1b2c3d4e5f6, chat)`, so they know who has appeared and
can ask for the person's full public key to add them to the users file. Set
`notify_admins = false` under `[contacts]` to turn this off. Admins must
themselves be contacts to receive it. Notices are sent in the background, one
message at a time, so they never hold up replies to incoming messages.

So a burst of adverts can't fill the contact table or swamp the admins:

```toml
[contacts]
max_new_per_hour = 20   # new nodes added per hour; users and admins always are
notices_per_hour = 5    # new-contact notices sent one by one per hour
```

Nodes over the cap aren't added (they are when they advert again later). After
the hour's notices are used up, the rest are counted and the admins get one
summary when the hour is up, e.g. `In the last hour: 14 more new contact(s);
3 new node(s) not added (over max_new_per_hour)`. These are the defaults; 0
means no limit.

The radio holds only so many contacts (`health` shows e.g. `contacts 41/350`).
`contacts` lists them, and admins manage one with `contact`:

- `contact remove <name or key>` takes it off the radio. It asks first, and
  says if it's a user or an admin: they can't be messaged until they advert
  again. A node of a type `auto_add` takes comes back by itself when it next
  adverts.
- `contact path <name or key>` resets the route the radio keeps to it, for one
  whose messages stopped getting through: the next message floods to find a
  new one.

A contact is named by its name, the start of its name, or 4 or more hex digits
of its key; when several match, give more of the key. The web console's Radio
page lists the contacts with a **Remove** and a **Reset path** button for each.

### Radio settings

`radio` shows an admin the radio's own settings, e.g. `radio: Ridgeview Relay;
910.525 MHz BW62.5 SF7 CR5 (Canada, USA); TX 22/22 dBm; position 38.84620,
-91.94880 (in adverts); clock right; firmware Heltec V3 v1.9.1`, with the
MeshCore presets that use the same values and how far the radio's clock is
off.

Over the mesh it only shows them. Every change is made from the
[web console](#web-console), on the node's own computer, which reaches the
radio over USB: a setting that cuts the node off from the mesh can't cut off
the console, so it can always be set back. Its Radio page has a **Settings**
tab, or type them on the command line there:

| From the console | Does |
|---|---|
| `radio name <name>` | Rename the node (up to 31 bytes); others see it after the next advert |
| `radio power <dBm>` | Set the TX power, 1 to the radio's maximum |
| `radio position <lat> <lon>` | Set the position the radio has (whether adverts carry it is the radio's own setting) |
| `radio clock` | Set the radio's clock from the computer's (the bot also does at each start, if it's off) |
| `radio reboot` | Reboot the radio (it asks first); the bot restarts with it |
| `radio freq <preset or MHz kHz SF CR>` | Set the frequency, bandwidth, spreading factor and coding rate (it asks first), then reboot |

`radio freq` takes one of [MeshCore's regional presets](https://api.meshcore.nz/api/v1/config)
by name (`radio freq usa`, `radio freq "EU/UK (Narrow)"`), or the four values,
e.g. `radio freq 910.525 62.5 7 5`. Every radio on a mesh must use the same
frequency, bandwidth and spreading factor, so its confirmation says what the
radio is on now and how to go back; the Settings tab also has you type the
node's name first. A preset's suggested path hash size is a network setting
it leaves alone. After a reboot or a new frequency the bot stops with an
error, so the [service](#as-a-service) starts it again (30 s later; if the
radio is still starting, 30 s after that): open the console again then, as it
has a new key. The [node watch](#node-watch) doesn't announce that restart.

### Email

Mail is sent by running `mail -s <subject> <addresses...>`, so `mail` must be
configured to deliver through an SMTP server. With s-nail and Gmail (using an
[app password](https://support.google.com/accounts/answer/185833)), for
example, in `~/.mailrc`:

```
set mta=smtps://you%40gmail.com:APP_PASSWORD@smtp.gmail.com:465
set from="you@gmail.com"
```

Keep SMTP credentials in your mail client's config, never in this repository.
Test with `echo test | mail -s test you@example.com` before relying on it.

An email that can't be sent isn't kept to try again later: the sender is told
straight away, with the cause in a few words, e.g.
`qm: not sent, no internet at the node; try again later`. The causes are no
internet, the email login refused, an address refused, timed out, `mail` not
installed, or another email error; the sender's reply never includes `mail`'s
own output, which can hold the node's address. The full reason goes to the
console, `health` shows `last email failed 5m ago: <cause>`, and a failed
email doesn't count toward the daily limits. s-nail would normally save the
unsent message to `~/dead.letter`, unsealed; the bot runs `mail` with
`DEAD=/dev/null` so it doesn't.

## Running

```sh
.venv/bin/mesh-contingency              # auto-detects the serial port
.venv/bin/mesh-contingency -p /dev/ttyUSB0 -c /path/to/config.toml
```

With the venv activated (`source .venv/bin/activate`), plain
`mesh-contingency` works, as does `python -m mesh_contingency`.

Options: `-p/--port`, `-b/--baud` (default 115200), `-c/--config`
(default `config.toml` in the project folder), `--debug` for library logging.

### As a service

To start the bot at boot, restart it after a crash and keep its output in the
journal, run it as a systemd user service with
[`deploy/mesh-contingency.service`](deploy/mesh-contingency.service). Step-by-step
setup, day-to-day commands and troubleshooting are in the wiki:
[Running as a systemd Service on Linux](https://github.com/DJSnitker/mesh-contingency/wiki/Running-as-a-systemd-Service-on-Linux).
In short, from the project folder:

```sh
mkdir -p ~/.config/systemd/user
sed "s|/path/to/mesh-contingency|$PWD|g" deploy/mesh-contingency.service \
    > ~/.config/systemd/user/mesh-contingency.service
loginctl enable-linger "$USER"     # start at boot without logging in
systemctl --user daemon-reload
systemctl --user enable --now mesh-contingency
journalctl --user -u mesh-contingency -f
```

`systemctl stop` (SIGTERM) shuts the bot down cleanly. If the radio is lost
and the library's reconnects fail, the bot logs `Lost the radio (...)` and
exits with an error, so systemd starts it again (every 30 s) until the radio
is back.

At startup it checks the config and loads the enabled commands before
connecting, prints which commands are available at each permission level, and
warns about any that are disabled or failed to load. It then watches the
users file (see [Users file](#users-file)). Each command has a time
limit (60 s unless its config says otherwise). Each reply is
retried until the radio reports an ack, and the console notes whether it was
delivered.

### While it runs

Two radios can only exchange direct messages once each has the other as a
contact, which happens when each hears the other's advert. A new user's radio
learns the node from its advert, and the node adds theirs when it hears it
(see [Contacts](#contacts)). This can all be done without stopping the bot:

- **In the bot's terminal**, type:
  - `advert`: a zero-hop advert, heard by radios in direct range;
  - `advert flood`: a flood advert, repeated across the mesh;
  - `contacts [name]`: the radio's contacts (or those whose name or key starts
    with `name`), to check that the other radio has been added;
  - `help`: this list.
- **From another shell**, when the bot has no terminal: `kill -USR1 <pid>`
  sends a flood advert (as a service:
  `systemctl --user kill --kill-whom=main -s USR1 mesh-contingency`).
- **By itself**, from `config.toml`:

  ```toml
  [advert]
  every_hours = 12     # advert this often (default 0, never)
  flood = true         # flood or zero-hop (default true)
  at_startup = false   # also advert every time the bot starts (default false)
  ```

  The next advert goes out 12 hours after the last one of that kind, whether
  the schedule sent it or someone did by hand (from the terminal,
  `kill -USR1` or the `advert` command). The time is kept in `adverts.json`
  next to `config.toml`, so a restart doesn't flood the mesh again: the bot
  adverts at startup only if the last one was 12 or more hours ago.

So for a new user: ask them to advert from their app, send `advert flood` (or
`advert` if they're in range), and check with `contacts <their name>`.

### Web console

The node can also be run from a browser on its own computer, without a radio
in hand and without 133-character replies. It's off by default. To turn it
on:

1. Install its extra, and build the app (needs [Node.js](#requirements); a
   wheel built with `python -m build` already has the app inside):
   ```sh
   .venv/bin/pip install -e ".[console]"
   cd console && npm ci && npm run build && cd ..
   ```
2. In `config.toml`:
   ```toml
   [console]
   enabled = true
   port = 8737          # the default
   ```
3. Restart the bot. It prints the link, with a key, and writes it to
   `console.url` next to `config.toml` (readable only by you):
   ```
   Web console: http://127.0.0.1:8737/?key=... (also in /home/you/mesh-contingency/console.url)
   ```
4. Open it in a browser on that computer, with one command:
   ```sh
   .venv/bin/mesh-contingency-console      # -c path/to/config.toml if it isn't the default
   ```
   It reads `console.url`, checks the bot answers that link, and opens it in
   your browser. If it can't, it says why: the console is off, the bot isn't
   running, or the link is old. (Or open the link from `console.url`
   yourself.) The key moves into a cookie and leaves the address bar, so
   after that `http://127.0.0.1:8737/` is enough, until the bot restarts:
   each start makes a new key, and the page then says to open the console
   again.

Its pages, in the order of the menu (the Dashboard first, then A–Z):

- **Dashboard:** users, join requests, check-ins and messages waiting, the
  weather alerts out now for the counties in `[alerts]` (each with its
  counties, in orange; it links to Area Weather), the node watch, the last
  backup, `health`, and a live log of what the bot prints (as in the
  journal, with private commands' text left out).
- **Area Weather:** a card for each county in `[alerts] counties`, alert or
  not: the latest reading from the nearest NWS station, the next three
  forecast periods, and any alert out for it. The bot asks the NWS every 15
  min and keeps the last report, so a card says how old it is, and why if
  it couldn't be updated (no internet, say). Without counties in `[alerts]`
  there's nothing to show. Below the cards: **Post alert test** (`testalert`;
  the page asks first, since it goes out on the air) and **Look up counties
  again** (`alertmap`).
- **Check-ins:** who has sent `ok`, newest first, and who hasn't, with
  **Clear check-ins**.
- **History:** what admins have done, newest first, with a filter.
- **Inbox:** who has messages waiting, from whom, read or not, sealed or not.
  Never what they say: that stays for the recipient, over the radio.
- **Radio:** **Advert**, **Flood advert** and **Back up now**; the radio's
  [settings](#radio-settings), with a form for each change, and the
  frequency set apart, on one tab; its contacts (with a filter): each one's type, whether it's a user or an
  admin, its path and when it was last heard, with **Reset path** and
  **Remove** ([`contact`](#contacts)), on another; on the third, the radio's
  channel slots in use: each one's name, whether it's the usual Public
  channel, a hashtag channel or a private one, and what the bot posts there
  (`alert`, `comm`, the automatic alerts, the weekly test), but never its
  key. A channel opens to what the radio heard on it since the bot started,
  newest first, with who sent it, the hops and the signal, and what this
  node posted there. The bot keeps the last 200 of each channel while the
  console is on, in memory only: a restart forgets them, and none are
  written to disk. It takes no commands from channels.
- **Send:** post to `#contingency-wx` or `#contingency-comm` (with a count
  against the one-message limit), or leave a message in a user's inbox.
- **Users:** every user and admin with their settings, last seen, check-in
  and messages, with **Whois**, **Edit emails** (`setemail`: the qm
  address and the emailall group), **Reset passphrase** and **Remove**; the
  join requests waiting, with **Approve** and **Deny**; and **Reload users
  file** (`reload`), after editing it.

Everything it does runs the same commands as over the radio, as an admin
called `console`: the same checks, rate limits and confirmations (`remove`
asks first, and the page shows a **Confirm** button), and `history` records
them `by console`. A message left from the Send page is `from console`.
Commands turned off in `config.toml` aren't offered. It doesn't edit
`config.toml`, and it can't read sealed messages.

It answers only on `127.0.0.1` (`host = "localhost"` is the only other
choice), so other computers can't reach it; see
[Security notes](#security-notes). If the port is taken, the bot says
`Warning: web console not started: port 8737 can't be used (...)` and runs
without it; set another `port`. Without a build it says `Note: the web
console's app isn't built, so only its API answers`. After a `git pull` that
changes `console/`, build again and restart the bot. Working on the app
itself: see [`console/README.md`](console/README.md).

### Phone app

*In progress:* a phone app for users, in `app/`, that talks Bluetooth to
the user's own MeshCore radio and reaches the node by ordinary direct
messages, so the bot needs nothing new and its permissions, limits and
sealing all apply. Android first; the plan is in
[`docs/plans/mobile-app.md`](docs/plans/mobile-app.md). So far it connects
to the radio (its name, battery and firmware), finds the node, joins, and
has the mailbox, check-ins, email, weather and verse, and chat;
the Radio screen says what it will do. The replies it reads are pinned
in `tests/fixtures/app_replies.json`: change a reply there and in the app
together. Building it, running it on an emulator and installing it on a
phone: see [`app/README.md`](app/README.md).

## Testing

```sh
.venv/bin/python -m unittest
.venv/bin/pip install -e ".[dev]" && .venv/bin/ruff check .   # lint
```

The web console's tests need aiohttp (`pip install -e ".[console]"`) and are
skipped without it; its app has its own (`npm test` in `console/`), and so
does the phone app (`npm test` in `app/`).

The tests use only the standard library. Network calls, the `mail` command
and the radio are all faked (see `mesh_contingency/testing.py`), so they run
offline and without a device. `tests/test_bot.py` drives the real
`mesh_contingency.bot.main()` with simulated direct messages.

## Contributing

Pull requests run [CI](.github/workflows/ci.yml) on GitHub, and it must pass:

- **Tests** on Python 3.11, 3.12, 3.13 and 3.14.
- **Lint** with [ruff](https://docs.astral.sh/ruff/); the rules are in `pyproject.toml`.
- **Package**: builds the web console's app and the wheel, checks the Bible
  data, the app and the command registrations are inside it, installs it
  with `examples/mesh-dice`, and runs a verse lookup and a dice roll through
  the installed commands.
- **Web console app**: formatting (Prettier), unit tests (Vitest) and the
  build, in `console/`.
- **Phone app**: the same, in `app/`.
- **Android build**: the phone app's debug APK, kept for 14 days as the
  run's `mesh-contingency-debug-apk` artifact.

The PR template has a short checklist. Never include real data (your
`config.toml` or `users.toml`, email addresses, node keys) in code, tests or issues.
Dependabot opens weekly PRs to update GitHub Actions, Python dependencies, the
web console's and the phone app's npm packages, and the phone app's Gradle
dependencies.

## Project layout

```
mesh_contingency/
  api.py              the interface for commands: Command, Context, CommandResult, reply limits
  registry.py         finding commands (entry points), checking [commands], loading them
  directory.py        the users file: checking it and reloading it while running
  state.py            senders seen since startup; status.json and mailbox.json
  watch.py            the node watch: problems with the node, sent to the admins
  backup.py           backups of the bot's data, on a schedule and with the backup command
  sealing.py          sealing mailbox messages to a passphrase
  limits.py           rate limits and email caps
  names.py            checking radios' names at join: control characters, profanity
  output.py           escaping terminal control codes in everything printed
  console.py          commands typed into the bot's terminal, scheduled adverts
  bot.py              entry point: radio connection, permissions, dispatch, replies
  running.py          running a command and turning its result into reply messages
  testing.py          fake radio and make_context() for testing commands
  contacts.py         auto-adding new contacts by node type
  weather.py          api.weather.gov / zipcode lookups (data only)
  alerts.py           the alert channel; the automatic weather alerts and the weekly test
  area_weather.py     the weather now in each watched county, for the console's Area Weather page
  web/                the web console: [console] settings, server.py (key, cookie and
                      host checks; serving the app), api.py (the JSON API), launch.py
                      (mesh-contingency-console), static/ (the build)
  bible/
    __init__.py       reference parsing and verse lookup
    bsb.json.gz       the bundled Berean Standard Bible
    build.py          rebuilds bsb.json.gz
    votd.py           verse-of-the-day list
  commands/           built-in commands, one module each
    help.py, wx.py, verse.py, advert.py, reload.py, roster.py, contacts.py, health.py, history.py
    status.py         ok, status, clearstatus and checkins
    mailbox.py        msg, inbox, clearinbox and setpass
    alert.py          an admin's message to the alert channel
    alertmap.py       looking up the watched counties' NWS codes again
    testalert.py      posting the alert test now
    comm.py           an admin's message to the communications channel
    join.py           join, approve and deny
    settings.py       setqm, addgroup, cleargroup and setemail
    users.py          users, whois, remove, resetpass, whoami and leave
    mail.py           the shared email sending and address checks
    qm.py, emailall.py, email.py
console/              the web console's Angular app (see console/README.md)
app/                  the phone app: Angular and Capacitor, android/ its Android project
                      (see app/README.md)
examples/mesh-dice/   an example third-party command package
.github/              CI workflow, Dependabot, PR and issue templates
pyproject.toml        package metadata, the mesh-contingency command and built-in command registrations
config.example.toml   example configuration
users.example.toml    example users file
deploy/
  mesh-contingency.service  systemd user unit (see "As a service")
scripts/
  demo_console.py     the web console on made-up data, for screenshots (see console/README.md)
docs/
  branding/           the logo: lockups (light and dark), mark, app icons, favicon
  plans/              design plans and what was decided
tests/                unit tests (python -m unittest)
```

## Writing a command

A command is a Python class or function. It can live in its own package,
installed next to the bot, so you never edit this project.
`examples/mesh-dice` is a complete example.

### As a function

```python
from mesh_contingency.api import CommandError, command

@command(args="[NdS]", summary="Roll dice, e.g. 2d6")
def roll(text, sender, ctx):
    ...
    return f"{sender.name} rolled {total}"
```

The function gets the text after the command name, the `Sender` (`name` and
`public_key`, the full 64-hex key, or `None` if the sender couldn't be
identified) and the `Context`. It returns the reply text.
It can be `async def`; a plain `def` runs in a worker thread so it can't stall
the radio.

### As a class

```python
from mesh_contingency.api import Command, CommandError, CommandResult

class TideCommand(Command):
    args = "<station>"
    summary = "Today's tides"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.default = ctx.options.get("station")

    async def execute(self, text, sender):
        ...
        return CommandResult(console=full_report, reply=short_text)
```

Use a class when the command keeps state or needs setup. Setup that needs the
radio goes in `async def start(self)`, which the bot calls once after
connecting and before handling messages; it may return a line to print.

Set `private = True` on the class when what senders write or get back must
stay off the console (messages, passphrases). The bot then prints only the
command name and sender, not the text, error or reply. Keep the `console` of
your `CommandResult` free of that text too.

For something that can't be undone, `Confirmations` from `mesh_contingency.api`
asks first: `if not self.confirmations.confirmed(sender.public_key, what):`
reply with what would happen; the same request again within 5 minutes
confirms it. Return that question as `CommandResult(..., asks=True)`, so the
[web console](#web-console) shows a **Confirm** button.

The web console runs admin and public commands as the admin `console`. Set
`own = True` on a command that acts on the sender's own records (as `join`
and `ok` do), which the console has none of, so it isn't offered there; and
`sends = True` on a user command that only leaves something for someone else
(as `msg` does), so it is.

### What a command gets and returns

`ctx` (a `Context`) holds:
- `name`: the name the command answers to
- `options`: the extra keys from its config entry
- `users`: each user's `[users.<key>]` settings from the users file, by public key
- `admins`: the admins' public keys
- `directory`: the users file itself

`users` and `admins` change when the users file is reloaded, so read them
when the command runs instead of keeping a copy from `__init__`.
- `radio`: the connected `meshcore.MeshCore`
- `commands`: every loaded command
- `state`: shared by every command: `seen` (who has messaged the node) and
  `store("<file>.json")`, a JSON file next to `config.toml` that survives restarts
- `name_of(sender)`: the sender's name from the users file, or as advertised
- `allowed(command, sender)`

A command returns reply text, a list of messages, a `CommandResult(console=...,
reply=...)` or `None` for no reply. The bot enforces the mesh limits for every
command:
- text is split into numbered messages;
- each reply is capped at 8 messages, and each message at 133 characters;
- each command has a time limit.

To fail, raise `CommandError("...")` with a short message to send back. Any
other exception is logged and answered with `<name>: failed`, so error details
never leak onto the mesh.

### Registering it

In your package's `pyproject.toml`, the name on the left is the command name:

```toml
[project.entry-points."mesh_contingency.commands"]
roll = "mesh_dice:roll"
flip = "mesh_dice:FlipCommand"
```

Install it into the bot's environment (`.venv/bin/pip install ./mesh-dice`
or from PyPI) and add an entry for it under `[commands]` in `config.toml`.
Without installing, `handler = "module:attr"` in that entry works too, as long
as the module is importable (e.g. on `PYTHONPATH`).

The built-in commands are registered the same way, in this project's
`pyproject.toml`. If two installed packages offer the same command name, the
bot stops at startup; pick one with `handler`.

### Testing it

```python
from mesh_contingency.api import Sender
from mesh_contingency.testing import FakeMeshCore, make_context

cmd = TideCommand(make_context("tide", options={"station": "8724580"}, radio=FakeMeshCore()))
result = await cmd.execute("", Sender("Dana", "d0" * 32))
```

## Security notes

- Commands never pass mesh text to a shell. Email goes to `mail` as argument
  and stdin; addresses typed into `email` are strictly validated, and
  control characters are stripped from subjects.
- Anyone in the users file can email any address with `email` while it is
  a `user` command; only add people you trust.
- Think before making a command `public`: anyone on the mesh who can reach
  the node could run it. The email commands and `advert` act outside the bot.
- Installed commands run inside the bot with all of its access (radio,
  network, `mail`, files). Permissions only decide who on the mesh may
  trigger them. Install only command packages you trust. Disabled commands
  are never imported.
- A flood `advert` is sent to the whole mesh; use it sparingly.
- `ok` and `status` are public: anyone who can reach the node can read
  anyone's check-in by name. Don't put anything in a status you wouldn't
  say on an open channel. `alert` and the automatic weather alerts post to a
  public channel.
- `join` is public, so anyone can ask; nothing changes until an admin
  approves. Approving gives the person every `user` command, including
  `email` to any address.
- Addresses set over the mesh must be plain `user@domain.tld`, starting with
  a letter or digit; anything else is refused, as with `email`.
- Everything the bot prints (to the terminal or the journal) has terminal
  control sequences escaped, e.g. `\x1b[2J`, since message text and node
  names come from anyone on the mesh: a message can't clear the screen,
  recolour it, set the window title, overwrite earlier lines or reverse how
  text displays.
- `status.json`, `mailbox.json` and `requests.json` hold node keys and what
  people wrote; they are created readable only by you. Messages to users who
  set a passphrase are sealed in `mailbox.json`, but someone with a copy of it
  and the users file can try guessing passphrases offline; scrypt makes each
  guess slow, and the 12-character minimum keeps the number of guesses large.
  Passphrases reach the bot inside encrypted direct messages, and the bot
  sees each one briefly while handling `setpass` or `inbox`.
- The users file decides who is an admin, and changes to it apply while the
  bot runs. Keep it writable only by you (`chmod 600 users.toml`). Admin
  rights can't be given over the mesh.
- At startup, and whenever the users file reloads, the bot warns if
  `config.toml`, `users.toml` or the mail settings (`~/.mailrc`, or the file
  `$MAILRC` names) can be read or changed by other accounts, with the
  `chmod 600` command that fixes it. `~/.mailrc` usually holds an SMTP
  password.
- `meshcore` is held to the tested minor version, and CI's GitHub Actions are
  pinned to commit SHAs; Dependabot proposes updates to both.
- Rate limits and email caps (see [Limits](#limits)) are per sender and kept
  in memory; restarting the bot resets them.
- The [web console](#web-console) listens only on `127.0.0.1`, never the
  network. Every request needs the key the bot makes at each start (in the
  link, then an `HttpOnly`, `SameSite=Strict` cookie), so other accounts on
  the computer can't use it; `console.url` is readable only by you. Only
  requests addressed to `127.0.0.1:<port>` or `localhost:<port>` are
  answered, and anything that changes something needs the console's own
  `Origin`, so web pages in your browser can't use it either, even with DNS
  rebinding. Every response forbids loading anything from elsewhere and
  being framed. Sealed text, sealing keys and message text never leave the
  node this way. Anyone who can use your account on that computer can use
  the console as an admin, as they could edit `users.toml`.

## License

Proprietary. © 2026 Doug Snitker, all rights reserved; see [LICENSE](LICENSE).
