"""The README and config.example.toml list every command with the same
permissions, and every command the package declares."""

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
WHO = {"public": "anyone", "user": "users", "admin": "admins"}


def example_commands():
    """{command: permission} from config.example.toml's [commands]."""
    commands = tomllib.loads((ROOT / "config.example.toml").read_text())["commands"]
    return {name: entry["permission"] for name, entry in commands.items()}


def readme_config_commands():
    """{command: permission} from the README's ```toml block with [commands]."""
    blocks = re.findall(r"```toml\n(.*?)```", README, re.S)
    (block,) = [b for b in blocks if b.startswith("[commands]\n")]
    return {name: entry["permission"] for name, entry in tomllib.loads(block)["commands"].items()}


def readme_table():
    """{command: who} from the README's command table."""
    table = README[README.index("| Command | Who can run it"):]
    table = table[:table.index("\n\n")]
    rows = {}
    for line in table.splitlines()[2:]:
        command, who = (cell.strip() for cell in line.split("|")[1:3])
        rows[re.match(r"`(\w+)", command).group(1)] = who
    return rows


class DocsTest(unittest.TestCase):
    def test_example_config_has_every_command(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        declared = set(project["entry-points"]["mesh_contingency.commands"])
        self.assertEqual(set(example_commands()), declared)

    def test_readme_config_matches_the_example(self):
        self.assertEqual(readme_config_commands(), example_commands())

    def test_readme_table_matches_the_example(self):
        self.assertEqual(readme_table(), {name: WHO[permission] for name, permission in example_commands().items()})


if __name__ == "__main__":
    unittest.main()
