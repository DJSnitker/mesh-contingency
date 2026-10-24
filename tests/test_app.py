"""Checks on the phone app (app/) that its own tests can't make."""

import json
import unittest
from pathlib import Path

from mesh_contingency.radio_presets import PRESETS

ROOT = Path(__file__).resolve().parent.parent


class SharedWithConsoleTest(unittest.TestCase):
    def test_icons_are_the_consoles(self):
        # The app keeps a copy of the console's icons: compiling the console's
        # file from the app would bring in a second Angular from
        # console/node_modules, which breaks at run time. So the copy must
        # stay the same; change both together.
        console = (ROOT / "console/src/app/icon.ts").read_text(encoding="utf-8")
        app = (ROOT / "app/src/app/icon.ts").read_text(encoding="utf-8")
        self.assertEqual(app, console, "app/src/app/icon.ts differs from console/src/app/icon.ts; copy it over")

    def test_app_uses_the_consoles_styles(self):
        # The palette, type, panels and buttons are the console's own file.
        angular = (ROOT / "app/angular.json").read_text(encoding="utf-8")
        self.assertIn('"../console/src/styles.scss"', angular)


    def test_presets_are_the_bots(self):
        # The Radio tab offers the same MeshCore presets as the bot's radio
        # command, from a copy: change radio_presets.py, then the copy.
        app = json.loads((ROOT / "app/src/app/radio/presets.json").read_text(encoding="utf-8"))["presets"]
        self.assertEqual([(p["title"], p["freq"], p["bw"], p["sf"], p["cr"]) for p in app],
                         [preset[:5] for preset in PRESETS],
                         "app/src/app/radio/presets.json differs from radio_presets.py; copy it over")

if __name__ == "__main__":
    unittest.main()
