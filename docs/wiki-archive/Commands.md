# Commands (A–Z)

Every command is sent as a **direct message** to the bot's node. The bot never
reads channels, so commands posted in a channel are ignored. A message is the
command name, then anything it needs, and names aren't case-sensitive:

```
wx 33101
```

In the usage lines, `<angle brackets>` mark something you must give and
`[square brackets]` something you can leave out. Don't type the brackets.

## Naming people

Everyone is known by **their radio's name**, exactly as their radio shows it,
spaces and punctuation included: `Ridge Base 1`, `Sam T-Deck`. To change your
name, rename your radio; the bot picks up the new name the next time it hears
from you. Nobody chooses a name with a command.

Where a command takes a `<name>`, type the name as it is, in any case:

```
msg sam t-deck the road north is open
```

If that picks the wrong person (another user's name is the start of a longer
one), or a name has odd punctuation, put it in **parentheses**, `(` and `)`.
Unlike the other brackets, you type these:

```
msg (Sam T-Deck) the road north is open
```

Every keyboard has them, including the small ones on mesh devices, which is why
a radio's name can't contain them. You can
always use the start of someone's key instead (4 or more characters, as
`users` and `whois` show it), and you'll be asked to if two people's radios
have the same name.

For how to get things done, see the **[User Guide](User-Guide)** and the
**[Admin Guide](Admin-Guide)**.

## Who can use what

| Level | Who |
|---|---|
| **Anyone** | Any node that can direct-message the bot |
| **Users** | People in the node's users file. Ask to join with `join`. |
| **Admins** | The node's operators |

The levels below are the defaults; the node's owner can change any of them in
`config.toml`. A command you can't use, or one that doesn't exist, gets
`unrecognized user or function` (at most once every 5 minutes). If you're a
user and mistype one, the bot suggests the nearest command you can use:
`unknown command inbx; did you mean inbox? help lists yours`. `help` lists
only the commands **you** can use.

## Quick reference

