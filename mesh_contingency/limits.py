"""Limits on how much one sender (or everyone) can make the bot do.

    [limits]
    public_rate = "10/hour"       # default for public commands
    user_rate = "30/hour"         # default for user commands
    admin_rate = "none"           # default for admin commands
    emails_per_day = 50           # emails sent per sender, per 24 hours
    emails_per_day_total = 200    # addresses emailed by the whole bot, per 24 hours

    [commands.wx]
    permission = "public"
    rate = "5/hour"               # this command's own limit

Counts are kept in memory, so they start again when the bot restarts.
"""

import re
import time
from collections import deque
from dataclasses import dataclass, field

UNITS = {"minute": 60, "hour": 3600, "day": 86400}
RATE_RE = re.compile(r"\s*(\d+)\s*/\s*(minute|hour|day)\s*")
NO_LIMIT = "none"
# By permission level (api.PUBLIC, USER and ADMIN; api imports this module).
DEFAULT_RATES = {"public": "10/hour", "user": "30/hour", "admin": NO_LIMIT}
DEFAULT_EMAILS_PER_DAY = 50
DEFAULT_EMAILS_PER_DAY_TOTAL = 200
EMAIL_WINDOW = 86400
LIMITS_KEYS = {f"{level}_rate" for level in DEFAULT_RATES} | {"emails_per_day", "emails_per_day_total"}


def parse_rate(value, where):
    """Return (count, seconds) for a rate like "5/hour", or None for "none".
    Exits on anything else."""
    if value == NO_LIMIT:
        return None
    match = RATE_RE.fullmatch(value) if isinstance(value, str) else None
    if not match or int(match[1]) < 1:
        raise SystemExit(f'{where} rate must look like "5/hour" (per minute, hour or day) or "none", '
                         f"not {value!r}.")
    return int(match[1]), UNITS[match[2]]


def describe_rate(rate):
    """ "5/hour" for (5, 3600), "none" for None."""
    if rate is None:
        return NO_LIMIT
    count, seconds = rate
    return f"{count}/{next(unit for unit, size in UNITS.items() if size == seconds)}"


@dataclass
class Limits:
    """The [limits] settings. A cap of 0 means no cap."""

    rates: dict = field(default_factory=lambda: {level: parse_rate(rate, "") for level, rate in DEFAULT_RATES.items()})
    emails_per_day: int = DEFAULT_EMAILS_PER_DAY
    emails_per_day_total: int = DEFAULT_EMAILS_PER_DAY_TOTAL

    @classmethod
    def from_config(cls, config):
        section = config.get("limits", {})
        if not isinstance(section, dict) or set(section) - LIMITS_KEYS:
            raise SystemExit(f"[limits] may only set {', '.join(sorted(LIMITS_KEYS))}.")
        rates = {level: parse_rate(section.get(f"{level}_rate", default), f"[limits] {level}_rate")
                 for level, default in DEFAULT_RATES.items()}
        caps = {}
        for key, default in [("emails_per_day", DEFAULT_EMAILS_PER_DAY),
                             ("emails_per_day_total", DEFAULT_EMAILS_PER_DAY_TOTAL)]:
            value = section.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SystemExit(f"[limits] {key} must be a whole number, or 0 for no cap.")
            caps[key] = value
        return cls(rates=rates, **caps)


class RateLimiter:
    """Counts each sender's uses of each command over a sliding window."""

    def __init__(self):
        self._uses = {}  # (who, command name) -> deque of time.monotonic()
        self._told = set()  # (who, command name) already told they reached the limit

    def check(self, who, command, rate):
        """Count a use and return 0 if it is allowed; otherwise return the
        seconds until it would be, plus whether this is the first refusal
        since the limit was reached (so the sender is told only once)."""
        if rate is None:
            return 0, False
        count, seconds = rate
        now = time.monotonic()
        uses = self._uses.setdefault((who, command), deque())
        while uses and now - uses[0] >= seconds:
            uses.popleft()
        if len(uses) < count:
            uses.append(now)
            self._told.discard((who, command))
            return 0, False
        first = (who, command) not in self._told
        self._told.add((who, command))
        return uses[0] + seconds - now, first


class EmailLog:
    """Emails sent in the last 24 hours, for the email caps."""

    def __init__(self):
        self._sent = deque()  # (time.time(), sender's key, addresses)

    def _recent(self):
        cutoff = time.time() - EMAIL_WINDOW
        while self._sent and self._sent[0][0] < cutoff:
            self._sent.popleft()
        return self._sent

    def sends(self, who):
        """Emails `who` sent in the last 24 hours, however many addresses
        each went to."""
        return sum(key == who for _, key, _ in self._recent())

    def addresses(self):
        """Addresses emailed by everyone in the last 24 hours."""
        return sum(n for _, _, n in self._recent())

    def record(self, who, addresses):
        self._sent.append((time.time(), who, addresses))


def wait_text(seconds):
    """ "23 min" or "2 h", rounded up, for a limit reply."""
    minutes = max(1, -(-int(seconds) // 60))
    return f"{minutes} min" if minutes < 120 else f"{-(-minutes // 60)} h"
