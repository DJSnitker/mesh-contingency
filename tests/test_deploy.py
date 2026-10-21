import configparser
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "/path/to/mesh-contingency"


class ServiceFileTest(unittest.TestCase):
    def setUp(self):
        self.unit = configparser.ConfigParser(strict=False, interpolation=None)
        self.unit.optionxform = str  # systemd keys are case-sensitive
        self.unit.read(ROOT / "deploy" / "mesh-contingency.service")

    def test_runs_the_installed_command_from_the_project_folder(self):
        scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
        service = self.unit["Service"]
        self.assertEqual(service["WorkingDirectory"], PLACEHOLDER)
        command = service["ExecStart"]
        self.assertTrue(command.startswith(f"{PLACEHOLDER}/.venv/bin/"), command)
        self.assertIn(command.rsplit("/", 1)[1], scripts)

    def test_restarts_after_failures_and_starts_at_boot(self):
        self.assertEqual(self.unit["Service"]["Restart"], "on-failure")
        self.assertEqual(self.unit["Unit"]["StartLimitIntervalSec"], "0")
        self.assertEqual(self.unit["Install"]["WantedBy"], "default.target")

    def test_the_install_command_in_the_file_fills_in_the_placeholder(self):
        text = (ROOT / "deploy" / "mesh-contingency.service").read_text()
        self.assertIn(f'sed "s|{PLACEHOLDER}|$PWD|g"', text)


if __name__ == "__main__":
    unittest.main()
