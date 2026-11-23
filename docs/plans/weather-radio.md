# Plan: alerts from NOAA Weather Radio, with no internet

Status: planned, nothing built yet; the receiver settled (an RTL-SDR Blog V4, ordered 2026-11-19), the other decisions left · Requested 2026-11-07 · Updated 2026-11-23 for 1.0 (posts to Public; no `health`, watch or console)

## Goal

The automatic weather alerts (`[alerts]`) come from
api.weather.gov, so they stop when the node's computer loses the internet,
which in a disaster is often when they matter most. NOAA Weather Radio (NWR)
is broadcast over the air on 162.400–162.550 MHz, and every warning starts
with a short digital **SAME** header (Specific Area Message Encoding). The
node listens to its local NWR station with a cheap receiver, decodes those
headers, and posts the alerts for its watched counties to the Public
channel, as the NWS API's alerts are, whether or not the internet is up.

## What a SAME header holds

```
ZCZC-WXR-TOR-048441-048253+0045-3101642-WXK00   -
     │   │   │             │    │       └ the station that sent it (8 characters)
     │   │   │             │    └ issued: day of the year, hour, minute (UTC)
     │   │   │             └ how long it's valid: hours and minutes
     │   │   └ the places: PSSCCC (part of the county, state FIPS, county FIPS), up to 31
     │   └ the event: TOR = Tornado Warning
     └ who sent it: WXR = the National Weather Service
```

Each header is sent three times and the message ends with `NNNN`. What it
does **not** hold is the details ("near Tye, moving east at 30 mph"): those
are in the spoken audio after it. NWR's routine forecasts and observations
have no header at all, only voice.

The bot already reads SAME place codes: `alert_counties` in `weather.py`
turns `048441` into the NWS county code `TXC441`, which is what
`alerts.json` keeps for each watched county. So matching a header to the
watched counties needs no new lookups and no internet.

## Decisions to make before building

These are proposals; each needs the user's yes or no. The first is settled.

1. **The receiver. Settled 2026-11-19:** an RTL-SDR Blog V4 dongle (its kit
   with the telescoping dipole, mount and USB extension cable; ordered
   2026-11-19) on the node's computer, with `rtl_fm` (from `rtl-sdr`) tuning
   the station and `multimon-ng -a EAS` decoding the headers. Both are
   packaged on Arch and Debian. The V4 was chosen over cheaper dongles for
   its temperature-compensated oscillator (no drift when always on) and its
   shielded case (it sits next to the companion radio's 900 MHz
   transmitter). The bot runs a command set in the config and reads its
   output, so any other decoder that prints `ZCZC-...` lines works too
   (another SDR program, or a decoder on another machine over `ssh`).
   - The V4's R828D tuner needs `rtl-sdr` 2.0.2 or later: `rtl_test` should
     name the tuner when it's plugged in.
   - The antenna: each arm of the dipole about 46 cm (18 in), a quarter
     wave at 162.5 MHz, standing vertically (NWR is vertically polarized),
     high and near a window. The USB extension keeps the dongle and antenna
     a foot or more from the companion radio and the computer. If an indoor
     antenna is too weak, a marine VHF antenna (156–162 MHz) is the step up.
   - The frequency: the local station's, from NOAA's NWR station listing by
     county. The 162.550 MHz in the example command is only a placeholder.
2. **Always on, not only when the internet is down.** Proposed: NWR and
   the NWS API both post to Public, and the first source to report
   an alert posts it. NWR is often minutes ahead of the API, and running both
   all the time means the NWR path is tested every week, not first tried in
   a disaster.
3. **Which events get posted.** Proposed: warnings, watches, advisories
   and statements for the watched counties only, like the API's alerts. The weekly and monthly tests (`RWT`, `RMT`) are not posted; they
   only show that the receiver works (see *Health*). Codes for non-weather
   events (`CEM`, `EVI`, `LAE` and others) are posted too, because NWR
   carries them for local emergency management.

   The `[alerts]` filter applies too. `events` matches the event's name,
   e.g. `TOR` is `Tornado Warning`. A SAME header has no severity, so
   proposed: with `severity` set, each event code is given the severity the
   NWS usually gives it (warnings Severe or Extreme, watches and advisories
   Moderate or Minor), from a table in `same.py`. **Accepted 2026-11-23.**
4. **How a post reads.** Proposed: the same format as the API's posts,
   with `(NWR)` after `ALERT` so people know where it came from and that
   it has no details:
   ```
   Taylor, TX ALERT (NWR): Tornado Warning | until 5:27PM | Taylor; Jones
   ```
   "Until" is the issue time plus the valid-for time, in the node's time
   zone.