| Command | Usage | Who | What it does |
|---|---|---|---|
| [addgroup](#addgroup) | `addgroup <address>` | Users | Add an address to your emailall group; alone, list it |
| [advert](#advert) | `advert [flood]` | Admins | Make the radio advertise itself |
| [alert](#alert) | `alert <message>` | Admins | Post a message to the alert channel, `#contingency-wx` |
| [alertmap](#alertmap) | `alertmap [county, ST]` | Admins | Look up the NWS codes of the watched counties again |
| [approve](#approve) | `approve [name or key]` | Admins | Approve a join request; alone, list them |
| [area](#area) | `area [county, ST]` | Anyone | The weather now in the counties the node watches; alone, list them |
| [backup](#backup) | `backup` | Admins | Back up the bot's data now |
| [checkins](#checkins) | `checkins [page <n>]` | Admins | Roll call: everyone's check-in, or missing |
| [cleargroup](#cleargroup) | `cleargroup` | Users | Empty your emailall group |
| [clearinbox](#clearinbox) | `clearinbox [all]` | Users | Delete the messages you've read, or all of them |
| [clearstatus](#clearstatus) | `clearstatus` | Admins | Delete every check-in |
| [comm](#comm) | `comm <message>` | Admins | Post a message to the communications channel, `#contingency-comm` |
| [contact](#contact) | `contact remove <name or key>`, `contact path <name or key>` | Admins | Remove a contact from the radio (it asks first), or reset the path to it |
| [contacts](#contacts) | `contacts [name or key] [page]` | Admins | List the radio's contacts |
| [deny](#deny) | `deny <name or key>` | Admins | Turn down a join request |
| [email](#email) | `email <address> <message>` | Users | Email any address |
| [emailall](#emailall) | `emailall <message>` | Users | Email your group |
| [health](#health) | `health` | Admins | How the node is doing: radio, battery, users, messages, errors |
| [help](#help) | `help [command]` | Anyone | List your commands, or how to use one |
| [history](#history) | `history [page]` | Admins | What admins have done, newest first |
| [inbox](#inbox) | `inbox [passphrase] [page]` | Users | Read your messages |
| [join](#join) | `join` | Anyone | Ask to become a user, under your radio's name |
| [leave](#leave) | `leave` | Users | Stop being a user |
| [msg](#msg) | `msg <name> <message>` | Users | Leave a message for another user |
| [ok](#ok) | `ok [status]` | Anyone | Check in: tell others you're ok |
| [qm](#qm) | `qm <message>` | Users | Quick message: email your preset contact |
| [radio](#radio) | `radio` | Admins | Show the radio's settings; change them from the web console only |
| [reload](#reload) | `reload` | Admins | Re-read the users file now |
| [remove](#remove) | `remove <name or key>` | Admins | Remove a user and their messages |
| [resetpass](#resetpass) | `resetpass <name or key>` | Admins | Clear a user's forgotten passphrase |
| [roster](#roster) | `roster` | Admins | Who has messaged the node since it started |
| [setemail](#setemail) | `setemail <name or key> qm [address] group [address ...]` | Admins | Set a user's qm address and emailall group; a part with no address clears it |
| [setpass](#setpass) | `setpass <passphrase>` | Users | Seal your messages with a passphrase |
| [setqm](#setqm) | `setqm <address>` | Users | Set your qm address; alone, show it |
| [status](#status) | `status <name or key>` | Anyone | See someone's last check-in |
| [testalert](#testalert) | `testalert` | Admins | Post the test message to the alert channel now |
| [users](#users) | `users [page]` | Admins | List the users and what each has set |
| [verse](#verse) | `verse [book chapter:verse[-verse]]` | Anyone | A Bible verse, or the verse of the day |
| [whoami](#whoami) | `whoami` | Users | What the node knows about you |
| [whois](#whois) | `whois <name or key>` | Admins | What the node knows about a user |
| [wx](#wx) | `wx <zipcode>` or `wx <county, ST>` | Anyone | Weather and alerts for a US zipcode or county |

---

### addgroup

`addgroup <address>` · **Users**

Adds an address to the group `emailall` sends to (up to 10). On its own, lists
the group.

```
addgroup mom@example.com
→ addgroup: mom@example.com added (1 in the group)

addgroup
→ emailall: mom@example.com
```

Addresses must be plain `name@domain.tld`; anything else is refused.

### advert

`advert [flood]` · **Admins**

Makes the radio announce itself, so other radios add it as a contact. On its
own it's a zero-hop advert (radios in direct range); `flood` repeats it across
the whole mesh. Use `flood` sparingly: it uses airtime on every repeater.

```
advert
→ advert: zero-hop sent

advert flood
→ advert: flood sent
```

A flood advert sent this way counts toward the node's advert schedule, if it
has one. Admins at the node's computer can also advert without the mesh; see
[Admin Guide: from the node's computer](Admin-Guide#from-the-nodes-computer).

### alert

`alert <message>` · **Admins**

Posts the message, exactly as typed, to the public channel **#contingency-wx**.
It must fit in one channel message (133 characters, less the node's name);
a longer one is refused and nothing is posted.

```
alert Shelter open at First Baptist on 5th St
→ alert: posted to #contingency-wx
```

To see it, add the hashtag channel `#contingency-wx` in your MeshCore app.

The bot also posts new National Weather Service alerts there by itself for
the counties listed in `[alerts]` in `config.toml`, like
`Taylor, TX ALERT: Rip Current Statement | until Thu 8:00PM | Taylor`; see
[Warn people about the weather](Admin-Guide#warn-people-about-the-weather).

### alertmap

`alertmap [county, ST]` · **Admins**

The automatic alerts (`[alerts]` in `config.toml`) watch counties. The bot
looks up each county's NWS code once, keeps it, and then asks for every
county's alerts in one request each round. `alertmap` looks the codes up
again, for every watched county or just the one given (`alertmap Jones, TX`).
Counties that couldn't be looked up (for example with no internet at startup)
are retried by themselves every round.

```
alertmap
→ alertmap: 2 looked up: Taylor, Jones
```

With many counties the list takes as few messages as it needs, numbered
`(1/2)`, `(2/2)`. Any county that couldn't be looked up is listed after
`not looked up:` with the reason. The codes themselves are in the console.

### approve

`approve [name or key]` · **Admins**

On its own, lists the waiting join requests. With a name or the start of a key,
adds that person to the users file and sends them a welcome message.

```
approve
→ requests: Sam T-Deck (ffeeddccbbaa) 5m ago

approve (Sam T-Deck)
→ approve: Sam T-Deck added to users.toml
```

Admins get a direct message for each new request. Up to 20 can wait at once.

### area

`area [county, ST]` · **Anyone**

The weather right now in the counties the node watches for alerts. On its
own, `area` lists them. With one, it sends that county's latest report in one
message: any active alerts, then the temperature and sky, the wind (`G17`
means gusts of 17 mph), how old the reading is, and the next forecast period
with its chance of rain.

```
area
→ area: Taylor, TX; Jones, TX

area Taylor, TX
→ Taylor, TX ALERT: Wind Advisory | 66F, Cloudy | SSE10mph G17 | 26m ago | Today: 81F Mostly Cloudy 4%
```

The county can be just its name (`area taylor`) when no other watched county
has the same one. The node checks every county every 15 minutes, so the reply
comes at once; if the node has lost its internet, you still get the last
report, and its age tells you how old it is. A county the node doesn't watch
gets `area: Dallas, TX isn't a watched county; send area for the list`; for
anywhere else, use [wx](#wx).

The phone app's Weather tab shows a card for each county from `area`. The
node's owner turns it on with `area = { permission = "public" }` under
`[commands]` in `config.toml`; it needs counties listed under `[alerts]`.

### backup

`backup` · **Admins**

Copies the bot's data (`config.toml`, `users.toml`, the check-ins, mailbox,
history and other state files, and the users file's own backups) into a new
folder named for the time, in the backup folder set in `[backup]` in
`config.toml`.

```
backup
→ backup: 12 file(s) saved in ~/MeshContingencyBackups/20261022-091340; newest 7 kept
```

The bot also does this by itself once a day. If it can't (the backup disk
isn't plugged in, or is full), the reply says why, e.g.
`backup: failed, No such file or directory; see the console`. See
[Admin Guide: Back up the node's data](Admin-Guide#back-up-the-nodes-data).

### checkins

`checkins [page <n>]` · **Admins**

A roll call: every user, in name order, with their last check-in and how long ago,
or `missing` if they haven't checked in. Five users to a page, then how many
have checked in.

```
checkins
→ Roll Call:
  ✓ Alex Base: at the shelter on 5th st (2h ago)
  ✗ Sam T-Deck: missing
  1/2 checked in. Page 1/1.

checkins page 2
```

With more than one page, the last line adds `Use 'checkins page <n>' to see
other pages.` Clear old check-ins with `clearstatus` after an event, so the
next roll call starts fresh.

### cleargroup

`cleargroup` · **Users**

Removes every address from your `emailall` group.

```
cleargroup
→ cleargroup: removed 3 address(es)
```

### clearinbox

`clearinbox [all]` · **Users**

Deletes the messages `inbox` has shown you; any that arrived since, or that are
on a page you haven't opened, are kept. `clearinbox all` deletes every message,
unread and sealed ones too.

```
clearinbox
→ clearinbox: deleted 3 message(s); 1 new one(s) kept, see inbox

clearinbox all
→ clearinbox: deleted 4 message(s)
```

If you have a passphrase, plain `inbox` doesn't count as reading: open them with
`inbox <passphrase>` first, or use `clearinbox all`.

### clearstatus

`clearstatus` · **Admins**

Deletes every check-in.

```
clearstatus
→ clearstatus: cleared 4 statuses
```

### comm

`comm <message>` · **Admins**

Posts the message, exactly as typed, to the public channel
**#contingency-comm**, for news and updates that everyone should see at once.
It must fit in one channel message (133 characters, less the node's name); a
longer one is refused and nothing is posted.

```
comm Water distribution at the fire station until 4pm
→ comm: posted to #contingency-comm
```

The bot adds the channel to its radio when it starts. To see it, add the
hashtag channel `#contingency-comm` in your MeshCore app; anyone who has it
can post there from their own radio too. Weather alerts go to
**#contingency-wx** instead (see [alert](#alert)).

### contact

`contact remove <name or key>`, `contact path <name or key>` · **Admins**

Manages one of the radio's contacts, named by its name, the start of its name,
or 4 or more hex digits of its key. `remove` takes it off the radio: it asks
first, and says if it's a user or an admin, who can't be messaged until they
advert again. `path` resets the route the radio keeps to it, for one whose
messages stopped getting through: the next message floods to find a new one.

```
contact remove old relay
→ contact: this removes Old Relay (7c21e0a9b4d3) from the radio. Send it again within 5 min to confirm.

contact remove old relay
→ contact: Old Relay (7c21e0a9b4d3) removed from the radio

contact path sam
→ contact: path to Sam T-Deck (5a3e1c7b9d20) reset; the next message to it floods
```

### contacts

`contacts [name or key] [page]` · **Admins**

Lists the radio's contacts with the start of each key, marking users, admins and
nodes that aren't chat radios (repeaters, rooms, sensors). With a name or the
start of a key, lists only those that match. Long lists come in pages.

```
contacts
→ contacts (8): Hilltop-RPT 4f7d2b9e6c13 (repeater) Alex Base a1e2c3d4b5f6 (user) Sam T-Deck 5a3e1c7b9d20 (user) ...

contacts sam
→ contacts matching sam (1): Sam T-Deck 5a3e1c7b9d20 (user)

contacts 2
```

Use it to check that a new person's radio has been added before they try to
message the node.

### deny

`deny <name or key>` · **Admins**

Removes a join request. The person isn't told.

```
deny ffeeddccbbaa
→ deny: request from Sam T-Deck removed
```

### email

`email <address> <message>` · **Users**

Emails your message to any address.

```
email friend@example.com power is back on here
→ email: sent
```

The subject is "You have received a MeshCore message from: <your name>", and the
email says replies don't come back over the mesh. Each email command counts
toward a daily limit set by the node; see [Limits](#limits).

If the node can't send it, nothing is kept to try later; the reply says why,
and you can send it again:

```
email friend@example.com power is back on here
→ email: not sent, no internet at the node; try again later
```

The other reasons: `the node's email login was refused; tell an admin`, `an
address was refused; check the address`, `email timed out; try again later`,
`email isn't set up on the node; tell an admin` and `email error at the node;
tell an admin`. The same goes for `qm` and `emailall`. A message that wasn't
sent doesn't count toward the daily limit.

### emailall

`emailall <message>` · **Users**

Emails your message to everyone in your group (build it with `addgroup`), as
one email with every address in the To line.

```
emailall roads closed, staying put tonight
→ emailall: sent
```

### health

`health` · **Admins**

How the node is doing, in a few messages:

```
health
→ health: up 5h 20m; radio Hilltop Node (Heltec V3 v1.18.0); radio up 2d 4h; battery 4.17V; contacts 8/350; users 2 (1 admin)
→ join requests 0; inbox 3 message(s) for 2 user(s); check-ins 1; since start 14 message(s) in, 17 out (1 undelivered); errors none
→ emails 24h 2/200 address(es); auto alerts 2 counties, checked 4m ago; last flood advert 2h ago; users.toml loaded 5h ago
```

| Part | Meaning |
|---|---|
| `up` | How long the bot has been running |
| `radio` | The node's name, and the radio's model and firmware |
| `radio up` | How long the radio has been on; restarting the bot doesn't reset it, so shorter than `up` means the radio itself restarted |
| `battery` | The radio's battery voltage (about 4.2 V full, 3.3 V nearly empty) |
| `contacts` | Contacts on the radio, and how many it can hold |
| `users`, `join requests`, `inbox`, `check-ins` | People in the users file, requests waiting, messages waiting and for how many people, saved check-ins |
| `since start` | Direct messages received, and replies and notices sent, since the bot started; `undelivered` means no acknowledgement came back |
| `errors` | Commands that failed or timed out since the bot started, and the last one |
| `emails 24h` | Addresses emailed in the last 24 hours, against the node's daily cap |
| `last backup` | When the bot last backed up its data; `no backup yet`, or `backup failing:` and why |
| `last email failed` | Only after an email couldn't be sent: when, and why (`no internet at the node`, `the node's email login was refused`...) |
| `auto alerts` | Only if `[alerts]` watches counties: how many, and when the NWS was last checked; `last check failed` or `not looked up:` if something couldn't be reached |
| `next alert test` | Only if `[alert_test]` sets `weekly`: when the next weekly test goes out |
| `watch` | `no problems`, or the problems the node watch has found (`battery low`, `email failing`...); see [Admin Guide: Get told about problems](Admin-Guide#get-told-about-problems) |
| `last flood advert` | When the node last flood-adverted |
| `users.toml` | When the users file was last loaded, or `NOT reloaded` and why, if the last edit had a mistake |

Anything the radio doesn't report (older firmware, or a radio that's busy) is
left out.

### help

`help [command]` · **Anyone**

Lists the commands you can use, or shows how to use one.

```
help
→ commands: help, wx, verse, ok, status, join. Send help <command> for usage

help wx
→ wx <zipcode | county, ST> - Weather, precipitation and alerts for a US zipcode or county
```


### history

`history [page]` · **Admins**

What admins have done, newest first, with who did it and when:
`approve`, `deny`, `remove`, `resetpass`, `setemail`, `clearstatus`, `alert`, `comm` and `backup`, users
who `leave`, radios that changed their name (shown as by `radio`), and the
bot's own daily backups (as by `auto`). The newest 200 are kept, across restarts.

```
history
→ history (3): 5m ago Doug: approved Sam T-Deck (5a3e1c7b9d20); 2h ago radio: Al (a1e2c3d4b5f6) is now Alex Base; 1d ago Alex Base: left the users (a1e2c3d4b5f6)
```

Long histories come in pages: `history 2`, `history 3` and so on.

### inbox

`inbox [passphrase] [page]` · **Users**

Shows your messages, oldest first, with who sent each and when. They stay until
you clear them, so you can read them again if a reply is lost on the air. One
reply holds up to 8 messages; send `inbox 2` and so on for more.

```
inbox
→ Sam T-Deck 5m ago: water is out on the east side, we're ok
```

If you've set a passphrase with `setpass`, plain `inbox` only says who left
messages and when; add the passphrase to read them:

```
inbox
→ inbox: 2 message(s) from Sam T-Deck 5m ago, Alex Base just now. Send inbox <passphrase> to read.

inbox blue-canoe-42x
→ Sam T-Deck 5m ago: water is out on the east side, we're ok
→ Alex Base just now: on my way

inbox blue-canoe-42x 2
```

### join

`join` · **Anyone**

Asks the node's admins to make you a user, under your radio's name (see
[Naming people](#naming-people)).

```
join                  (from a radio named "Sam T-Deck")
→ join: request sent to the admins as Sam T-Deck
```

An approval brings a welcome message; you aren't told about a refusal. If you
rename your radio before then, send `join` again to update the request.

Some radio names can't be used: no name at all, one with parentheses or
control characters in it, or a profane one. Rename the radio, send an advert,
and send `join` again:

```
join                  (from a radio named "Big Ass")
→ join: your radio's name isn't allowed; change it on the radio and try again
```

A name typed after `join` is ignored, and the reply says so.

### leave

`leave` · **Users**

Takes you out of the users file and deletes your messages. It asks first; send
it again within 5 minutes to confirm.

```
leave
→ leave: this removes you from the users and deletes your 2 message(s). Send it again within 5 min to confirm.

leave
→ leave: you're no longer a user; send join to ask again.
```

### msg

`msg <name> <message>` · **Users**

Leaves a message for another user, named by their radio's name or by the start
of their key (4 or more characters; see [Naming people](#naming-people)). Up to
20 wait per person, for 30 days.

```
msg Alex Base water is out on the east side, we're ok
→ msg: saved for Alex Base (1 in their inbox)

msg (Alex Base) water is out on the east side, we're ok
→ msg: saved for Alex Base (2 in their inbox)
```

Alex gets a short notice, `inbox: new message from Sam T-Deck; send inbox to
read`, at most once every 10 minutes and never with the text.

### ok

`ok [status]` · **Anyone**

Checks in so others know how you are, replacing your last check-in. On its own
it saves "ok".

```
ok at the shelter on 5th st
→ ok: saved for Sam T-Deck
```

**Anyone** can read check-ins with `status`, so don't include anything private.

### qm

`qm <message>` · **Users**

A **quick message**: emails your message to your preset contact (set it with
`setqm`). It used to be called `quickim`.

```
qm made it home safe, phone is dead
→ qm: sent
```

### radio

`radio` · **Admins**

Shows the radio's own settings: its name, frequency, bandwidth, spreading
factor and coding rate (with the MeshCore presets that use them), TX power,
position, how far its clock is off, and its firmware. Over the mesh it only
shows them; changing them (name, power, position, clock, reboot, frequency)
is done from the web console (on the node's computer, or as a console user
from another one): see
[Change the radio's settings](Admin-Guide#change-the-radios-settings).

```
radio
→ radio: Hilltop Base; 910.525 MHz BW62.5 SF7 CR5 (Canada, USA); TX 22/22 dBm; no position; clock right; firmware Heltec V3 v1.9.1
```

### reload

`reload` · **Admins**

Re-reads the users file straight away and says what changed. The bot also checks
it by itself every few seconds.

```
reload
→ reload: added Sam T-Deck; changed Alex Base
```

### remove

`remove <name or key>` · **Admins**

Takes a user out of the users file and deletes their messages. It asks first;
send it again within 5 minutes to confirm. Admin rights stay until `[admin] keys`
is edited by hand.

```
remove sam t-deck
→ remove: this removes Sam T-Deck (5a3e1c7b9d20) and their 1 message(s). Send it again within 5 min to confirm.

remove sam t-deck
→ remove: Sam T-Deck removed, 1 message(s) deleted
```

### resetpass

`resetpass <name or key>` · **Admins**

For a forgotten passphrase: clears the user's passphrase and deletes the
messages sealed with it, and tells the user. If sealed messages would be lost,
it asks first; send it again within 5 minutes to confirm.

```
resetpass (Alex Base)
→ resetpass: this clears Alex Base's passphrase and deletes 2 sealed message(s). Send it again within 5 min to confirm.

resetpass (Alex Base)
→ resetpass: Alex Base's passphrase cleared, 2 sealed message(s) deleted
```

### roster

`roster` · **Admins**

The node names (as their radios advertise them) of everyone who has messaged the
bot since it last started, most recent first. One the bot couldn't identify
shows as the start of its key.

```
roster
→ roster since Oct 20 08:47 (3): Sam T-Deck, Alex Base, ffeeddccbbaa
```

### setemail

`setemail <name or key> qm [address] group [address ...]` · **Admins**

Sets a user's `qm` address and their `emailall` group (up to 10 addresses) for
them. Give either part alone, or both; a part with no address clears it. The
group is replaced, not added to. The user is told what changed (*An admin
changed your email addresses: ...*), and it's recorded in `history`.

```
setemail (Sam T-Deck) qm partner@example.com group mom@example.com dad@example.com
→ setemail: Sam T-Deck's qm partner@example.com; emailall mom@example.com, dad@example.com

setemail (Sam T-Deck) qm
→ setemail: Sam T-Deck's qm cleared
```

The web console's **Users** page does the same with **Edit emails**.

### setpass

`setpass <passphrase>` · **Users**

Seals every new message left for you, so they can't be read from the node's
files; read them with `inbox <passphrase>`. Passphrases are 12 to 16 characters
with no spaces. **A forgotten passphrase can't be recovered**, and the messages
sealed with it are lost (an admin can clear it with `resetpass`).

```
setpass blue-canoe-42x
→ setpass: passphrase set; new messages to you will be sealed.
→ A forgotten passphrase can't be recovered, and messages sealed with it are lost.
```

Changing it while sealed messages are waiting warns that they'll be deleted and
asks you to send the same `setpass` again within 5 minutes.

### setqm

`setqm <address>` · **Users**

Sets the one address `qm` sends to. On its own, shows it.

```
setqm partner@example.com
→ qm now sends to partner@example.com

setqm
→ qm: partner@example.com
```

### status

`status <name or key>` · **Anyone**

Shows someone's last check-in and how long ago it was. Search by name (whole or
part, plain or in parentheses) or by the first 4 or more characters of their key. On
its own, shows your own.

```
status sam
→ Sam T-Deck: at the shelter on 5th st (2h ago)
```

### testalert

`testalert` · **Admins**

Posts the test message to the alert channel (**#contingency-wx**) now, so
people can check they receive it. The message, and a weekly day and time to
post it by itself, are set in `[alert_test]` in `config.toml`; see
[Test the alert channel every week](Admin-Guide#test-the-alert-channel-every-week).

```
testalert
→ testalert: posted to #contingency-wx; next weekly test Wed 5:00PM CDT
```

The channel shows the message, then the counties `[alerts]` watches (without
their states), in as few messages as fit:

```
TEST: this is a test of the #contingency-wx alert channel. No action needed.
(1/2) Counties watched for alerts: Taylor, Brown, Callahan, Coleman, Comanche, Eastland, Fisher, Haskell
(2/2) Jones, Kent, Knox, Mitchell, Nolan, Runnels, Scurry, Shackelford, Stephens, Stonewall, Throckmorton
```

### users

`users [page]` · **Admins**

Every user with the start of their key and what they have set: `admin`, `pass`
(a passphrase), `qm`, `emailall`.

```
users
→ users (2): Alex Base a1e2c3d4b5f6 (admin, qm) Sam T-Deck 5a3e1c7b9d20 (pass, qm, emailall)
```

### verse

`verse [book chapter:verse[-verse]]` · **Anyone**

A verse or short passage from the Berean Standard Bible; on its own, the verse
of the day. Works without internet.

```
verse
verse john 3:16
verse ps 23:1-3
```

Passages that would need more than 8 messages are refused; ask for fewer verses.

### whoami

`whoami` · **Users**

What the node knows about you: name, key, passphrase or not, your settings and
messages waiting.

```
whoami
→ Sam T-Deck (5a3e1c7b9d20); passphrase set; qm partner@example.com; emailall 3 address(es); 1 message(s), 1 unread
```

### whois

`whois <name or key>` · **Admins**

The same as `whoami`, for any user. Give the whole radio name (or the start of
the key): `whois alex` doesn't find `Alex Base`.

```
whois alex base
→ Alex Base (a1e2c3d4b5f6); admin; no passphrase; qm alex@example.com; no messages
```

### wx

`wx <zipcode | county, ST>` · **Anyone**

Current conditions, the chance of rain and any active National Weather Service
alerts for a US zipcode or county: alerts first, then rain, then temperature
and wind (`G18` means gusts of 18 mph).

```
wx 33101
→ 33101 ALERT: Rip Current Statement | Mostly Cloudy, 20% precip 6h | 82F E14mph G18
```

A county is written as its name and state (`wx Taylor, TX`,
`wx taylor county tx`) or as its NWS code (`wx TXC441`). The conditions are
from the station nearest the county's middle, and the alerts are the ones
issued for the county:

```
wx Taylor, TX
→ Taylor, TX Clear, 0% precip 6h | 81F S11mph
```

---

## Limits

- One mesh message holds about 133 characters. Longer replies arrive as numbered
  parts, `(1/2) …`, at most 8 per reply.
- **How often:** each person may use each command only so often (by default 10
  an hour for commands anyone can use, 30 an hour for user commands, no limit
  for admins). Past that, one reply says when to try again, e.g.
  `wx: limit reached, try again in 23 min`, and later tries get no reply.
- **Email:** each person may send a limited number of emails a day across
  `qm`, `emailall` and `email`, e.g.
  `email: you've reached your daily email limit (10); try again later`.
- A command that takes more than 60 seconds gets `<command>: timed out`; an
  error gets a short reply such as `wx: failed` or `usage: wx <zipcode | county, ST>`; an
  email that couldn't be sent says why (see [email](#email)).
