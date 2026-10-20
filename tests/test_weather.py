import io
import json
import unittest
import urllib.error
from unittest import mock

from mesh_contingency import weather


def http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "error", {}, io.BytesIO())


class FakeApi:
    """Routes weather._get_json URLs to canned responses or exceptions."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        for prefix, response in self.routes.items():
            if url.startswith(prefix):
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected URL {url}")


ZIP_RESPONSE = {"places": [{"place name": "Miami", "state abbreviation": "FL",
                            "latitude": "25.7743", "longitude": "-80.1937"}]}


def station(sid, name):
    return {"properties": {"stationIdentifier": sid, "name": name}}


def observation(temp_c=20.0):
    return {"properties": {"temperature": {"value": temp_c}, "textDescription": "Clear"}}


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


class ConversionTest(unittest.TestCase):
    def test_value(self):
        self.assertEqual(weather.value({"t": {"value": 3}}, "t"), 3)
        self.assertIsNone(weather.value({"t": {"value": None}}, "t"))
        self.assertIsNone(weather.value({"t": None}, "t"))
        self.assertIsNone(weather.value({}, "t"))
        self.assertIsNone(weather.value(None, "t"))

    def test_conversions(self):
        self.assertAlmostEqual(weather.c_to_f(100), 212)
        self.assertAlmostEqual(weather.c_to_f(-40), -40)
        self.assertAlmostEqual(weather.kmh_to_mph(100), 62.1371)
        self.assertAlmostEqual(weather.mm_to_in(25.4), 1)

    def test_conversions_pass_none_through(self):
        for fn in (weather.c_to_f, weather.kmh_to_mph, weather.mm_to_in):
            self.assertIsNone(fn(None))


class GeocodeZipTest(unittest.TestCase):
    def test_returns_lat_lon_and_place(self):
        api = FakeApi({weather.ZIP_API: ZIP_RESPONSE})
        with mock.patch("mesh_contingency.weather._get_json", api):
            self.assertEqual(weather.geocode_zip("33101"), (25.7743, -80.1937, "Miami, FL"))
        self.assertEqual(api.calls, [f"{weather.ZIP_API}/33101"])

    def test_unknown_zip_raises_value_error(self):
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({weather.ZIP_API: http_error(404)})):
            with self.assertRaisesRegex(ValueError, "unknown zipcode 00000"):
                weather.geocode_zip("00000")

    def test_other_http_errors_propagate(self):
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({weather.ZIP_API: http_error(500)})):
            with self.assertRaises(urllib.error.HTTPError):
                weather.geocode_zip("33101")


class LatestObservationTest(unittest.TestCase):
    STATIONS = "https://api.weather.gov/gridpoints/X/1,1/stations"

    def obs_url(self, sid):
        return f"{weather.NWS_API}/stations/{sid}/observations/latest"

    def test_returns_first_station_with_temperature(self):
        api = FakeApi({
            self.STATIONS: {"features": [station("A", "Alpha"), station("B", "Bravo")]},
            self.obs_url("A"): observation(21.0),
        })
        with mock.patch("mesh_contingency.weather._get_json", api):
            name, obs = weather.latest_observation(self.STATIONS)
        self.assertEqual(name, "Alpha")
        self.assertEqual(weather.value(obs, "temperature"), 21.0)
        self.assertNotIn(self.obs_url("B"), api.calls)

    def test_skips_missing_temperature_and_http_errors(self):
        api = FakeApi({
            self.STATIONS: {"features": [station("A", "Alpha"), station("B", "Bravo"), station("C", "Charlie")]},
            self.obs_url("A"): observation(None),
            self.obs_url("B"): http_error(404),
            self.obs_url("C"): observation(5.0),
        })
        with mock.patch("mesh_contingency.weather._get_json", api):
            name, _ = weather.latest_observation(self.STATIONS)
        self.assertEqual(name, "Charlie")

    def test_tries_at_most_max_stations(self):
        features = [station(f"S{i}", f"Station {i}") for i in range(weather.MAX_STATIONS + 2)]
        routes = {self.STATIONS: {"features": features}}
        routes.update({self.obs_url(f"S{i}"): observation(None) for i in range(len(features))})
        api = FakeApi(routes)
        with mock.patch("mesh_contingency.weather._get_json", api):
            self.assertEqual(weather.latest_observation(self.STATIONS), (None, None))
        self.assertEqual(len(api.calls), 1 + weather.MAX_STATIONS)


class PrecipChanceTest(unittest.TestCase):
    URL = "https://api.weather.gov/gridpoints/X/1,1/forecast/hourly"

    def periods(self, *chances):
        return {"properties": {"periods": [{"probabilityOfPrecipitation": {"value": c}} for c in chances]}}

    def test_max_over_next_hours(self):
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({self.URL: self.periods(5, 40, None, 10)})):
            self.assertEqual(weather.precip_chance(self.URL), 40)

    def test_only_first_pop_hours_count(self):
        chances = [0] * weather.POP_HOURS + [90]
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({self.URL: self.periods(*chances)})):
            self.assertEqual(weather.precip_chance(self.URL), 0)

    def test_none_when_no_values(self):
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({self.URL: self.periods(None, None)})):
            self.assertIsNone(weather.precip_chance(self.URL))

    def test_none_on_errors(self):
        for failure in (http_error(500), urllib.error.URLError("down")):
            with mock.patch("mesh_contingency.weather._get_json", FakeApi({self.URL: failure})):
                self.assertIsNone(weather.precip_chance(self.URL))
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({self.URL: {"unexpected": 1}})):
            self.assertIsNone(weather.precip_chance(self.URL))


class ActiveAlertsTest(unittest.TestCase):
    def test_returns_alert_properties_for_point(self):
        url = f"{weather.NWS_API}/alerts/active?point=25.7743,-80.1937"
        api = FakeApi({url: {"features": [{"properties": {"event": "Flood Warning"}}]}})
        with mock.patch("mesh_contingency.weather._get_json", api):
            self.assertEqual(weather.active_alerts(25.7743, -80.1937), [{"event": "Flood Warning"}])

    def test_no_features(self):
        with mock.patch("mesh_contingency.weather._get_json", FakeApi({weather.NWS_API: {}})):
            self.assertEqual(weather.active_alerts(1, 2), [])


class FetchWeatherTest(unittest.TestCase):
    def test_rejects_invalid_zipcodes_without_network(self):
        with mock.patch("mesh_contingency.weather._get_json") as get_json:
            for bad in ("abc", "1234", "123456", "", "12a45"):
                with self.assertRaisesRegex(ValueError, "invalid zipcode"):
                    weather.fetch_weather(bad)
        get_json.assert_not_called()

    def test_assembles_full_result(self):
        stations = "https://api.weather.gov/gridpoints/MFL/1,1/stations"
        hourly = "https://api.weather.gov/gridpoints/MFL/1,1/forecast/hourly"
        api = FakeApi({
            weather.ZIP_API: ZIP_RESPONSE,
            f"{weather.NWS_API}/points/25.7743,-80.1937": {
                "properties": {"observationStations": stations, "forecastHourly": hourly}},
            stations: {"features": [station("KMIA", "Miami Intl")]},
            f"{weather.NWS_API}/stations/KMIA/": observation(28.0),
            hourly: {"properties": {"periods": [{"probabilityOfPrecipitation": {"value": 20}}]}},
            f"{weather.NWS_API}/alerts/": {"features": [{"properties": {"event": "Rip Current Statement"}}]},
        })
        with mock.patch("mesh_contingency.weather._get_json", api):
            wx = weather.fetch_weather(" 33101 ")
        self.assertEqual(wx["zipcode"], "33101")
        self.assertEqual(wx["place"], "Miami, FL")
        self.assertEqual(wx["station"], "Miami Intl")
        self.assertEqual(weather.value(wx["obs"], "temperature"), 28.0)
        self.assertEqual(wx["pop"], 20)
        self.assertEqual(wx["alerts"], [{"event": "Rip Current Statement"}])


    def test_alerts_only(self):
        api = FakeApi({
            weather.ZIP_API: ZIP_RESPONSE,
            f"{weather.NWS_API}/alerts/": {"features": [{"properties": {"event": "Flood Warning"}}]},
        })
        with mock.patch("mesh_contingency.weather._get_json", api):
            self.assertEqual(weather.fetch_alerts("33101 "), ("33101", "Miami, FL", [{"event": "Flood Warning"}]))
        with self.assertRaisesRegex(ValueError, "invalid zipcode"):
            weather.fetch_alerts("331")

if __name__ == "__main__":
    unittest.main()
