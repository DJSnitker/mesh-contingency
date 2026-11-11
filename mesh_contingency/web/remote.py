"""Logging in to the remote console: who may, and for how long.

- Only the local network: a request from a public (internet) address is
  refused before anything else, as a guard against a port forward or a
  misconfigured router (private_address).
- Console users (console_users.py) log in with their name and password. The
  file is read again whenever it changes, so mesh-contingency-console user
  ... applies at once: a removed user, or one whose password was set
  again, is logged out at their next request, and a new password on the
  node also ends that name's lockout.
- A login is a random session id in a cookie (Secure, HttpOnly,
  SameSite=Strict), kept only in the bot's memory: a restart logs everyone
  out. It ends after IDLE_SECONDS without being used, MAX_SECONDS after the
  login, or on logging out. The app marks the reads it makes on its own
  (refreshing a page, unread counts) with BACKGROUND_HEADER: they need the
  login but don't count as use, so a console left open logs out too.
- After NAME_FAILURES failed logins in FAIL_WINDOW for one name, or
  ADDRESS_FAILURES from one address, that name or address waits
  LOCK_SECONDS. A wrong name and a wrong password get the same answer and
  take as long (an unknown name is checked against a made-up password).
- Every login, failure, lockout and logout is printed to the journal, never
  a password. Failed logins (and tries while locked out) are also counted
  for the node watch (recent_failures), which tells the mesh's admins about
  a burst; a lockout calls on_lockout, so it can check straight away.
"""

import asyncio
import ipaddress
import secrets
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from . import console_users as store

PRIVATE_NETWORKS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",  # private
    "169.254.0.0/16",  # link-local
    "100.64.0.0/10",  # shared (carrier-grade NAT, Tailscale-style VPNs)
    "127.0.0.0/8", "::1/128",  # this computer
    "fc00::/7", "fe80::/10",  # IPv6 unique local and link-local
)]
SESSION_COOKIE = "mesh_console_session"
IDLE_SECONDS = 30 * 60
MAX_SECONDS = 12 * 3600
FAIL_WINDOW = 15 * 60
NAME_FAILURES = 5
ADDRESS_FAILURES = 10
LOCK_SECONDS = 15 * 60
WRONG = "Wrong name or password."
BACKGROUND_HEADER = "X-Console-Background"  # "1": the app refreshing itself (console/src/app/api.ts)


def private_address(text):
    """True if text is an address of the local network (or this computer)."""
    try:
        address = ipaddress.ip_address((text or "").split("%", 1)[0])
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:  # 192.168.1.5 on an IPv6 socket
        address = address.ipv4_mapped
    return any(address in network for network in PRIVATE_NETWORKS)


def minutes(seconds):
    whole = max(1, round(seconds / 60))
    return f"{whole} minute{'s' if whole != 1 else ''}"


class LoginRefused(Exception):
    """A login that didn't work: status and the text to answer with."""

    def __init__(self, status, text):
        super().__init__(text)
        self.status = status
        self.text = text