5. **Speech-to-text later, if at all.** The details and the voice forecast
   would need a speech-to-text model on the node (for example a small local
   Whisper). That's a separate, later item, after the headers have worked
   through a storm season.

## How it fits together

```
NWR station ── 162.xxx MHz ──> RTL-SDR ──> rtl_fm | multimon-ng -a EAS
                                                │  "EAS: ZCZC-WXR-TOR-048441..."
                                                ▼
                               NwrListener (new, mesh_contingency/nwr.py)
                                 parse → watched counties? → already posted?
                                                │
api.weather.gov ──> AlertWatcher.check ─────────┤ (the posting half of check(),
                                                │  split out so both use it)
                                                ▼
                                   Public, alerts.json
```

- **`mesh_contingency/same.py` (new, data only):** `parse_header(line)` →
  `{org, event, places, valid_minutes, issued, station}` or `None` for
  anything that isn't a whole, well-formed header; `EVENTS`, the event
  codes' names (`TOR` → `Tornado Warning`, from the NWS list, with an
  unknown code shown as itself); `issued_time(jjjhhmm, now)` handles the year boundary (a
  header from day 365 read on 1 January).
- **`NwrListener` (new, `mesh_contingency/nwr.py`):** starts the command
  as a child process (`/bin/sh -c`, so the pipe works; the command comes
  from `config.toml`, which only the node's owner can write), reads its
  lines, and hands each new header to the watcher. If the command exits,
  it says so once and starts it again after 30 s, then 1, 2 and 5
  minutes, like the bot's radio reconnects. The child is stopped with the
  bot.
- **One alert, one post.** Each header is sent three times, so repeats
  within a few minutes are dropped by their whole text. Against the API, an
  NWR alert's key in `posted` is
  `same|<event>|<county code>|<issued, to the minute>`; an API alert carries the same SAME
  event code (`parameters.eventCode.SAME`) and county codes
  (`geocode.SAME`), so when one arrives the bot checks whether the other
  source posted the same event for the same county within 15 minutes of
  it, and stays quiet if so. Kept in `alerts.json` as now, so a
  restart doesn't post anything twice.
- **Health.** 1.0 has no `health` command and no node watch, so the
  receiver reports in the log, which `install.sh --check` shows:
  - at startup: `NWR: listening (rtl_fm ...)`;
  - each time a weekly test is heard: `NWR: weekly test heard (WXK00)`;
  - when the command keeps failing, or no weekly test has been heard for 8
    days: a `Warning:`. NWR's weekly test is normally on a set day each
    week, and the antenna and dongle are the thing most likely to fail
    quietly.

  **Accepted 2026-11-23:** with `[nwr]` set, the weekly alert test
  (`[alert_test]`) adds a line such as `NWR: last weekly test heard 3d ago`
  (or `NWR: no weekly test heard yet`), so people on the mesh see that the
  receiver works too. An admin DM instead would have needed the node watch
  back.

## Config

Off unless set:

```toml
[nwr]
# The command that prints decoded SAME headers, one per line.
command = "rtl_fm -f 162.550M -M fm -s 22050 - | multimon-ng -q -t raw -a EAS -"
# no_test_days = 8   # tell admins if no weekly test is heard for this long
```

It posts to Public and watches the `[alerts]` counties, so
NWR needs `[alerts] counties` set. Tune the frequency to the station for
those counties (the NWS lists each station's frequency and the counties it
serves).

## PRs

1. **This plan** and roadmap item 19 (done, #109).
2. **SAME headers** (`same.py`): the parser, the event names, the issue
   time, matching to watched counties; tests from recorded header lines,
   including broken and partial ones (a weak signal decodes garbage).
   Nothing runs yet.
3. **The listener:** `[nwr]` in the config, `NwrListener`, the posting half
   of `AlertWatcher.check` split out and shared, the de-duplication against
   the API, the filter (with `same.py`'s severity table), the log lines and
   warnings, and the NWR line in the weekly test. Tests use a
   fake command (`printf` of recorded lines, one that exits, one that
   hangs) in CI, so no radio is needed.
4. **Docs:** the README (*Automatic weather alerts*, *Requirements*,
   *Configuration*), `config.example.toml`, the wiki (setting up a
   receiver), and the changelog. Then a release.
5. **Later, if wanted:** the spoken details by speech-to-text.

## To check on real hardware

- That `rtl_fm` and `multimon-ng`, as in the example command, decode the
  local station's weekly test on the node's computer, and how strong the
  signal is with an indoor and an outdoor antenna.
- The dongle and the companion radio on USB together: power and noise
  (the dongle sits next to a 900 MHz transmitter).
- What the decoder prints for a weak or partial header, to add to the
  tests.
- A real alert reaching Public by both paths, posted once.
- Unplugging the dongle: the warning in the log, then recovery when it's
  plugged back in.
