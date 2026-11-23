"""Active alerts for US counties from the National Weather Service (api.weather.gov)."""

import json
import urllib.request

# api.weather.gov rejects requests without a User-Agent identifying the app.
USER_AGENT = "mesh-contingency (weather alerts)"
NWS_API = "https://api.weather.gov"
TIMEOUT = 10


def _get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


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
