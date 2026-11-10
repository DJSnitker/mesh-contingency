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

The remote console (item 20) is a second listener, off unless remote = true:
the same console for console users (console_users.py) on other computers of
the local network, over HTTPS, after a login. See remote.py.

    [console]
    remote = true
    remote_port = 8738              # all addresses, private ones answered
    # cert = "/path/to/cert.pem"   # your own certificate, instead of the
    # key = "/path/to/key.pem"     # one the bot makes (console_tls/)
"""

from dataclasses import dataclass

CONSOLE_KEYS = {"enabled", "port", "host", "remote", "remote_port", "cert", "key"}
DEFAULT_PORT = 8737
DEFAULT_REMOTE_PORT = 8738
HOSTS = ("127.0.0.1", "localhost")
# The link to open, with its key, beside config.toml.
URL_FILE = "console.url"
INSTALL = 'pip install -e ".[console]"'


@dataclass(frozen=True)
class ConsoleSettings:
    enabled: bool = False
    port: int = DEFAULT_PORT
    host: str = "127.0.0.1"
    remote: bool = False
    remote_port: int = DEFAULT_REMOTE_PORT
    cert: str | None = None  # your own certificate and its key, or None for the bot's
    key: str | None = None


def _port(section, name, default):
    port = section.get(name, default)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise SystemExit(f"[console] {name} must be a whole number from 1024 to 65535.")
    return port


def load_console(config):
    """ConsoleSettings from [console] in config.toml. Exits on a mistake."""
    section = config.get("console", {})
    if not isinstance(section, dict) or set(section) - CONSOLE_KEYS:
        raise SystemExit(f"[console] may only set {', '.join(sorted(CONSOLE_KEYS))}.")
    defaults = ConsoleSettings()
    enabled = section.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise SystemExit("[console] enabled must be true or false.")
    port = _port(section, "port", defaults.port)
    host = section.get("host", defaults.host)
    if host not in HOSTS:
        raise SystemExit("[console] host may only be 127.0.0.1 or localhost: the console is for this computer "
                         "only; for other computers, set remote = true.")
    remote = section.get("remote", defaults.remote)
    if not isinstance(remote, bool):
        raise SystemExit("[console] remote must be true or false.")
    remote_port = _port(section, "remote_port", defaults.remote_port)
    if remote and remote_port == port:
        raise SystemExit("[console] remote_port must differ from port.")
    cert, key = section.get("cert"), section.get("key")
    for name, value in (("cert", cert), ("key", key)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise SystemExit(f"[console] {name} must be the path to a file.")
    if (cert is None) != (key is None):
        raise SystemExit("[console] cert and key go together: set both (your own certificate) or neither (the "
                         "bot's).")
    return ConsoleSettings(enabled, port, host, remote, remote_port, cert, key)


def aiohttp_missing():
    """True if aiohttp, which the console needs, isn't installed."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return True
    return False
