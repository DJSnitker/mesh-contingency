import json
import tempfile
import unittest
from pathlib import Path

from mesh_contingency.state import State, Store, StoreError, duration


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "data.json"

    def test_missing_file_is_empty(self):
        self.assertEqual(Store(self.path).data, {})
        self.assertFalse(self.path.exists())  # not created until saved

    def test_saved_data_is_read_back(self):
        store = Store(self.path)
        store.data["k"] = {"text": "héllo"}
        store.save()
        self.assertEqual(Store(self.path).data, {"k": {"text": "héllo"}})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.folder.iterdir()), [self.path])  # no temporary file left

    def test_unreadable_file(self):
        for text in ("{not json", "[1, 2]"):
            self.path.write_text(text)
            with self.subTest(text=text), self.assertRaisesRegex(StoreError, "data.json"):
                Store(self.path)

    def test_in_memory(self):
        store = Store()
        store.data["k"] = 1
        store.save()  # nothing to write
        self.assertEqual(store.data, {"k": 1})


class StateTest(unittest.TestCase):
    def test_stores_are_shared_and_kept_in_data_dir(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        state = State(folder)
        self.assertIs(state.store("a.json"), state.store("a.json"))
        state.store("a.json").data["x"] = 1
        state.store("a.json").save()
        self.assertEqual(json.loads((folder / "a.json").read_text()), {"x": 1})
        self.assertEqual(State(folder).store("a.json").data, {"x": 1})  # after a restart


class DurationTest(unittest.TestCase):
    def test_duration(self):
        for seconds, text in [(59, "0m"), (300, "5m"), (3 * 3600 + 300, "3h 5m"), (2 * 86400 + 3 * 3600, "2d 3h")]:
            self.assertEqual(duration(seconds), text)


if __name__ == "__main__":
    unittest.main()
