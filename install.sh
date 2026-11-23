#!/usr/bin/env bash
# Installs or updates a mesh-contingency node on Linux, as your own user:
#
#   curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
#
# It checks out the latest release into ~/mesh-contingency, installs the bot
# into a .venv there, copies the example config and users files (never over
# your own), and sets up the systemd user service. Run it again to update:
# your config, users and saved data are left alone.
#
# It never uses sudo. When something needs it (a missing package, the dialout
# group), it prints the command for you to run.
#
# Options, after "bash -s --" when piped (curl ... | bash -s -- --console):
#   --dir DIR      install here instead of ~/mesh-contingency
#   --ref REF      a tag or branch instead of the latest release (e.g. main)
#   --console      also install and build the web console (needs Node.js)
#   --no-service   don't install the systemd user service
#
# MC_REPO overrides the repository to clone (CI uses a local copy).

# Everything is inside main, so a download cut short runs nothing.
main() {
    set -euo pipefail

    local repo="${MC_REPO:-https://github.com/DJSnitker/mesh-contingency.git}"
    local dir="$HOME/mesh-contingency" ref="" console=0 service=1

    while [ $# -gt 0 ]; do
        case "$1" in
            --dir) dir="${2:?--dir needs a folder}"; shift 2 ;;
            --ref) ref="${2:?--ref needs a tag or branch}"; shift 2 ;;
            --console) console=1; shift ;;
            --no-service) service=0; shift ;;
            -h|--help) sed -n '2,/^$/s/^# \{0,1\}//p' "$0" 2>/dev/null \
                           || echo "See the comments at the top of install.sh"; return 0 ;;
            *) die "unknown option: $1 (try --help)" ;;
        esac
    done

    [ "$(uname -s)" = Linux ] || die "the node runs on Linux only"
    [ "$(id -u)" -ne 0 ] || die "run this as the user the node will run as, not root"

    # What the system needs; one command lists everything missing.
    local missing=() python
    command -v git >/dev/null || missing+=(git)
    python="$(find_python)" || missing+=(python)
    if [ "$console" = 1 ] && ! node_ok; then missing+=(nodejs); fi
    if [ ${#missing[@]} -gt 0 ]; then
        say "Missing: ${missing[*]}. Install it, then run this again:"
        say "  $(package_hint "${missing[@]}")"
        [ "$console" = 0 ] || say "  (the web console needs Node.js 22.22+ or 24.15+, with npm)"
        exit 1
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
    if [ "$console" = 1 ]; then
        .venv/bin/python -m pip install -q -e ".[console]"
        say "Building the web console (npm)"
        (cd console && npm ci --silent --no-audit --no-fund && npm run --silent build)
    else
        .venv/bin/python -m pip install -q -e .
    fi

    # Your own files, made once from the examples and never overwritten.
    local made=()
    for f in config users; do
        if [ ! -e "$f.toml" ]; then
            cp "$f.example.toml" "$f.toml"
            made+=("$dir/$f.toml")
        fi
        chmod 600 "$f.toml"
    done

    if [ "$service" = 1 ]; then install_service "$dir" "${#made[@]}"; fi

    # What's left for you to do.
    say ""
    say "Done: mesh-contingency $(git describe --tags --always) in $dir"
    local step=1
    if [ ${#made[@]} -gt 0 ]; then
        say "$((step++)). Edit $(printf '%s and ' "${made[@]}" | sed 's/ and $//')"
        say "   (see https://github.com/DJSnitker/mesh-contingency#configuration)"
    fi
    if ! groups | grep -qwE 'dialout|uucp'; then
        say "$((step++)). Let your user reach the radio's USB port, then log out and back in:"
        if [ -e /etc/arch-release ]; then
            say "     sudo usermod -aG uucp \"\$USER\""
        else
            say "     sudo usermod -aG dialout \"\$USER\""
        fi
    fi
    if ! command -v mail >/dev/null; then
        say "$((step++)). For the email commands, install mail and set it up to send:"
        say "     $(package_hint mail)"
    fi
    if [ "$service" = 1 ] && [ "$fresh" = 1 ]; then
        say "$((step++)). Plug in the radio and start the bot:"
        say "     systemctl --user start mesh-contingency"
        say "     journalctl --user -u mesh-contingency -f"
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

# Node.js 22.22+ or 24.15+ (or newer than 24), with npm.
node_ok() {
    command -v node >/dev/null && command -v npm >/dev/null || return 1
    node -e '
        const [a, b] = process.versions.node.split(".").map(Number);
        process.exit((a === 22 && b >= 22) || (a === 24 && b >= 15) || a > 24 ? 0 : 1);
    '
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
            apt:mail) names+=(s-nail) ;;
            pacman:python|pacman:venv) names+=(python) ;;
            pacman:nodejs) names+=(nodejs npm) ;;
            pacman:mail) names+=(s-nail) ;;
            dnf:python) names+=(python3) ;;
            dnf:venv) names+=(python3) ;;
            dnf:nodejs) names+=(nodejs npm) ;;
            dnf:mail) names+=(s-nail) ;;
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
