## What this changes

<!-- What and why, in a few sentences. Link any issue it fixes: "Fixes #12". -->

## Checklist

- [ ] Tests pass: `python -m unittest`
- [ ] Lint passes: `ruff check .`
- [ ] New or changed behavior has tests
- [ ] `config.example.toml` and the README are updated if commands or config changed
- [ ] New commands are registered under `[project.entry-points."mesh_contingency.commands"]` and have a `[commands]` entry in `config.example.toml`
- [ ] No real data: no `config.toml` or `users.toml`, real email addresses, node keys, names or credentials (tests and examples use placeholders such as `example.com` and `"d0" * 32`)
