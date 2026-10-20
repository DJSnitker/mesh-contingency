import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.state import State, Store, StoreError, ago


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

    def test_seen_most_recent_last(self):
        state = State()
        with mock.patch("mesh_contingency.state.time.time", side_effect=[1, 2, 3]):
            state.saw("a", "Alice")
            state.saw("b", "Bob")
            state.saw("a", "Alice")
        self.assertEqual(list(state.seen.items()), [("b", ("Bob", 2)), ("a", ("Alice", 3))])


class AgoTest(unittest.TestCase):
    def test_ago(self):
        for seconds, text in [(5, "just now"), (60, "1m ago"), (3599, "59m ago"), (7200, "2h ago"),
                              (3 * 86400, "3d ago")]:
            self.assertEqual(ago(1000, now=1000 + seconds), text)


if __name__ == "__main__":
    unittest.main()
