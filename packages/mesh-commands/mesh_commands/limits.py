"""Limits on how often one sender can use each command.

    [limits]
    public_rate = "10/hour"       # default for public commands
    user_rate = "30/hour"         # default for user commands
    admin_rate = "none"           # default for admin commands

    [commands.roll]
    permission = "public"
    rate = "5/hour"               # this command's own limit

Counts are kept in memory, so they start again when the bot restarts.
"""

import re
import time
from collections import deque
from dataclasses import dataclass, field

from .permissions import ADMIN, PUBLIC, USER

UNITS = {"minute": 60, "hour": 3600, "day": 86400}
RATE_RE = re.compile(r"\s*(\d+)\s*/\s*(minute|hour|day)\s*")
NO_LIMIT = "none"
# By permission level.
DEFAULT_RATES = {PUBLIC: "10/hour", USER: "30/hour", ADMIN: NO_LIMIT}
LIMITS_KEYS = {f"{level}_rate" for level in DEFAULT_RATES}


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
    """The [limits] settings: the default rate for each permission level."""

    rates: dict = field(default_factory=lambda: {level: parse_rate(rate, "") for level, rate in DEFAULT_RATES.items()})

    @classmethod
    def from_config(cls, config, ignore=()):
        """The config's [limits] section; keys in `ignore` (ones a project used
        to have there, say) are allowed and ignored, any other unknown key exits."""
        section = config.get("limits", {})
        if not isinstance(section, dict) or set(section) - LIMITS_KEYS - set(ignore):
            raise SystemExit(f"[limits] may only set {', '.join(sorted(LIMITS_KEYS))}.")
        return cls({level: parse_rate(section.get(f"{level}_rate", default), f"[limits] {level}_rate")
                    for level, default in DEFAULT_RATES.items()})


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


def wait_text(seconds):
    """ "23 min" or "2 h", rounded up, for a limit reply."""
    minutes = max(1, -(-int(seconds) // 60))
    return f"{minutes} min" if minutes < 120 else f"{-(-minutes // 60)} h"
