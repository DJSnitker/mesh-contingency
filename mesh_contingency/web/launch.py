"""mesh-contingency-console: open the web console in a browser on this
computer, with the link the running bot wrote to console.url.

It checks the bot answers that link first, so a stopped bot or an old link
says so here rather than in the browser.

Needs no aiohttp: only the bot serves the console.
"""

import argparse
import re
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from ..bot import DEFAULT_CONFIG, load_config
from . import URL_FILE, load_console

# What the bot writes: its own address, and a key (secrets.token_urlsafe).
URL_RE = re.compile(r"http://(127\.0\.0\.1|localhost):(\d+)/\?key=[A-Za-z0-9_-]+")
CHECK_SECONDS = 5
STATIC = Path(__file__).resolve().parent / "static"
SERVICE_HELP = "check with: systemctl --user status mesh-contingency"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report a redirect rather than follow it: the link answers with one."""

    def redirect_request(self, *args, **kwargs):
        return None


def read_url(config_path):
    """The link in console.url next to config_path. Exits saying why if there
    is none, or it isn't one the bot writes."""
    path = Path(config_path).resolve().parent / URL_FILE
    try:
        url = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise SystemExit(f"No {path}: the bot isn't running, or its console didn't start; {SERVICE_HELP}.") from None
    except OSError as e:
        raise SystemExit(f"Can't read {path}: {e.strerror or e}.") from None
    if not URL_RE.fullmatch(url):
        raise SystemExit(f"{path} doesn't hold a console link; restart the bot to write a new one.")
    return url


def check(url):
    """Exit saying why if the bot doesn't answer the link: it answers a good
    key by sending the browser on, with its cookie."""
    address = url.split("?", 1)[0]
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=CHECK_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code
        e.close()
    except (urllib.error.URLError, OSError):
        raise SystemExit(f"Nothing answers at {address}: the bot isn't running (console.url is left from an "
                         f"earlier start); {SERVICE_HELP}.") from None
    if status != 302:
        raise SystemExit(f"The bot at {address} didn't take the key in console.url; restart the bot to write a "
                         "new one.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mesh-contingency-console",
                                     description="Open the web console in a browser on this computer.")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"the bot's config file (default: {DEFAULT_CONFIG})")
    args = parser.parse_args(argv)

    if not load_console(load_config(args.config)).enabled:
        raise SystemExit(f"The web console is off: set enabled = true under [console] in {args.config}, then "
                         "restart the bot.")
    url = read_url(args.config)
    check(url)
    if not (STATIC / "index.html").is_file():
        print("Note: the console's app isn't built, so the page will say so: in console/, run npm ci and npm run "
              "build, then restart the bot.")
    if not webbrowser.open(url):
        raise SystemExit(f"No browser to open here. In a browser on this computer, open the link in "
                         f"{Path(args.config).resolve().parent / URL_FILE}.")
    print(f"Opened the web console ({url.split('?', 1)[0]}) in the browser.")


def run():
    """Entry point for the mesh-contingency-console command."""
    sys.exit(main())