class ConsoleUsers:
    """The console users file, read again when it changes. A file that can't
    be used is said once and lets nobody in until it's fixed."""

    def __init__(self, path, on_new_password=None):
        self.path = Path(path)
        self.on_new_password = on_new_password  # called with a name whose password was set again
        self._stamp = object()  # matches no file, so the first call reads it
        self._users = {}
        self._problem = None

    def _file_stamp(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size, st.st_ino

    def users(self):
        """{name: user} as the file has them now."""
        stamp = self._file_stamp()  # None: no file, so no console users
        if stamp == self._stamp:
            return self._users
        try:
            users = store.load(self.path)
        except store.ConsoleUsersError as e:
            if str(e) != self._problem:
                print(f"Warning: {self.path}: {e}; no console user can log in until it's fixed.", flush=True)
            self._problem = str(e)
            self._users, self._stamp = {}, stamp
            return self._users
        if self._problem:
            print(f"{self.path} is usable again.", flush=True)
            self._problem = None
        if self.on_new_password:
            for name, user in users.items():
                old = self._users.get(name)
                if old and old["changed"] != user["changed"]:
                    self.on_new_password(name)
        self._users, self._stamp = users, stamp
        return self._users

    def get(self, name):
        return self.users().get(name)


@dataclass
class Session:
    name: str
    changed: int  # the user's changed when logged in: a new password ends it
    started: float
    last: float


class Logins:
    """The remote console's sessions and lockouts."""

    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.users = ConsoleUsers(path, on_new_password=self.unlock_name)
        self.sessions = {}
        self.failures = {}  # ("name", name) or ("address", address) -> deque of times
        self.locked_until = {}
        # Every failed login and try while locked out, as (time, address), for the node watch:
        # unlike failures, a lockout doesn't clear it.
        self.failure_log = deque()
        self.on_lockout = None  # called after a name or address is locked out
        # Checked for a name that isn't a console user, so it takes as long.
        self._made_up = store.hash_password(secrets.token_urlsafe(16))

    # Lockouts

    def _recent(self, what, now):
        times = self.failures.get(what)
        while times and times[0] <= now - FAIL_WINDOW:
            times.popleft()
        return times

    def locked(self, name, address):
        """Seconds until name or address may try again, or 0."""
        now = self.clock()
        wait = 0
        for what in (("name", name), ("address", address)):
            until = self.locked_until.get(what, 0)
            if until > now:
                wait = max(wait, until - now)
            elif what in self.locked_until:
                del self.locked_until[what]
        return wait

    def failed(self, name, address, shown):
        """Count a failed login (or a wrong current password) for name and address."""
        now = self.clock()
        print(f"Console login failed: {shown} from {address}", flush=True)
        self.failure_log.append((now, address))
        locked = False
        for what, limit in ((("name", name), NAME_FAILURES), (("address", address), ADDRESS_FAILURES)):
            times = self.failures.setdefault(what, deque())
            self._recent(what, now)
            times.append(now)
            if len(times) >= limit:
                self.locked_until[what] = now + LOCK_SECONDS
                times.clear()
                who = shown if what[0] == "name" else address
                print(f"Console login: {who} locked out for {minutes(LOCK_SECONDS)} after {limit} failed "
                      f"login(s) in {minutes(FAIL_WINDOW)}", flush=True)
                locked = True
        if locked and self.on_lockout:
            self.on_lockout()

    def unlock_name(self, name):
        """A new password for name (on the node): its lockout ends."""
        self.failures.pop(("name", name), None)
        if self.locked_until.pop(("name", name), None):
            print(f"Console login: {name} may log in again (a new password)", flush=True)

    def _recent_log(self, window):
        now = self.clock()
        while self.failure_log and self.failure_log[0][0] <= now - window:
            self.failure_log.popleft()
        return self.failure_log

    def recent_failures(self, window=FAIL_WINDOW):
        """Failed logins, and tries while locked out, in the last window seconds."""
        return len(self._recent_log(window))

    def recent_addresses(self, window=FAIL_WINDOW):
        """The addresses those came from, most first."""
        counts = {}
        for _, address in self._recent_log(window):
            counts[address] = counts.get(address, 0) + 1
        return sorted(counts, key=lambda a: (-counts[a], a))

    # Logging in and out

    async def log_in(self, typed_name, password, address):
        """A new session id for name, or raises LoginRefused."""
        name = store.normal_name(typed_name) if isinstance(typed_name, str) else ""
        password = password if isinstance(password, str) else ""
        shown = name if not store.check_name(name) else "(not a name)"
        wait = self.locked(name, address)
        if wait:
            print(f"Console login refused: {shown} from {address} (locked out)", flush=True)
            self.failure_log.append((self.clock(), address))
            raise LoginRefused(429, f"Too many failed logins: try again in {minutes(wait)}.")
        user = self.users.get(name) if not store.check_name(name) else None
        ok = await asyncio.to_thread(store.verify_password, password[:store.PASSWORD_MAX],
                                     user["password"] if user else self._made_up)
        if not (ok and user):
            self.failed(name, address, shown)
            raise LoginRefused(401, WRONG)
        self.failures.pop(("name", name), None)
        now = self.clock()
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = Session(name, user["changed"], now, now)
        print(f"Console login: {name} from {address}", flush=True)
        await asyncio.to_thread(self._note_login, name, int(now))
        return session_id, name

    def _note_login(self, name, when):
        try:
            with store.changing(self.users.path) as users:
                if name in users:
                    users[name]["last_login"] = when
        except (OSError, store.ConsoleUsersError) as e:
            print(f"Warning: couldn't note {name}'s login in {self.users.path}: {e}", flush=True)

    def session(self, session_id, use=True):
        """The live Session for session_id, or None (ending it if it's over).
        use=False checks it without counting as use (a background refresh)."""
        found = self.sessions.get(session_id) if session_id else None
        if found is None:
            return None
        now = self.clock()
        user = self.users.get(found.name)
        why = None
        if user is None:
            why = "no longer a console user"
        elif user["changed"] != found.changed:
            why = "a new password"
        elif now - found.last > IDLE_SECONDS:
            why = f"{minutes(IDLE_SECONDS)} without being used"
        elif now - found.started > MAX_SECONDS:
            why = f"{MAX_SECONDS // 3600} hours since logging in"
        if why:
            del self.sessions[session_id]
            print(f"Console logout: {found.name} ({why})", flush=True)
            return None
        if use:
            found.last = now
        return found

    def log_out(self, session_id):
        found = self.sessions.pop(session_id, None) if session_id else None
        if found:
            print(f"Console logout: {found.name}", flush=True)
        return found

    def keep_after_new_password(self, session_id, changed):
        """The user changed their own password in this session: it stays."""
        if session_id in self.sessions:
            self.sessions[session_id].changed = changed
