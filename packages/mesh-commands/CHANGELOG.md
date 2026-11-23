# Changelog

## 0.1.0 - 2026-11-23

Released with Mesh Contingency 1.0.0, in its repository (not on PyPI).

First version, taken out of Mesh Contingency 0.12 (its `api.py`,
`registry.py`, `running.py`, `limits.py`, `output.py`, `testing.py`, the `help`
command and the direct-message handling in `bot.py`).

The changes from that code:
- `Context` has `roles` (any object with `is_user`/`is_admin`; `KeyRoles` for
  two sets of keys) and an `extras` dict, in place of Mesh Contingency's
  users, admins, state and limits.
- `Registry` takes the entry point group, and optionally the limits and the
  names of retired commands.
- `Registry.build(radio, roles, send, extras)` replaces `build(admins, radio, state, send)`.
- `Dispatcher` and `MeshLink` are new: the direct-message handling from the bot.
- `SafeOutput` no longer keeps lines for listeners.
