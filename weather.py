"""Look up current conditions and active alerts for a US zipcode via api.weather.gov."""

import json
import urllib.error
import urllib.request

# api.weather.gov rejects requests without a User-Agent identifying the app.
USER_AGENT = "meshcore-listener (weather lookup)"
NWS_API = "https://api.weather.gov"
# api.weather.gov has no zipcode lookup, so resolve the zip to lat/lon first.
ZIP_API = "https://api.zippopotam.us/us"
TIMEOUT = 10
# How many nearby stations to try before giving up on an observation.
MAX_STATIONS = 3
# Hours of the hourly forecast to scan for the chance of precipitation.
POP_HOURS = 6


def _get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def value(obs, field):
    """Return the numeric value of an observation field, or None."""
    return ((obs or {}).get(field) or {}).get("value")


def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32


def kmh_to_mph(kmh):
    return None if kmh is None else kmh * 0.621371


def mm_to_in(mm):
    return None if mm is None else mm / 25.4


def geocode_zip(zipcode):
    """Return (lat, lon, "City, ST") for a US zipcode."""
    try:
        data = _get_json(f"{ZIP_API}/{zipcode}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"unknown zipcode {zipcode}") from e
        raise
    place = data["places"][0]
    name = f"{place['place name']}, {place['state abbreviation']}"
    return float(place["latitude"]), float(place["longitude"]), name


def latest_observation(stations_url):
    """Return (station name, observation properties) from the nearest reporting station."""
    stations = _get_json(stations_url)["features"][:MAX_STATIONS]
    for station in stations:
        sid = station["properties"]["stationIdentifier"]
        try:
            obs = _get_json(f"{NWS_API}/stations/{sid}/observations/latest")["properties"]
        except urllib.error.HTTPError:
            continue
        # Stations sometimes report an observation with no temperature; try the next one.
        if value(obs, "temperature") is not None:
            return station["properties"]["name"], obs
    return None, None


def precip_chance(hourly_url):
    """Return the highest chance of precipitation (%) over the next POP_HOURS, or None."""
    try:
        periods = _get_json(hourly_url)["properties"]["periods"][:POP_HOURS]
    except (urllib.error.URLError, KeyError):
        # The gridpoint forecast endpoint is flaky; precip chance is optional.
        return None
    chances = [value(p, "probabilityOfPrecipitation") for p in periods]
    chances = [c for c in chances if c is not None]
    return max(chances) if chances else None


def active_alerts(lat, lon):
    """Return the active (current and upcoming) alerts covering a point."""
    data = _get_json(f"{NWS_API}/alerts/active?point={lat:.4f},{lon:.4f}")
    return [f["properties"] for f in data.get("features", [])]


def fetch_weather(zipcode):
    """Return a dict of current conditions, precip chance and alerts for a zipcode."""
    zipcode = zipcode.strip()
    if not (zipcode.isdigit() and len(zipcode) == 5):
        raise ValueError(f"invalid zipcode {zipcode!r}; expected 5 digits")

    lat, lon, place = geocode_zip(zipcode)
    point = _get_json(f"{NWS_API}/points/{lat:.4f},{lon:.4f}")["properties"]
    station, obs = latest_observation(point["observationStations"])
    return {
        "zipcode": zipcode,
        "place": place,
        "station": station,
        "obs": obs,
        "pop": precip_chance(point["forecastHourly"]),
        "alerts": active_alerts(lat, lon),
    }
