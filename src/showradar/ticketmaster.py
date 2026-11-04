"""Minimal Ticketmaster Discovery API client (stdlib only).

Default quota is 5,000 calls/day and 5 requests/second, so pagination is throttled.
The API refuses deep pagination (size * page must stay under 1,000), which caps one
query at ~1,000 events; that's plenty for one metro area.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

API = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MIN_INTERVAL = 0.25  # seconds between requests (<= 4 req/s)


class TicketmasterError(RuntimeError):
    pass


def geohash(lat: float, lon: float, precision: int = 9) -> str:
    """Encode a point as a geohash, the format the API's geoPoint parameter expects."""
    alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit, ch, even, out = (16, 8, 4, 2, 1), 0, 0, True, []
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if val > mid:
            ch |= bits[bit]
            rng[0] = mid
        else:
            rng[1] = mid
        even, bit = not even, bit + 1
        if bit == 5:
            out.append(alphabet[ch])
            bit, ch = 0, 0
    return "".join(out)


def _http_get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise TicketmasterError("Ticketmaster rejected the API key (401). Check TICKETMASTER_API_KEY.") from e
        if e.code == 429:
            raise TicketmasterError("Ticketmaster rate limit hit (429). Try again later.") from e
        raise TicketmasterError(f"Ticketmaster HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise TicketmasterError(f"Could not reach Ticketmaster: {e.reason}") from e


def fetch_music_events(
    api_key: str,
    lat: float,
    lon: float,
    radius_miles: int = 40,
    max_pages: int = 5,
    get: Callable[[str], dict] = _http_get,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """All music events near (lat, lon), oldest first. `get`/`sleep` are injectable for tests."""
    if not api_key:
        raise TicketmasterError("TICKETMASTER_API_KEY is not set. Copy .env.example to .env and add your key.")
    events: list[dict] = []
    for page in range(max_pages):
        if page:
            sleep(MIN_INTERVAL)
        params = {
            "apikey": api_key,
            "classificationName": "music",
            "geoPoint": geohash(lat, lon),
            "radius": radius_miles,
            "unit": "miles",
            "size": PAGE_SIZE,
            "page": page,
            "sort": "date,asc",
        }
        body = get(f"{API}?{urllib.parse.urlencode(params)}")
        batch = body.get("_embedded", {}).get("events", [])
        events.extend(e for e in batch if not e.get("test"))
        total_pages = body.get("page", {}).get("totalPages", 0)
        if len(batch) < PAGE_SIZE or page + 1 >= total_pages:
            break
    return events
