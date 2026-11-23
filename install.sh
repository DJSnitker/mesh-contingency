#!/usr/bin/env bash
# Installs or updates a mesh-contingency node on Linux, as your own user:
#
#   curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
#
# It checks out the latest release into ~/mesh-contingency, installs the bot
# into a .venv there, copies the example config (never over your own), and
# sets up the systemd user service. Run it again to update: your config and
# saved data are left alone.
#
# No sudo: run it as the user the node will run as, never with sudo or as
# root (it refuses). It never calls sudo itself either. A few one-time steps
# need an admin of the computer (installing a missing package, joining the
# dialout group, sometimes lingering), so it prints those commands, with
# sudo, for you to run.
#
# After editing config.toml, check the node:
#
#   ~/mesh-contingency/install.sh --check
#
# starts (or restarts) the service and waits for the bot to say it's
# listening, reporting any warnings or what stopped it.
#
# Options, after "bash -s --" when piped (curl ... | bash -s -- --no-service):
#   --dir DIR      install here instead of ~/mesh-contingency
#   --ref REF      a tag or branch instead of the latest release (e.g. main)
#   --no-service   don't install the systemd user service
#   --alert-channel NAME   the alert channel (weather alerts, alert), e.g. #district7-wx
#   --check        don't install: start the service and check the node runs
#
# A new install asks for the alert channel (Enter keeps #contingency-wx),
# unless it's given as an option or there's no terminal to ask on. An update
# never asks: change it in config.toml.
#
# MC_REPO overrides the repository to clone (CI uses a local copy), and
# MC_PORTS the radio ports checked (default /dev/ttyUSB* /dev/ttyACM*); MC_UNIT
# the service --check starts (default mesh-contingency), and MC_WAIT how many
# seconds it waits (default 90).

