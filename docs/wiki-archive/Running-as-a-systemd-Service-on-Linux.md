# Running as a systemd Service on Linux

Part of **[Set Up a Node](Set-Up-a-Node)**.

Run by hand, the bot stops when you close its terminal, log out or reboot. As a
**systemd user service** it starts when the computer boots, restarts itself
after a crash or a lost radio, and keeps a log you can read at any time, with
nobody logged in.

Nothing is copied or moved. systemd runs the same program you start by hand
(`.venv/bin/mesh-contingency` in the project folder), as your own account, so
it uses the same `config.toml`, `users.toml`, saved messages and `~/.mailrc`.
All it needs is a short text file (a *unit*) saying how to start it, which is
in the project as
[`deploy/mesh-contingency.service`](https://github.com/DJSnitker/mesh-contingency/blob/main/deploy/mesh-contingency.service).

**Installed with the [one-command installer](Set-Up-a-Node)?** It has
already done steps 3 to 5 except starting the service: start it with
`systemctl --user start mesh-contingency`, then carry on from
[step 6](#step-6-check-its-working). The rest of this page (the log,
troubleshooting) applies as it is.

These steps take about 10 minutes. Commands are typed in a terminal **as your
normal account**; only step 3 might ask for your password. They work in bash,
zsh and fish.

**Contents**

- [Before you start](#before-you-start)
- [Step 1: Check the bot runs by hand](#step-1-check-the-bot-runs-by-hand)
- [Step 2: Check your account can use the radio](#step-2-check-your-account-can-use-the-radio)
- [Step 3: Let your services run without you logged in](#step-3-let-your-services-run-without-you-logged-in)
- [Step 4: Install the unit file](#step-4-install-the-unit-file)
- [Step 5: Start the service and turn it on at boot](#step-5-start-the-service-and-turn-it-on-at-boot)
- [Step 6: Check it's working](#step-6-check-its-working)
- [Step 7: Test a reboot](#step-7-test-a-reboot)
- [Day-to-day commands](#day-to-day-commands)
- [Reading the log](#reading-the-log)
- [Changing settings](#changing-settings)
- [Updating the bot](#updating-the-bot)
- [Moving or renaming the project folder](#moving-or-renaming-the-project-folder)
- [Running it by hand for testing](#running-it-by-hand-for-testing)
- [What happens when something goes wrong](#what-happens-when-something-goes-wrong)
- [Troubleshooting](#troubleshooting)
- [Removing the service](#removing-the-service)
- [What's in the unit file](#whats-in-the-unit-file)

---

## Before you start

You need:

- **A Linux computer that uses systemd.** Almost all current distributions do:
  Debian, Ubuntu, Raspberry Pi OS, Fedora, Arch and its relatives. Check with:
  ```sh
  systemctl --version
  ```
  It should print `systemd` and a version number (anything from 240 up is
  fine). If it says `command not found`, your system doesn't use systemd and
  this page doesn't apply.
- **The bot set up as in the
  [README's Setup](https://github.com/DJSnitker/mesh-contingency#setup)**: the
  project folder with its `.venv`, `config.toml` and `users.toml`.
- **The radio plugged in by USB.**
- **Email working**, if you use `qm`, `emailall` or `email`: the README's
  [Email](https://github.com/DJSnitker/mesh-contingency#email) section, tested
  with `echo test | mail -s test you@example.com`.
- **The project folder where it will stay.** The `.venv` and the service both
  record the folder's full path, so moving or renaming it later takes a few
  extra steps (see
  [Moving or renaming the project folder](#moving-or-renaming-the-project-folder)).
  Settle on the name and place now.
- **Your settings files private.** `config.toml` and `users.toml` hold email
  addresses and radio keys, and `~/.mailrc` usually holds your SMTP password.
  Make them readable only by you:
  ```sh
  chmod 600 config.toml users.toml ~/.mailrc
  stat -c '%a %n' config.toml users.toml ~/.mailrc
  ```
  Each line should start with `600`. The bot warns at every start if one
  isn't.

Throughout this page, the **project folder** is the folder you cloned, the one
holding `config.toml`, `users.toml` and `.venv`, e.g.
`/home/sam/mesh-contingency`.

## Step 1: Check the bot runs by hand

The service runs exactly what you run by hand, so make sure that works first.

1. Go to the project folder:
   ```sh
   cd ~/mesh-contingency        # wherever yours is
   ```
2. Start the bot:
   ```sh
   .venv/bin/mesh-contingency
   ```
3. Wait for `Listening for direct messages`. Send `help` to the node from
   another radio and check it answers.
4. Stop it with **Ctrl+C**. It prints `Stopped.`

Fix any problem now (see the README) before going on: a service that can't
start by hand can't start under systemd either.

> **Only one program can use the radio at a time.** Stop the bot, and close
> the MeshCore app or anything else connected to the radio by USB, before the
> next steps.

## Step 2: Check your account can use the radio

The radio appears as a serial device, usually `/dev/ttyUSB0` or
`/dev/ttyACM0`. If the bot ran in step 1, your account can already open it and
you can skip to step 3. Otherwise:

1. Find the device and the group that owns it:
   ```sh
   ls -l /dev/ttyUSB0 /dev/ttyACM0
   ```
   A line like `crw-rw---- 1 root uucp ... /dev/ttyUSB0` means members of the
   group **uucp** can use it. On Debian, Ubuntu and Raspberry Pi OS the group
   is usually **dialout**; on Arch and Fedora, **uucp** or **dialout**.
2. Check your groups:
   ```sh
   id
   ```
3. If that group isn't listed, add yourself (use the group name from step 1):
   ```sh
   sudo usermod -aG dialout "$USER"
   ```
4. **Log out and back in** (or reboot) for the new group to take effect, then
   run step 1 again.

## Step 3: Let your services run without you logged in

A user service normally runs only while you're logged in. *Lingering* lets it
start at boot and keep running when you log out:

```sh
loginctl enable-linger "$USER"
```

Some systems ask for your password here. Check it worked:

```sh
loginctl show-user "$USER" -p Linger
```

It should print `Linger=yes`. You only ever do this once.

## Step 4: Install the unit file

User units live in `~/.config/systemd/user/`. The copy in the project has a
placeholder, `/path/to/mesh-contingency`, which this command replaces with your
project folder as it copies the file.

1. Go to the project folder (the command uses the current folder):
   ```sh
   cd ~/mesh-contingency
   ```
2. Make the folder for user units, if it isn't there yet:
   ```sh
   mkdir -p ~/.config/systemd/user
   ```
3. Copy the unit, filling in the path:
   ```sh
   sed "s|/path/to/mesh-contingency|$PWD|g" deploy/mesh-contingency.service > ~/.config/systemd/user/mesh-contingency.service
   ```
4. Check the two paths point at your project folder:
   ```sh
   grep -E "^(WorkingDirectory|ExecStart)" ~/.config/systemd/user/mesh-contingency.service
   ```
   You should see something like:
   ```
   WorkingDirectory=/home/sam/mesh-contingency
   ExecStart=/home/sam/mesh-contingency/.venv/bin/mesh-contingency
   ```
5. Ask systemd to check the file:
   ```sh
   systemd-analyze --user verify ~/.config/systemd/user/mesh-contingency.service
   ```
   No output means it's fine.
6. Tell systemd about the new file:
   ```sh
   systemctl --user daemon-reload
   ```

**Using another config file or serial port?** Edit
`~/.config/systemd/user/mesh-contingency.service` and add the options to the
`ExecStart` line, e.g.
`ExecStart=/home/sam/mesh-contingency/.venv/bin/mesh-contingency -p /dev/ttyACM0 -c /etc/mesh-contingency/config.toml`,
then run `systemctl --user daemon-reload` again.

## Step 5: Start the service and turn it on at boot

```sh
systemctl --user enable --now mesh-contingency
```

`enable` makes it start at every boot; `--now` also starts it straight away.
It prints a line like
`Created symlink '.../default.target.wants/mesh-contingency.service' → ...`.

## Step 6: Check it's working

1. Look at its status:
   ```sh
   systemctl --user status mesh-contingency
   ```
   The important line is `Active: active (running)`. Below it are the last few
   lines the bot printed. Press **q** to get out if it opens a pager.
2. Watch the log as it happens:
   ```sh
   journalctl --user -u mesh-contingency -f
   ```
   You should see the usual startup lines, ending with
   `Listening for direct messages`. Press **Ctrl+C** to stop watching (the bot
   keeps running).
3. Look through the startup lines for any starting with `Warning:`, and deal
   with them now:

   | Warning | What to do |
   |---|---|
   | `... can be read or changed by other accounts (mode 644); fix with: chmod 600 ...` | Run the `chmod 600` command it shows. The warning goes at the next restart. |
   | `<command> has no [commands.<command>] section; disabled.` | A command your `config.toml` doesn't list yet (often one added by an update). To use it, copy its line from `config.example.toml` into the `[commands]` section of `config.toml` and restart. |
   | `no user has qm/emailall addresses in users.toml` | Harmless: nobody has set one up yet. |
   | `<file> not found; no users or admins until it is created` | `users.toml` is missing or the path is wrong; see the README's Setup. |

4. With the log still open, send `help` to the node from another radio. The
   message and the reply appear in the log, and the radio gets the answer.

## Step 7: Test a reboot

1. Reboot the computer:
   ```sh
   sudo reboot
   ```
2. **Don't log in.** Wait a minute, then send `help` to the node from another
   radio. It should answer.
3. Log in and check the log of this boot:
   ```sh
   journalctl --user -u mesh-contingency -b
   ```
   A first `Could not connect to MeshCore device` is normal: the radio is
   still starting after the computer powered its USB, and the bot tries again
   30 seconds later. If the network is slow to come up, `Auto alerts: no
   network yet; waiting...` comes before the first alert check. If the radio
   restarted with the computer, admins get
   one direct message, `Node restarted: the computer started 1m ago, and the
   radio with it`.

It's done. The bot now runs whenever the computer is on.

---

## Day-to-day commands

| To | Run |
|---|---|
| See if it's running | `systemctl --user status mesh-contingency` |
| Stop it | `systemctl --user stop mesh-contingency` |
| Start it | `systemctl --user start mesh-contingency` |
| Restart it (e.g. after changing `config.toml`) | `systemctl --user restart mesh-contingency` |
| Watch the log | `journalctl --user -u mesh-contingency -f` |
| Send a flood advert | `systemctl --user kill --kill-whom=main -s USR1 mesh-contingency` |
| Re-read `users.toml` now | `systemctl --user kill --kill-whom=main -s HUP mesh-contingency` |
| Stop it starting at boot | `systemctl --user disable mesh-contingency` |
| Start at boot again | `systemctl --user enable mesh-contingency` |

`stop` lasts until the next `start` or reboot; to keep it off across reboots,
`disable` it as well.

`--kill-whom=main` sends the signal to the bot only, not to a `mail` command it
may be running at that moment. Each signal shows in the log, e.g.
`Sent signal SIGHUP to main process ...` followed by
`users.toml reloaded: no changes`.

The commands typed into the bot's terminal (`advert`, `contacts`) need a
terminal, so they don't work while it runs as a service. Use the signals above,
or the mesh commands `advert`, `advert flood` and `contacts` from an admin
radio.

## Reading the log

Everything the bot prints goes to the systemd journal, with the time of each
line. The journal rotates itself, so it never fills the disk.

| To see | Run |
|---|---|
| Follow it live | `journalctl --user -u mesh-contingency -f` |
| The last 100 lines | `journalctl --user -u mesh-contingency -n 100` |
| Since the last boot | `journalctl --user -u mesh-contingency -b` |
| A time range | `journalctl --user -u mesh-contingency --since "2026-10-20 18:00" --until "2026-10-20 20:00"` |
| The last hour | `journalctl --user -u mesh-contingency --since "1 hour ago"` |
| Search it | `journalctl --user -u mesh-contingency \| grep -i alex` |
| Without the pager | add `--no-pager` |

The log shows what happened, never what anyone wrote: who sent a command,
its name, whether it was refused, failed or timed out, and how long each
reply was. Never the command's text (a message, an email address, a
passphrase) or the reply:

```
[d0d0d0d0d0d0 Dana] status
  -> running status
  (reply to d0d0d0d0d0d0 delivered)
  -> replied (42 chars)
```

A message that isn't a command shows as `not a command`. Older versions
(0.9.0 and before) logged commands' text and replies. To clear what they
logged, the journal of every service run as your user (it can't be undone):

```bash
sudo journalctl --rotate
sudo rm /var/log/journal/*/user-$(id -u)@*.journal
```

The journal files belong to root, so this needs `sudo`. On a system that
keeps the journal in memory only, a reboot clears it.

**Keeping logs across reboots.** If `journalctl ... -b -1` (the previous boot)
says `No journal files were found` or shows nothing, your system keeps the
journal in memory only. To keep it on disk:

```sh
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

## Changing settings

| You changed | Do |
|---|---|
| `users.toml` | Nothing: the bot picks it up within about 10 seconds. To apply it at once, send `reload` from an admin radio or run `systemctl --user kill --kill-whom=main -s HUP mesh-contingency`. |
| `config.toml` | `systemctl --user restart mesh-contingency` |
| The unit file in `~/.config/systemd/user/` | `systemctl --user daemon-reload`, then `systemctl --user restart mesh-contingency` |

After a restart, check the log for errors: a mistake in `config.toml` stops
the bot at startup with a message saying what's wrong, and systemd tries again
every 30 seconds until it's fixed.

## Updating the bot

**Installed with the [one-command installer](Set-Up-a-Node)?** Run it again
instead: it does all of this, as in [Updating](Set-Up-a-Node#updating). (Its
checkout follows release tags, so `git pull` there says you're not on a
branch.)

Otherwise, first read the [changelog](https://github.com/DJSnitker/mesh-contingency/blob/main/CHANGELOG.md)
for the releases you're skipping: a release that changes the config says what
to do under "Upgrading". Then, from the project folder:

```sh
git pull
.venv/bin/python -m pip install -e .
systemctl --user restart mesh-contingency
journalctl --user -u mesh-contingency -n 40
```

- **The `pip install` step** registers any commands an update adds, and is
  harmless otherwise. `.venv/bin/python -m pip` works even if the `pip` script
  itself is broken (see
  [Moving or renaming the project folder](#moving-or-renaming-the-project-folder)).
- **New commands start turned off.** After an update, look in the log for
  `Warning: <command> has no [commands.<command>] section; disabled.`. To turn
  one on, copy its line from `config.example.toml` into `[commands]` in your
  `config.toml` (e.g. `health = { permission = "admin" }`) and restart. To see
  everything the update changed in the example config:
  ```sh
  git diff HEAD@{1} -- config.example.toml
  ```
- **If the update changed `deploy/mesh-contingency.service`**, repeat
  [step 4](#step-4-install-the-unit-file) as well.

## Moving or renaming the project folder

The `.venv` folder records the project folder's full path inside its scripts,
and the installed unit file names it in `WorkingDirectory` and `ExecStart`.
After a move or rename, both still point at the old place. You'll see errors
like these:

- `bad interpreter: /home/sam/old-name/.venv/bin/python3: no such file or directory`
  when running `.venv/bin/pip`;
- `status=203/EXEC` or `status=200/CHDIR` in `systemctl --user status
  mesh-contingency`.

To fix it, from the project folder in its new place:

1. Stop the service:
   ```sh
   systemctl --user stop mesh-contingency
   ```
2. Rebuild the `.venv`, keeping the old one until the new one works:
   ```sh
   mv .venv .venv-old
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -e .
   ```
3. Check the bot runs by hand, then stop it with **Ctrl+C**:
   ```sh
   .venv/bin/mesh-contingency
   ```
4. Reinstall the unit file with the new path, as in
   [step 4](#step-4-install-the-unit-file):
   ```sh
   sed "s|/path/to/mesh-contingency|$PWD|g" deploy/mesh-contingency.service > ~/.config/systemd/user/mesh-contingency.service
   systemctl --user daemon-reload
   ```
5. Start the service and check the log:
   ```sh
   systemctl --user start mesh-contingency
   journalctl --user -u mesh-contingency -n 40
   ```
6. Once it's listening, delete the old environment:
   ```sh
   rm -rf .venv-old
   ```

Your settings, users, saved messages and history are in the project folder
itself, so they move with it.

## Running it by hand for testing

Only one program can use the radio, so stop the service first:

```sh
systemctl --user stop mesh-contingency
.venv/bin/mesh-contingency            # in the project folder; Ctrl+C when done
systemctl --user start mesh-contingency
```

The same goes for the MeshCore app over USB: stop the service, use the app,
close it, start the service.

## What happens when something goes wrong

| What happens | What the bot and systemd do |
|---|---|
| The bot crashes | systemd starts it again after 30 seconds. |
| The radio is unplugged, or its USB link drops | The bot tries to reconnect a few times, then logs `Lost the radio (...); stopping.` and exits. systemd starts it again every 30 seconds until the radio is back. |
| The radio isn't plugged in at boot | The bot logs `No serial device found` and exits; systemd keeps trying every 30 seconds. |
| A mistake in `config.toml` | The bot logs what's wrong and exits; systemd keeps trying every 30 seconds until it's fixed. |
| `systemctl --user stop` | The bot disconnects from the radio, logs `Stopped.`, and stays stopped. |
| The computer reboots | The bot starts again by itself, logged in or not. |

Check-ins, messages, join requests and the advert schedule are saved on disk,
so a restart loses nothing. Rate-limit counts start again from zero.

## Troubleshooting

Start with `systemctl --user status mesh-contingency` and
`journalctl --user -u mesh-contingency -n 50`.

| What you see | What to do |
|---|---|
| `Unit mesh-contingency.service not found` | The file isn't in `~/.config/systemd/user/`, or systemd hasn't read it: redo [step 4](#step-4-install-the-unit-file), including `daemon-reload`. |
| `Failed to connect to bus` or `$DBUS_SESSION_BUS_ADDRESS` errors | You're in a shell without a user session (e.g. after `su`). Log in as that user directly, over SSH or at the console. |
| `status=203/EXEC` | `ExecStart` points at something that isn't there. Check the paths (step 4.4) and that `.venv/bin/mesh-contingency` exists; if not, redo the README's Setup. If you moved or renamed the project folder, see [Moving or renaming the project folder](#moving-or-renaming-the-project-folder). |
| `bad interpreter: ... no such file or directory` from `.venv/bin/pip` | The project folder was moved or renamed after the `.venv` was made: see [Moving or renaming the project folder](#moving-or-renaming-the-project-folder). Until then, `.venv/bin/python -m pip` works. |
| `<command> has no [commands.<command>] section; disabled` | The command is new to your `config.toml`. Copy its line from `config.example.toml` into `[commands]` and restart. |
| `status=200/CHDIR` | `WorkingDirectory` is wrong. Check the paths (step 4.4). |
| `No serial device found` over and over | The radio isn't plugged in or isn't detected. Run `ls /dev/serial/by-id/`. If it's there but has an unusual name, add `-p /dev/ttyUSB0` (your device) to `ExecStart`. |
| `Permission denied` on `/dev/ttyUSB0` | Your account isn't in the radio's group: see [step 2](#step-2-check-your-account-can-use-the-radio). |
| `Could not connect to MeshCore device`, or replies missing and odd errors | Something else may have the radio open, such as the MeshCore app or a copy of the bot started by hand; two programs on one radio interfere with each other. Close the other one and `systemctl --user restart mesh-contingency`. Check for a stray copy with `pgrep -af mesh-contingency` (only one line should be the service's). |
| It works until you log out | Lingering is off: redo [step 3](#step-3-let-your-services-run-without-you-logged-in). |
| It doesn't start after a reboot | Check `systemctl --user is-enabled mesh-contingency` says `enabled` (if not, `systemctl --user enable mesh-contingency`) and that lingering is on. |
| `Warning: ... can be read or changed by other accounts` in the log | Run the `chmod 600 ...` command it shows, then `systemctl --user restart mesh-contingency`. |
| Emails fail but worked by hand | Check `~/.mailrc` is in the home folder of the account the service runs as. Test: `echo test \| mail -s test you@example.com`. |
| `systemctl --user kill ... -s USR1` does nothing | Look in the log for `Sent flood advert (SIGUSR1)`; if the radio refused it, the log says so. |
| Replies are slow to show in the log | Check the unit has `Environment=PYTHONUNBUFFERED=1`. |

## Removing the service

```sh
systemctl --user disable --now mesh-contingency
rm ~/.config/systemd/user/mesh-contingency.service
systemctl --user daemon-reload
```

This leaves the project folder, your settings and saved messages alone. If
nothing else of yours needs lingering:

```sh
loginctl disable-linger "$USER"
```

## What's in the unit file

```ini
[Unit]
Description=mesh-contingency MeshCore bot
StartLimitIntervalSec=0

[Service]
Type=exec
WorkingDirectory=/path/to/mesh-contingency
ExecStart=/path/to/mesh-contingency/.venv/bin/mesh-contingency
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=30
TimeoutStopSec=20

[Install]
WantedBy=default.target
```

| Line | Meaning |
|---|---|
| `StartLimitIntervalSec=0` | Never give up retrying, however long the radio is unplugged. |
| `Type=exec` | The bot is the program itself; it's running once it has started. |
| `WorkingDirectory` | The project folder, where `config.toml` is found. |
| `ExecStart` | The program to run, from the project's `.venv`. |
| `PYTHONUNBUFFERED=1` | Each line reaches the log as it's printed. |
| `Restart=on-failure` | Start again after a crash or error exit, but not after `systemctl stop`. |
| `RestartSec=30` | Wait 30 seconds before starting again. |
| `TimeoutStopSec=20` | On `stop`, allow 20 seconds to disconnect from the radio. |
| `WantedBy=default.target` | `enable` starts it with your user session, which lingering starts at boot. |
