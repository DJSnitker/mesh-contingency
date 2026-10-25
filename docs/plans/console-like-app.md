# Plan: the web console, laid out and working like the phone app

Status: planned · Requested 2026-10-25

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
  - **Chat, direct messages:** the node messages a contact on the radio and
    sees the reply; a Contacts tab to start one.
  - **Weather:** favorite counties first, the rest under Show more, and the
    weather anywhere (`wx`).
  - **Bible and Check-ins:** look up a verse or the verse of the day; check
    in as the console and look up anyone's check-in.
- **Still this computer only** (`127.0.0.1`, the key in the link): nothing
  here changes who can reach the console.

## The pages

The rail, in order (the app's names where they're the same thing):

| Page | Today | Becomes |
|---|---|---|
| **Dashboard** | the node at a glance, health, live log | the same, in the app's panels |
| **Mailbox** | Inbox (who has messages waiting); Send's *Leave a message* | both, on one page: the waiting messages per user, and *Leave a message* below |
| **Check-ins** | the roll call | the roll call, plus *Check in* (as the console, with the app's quick choices) and *Look up a check-in* (`status`) |
| **Chat** | Radio's Channels tab (read only); Send's channel posting | three tabs as in the app: **Chat** (direct messages, newest first, unread counts), **Channels** (every channel as a thread, with a box to post), **Contacts** (start a chat, with Find) |
| **Weather** | Area Weather: a card per county, weather alerts | the cards, with favorites (kept in the browser) shown first and the rest under Show more; *Weather anywhere* (`wx`); the alerts panel as now |
| **Bible** | (none) | the verse of the day and *Look up a verse* (`verse`), as in the app |
| **Radio** | Advertise, Backup, the radio's settings, contacts and channels | the same; its Channels tab lists the slots, and each opens its thread in Chat |
| **Users** | users and join requests | the same, in the app's panels |
| **History** | what admins have done | the same |

**Send goes away:** posting moves to Chat → Channels, and leaving a message to
Mailbox. At phone width the bottom bar holds Dashboard, Mailbox, Chat,
Weather and **More** (the other pages, as a list).

Unread counts (Chat on the rail, each thread) are per browser: the newest
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

**Direct messages** are the new part of the bot:

- **A log of each contact's conversation with the node**, in memory only,
  like the channel log (newest 200 per contact; a restart forgets them;
  nothing written to disk): what they sent, what the node answered, and the
  console's messages, each with the time and, for the node's, delivered or
  not. A **private command's text** (`inbox` with a passphrase, `msg`,
  `setpass`...) is never kept: only its name, as the bot's own log prints it.
- **Sending:** `POST /api/contacts/{key}/messages` sends a direct message
  from the node (`send_dm`, retried until acknowledged, the same lock as
  replies), at most the mesh's 140 characters, and says delivered or not.
  It's recorded in `history`.
- **Replies come back to the console:** a message that isn't a command, from
  a contact the console messaged in the last 24 hours, is a chat reply: kept
  in their conversation, shown in Chat, and **not** answered with `unknown
  command` or `unrecognized user or function`. Anything that is a command
  runs as now, even from that contact. A contact the console hasn't
  messaged is answered as today, and the message still shows in their
  conversation.
- **Live:** the Chat pages ask for new messages every few seconds, as the
  channel threads do now; the rail's Chat count is updated the same way.

## PRs

1. **This plan** and its roadmap item.
2. **Layout:** the rail regrouped (Mailbox, Chat, Bible added; Send gone),
   the app's panels, folding sections and spinners on every page, the phone
   width bottom bar with More; Mailbox (Inbox and *Leave a message*);
   Check-ins' *Check in* and *Look up*; the Bible page. Chat starts as the
   Channels tab, read only, moved from Radio.
3. **Weather:** favorites, Show more, *Weather anywhere*.
4. **Chat, channels:** posting on any channel (the new API), threads with
   unread counts, the Channels tab's box to post.
5. **Chat, direct messages:** the bot's conversation log, sending, replies
   routed to the console; the Chat and Contacts tabs.
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