# Everything is inside main, so a download cut short runs nothing.
main() {
    set -euo pipefail

    local repo="${MC_REPO:-https://github.com/DJSnitker/mesh-contingency.git}"
    local dir="$HOME/mesh-contingency" ref="" service=1
    local alert_channel="" check=0

    while [ $# -gt 0 ]; do
        case "$1" in
            --dir) dir="${2:?--dir needs a folder}"; shift 2 ;;
            --ref) ref="${2:?--ref needs a tag or branch}"; shift 2 ;;
            --console) say "The web console has been removed; ignoring --console."; shift ;;
            --no-service) service=0; shift ;;
            --check) check=1; shift ;;
            --alert-channel) alert_channel="$(channel_name "${2:?--alert-channel needs a name}")" \
                                 || die "--alert-channel: $(channel_rule)"; shift 2 ;;
            --comm-channel) say "The comm command has been removed; ignoring --comm-channel."; shift 2 ;;
            -h|--help) sed -n '2,/^$/s/^# \{0,1\}//p' "$0" 2>/dev/null \
                           || echo "See the comments at the top of install.sh"; return 0 ;;
            *) die "unknown option: $1 (try --help)" ;;
        esac
    done

    [ "$(uname -s)" = Linux ] || die "the node runs on Linux only"
    [ "$(id -u)" -ne 0 ] || die "run this as the user the node will run as, not root (no sudo)"
    if [ "$check" = 1 ]; then check_node "$dir"; return; fi

    # What the system needs; one command lists everything missing.
    local missing=() python
    command -v git >/dev/null || missing+=(git)
    python="$(find_python)" || missing+=(python)
    if [ ${#missing[@]} -gt 0 ]; then
        say "Missing: ${missing[*]}. Install it, then run this again:"
        say "  $(package_hint "${missing[@]}")"
        exit 1
    fi

    # A new node's alert channel, asked now so the install runs on without you.
    if [ ! -e "$dir/config.toml" ]; then
        alert_channel="${alert_channel:-$(ask_channel "Alert channel, for weather alerts and the alert command" "#contingency-wx")}"
    fi

    # Get the code: a fresh checkout, or an update of the one already there.
    local fresh=0
    if [ -d "$dir/.git" ]; then
        say "Updating $dir"
        if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
            die "$dir has changes to its files; commit or undo them first"
        fi
        git -C "$dir" fetch -q --tags origin
        if [ -z "$ref" ] && git -C "$dir" symbolic-ref -q HEAD >/dev/null; then
            # A checkout on a branch (a developer's) follows its branch.
            git -C "$dir" pull -q --ff-only
        else
            ref="${ref:-$(latest_release "$repo")}"
            git -C "$dir" -c advice.detachedHead=false checkout -q "$ref"
        fi
    elif [ -e "$dir" ]; then
        die "$dir exists but isn't a mesh-contingency checkout; pick another with --dir"
    else
        fresh=1
        ref="${ref:-$(latest_release "$repo")}"
        say "Installing mesh-contingency ${ref} into $dir"
        git clone -q --no-checkout "$repo" "$dir"
        git -C "$dir" -c advice.detachedHead=false checkout -q "$ref"
    fi
    cd "$dir"

    # The bot, in its own environment.
    if [ ! -x .venv/bin/python ]; then
        "$python" -m venv .venv 2>/dev/null || {
            rm -rf .venv
            say "Python can't make a virtual environment. Install it, then run this again:"
            say "  $(package_hint venv)"
            exit 1
        }
    fi
    say "Installing the bot (pip)"
    # Quiets setuptools' warning about editable installs; pip errors still show.
    export PYTHONWARNINGS=ignore
    .venv/bin/python -m pip install -q --upgrade pip
    # The command library lives in this repo too (packages/mesh-commands).
    .venv/bin/python -m pip install -q -e packages/mesh-commands -e .

    # Your own config, made once from the example and never overwritten.
    local made=()
    if [ ! -e config.toml ]; then
        cp config.example.toml config.toml
        made+=("$dir/config.toml")
        set_channel alert "$alert_channel" "#contingency-wx"
    fi
    chmod 600 config.toml

    if [ "$service" = 1 ]; then install_service "$dir" "${#made[@]}"; fi

    # What's left for you to do.
    say ""
    say "Done: mesh-contingency $(git describe --tags --always) in $dir"
    local step=1
    if [ ${#made[@]} -gt 0 ]; then
        say "$((step++)). Edit ${made[0]}: your counties in [alerts], your radio's key in [admins]"
        say "   (see https://github.com/DJSnitker/mesh-contingency#configuration)"
    fi
    local access
    access="$(radio_access)"
    if [ -n "$access" ]; then
        say "$((step++)). $access"
    fi
    if [ "$service" = 1 ] && [ "$fresh" = 1 ]; then
        say "$((step++)). Plug in the radio, then start and check the node:"
        say "     $dir/install.sh --check"
    elif [ "$service" = 0 ]; then
        say "$((step++)). Run it: $dir/.venv/bin/mesh-contingency"
    fi
    return 0
}

say() { printf '%s\n' "$*"; }
die() { say "install.sh: $*" >&2; exit 1; }

# The first Python 3.11 or newer on the PATH.
find_python() {
    local p
    for p in python3 python3.14 python3.13 python3.12 python3.11; do
        if command -v "$p" >/dev/null \
            && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
            command -v "$p"
            return 0
        fi
    done
    return 1
}

# A channel name as the bot takes it: "#" and then letters, digits, - or _,
# up to 31 characters. A name without the "#" gets one. Fails on anything else.
channel_name() {
    local name="$1"
    case "$name" in "#"*) ;; *) name="#$name" ;; esac
    [[ "$name" =~ ^#[A-Za-z0-9_-]+$ ]] && [ ${#name} -le 31 ] || return 1
    printf '%s\n' "$name"
}
channel_rule() { printf '%s\n' 'a channel is # and up to 30 letters, digits, - or _, e.g. #district7-wx'; }

# Asks on the terminal (stdin is the script itself under curl | bash); with
# no terminal, or Enter, it's the default.
ask_channel() {
    local prompt="$1" default="$2" answer name
    if ! { exec 3</dev/tty; } 2>/dev/null; then
        printf '%s\n' "$default"
        return 0
    fi
    while true; do
        printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
        IFS= read -r answer <&3 || answer=""
        if [ -z "$answer" ]; then name="$default"; break; fi
        if name="$(channel_name "$answer")"; then break; fi
        printf '  %s\n' "$(channel_rule)" >/dev/tty
    done
    exec 3<&-
    printf '%s\n' "$name"
}

# Writes a command's channel into the new config.toml, when it isn't the default.
set_channel() {
    local command="$1" channel="$2" default="$3"
    [ -n "$channel" ] && [ "$channel" != "$default" ] || return 0
    sed -i "s|^$command = { permission = \"admin\" }|$command = { permission = \"admin\", channel = \"$channel\" }|" config.toml
    grep -q "^$command = .*channel = \"$channel\"" config.toml \
        || say "Couldn't set the $command channel in config.toml; set channel = \"$channel\" under [commands] yourself."
    say "Channel for $command: $channel"
}

# Whether this account can open the radio's USB port: nothing when it can,
# otherwise what to do. With a radio plugged in, it tries the port itself and
# names the group that owns it; without one, it checks the usual groups.
radio_access() {
    local ports=() p
    read -r -a ports <<< "$(radio_ports)"

    if [ ${#ports[@]} -eq 0 ]; then
        groups | grep -qwE 'dialout|uucp' && return 0
        say "Let your user reach the radio's USB port, then log out and back in:"
        if [ -e /etc/arch-release ]; then
            say "     sudo usermod -aG uucp \"\$USER\""
        else
            say "     sudo usermod -aG dialout \"\$USER\""
        fi
        say "   (no radio is plugged in now; plug it in and run this again to check)"
        return 0
    fi

    local group mode
    for p in "${ports[@]}"; do
        if [ -r "$p" ] && [ -w "$p" ]; then
            say "Radio port $p: you can use it." >&2
            continue
        fi
        group="$(stat -c %G "$p")"
        mode="$(stat -c %A "$p")"
        if [ "$group" = root ] || [ "${mode:4:2}" != rw ]; then
            say "Your user can't open $p ($mode, group $group), and no group can:"
            say "   a udev rule or another program set it that way; see"
            say "   https://github.com/DJSnitker/mesh-contingency/wiki/Set-Up-a-Node#2-let-your-account-use-the-radio"
        elif id -nG "$USER" | grep -qw "$group"; then
            say "You're in $group, which can open $p, but not yet in this login:"
            say "   log out and back in (or reboot), then run this again to check"
        else
            say "Let your user open $p (group $group), then log out and back in:"
            say "     sudo usermod -aG $group \"\$USER\""
        fi
        return 0
    done
}

# The USB serial ports there are now, on one line.
radio_ports() {
    local p found=()
    for p in ${MC_PORTS:-/dev/ttyUSB* /dev/ttyACM*}; do
        if [ -e "$p" ]; then found+=("$p"); fi
    done
    printf '%s\n' "${found[*]}"
}

# --check: what would stop the node, then start the service and wait for the
# bot's "Listening for direct messages", or the error it stopped with.
check_node() {
    local dir="$1" unit="${MC_UNIT:-mesh-contingency}" wait="${MC_WAIT:-90}"
    local blockers=0 notes=0 access
    [ -f "$dir/config.toml" ] || die "no node in $dir: install it first (or give --dir)"
    cd "$dir"
    say "Checking the node in $dir"

    # What would keep it from working: fix these before starting.
    if [ -z "$(radio_ports)" ]; then
        say "- No radio on USB (/dev/ttyUSB*, /dev/ttyACM*): plug the node's radio in"
        blockers=$((blockers + 1))
    else
        access="$(radio_access 2>/dev/null)"
        if [ -n "$access" ]; then say "- $access"; blockers=$((blockers + 1)); fi
    fi
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        say "- No systemd user session here (su or a container?): log in as this user directly"
        return 1
    fi
    if ! systemctl --user cat "$unit" >/dev/null 2>&1; then
        say "- The $unit service isn't installed: run the installer again (without --no-service)"
        return 1
    fi
    if [ "$blockers" -gt 0 ]; then
        say "Fix that, then run this again."
        return 1
    fi

    # What the node runs without, but you probably want.
    # (an older node's admins may still be in users.toml, which the bot reads)
    if ! grep -Eqs '"[0-9A-Fa-f]{64}"' config.toml users.toml; then
        say "- No admin keys in [admins] in config.toml: nobody can send alert or testalert"
        notes=$((notes + 1))
    fi
    if ! grep -Eq '^counties *= *\[ *"' config.toml; then
        say "- No counties in [alerts] in config.toml: no weather alerts will be posted"
        notes=$((notes + 1))
    fi

    # What only matters at boot: worth knowing, not a reason to stop.
    if ! systemctl --user -q is-enabled "$unit" 2>/dev/null; then
        say "- It won't start at boot: systemctl --user enable $unit"
        notes=$((notes + 1))
    fi
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]; then
        say "- It starts at boot only once you log in; to start without: sudo loginctl enable-linger \"\$USER\""
        notes=$((notes + 1))
    fi

    # Start it and read what it prints from here on.
    local cursor log waited=0
    cursor="$(journalctl --user -u "$unit" -n 0 --show-cursor 2>/dev/null | sed -n 's/^-- cursor: //p')"
    if systemctl --user -q is-active "$unit"; then say "Restarting the service"; else say "Starting the service"; fi
    systemctl --user restart "$unit"
    while true; do
        if [ -n "$cursor" ]; then
            log="$(journalctl --user -u "$unit" --after-cursor "$cursor" -o cat --no-pager 2>/dev/null)"
        else
            log="$(journalctl --user -u "$unit" -b -o cat --no-pager 2>/dev/null)"
        fi
        if grep -q "Listening for direct messages" <<< "$log"; then break; fi
        if grep -qE "Main process exited|Failed with result" <<< "$log" || [ "$waited" -ge "$wait" ]; then
            local printed
            printed="$(grep -vE "^(Starting|Started|Stopping|Stopped) |\.service: " <<< "$log" | tail -n 15 | sed 's/^/  /' || true)"
            if [ "$waited" -ge "$wait" ]; then
                say "The bot hasn't said it's listening after ${wait}s. What it printed:"
                say "${printed:-  (nothing yet)}"
                say "It may still be starting (a slow radio): watch with"
                say "  journalctl --user -u $unit -f"
            else
                say "The bot stopped. What it printed:"
                say "${printed:-  (nothing)}"
                say "It tries again every 30 seconds. Fix the cause, then run this again;"
                say "the full log: journalctl --user -u $unit -e"
            fi
            return 1
        fi
        sleep 2
        waited=$((waited + 2))
    done

    local warnings line
    warnings="$(grep "^Warning:" <<< "$log" || true)"
    if [ -n "$warnings" ]; then
        say "Running, with warnings (what each means: https://github.com/DJSnitker/mesh-contingency/wiki/Running-as-a-systemd-Service-on-Linux#step-6-check-its-working):"
        while IFS= read -r line; do say "  $line"; done <<< "$warnings"
    else
        say "Running, with no warnings."
    fi
    say "The node is listening. Next: send it health from your radio, and test a reboot."
    [ "$notes" = 0 ] || say "(see the notes above about starting at boot)"
    return 0
}

# The newest release tag, from the repository itself (no API, no jq).
latest_release() {
    local tag
    tag="$(git ls-remote --tags --refs --sort=-version:refname "$1" 'v*' \
        | head -n1 | sed 's|.*refs/tags/||')"
    [ -n "$tag" ] || die "found no release in $1"
    printf '%s\n' "$tag"
}

# The install command for this system's package manager.
package_hint() {
    local pm names=() n
    if command -v apt-get >/dev/null; then pm=apt
    elif command -v pacman >/dev/null; then pm=pacman
    elif command -v dnf >/dev/null; then pm=dnf
    else say "install with your package manager: $*"; return; fi
    for n in "$@"; do
        case "$pm:$n" in
            apt:python) names+=(python3 python3-venv) ;;
            apt:venv) names+=(python3-venv) ;;
            pacman:python|pacman:venv) names+=(python) ;;
            dnf:python) names+=(python3) ;;
            dnf:venv) names+=(python3) ;;
            *) names+=("$n") ;;
        esac
    done
    case "$pm" in
        apt) say "sudo apt-get install ${names[*]}" ;;
        pacman) say "sudo pacman -S --needed ${names[*]}" ;;
        dnf) say "sudo dnf install ${names[*]}" ;;
    esac
}

# The systemd user service: written every time (it follows the folder), and
# restarted on an update when it's running. A fresh install isn't started:
# its config still needs editing.
install_service() {
    local dir="$1" new_files="$2" unit="$HOME/.config/systemd/user/mesh-contingency.service"
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        say "No systemd user session here, so the service wasn't set up;"
        say "see https://github.com/DJSnitker/mesh-contingency/wiki/Running-as-a-systemd-Service-on-Linux"
        return 0
    fi
    mkdir -p "$(dirname "$unit")"
    sed "s|/path/to/mesh-contingency|$dir|g" deploy/mesh-contingency.service > "$unit"
    systemctl --user daemon-reload
    systemctl --user enable -q mesh-contingency
    # Start at boot without logging in; may be refused without admin rights.
    loginctl enable-linger "$USER" 2>/dev/null \
        || say "Couldn't turn on lingering; to start at boot without logging in: sudo loginctl enable-linger \"\$USER\""
    if [ "$new_files" = 0 ] && systemctl --user -q is-active mesh-contingency; then
        say "Restarting the service"
        systemctl --user restart mesh-contingency
    fi
}

main "$@"
