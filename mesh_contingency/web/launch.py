"""mesh-contingency-console: open the web console in a browser on this
computer, with the link the running bot wrote to console.url; and, as
mesh-contingency-console user ..., make the console's users (users_cli.py);
and, as mesh-contingency-console cert show|renew, see or remake the remote
console's HTTPS certificate (tls.py).

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
from . import URL_FILE, load_console, tls, users_cli

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
                                     description="Open the web console in a browser on this computer, or (user) "
                                                 "make and change the console's users.")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"the bot's config file (default: {DEFAULT_CONFIG})")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    users_cli.add_parser(commands)
    cert = commands.add_parser("cert", help="the remote console's HTTPS certificate",
                               description="See or remake the HTTPS certificate the bot made for the remote "
                                           "console (console_tls/ next to config.toml).")
    cert.add_argument("action", choices=["show", "renew"],
                      help="show: its fingerprint; renew: make a new one (used from the bot's next start)")
    args = parser.parse_args(argv)
    if args.command == "user":
        return users_cli.main(args)
    if args.command == "cert":
        return cert_command(args)

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


def cert_command(args):
    settings = load_console(load_config(args.config))
    if settings.cert:
        if args.action == "renew":
            raise SystemExit(f"[console] cert names your own certificate ({settings.cert}); renew it where it came "
                             "from, or remove cert and key to use the bot's.")
        cert = Path(settings.cert).expanduser()
    else:
        folder = tls.tls_folder(Path(args.config).resolve().parent)
        cert = folder / tls.CERT_FILE
        if args.action == "renew":
            if tls.cryptography_missing():
                raise SystemExit('Making a certificate needs cryptography: pip install -e ".[console]".')
            tls.make_certificate(folder)
            print(f"Made a new certificate, {cert}. The bot uses it from its next start "
                  "(systemctl --user restart mesh-contingency); browsers will warn about it once again.")
        elif not cert.is_file():
            raise SystemExit(f"No certificate yet ({cert}): the bot makes one when it starts with [console] "
                             "remote = true.")
    try:
        print(f"Certificate SHA-256 {tls.fingerprint(cert)}")
    except tls.CertificateError as e:
        raise SystemExit(f"{e}.") from None


def run():
    """Entry point for the mesh-contingency-console command."""
    sys.exit(main())
