# The web console's app

The browser side of the web console (`[console]` in `config.toml`): an
Angular app the bot serves on `127.0.0.1`, with its API in
`mesh_contingency/web/`. The plan is in `docs/plans/web-console.md`.

```sh
npm ci                 # once, and after package-lock.json changes
npm run build          # builds into mesh_contingency/web/static/, which the bot serves
npm test               # unit tests (Vitest)
npm run format:check   # formatting (Prettier); npm run format fixes it
```

Restart the bot after a build. The build isn't committed; the Python package
includes it, so build before `python -m build`.

To work on the app with live reloading, run the bot with `[console]` enabled,
open the console's link (from `console.url`) once, then run `npm start` and
open http://127.0.0.1:4200: it proxies `/api` to the bot (`proxy.conf.json`),
and the browser sends the same cookie, since cookies don't go by port.
The proxy also sends the bot's own `Origin`, so commands run from the dev
server; other sites still can't use it, since the cookie is `SameSite=Strict`
and never goes with their requests.

## Demo and screenshots

`scripts/demo_console.py` runs the console on a fake radio with made-up
users, messages and history: the real server and the built app, nothing of
a real node's read or written. Use it to try the app without a node, and for
the screenshots in the wiki (they never show real users).

```sh
.venv/bin/python scripts/demo_console.py                     # prints a link; Ctrl+C stops it
.venv/bin/python scripts/demo_console.py --screenshots /tmp/shots   # a PNG of each page, then stops
```

Build the app first. Screenshots need Chrome or Chromium; they're the Admin
Guide's `images/console-*.png` in the wiki, so retake them when a page
changes how it looks.
