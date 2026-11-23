import io
import json
import unittest
from unittest import mock

from mesh_contingency import weather


class GetJsonTest(unittest.TestCase):
    def test_sends_user_agent_and_parses_json(self):
        with mock.patch("mesh_contingency.weather.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps({"ok": 1}).encode())
            self.assertEqual(weather._get_json("https://example.test/x"), {"ok": 1})
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://example.test/x")
        self.assertEqual(req.get_header("User-agent"), weather.USER_AGENT)
        self.assertEqual(req.get_header("Accept"), "application/geo+json")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], weather.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
