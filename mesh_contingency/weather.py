"""Look up current conditions and active alerts for a US zipcode or county via api.weather.gov."""

import json
import urllib.error
import urllib.request

# api.weather.gov rejects requests without a User-Agent identifying the app.
USER_AGENT = "mesh-contingency (weather lookup)"
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


# State FIPS codes, which NWS alerts use (with the county's) to list the counties they cover.
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11",
    "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30",
    "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56", "AS": "60", "GU": "66", "MP": "69",
    "PR": "72", "VI": "78",
}
STATES_BY_FIPS = {fips: state for state, fips in STATE_FIPS.items()}


def county_code(name, state):
    """Return the NWS code of a county, e.g. "TXC441" for ("Taylor", "TX").
    Raises ValueError if the state has no county by that name."""
    data = _get_json(f"{NWS_API}/zones?type=county&area={state}")
    for feature in data.get("features", []):
        if feature["properties"].get("name", "").lower() == name.lower():
            return feature["properties"]["id"]
    raise ValueError(f"the NWS has no county {name!r} in {state}")


def county_alerts(codes):
    """Return the active alerts for any of these counties (NWS codes), in
    one request. The NWS includes alerts issued for the forecast zones that
    overlap them."""
    data = _get_json(f"{NWS_API}/alerts/active?zone={','.join(codes)}")
    return [f["properties"] for f in data.get("features", [])]


def alert_counties(alert):
    """The NWS codes of the counties an alert (its properties) covers, from
    its county codes and the FIPS codes it lists."""
    geocode = alert.get("geocode") or {}
    codes = {ugc for ugc in geocode.get("UGC") or [] if len(ugc) == 6 and ugc[2] == "C"}
    for same in geocode.get("SAME") or []:  # "048441": 0, the state's FIPS, the county's
        state = STATES_BY_FIPS.get(same[1:3])
        if state and len(same) == 6:
            codes.add(f"{state}C{same[3:]}")
    return codes


def check_zip(zipcode):
    """Return the zipcode without surrounding spaces; raise ValueError unless it is 5 digits."""
    zipcode = zipcode.strip()
    if not (zipcode.isdigit() and len(zipcode) == 5):
        raise ValueError(f"invalid zipcode {zipcode!r}; expected 5 digits")
    return zipcode


def _weather_at(lat, lon):
    """The station, latest observation and precip chance nearest a point."""
    point = _get_json(f"{NWS_API}/points/{lat:.4f},{lon:.4f}")["properties"]
    station, obs = latest_observation(point["observationStations"])
    return {"station": station, "obs": obs, "pop": precip_chance(point["forecastHourly"])}


def fetch_weather(zipcode):
    """Return a dict of current conditions, precip chance and alerts for a zipcode."""
    zipcode = check_zip(zipcode)
    lat, lon, place = geocode_zip(zipcode)
    return {"where": zipcode, "place": place, **_weather_at(lat, lon), "alerts": active_alerts(lat, lon)}


def fetch_county_weather(code):
    """Like fetch_weather, for a county (its NWS code, e.g. "TXC441"): the
    conditions nearest its middle and the alerts for the county."""
    try:
        zone = _get_json(f"{NWS_API}/zones/county/{code}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"unknown county code {code}") from e
        raise
    lat, lon = _middle(zone["geometry"])
    where = f"{zone['properties']['name']}, {zone['properties']['state']}"
    return {"where": where, "place": code, **_weather_at(lat, lon), "alerts": county_alerts([code])}


def compass(degrees):
    """The compass point of a wind direction in degrees, e.g. "SSE", or ""."""
    if degrees is None:
        return ""
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return points[round(degrees / 22.5) % 16]


def _middle(geometry):
    """(lat, lon) of the middle of a zone's outline."""
    rings = [geometry["coordinates"][0]] if geometry["type"] == "Polygon" else \
        [polygon[0] for polygon in geometry["coordinates"]]
    corners = [corner for ring in rings for corner in ring]
    return sum(c[1] for c in corners) / len(corners), sum(c[0] for c in corners) / len(corners)


def county_point(code):
    """Where to ask about a county's weather: {"lat", "lon"} (its middle,
    from its outline), "place" (the town the NWS names nearest that point),
    "forecast" (the URL of its forecast) and "stations" ([[id, name]] of the
    nearest stations)."""
    lat, lon = _middle(_get_json(f"{NWS_API}/zones/county/{code}")["geometry"])
    point = _get_json(f"{NWS_API}/points/{lat:.4f},{lon:.4f}")["properties"]
    near = point["relativeLocation"]["properties"]
    stations = _get_json(point["observationStations"])["features"][:MAX_STATIONS]
    return {
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "place": f"{near['city']}, {near['state']}",
        "forecast": point["forecast"],
        "stations": [[s["properties"]["stationIdentifier"], s["properties"]["name"]] for s in stations],
    }


def area_conditions(point, periods):
    """The weather now at a county_point: the latest observation from the
    nearest station that has one, and the next periods of the forecast, as
    {"station", "observed" (ISO time), "text", "temp_f", "feels_f",
    "humidity", "wind_mph", "gust_mph", "wind_dir", "periods": [{"name",
    "temp", "unit", "text", "pop", "wind"}]}. Missing numbers are None."""
    station, obs = None, None
    for sid, name in point["stations"]:
        try:
            found = _get_json(f"{NWS_API}/stations/{sid}/observations/latest")["properties"]
        except urllib.error.HTTPError as e:  # a station that's down: try the next
            e.close()
            continue
        if value(found, "temperature") is not None:
            station, obs = name, found
            break
    forecast = _get_json(point["forecast"])["properties"]["periods"][:periods]
    feels = value(obs, "heatIndex") or value(obs, "windChill")
    return {
        "station": station,
        "observed": (obs or {}).get("timestamp"),
        "text": (obs or {}).get("textDescription") or None,
        "temp_f": c_to_f(value(obs, "temperature")),
        "feels_f": c_to_f(feels),
        "humidity": value(obs, "relativeHumidity"),
        "wind_mph": kmh_to_mph(value(obs, "windSpeed")),
        "gust_mph": kmh_to_mph(value(obs, "windGust")),
        "wind_dir": compass(value(obs, "windDirection")) or None,
        "periods": [{"name": p["name"], "temp": p["temperature"], "unit": p["temperatureUnit"],
                     "text": p["shortForecast"], "pop": value(p, "probabilityOfPrecipitation"),
                     "wind": " ".join(filter(None, (p.get("windDirection"), p.get("windSpeed")))) or None}
                    for p in forecast],
    }
