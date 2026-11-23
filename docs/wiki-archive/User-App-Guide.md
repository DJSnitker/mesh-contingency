# User App Guide

The **Mesh Contingency app** does what the [User Guide](User-Guide)'s
commands do, from screens instead of typing. It talks to **your own MeshCore
radio** (over Bluetooth, or a USB cable on a computer), and your radio sends
the node the same direct messages you'd type. Nothing goes over the internet:
the app works wherever your radio reaches the node through the mesh.

It runs on Android phones, and on Windows, Mac and Linux computers (64-bit
Intel/AMD; there's no ARM Linux build, so not on a Raspberry Pi). There's no
iPhone version yet.

- [Install it](#install-it)
- [Connect your radio and pick the node](#connect-your-radio-and-pick-the-node)
- [Join the node](#join-the-node)
- [While the node answers](#while-the-node-answers)
- [Mailbox: read and leave messages](#mailbox-read-and-leave-messages)
- [Email](#email)
- [Check-ins](#check-ins)
- [Chat](#chat)
- [Weather](#weather)
- [Bible](#bible)
- [Radio: your radio's settings](#radio-your-radios-settings)
- [If something goes wrong](#if-something-goes-wrong)

The screenshots are from the app's demo, with made-up names.

---

## Install it

Download it from the **[latest release](https://github.com/DJSnitker/mesh-contingency/releases/latest)**.
Each file name starts with the version, for example
`mesh-contingency-0.12.0-win-x64.exe`:

| On | Download | Then |
|---|---|---|
| Android | `…-debug.apk` | Open it on the phone and allow installing it. (It's the only Android build for now; "debug" just means it isn't signed for an app store.) |
| Windows | `…-win-x64.exe` | Run it. Windows warns about an unknown publisher: **More info**, then **Run anyway**. |
| Mac (Apple silicon or Intel) | `…-mac-arm64.dmg` or `…-mac-x64.dmg` | Drag the app to Applications. The first time, open it, then allow it in **System Settings → Privacy & Security** (**Open Anyway**). |
| Linux | `…-linux-x86_64.AppImage` (any), `…-linux-amd64.deb` (Debian, Ubuntu) or `…-linux-x64.pacman` (Arch) | Install the package, or run the AppImage: see below. |

The warnings appear because the app isn't signed with a paid certificate.
To check a download, compare `sha256sum <file>` (on Windows,
`certutil -hashfile <file> SHA256`) with the SHA-256 the release page shows
next to it.
A new version installs over the old one and keeps your chats and settings.

On Linux:

```sh
# The package:
sudo apt install ./mesh-contingency-*-linux-amd64.deb        # Debian, Ubuntu
sudo pacman -U mesh-contingency-*-linux-x64.pacman           # Arch
# Or the AppImage, which needs FUSE 2:
sudo apt install libfuse2       # libfuse2t64 on Ubuntu 24.04 and later
sudo pacman -S fuse2            # Arch
chmod +x mesh-contingency-*.AppImage && ./mesh-contingency-*.AppImage
# (without FUSE 2, add --appimage-extract-and-run)
# For a radio on USB, join dialout (uucp on Arch), then log out and back in:
sudo usermod -aG dialout "$USER"
```

On a phone, Android asks for **Nearby devices** (on Android 11 and older,
**Location**), which it needs to find Bluetooth radios. The app asks for
nothing else.

Along the bottom are the app's seven tabs: **Mailbox**, **Check-ins**,
**Chat**, **Weather**, **Bible**, **Node** and **Radio**. The chip at the top
right shows your radio's name once it's connected; tap it to go to **Node**.

## Connect your radio and pick the node

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-node.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-node.png" alt="The Node screen: your radio, connected, and the node" width="260"></a>
</p>

Everything starts on the **Node** screen.

1. **Connect your radio.**
   - **Find my radio** connects over Bluetooth. Turn the radio on nearby and
     pick it from the list. The first time, it asks for the radio's Bluetooth
     PIN (shown on its screen, or `123456` if it has none).
   - **Connect over USB** (on a computer only) connects to a radio on a USB
     cable: pick its port from the list. On Linux, your user needs to be in
     the `dialout` group (`uucp` on Arch): see [Install it](#install-it).

   A radio takes one connection at a time: if the MeshCore app (or another
   copy of this one) is connected to it, disconnect that first.
2. **Pick the node** from your radio's contacts. It's listed once your radio
   has heard the node's advert. Not there? **Send an advert** so the node
   hears you, wait a minute, then **Refresh**.

The app remembers both. Next time it reconnects by itself; if it can't,
**Reconnect** tries again, and **Pick another** chooses a different radio.
Under **Your radio**: **Disconnect** lets go of it (for the MeshCore app, say),
and **Forget it** makes the app forget it. **Change node** picks another node.

## Join the node

Under the node's name, **Check** asks the node whether you're one of its
users (the `whoami` command), and says what it knows: whether you're a user,
how many messages wait for you, and whether you've set a passphrase.

Not a user yet? **Join** asks the node's admins to make you one, under your
radio's name, so set the name you want people to see first (on the
[Radio](#radio-your-radios-settings) tab). When an admin approves you, their
welcome shows under **From the node**, and the app checks again.

Anyone can check in, look up check-ins and get the weather and verses.
The Mailbox and Email need you to be a user.

## While the node answers

Each request goes to the node over the mesh, which can take a while. A line
above the screen's panels says where it's got to:

| What it says | What it means |
|---|---|
| Sending … (try 2) | Your radio is sending it. It tries up to three times. |
| … delivered; waiting for the answer | The node's radio has it. Over several hops the answer can take up to 3 minutes. |
| … wasn't delivered | The node's radio didn't acknowledge it. Is the node in range? Try again later. |
| No answer to … in 3 minutes | It arrived, but no answer came back. |

One request goes at a time: buttons that ask the node are grayed out until
the last one is answered.

## Mailbox: read and leave messages

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-mailbox.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-mailbox.png" alt="The Mailbox screen, a message opened with a passphrase" width="260"></a>
</p>

**Your messages:** **Open inbox** shows what other users have left for you.
If you've set a passphrase, type it in the box first; without it, sealed
messages show only who they're from. More than fit on one page? **Next
page**. Messages stay on the node until you clear them:
**Clear the ones read** deletes what you've been shown, and **Clear all**
deletes everything.

**Leave a message:** the user's name (as their radio shows it) and your
message, then **Leave it**. It waits on the node until they read it, even if
their radio is off. The count shows how much still fits in one message.

**Passphrase:** open it to set one. With a passphrase, new messages to you
are sealed: only your passphrase opens them, and the app never keeps it.
12 to 16 characters, no spaces, typed twice. **A forgotten passphrase can't
be recovered**, and the messages sealed with it are lost. If sealed messages
are waiting when you set a new one, it says so first: read them with the old
one, or **Set it, and delete them**. More about passphrases:
[Keep your messages private](User-Guide#keep-your-messages-private).

**Email** at the foot of the screen opens the Email screen.

## Email

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-email.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-email.png" alt="The Email screen" width="260"></a>
</p>

The node emails your message when it has the internet. Replies to it go
nowhere.

**Send an email:** pick who it goes to:
- **My preset contact**: one regular address, like a partner's (`qm`).
- **My group**: up to 10 addresses at once (`emailall`).
- **An address**: anyone; type the address (`email`).

Write the message, **Send**, then **Send it** to confirm: an email can't be
taken back. If the node can't send it (no internet there, say), it says so
and nothing is kept to send later; try again later. There's a daily limit
per person.

**Your addresses:** **Show them** shows your preset contact and group. Set the
preset contact, add addresses to the group one at a time, or
**Clear the group**. An admin can set them for you too.

## Check-ins

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-checkins.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-checkins.png" alt="The Check-ins screen: checked in, and a look-up" width="260"></a>
</p>

**Check in:** tap one of **I'm ok**, **Need help**, **Need medical**,
**Sheltering in place**, **Evacuating** or **No power**, or write your own
and tap **Check in**. It asks before sending: your check-in replaces your
last one, and **anyone can look it up**, so keep it to what you'd say on an
open channel.

**Look someone up:** a name, or the start of one, then **Look up**. Leave it
empty to see your own.

## Chat

<table>
<tr>
<td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-chat.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-chat.png" alt="Chat: the kept chats" width="220"></a><br><b>Chat</b></td>
<td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-chat-thread.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-chat-thread.png" alt="A chat with one contact" width="220"></a><br><b>A chat</b></td>
<td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-channels.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-channels.png" alt="Chat: Channels" width="220"></a><br><b>Channels</b></td>
<td align="center"><a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-contacts.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-contacts.png" alt="Chat: Contacts" width="220"></a><br><b>Contacts</b></td>
</tr>
</table>

Chat is for talking with other people's radios directly, like the MeshCore
app. It doesn't go through the node, so you don't need to be a user.

- **Chat** lists your conversations, newest first, with unread counts (also
  on the tab).
- **Channels** lists the channels set up on your radio. Add the node's
  `#contingency-wx` (weather alerts) and `#contingency-comm` (news) in the
  MeshCore app to see what the node posts.
- **Contacts** lists the radios yours has heard, with when and how far.
  Tap one to start a chat. With many, a **Find** box appears.

In a chat, write and **Send**. Under each of your messages:

| It says | Meaning |
|---|---|
| Sending… | Your radio is sending it. |
| Delivered | Their radio acknowledged it. |
| Not delivered | No acknowledgement after three tries; they may be out of range. |
| Sent | Posted to a channel (channels have no acknowledgement). |
| Couldn't send | Your radio wasn't connected, or refused it. |

Chats are kept on this phone or computer only, until you **Clear** one or
**Clear every chat**. The node isn't in the chats: its answers show on the
screen that asked.

## Weather

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-weather.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-weather.png" alt="The Weather screen: county cards, one with an alert" width="260"></a>
</p>

The node watches some counties for weather alerts. Weather lists them as
cards; **Get the weather** on a card asks the node for the weather there now,
with any alert first, in orange. **Update** asks again.

Tap the **star** on the counties you care about: they're shown first and
loaded each time you open Weather, with the rest under **Show more**.

**Another place:** a zipcode, or a county and state like `Taylor, TX`, then
**Look it up**. **Get the node's counties again** reloads the list if the
node's changes.

## Bible

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-bible.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-bible.png" alt="The Bible screen" width="260"></a>
</p>

**Verse of the day** loads when you open Bible, and is kept for the rest of
the day. **Look up a verse:** a reference like `John 3:16` or
`Psalm 23:1-4`, then **Look it up**. Verses are from the Berean Standard
Bible.

## Radio: your radio's settings

<p align="center">
  <a href="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-radio.png"><img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/app-radio.png" alt="The Radio screen" width="260"></a>
</p>

Radio is about **your** radio, not the node's.

- **Your radio:** its name, frequency, transmit power, position, clock,
  battery and firmware. If the clock is wrong, **Set the clock from the
  phone** (or computer).
- **Adverts:** an advert tells other radios yours is there, so they can
  message it. **Advert nearby** reaches radios in direct range;
  **Advert across the mesh** goes through repeaters too.
- **Settings:** **Rename** your radio (others see the new name after your
  next advert; the node picks it up next time it hears from you). **Set
  power** in dBm, up to the radio's limit. **Set position** by latitude and
  longitude, and **Share it in adverts** or stop sharing it.
- **Frequency:** every radio on a mesh uses the same settings, and a radio on
  others hears no one. Change it only when your mesh does: pick a preset
  (or **My own values**), **Set the frequency**, then **Set and restart**.
  It tells you what to set to go back.
- **Contacts:** every radio yours knows. **Reset path** when messages to one
  stopped getting through (your radio finds a new route), and **Remove** to
  drop one. Removing the node means the app can't reach it until your radio
  hears its next advert.

**Open-source licenses**, at the foot, lists the software the app is built on.

## If something goes wrong

| What you see | What to do |
|---|---|
| Your radio isn't in the list | Turn it on and bring it closer. Close the MeshCore app, or disconnect it there: a radio takes one connection at a time. |
| The PIN is refused | It's the radio's Bluetooth PIN: on its screen, or `123456`. On Android, forget the radio in Bluetooth settings and try again. |
| "Connect your radio and pick the node first" | Go to **Node** and do both. |
| The node isn't in your radio's contacts | **Send an advert**, wait a minute or two for the node's, then **Refresh**. |
| Wasn't delivered | The node's radio is out of reach. Try again later, or from somewhere higher. If it keeps happening, **Reset path** for the node on **Radio**. |
| **Check** gets no answer | The node answers someone who isn't a user only once every 5 minutes. Wait, or **Join**. |
| Mailbox or Email says you're not a user | **Join** on the **Node** screen, and wait for an admin. |
| Sealed messages won't open | Check the passphrase: it's case-sensitive. A forgotten one can't be recovered; see the [User Guide](User-Guide#keep-your-messages-private). |
| On Linux, no USB ports listed | Add your user to `dialout` (`uucp` on Arch), then log out and back in. |

Still stuck? Every screen sends one of the node's commands, so you can try the
same thing by typing it in the MeshCore app: see the [User Guide](User-Guide).
