# Plan: the web console, laid out and working like the phone app

Status: in progress: PRs 1–4 (#87–#90) merged; PR 5, the Contacts section, open · Requested 2026-10-25

## Goal

The phone app (item 16, [mobile-app.md](mobile-app.md)) got its screens
right through a phone test: grouped by what a person is doing (Mailbox,
Check-ins, Chat, Weather, Bible), tabs inside a screen, folding sections,
spinners wherever it waits, a centered column on a wide screen. The web
console ([web-console.md](web-console.md)) is older and grouped by the
bot's data (Inbox, Send, History...). Bring the console up to the app: the
same grouping and look, and what the app can do that the console can't,
while keeping what only admins need (Dashboard, Users, History, the radio's
settings).

## Decisions (2026-10-25)

- **The app's look, the side menu kept.** On a wide screen the console keeps
  its side menu (the rail): an admin works at the node's computer. Its pages
  are regrouped the way the app's are, and use the app's panels, folding
  sections (`details.accordion`), tabs and spinners. At phone width the rail
  becomes the app's bottom tab bar.
- **New in the console:**
  - **Chat, channels:** each channel as a chat thread, read and post, on
    any of the node's channels (today only `#contingency-wx` and
    `#contingency-comm`, through `alert` and `comm`).
  - ~~**Chat, direct messages:** the node messages a contact on the radio and
    sees the reply; a Contacts tab to start one.~~ Dropped (2026-10-25,
    below).
  - **Weather:** favorite counties first, the rest under Show more, and the
    weather anywhere (`wx`).
  - **Bible and Check-ins:** look up a verse or the verse of the day; look
    up anyone's check-in. (Not checking in as the console: `ok` records the
    sender's own check-in, which the console, not a person, can't run.)
- **Still this computer only** (`127.0.0.1`, the key in the link): nothing
  here changes who can reach the console.

**Dropped: direct messages (2026-10-25).** Built in #92 and taken out
before merging. A MeshCore direct message is only text, so the bot can't
tell a chat reply from a command except by its first word: "ok on my way"
would check the person in, "help is coming" would get the help text. The
best use of direct messages to this node is commands; people chat through
`msg` and the channels. So **Chat is renamed Contacts**, with two tabs,
Channels and the radio's contacts, and every direct message to the node is
a command, as before.

## The pages

The rail, in order (the app's names where they're the same thing):

| Page | Today | Becomes |
|---|---|---|
| **Dashboard** | the node at a glance, health, live log | the same, in the app's panels |
| **Mailbox** | Inbox (who has messages waiting); Send's *Leave a message* | both, on one page: the waiting messages per user, and *Leave a message* below |
| **Check-ins** | the roll call | the roll call, plus *Look up a check-in* (`status`) |
| **Contacts** (was to be Chat) | Radio's Contacts and Channels tabs; Send's channel posting | two tabs: **Channels** (every channel as a thread, with a box to post, and what each is and what the bot posts there, with unread counts) and **Contacts** (Radio's contacts tab moved here: each one's type, user or admin, path and when heard, with a filter, **Reset path** and **Remove**) |
| **Weather** | Area Weather: a card per county, weather alerts | the cards, with favorites (kept in the browser) shown first and the rest under Show more; *Weather anywhere* (`wx`); the alerts panel as now |
| **Bible** | (none) | the verse of the day and *Look up a verse* (`verse`), as in the app |
| **Radio** | Advertise, Backup, the radio's settings, contacts and channels | the radio itself only: Advertise, Backup and its settings. Its contacts and channels move up to Contacts (decided 2026-10-25: an admin managing a contact is usually about to message it, or just heard from it). Unlike the phone app, which keeps contacts on Radio too |
| **Users** | users and join requests | the same, in the app's panels |
| **History** | what admins have done | the same |

**Send goes away:** posting moves to Contacts → Channels, and leaving a message to
Mailbox. At phone width the bottom bar holds Dashboard, Mailbox, Contacts,
Weather and **More** (the other pages, as a list).

Unread counts (Contacts on the rail, each channel) are per browser: the newest
message seen is kept in `localStorage`, as the app keeps its on the phone.

## How it works

**Pages built on commands** (Check-ins, Bible, Weather anywhere, Leave a
message) use `/api/run`, as the console's pages do now: the console runs the
command as the admin `console`, with the same checks, and `history` records
it. No bot changes.

**Channels:** the bot already keeps each channel's newest 200 messages in
memory (`channel_log.py`), and adds its own posts. New:
`POST /api/channels/{slot}/messages` sends to that slot (`send_chan_msg`,
as `alert` does), held to what fits after the node's name, recorded in
`history` as `by console` and added to the log. `alert` and `comm` stay the
commands for the two hashtag channels over the radio.

**Direct messages** (dropped, as above; kept here for the record) were to be the new part of the bot:

- **A log of the console's conversations**, in memory only, like the
  channel log (newest 200 per contact; a restart forgets them; nothing
  written to disk): only the console's messages to a contact, each with the
  time and delivered or not, and the contact's replies to them (below).
  **Commands sent to the node, and the node's answers, are never kept**, as
  the bot's log keeps only their names (decided 2026-10-25, for privacy:
  they're the sender's business, not the console's).
- **Sending:** `POST /api/contacts/{key}/messages` sends a direct message
  from the node (`send_dm`, retried until acknowledged, the same lock as
  replies), at most the mesh's 140 characters, and says delivered or not.
  It's recorded in `history`.
- **Replies come back to the console:** a message that isn't a command, from
  a contact the console messaged in the last 24 hours, is a chat reply: kept
  in their conversation, shown in Chat, and **not** answered with `unknown
  command` or `unrecognized user or function`. Anything that is a command
  runs as now, even from that contact. A contact the console hasn't
  messaged is answered as today, and nothing of it is kept.
- **Live:** the Chat pages ask for new messages every few seconds, as the
  channel threads do now; the rail's Chat count is updated the same way.

## PRs

1. **This plan** and its roadmap item.
2. **Layout:** the rail regrouped (Mailbox, Chat, Bible added; Send gone),
   the app's panels, folding sections and spinners on every page, the phone
   width bottom bar with More; Mailbox (Inbox and *Leave a message*);
   Check-ins' *Look up*; the Bible page. Chat starts as the
   Channels tab, read only, moved from Radio.
3. **Weather:** favorites, Show more, *Weather anywhere*.
4. **Chat, channels:** posting on any channel (the new API), threads with
   unread counts, the Channels tab's box to post; Radio's Channels tab
   removed, since Chat's list then shows all it did.
5. **The Contacts section:** Chat renamed Contacts, with the Channels tab
   and the Contacts tab moved from Radio (its details, filter, Reset path
   and Remove); Radio's Contacts tab removed. (The direct messages built
   for this PR were taken out: see *Dropped* above.)
6. **Docs:** the README's "Web console", the wiki's Admin Guide ("Use the
   web console"), the demo's screenshots, the changelog.

Each PR checked in the demo console (`scripts/demo_console.py`) at desktop and
phone width, and the console's tests kept up.

## Open questions

- **Who replied:** a reply to the console lands in the console's chat, but an
  admin over the radio doesn't see it. Tell admins too, or leave it to the
  console? Leave it to the console for now.
- **Keeping conversations across restarts:** in memory only to start, like
  channel messages. Writing them to disk would keep other people's private
  messages on the node's computer; decide once the console is used for chat.
