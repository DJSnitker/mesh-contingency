# Roadmap

Status: 1.0.0 released (2026-11-23): weather alerts on the Public channel, or
one you pick ([simplify.md](simplify.md)); next, NOAA Weather Radio (item 19)
· Updated 2026-11-23

## Where things stand

Mesh Contingency 1.0 does one thing. It posts National Weather Service
alerts for the counties you list to MeshCore's Public channel, and its
admins can post there too (`alert`) and test it (`testalert`). The command
machinery is its own library, `packages/mesh-commands`.

Everything earlier versions had is kept on the tag `archive/full-system` and
the branch `archive/full` (commit 344769a). That covers:
- users, the mailbox and email;
- check-ins, `wx`, the node watch and backups;
- the web and remote consoles, the phone and desktop apps;
- items 1–18 and 20 of the old roadmap, with their plans and field-test
  results.

`git show archive/full:docs/plans/roadmap.md` shows the old roadmap.

| # | What | Status |
|---|---|---|
| 21 | Cut the system down to weather alerts on Public, plus the `mesh-commands` library | done: #143–#153, the wiki, released as 1.0.0; `[alerts] channel` added on the way (#153) |
| 19 | Alerts from NOAA Weather Radio (SAME headers), with no internet | planned: [weather-radio.md](weather-radio.md); the receiver settled (RTL-SDR Blog V4, ordered 2026-11-19); the other decisions left |
| 9 | Field testing on real radios | paused, waiting on more radios. Its checks are for the old system and on the archive branch; the 1.0 checks are below |

## Checks on the node for 1.0

These are tried on the live node after the release (step 8):
- **Reboot:** reboot without logging in. The service starts by itself, and
  `help` from an admin radio is answered.
- **Lost radio:** unplug the radio while the bot runs. Expect
  `Lost the radio (...); stopping.`, `No serial device found` every 30 s,
  then `Connected to ...` about 30 s after you plug it back in.
- **Weekly test:** the Wednesday 17:00 test arrives on Public on another
  radio, followed by the counties.
- **`alert` and `testalert`** from an admin radio arrive on Public.
  `alert` from any other radio gets `unrecognized user or function`.
- **A real NWS alert** for a watched county arrives on Public once, and
  isn't posted again after a restart.

## Next: NOAA Weather Radio (item 19)

The automatic alerts stop when the node loses the internet. So the node will
also listen to the local NOAA Weather Radio station:
- An RTL-SDR dongle and `multimon-ng` decode each warning's SAME header:
  the event, the counties, and how long it's valid.
- The bot posts the alerts for the `[alerts]` counties to Public.
- Each alert is posted once, whichever of NWR and the NWS API reports it
  first.

The headers have no details (those are spoken); speech-to-text would be a
later, separate step. The plan, its open decisions and its PRs are in
[weather-radio.md](weather-radio.md).
