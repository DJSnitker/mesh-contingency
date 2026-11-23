# Set Up a Node

How to turn a Linux computer and a MeshCore radio into a node, and make
yourself its first admin. It takes about 20 minutes. Everything is typed in a
terminal **as your normal account** (not root); the commands work in bash,
zsh and fish.

- [What you need](#what-you-need)
- [1. Install it](#1-install-it)
- [2. Let your account use the radio](#2-let-your-account-use-the-radio)
- [3. Make yourself the first admin](#3-make-yourself-the-first-admin)
- [4. Settle the node's settings](#4-settle-the-nodes-settings)
- [5. Start it](#5-start-it)
- [6. Meet the node from your radio](#6-meet-the-node-from-your-radio)
- [Next steps](#next-steps)
- [Updating](#updating)
- [If something goes wrong](#if-something-goes-wrong)
- [Running as a systemd service](Running-as-a-systemd-Service-on-Linux): the service in detail (its log, day-to-day commands, troubleshooting)

---

## What you need

- **A Linux computer that uses systemd**, on all the time: Debian, Ubuntu,
  Raspberry Pi OS, Fedora, Arch and their relatives all do.
- **git and Python 3.11 or newer.** The installer checks, and if one is
  missing it prints the command to install it.
- **The node's radio:** a MeshCore radio with the *companion* firmware for
  USB, plugged into the computer.
- **Your own radio**, with the MeshCore app, to be the admin's radio. It
  stays separate from the node's.
- Optional: an email account the node can send from, for `qm`, `emailall`
  and `email`.

## 1. Install it

```sh
curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
```

To read the script before it runs, download it first:

```sh
curl -fsSLO https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh
less install.sh
bash install.sh
```

It puts the latest release in **`~/mesh-contingency`** (the *node folder*),
installs the bot into a `.venv` there, makes `config.toml` and `users.toml`
from the examples, and sets up the
[systemd service](Running-as-a-systemd-Service-on-Linux) without starting it.
It never uses sudo. It ends with a numbered list of what's left, like:

```
Done: mesh-contingency v0.12.0 in /home/sam/mesh-contingency
1. Edit /home/sam/mesh-contingency/config.toml and /home/sam/mesh-contingency/users.toml
2. Let your user reach the radio's USB port, then log out and back in:
     sudo usermod -aG dialout "$USER"
3. For the email commands, install mail and set it up to send:
     sudo apt-get install s-nail
4. Plug in the radio and start the bot:
     systemctl --user start mesh-contingency
     journalctl --user -u mesh-contingency -f
```

The rest of this page walks through that list.

**Options** go after `bash -s --`, for example
`curl -fsSL … | bash -s -- --console`:

| Option | Does |
|---|---|
| `--console` | Also installs and builds the [web console](Admin-Guide#use-the-web-console). Needs Node.js 22.22+ or 24.15+ with npm. |
| `--dir DIR` | Installs into `DIR` instead of `~/mesh-contingency`. |
| `--ref main` | Follows the `main` branch instead of releases (for testing). |
| `--no-service` | Skips the systemd service; run the bot by hand. |

If it stops with `Missing: …`, run the install command it prints, then run
the installer again.

## 2. Let your account use the radio

The radio is a serial device (`/dev/ttyUSB0` or `/dev/ttyACM0`) that only one
group may open: usually `dialout` (`uucp` on Arch). With the radio plugged in,
the installer tries the port itself and says what's in the way, if anything:

| The installer says | What to do |
|---|---|
| `Radio port /dev/ttyUSB0: you can use it.` | Nothing: skip to step 3. |
| `Let your user open /dev/ttyUSB0 (group dialout)` | Run the `sudo usermod -aG <group> "$USER"` it shows, then log out and back in. |
| `You're in dialout, which can open /dev/ttyUSB0, but not yet in this login` | Log out and back in (or reboot). |
| `Your user can't open /dev/ttyUSB0 (...), and no group can` | Something changed the port's permissions, usually a udev rule. `ls -l /dev/ttyUSB0` shows them; a normal port looks like `crw-rw---- root dialout`. |
| `Let your user reach the radio's USB port` (no port named) | No radio was plugged in, so it checked your groups only. Join the group it shows, plug the radio in, and run the installer again to check. |

Joining a group by hand:

```sh
sudo usermod -aG dialout "$USER"     # Debian, Ubuntu, Raspberry Pi OS, Fedora
sudo usermod -aG uucp "$USER"        # Arch
```

The new group only applies to new logins, so **log out and back in** (or
reboot). `id` should then list it. Running the installer again is safe (it
leaves your files alone) and checks the port again.

## 3. Make yourself the first admin

Admins are listed by their radio's **full public key**, 64 hex characters.
The short 12-character prefix isn't accepted, since another radio could copy
it.

1. **Find your radio's public key.** In the MeshCore app on your own radio,
   open its settings and copy its public key. (Once the node is running and
   has heard your radio, the web console's Contacts page shows it too: hover
   over the short key.)
2. **Open `users.toml`** in the node folder:
   ```sh
   nano ~/mesh-contingency/users.toml
   ```
3. **Put your key in `[admin] keys`**, in place of the example key, and
   **delete the two example users** (`Alice T-Deck`, `Bob's Heltec`). To
   also use the user commands yourself (`msg`, `inbox`, `qm` and the rest),
   add a user section with the same key: an admin isn't automatically a user.
   ```toml
   [admin]
   keys = ["<your 64-character key>"]

   [users.<your 64-character key>]
   name = "Sam T-Deck"          # your radio's name; the bot keeps it up to date
   qm = "sam@example.com"       # optional: where your qm messages are emailed
   ```
   Another admin later is one more key in the list:
   `keys = ["<key 1>", "<key 2>"]`.

`[admin] keys` can only be changed by editing this file, never over the mesh,
so a lost radio can't make more admins. Everyone else joins over the mesh with
`join` and an admin's `approve`; you don't need to type their keys. The
`users.toml` comments explain the rest.

## 4. Settle the node's settings

`config.toml` works as installed. These are the settings worth looking at
before the first start (`nano ~/mesh-contingency/config.toml`):

| Section | Set | Why |
|---|---|---|
| `[advert]` | `every_hours = 12` | New radios find the node by hearing its advert. The example never sends one by itself. |
| `[alerts]` | `counties = ["Taylor, TX", "Jones, TX"]` | Your counties ("Name, ST"), for automatic weather alerts and `area`. Empty turns them off. |
| `[alert_test]` | `weekly = "Wednesday 17:00"` | A weekly test of the alert channel. Empty for never. |
| `[backup]` | `to = "/mnt/usb/MeshContingencyBackups"` | Backups each day. Another disk is best: one on the same disk is lost with it. |
| `[console]` | `enabled = true` | The [web console](Admin-Guide#use-the-web-console), if you installed with `--console`. |
| `[commands]` | `qm = { permission = "disabled" }` | Only if the node won't send email: do the same for `emailall` and `email`. |

Every setting is explained in the file's comments and in the
[README's Configuration](https://github.com/DJSnitker/mesh-contingency#configuration).
`config.toml` is read when the bot starts, so after changing it later run
`systemctl --user restart mesh-contingency`. `users.toml` is different: the bot
picks up changes by itself within a few seconds.

**Email**, if you keep it: the node sends with the `mail` command, which needs
an SMTP account. Install s-nail (`sudo apt-get install s-nail`, or
`sudo pacman -S s-nail`), set it up as in the
[README's Email](https://github.com/DJSnitker/mesh-contingency#email), then test:

```sh
echo test | mail -s test you@example.com
```

## 5. Start it

With the radio plugged in:

```sh
systemctl --user start mesh-contingency
journalctl --user -u mesh-contingency -f
```

The log ends with `Listening for direct messages`. Look above it for lines
starting with `Warning:`; the
[service page](Running-as-a-systemd-Service-on-Linux#step-6-check-its-working)
says what each means. Press **Ctrl+C** to stop watching; the bot keeps running.
The installer already turned the service on at boot.

## 6. Meet the node from your radio

Two radios can only message each other once each has heard the other's
advert.

1. **Advert from your radio** in the MeshCore app. The node adds your radio
   to its contacts (the log shows `+ contact … (chat)`).
2. **Advert the node**, from its computer, across the mesh:
   ```sh
   systemctl --user kill --kill-whom=main -s USR1 mesh-contingency
   ```
   Your app now lists the node.
3. **Send the node `health`** as a direct message. An admin gets the node's
   state back:
   ```
   health
   → health: up 3m; radio Hilltop Node (Heltec V3 v1.18.0); …; users 1 (1 admin)
   ```
   `unrecognized user or function` instead means the node doesn't see your
   key as an admin's: check it in `users.toml` (all 64 characters, no
   spaces).
4. **Name the node.** `radio` shows the radio's name and settings. Changes,
   the name included, are made from the web console on the node's computer
   (Radio page, or `radio name Hilltop Node`), so install with `--console`
   to make them. See
   [Change the radio's settings](Admin-Guide#change-the-radios-settings).

From now on you'll also get a direct message when a new radio appears or the
node has a problem.

## Next steps

- [Add your first users](Admin-Guide#add-a-new-user).
- [Test a reboot](Running-as-a-systemd-Service-on-Linux#step-7-test-a-reboot):
  the node should come back by itself.
- Send people the [User Guide](User-Guide) and the [User App Guide](User-App-Guide).
- The [Admin Guide](Admin-Guide) covers running the node day to day.

## Updating

Run the installer again:

```sh
curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
```

It moves to the newest release, reinstalls, and restarts the service if it's
running. It never overwrites `config.toml`, `users.toml` or the node's saved
data. Read the
[changelog](https://github.com/DJSnitker/mesh-contingency/blob/main/CHANGELOG.md)
first: a release that changes the config says what to do under "Upgrading".
New commands start turned off; copy their lines from `config.example.toml`
into your `config.toml` to turn them on.

## If something goes wrong

| What you see | What to do |
|---|---|
| `Missing: git` or `Missing: python` | Run the install command it prints, then the installer again. |
| `Python can't make a virtual environment` | Run the command it prints (`python3-venv` on Debian and Ubuntu). |
| `… has changes to its files; commit or undo them first` | Files in the node folder were edited (not your config, which git ignores). `git -C ~/mesh-contingency status` lists them; `git -C ~/mesh-contingency restore .` undoes them. |
| `No systemd user session here` | You're probably in `su` or a container. Log in as the user directly (or over SSH) and run the installer again. |
| `Couldn't turn on lingering` | Run `sudo loginctl enable-linger "$USER"` so the node starts at boot without anyone logged in. |
| The log says it can't open `/dev/ttyUSB0` | [Step 2](#2-let-your-account-use-the-radio): join the group, then log out and back in. |
| `health` gets no answer | The node hasn't heard your advert, or yours hasn't heard its: [step 6](#6-meet-the-node-from-your-radio). |

More fixes are on the [service page](Running-as-a-systemd-Service-on-Linux#troubleshooting)
and in the [Admin Guide](Admin-Guide#when-something-doesnt-work).
