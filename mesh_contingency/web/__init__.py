"""The web console: the node in a browser on the bot's own computer.

[console] in config.toml (off unless enabled = true):

    [console]
    enabled = true
    port = 8737     # 127.0.0.1 only

The server runs inside the bot, as one more task, and answers only on
127.0.0.1: host may be 127.0.0.1 or localhost, nothing else, so a mistake
can't put it on the network. Each start makes a new key; the link with it is
written to console.url next to config.toml (readable only by this account)
and printed. See server.py for how requests are checked, and api.py for what
they can read.

It needs aiohttp, an optional extra: pip install -e ".[console]". Without it
the bot says so and runs without the console.
"""

from dataclasses import dataclass

CONSOLE_KEYS = {"enabled", "port", "host"}
DEFAULT_PORT = 8737
HOSTS = ("127.0.0.1", "localhost")
# The link to open, with its key, beside config.toml.
URL_FILE = "console.url"
INSTALL = 'pip install -e ".[console]"'


@dataclass(frozen=True)
class ConsoleSettings:
    enabled: bool = False
    port: int = DEFAULT_PORT
    host: str = "127.0.0.1"


def load_console(config):
    """ConsoleSettings from [console] in config.toml. Exits on a mistake."""
    section = config.get("console", {})
    if not isinstance(section, dict) or set(section) - CONSOLE_KEYS:
        raise SystemExit(f"[console] may only set {', '.join(sorted(CONSOLE_KEYS))}.")
    defaults = ConsoleSettings()
    enabled = section.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise SystemExit("[console] enabled must be true or false.")
    port = section.get("port", defaults.port)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise SystemExit("[console] port must be a whole number from 1024 to 65535.")
    host = section.get("host", defaults.host)
    if host not in HOSTS:
        raise SystemExit("[console] host may only be 127.0.0.1 or localhost: the console is for this computer "
                         "only.")
    return ConsoleSettings(enabled, port, host)


def aiohttp_missing():
    """True if aiohttp, which the console needs, isn't installed."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return True
    return False
