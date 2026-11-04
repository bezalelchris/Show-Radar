"""Probe the Ticketmaster Discovery API: what price data comes back for Phoenix-area concerts?

Usage:  python scripts/probe_prices.py
Reads TICKETMASTER_API_KEY from .env. Uses only the standard library.
Saves the raw events to data/phoenix_events.json for inspection.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://app.ticketmaster.com/discovery/v2/events.json"
PHOENIX = (33.4484, -112.0740)
RADIUS_MILES = 40  # covers Tempe, Mesa, Scottsdale, Glendale
PAGE_SIZE = 200
MAX_PAGES = 3  # 3 calls, well under the 5,000/day quota


def load_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "TICKETMASTER_API_KEY" and v.strip():
                return v.strip()
    key = os.environ.get("TICKETMASTER_API_KEY", "").strip()
    if not key:
        sys.exit("No key found. Copy .env.example to .env and set TICKETMASTER_API_KEY.")
    return key


def geohash(lat: float, lon: float, precision: int = 9) -> str:
    """Encode lat/lon as a geohash (the Discovery API's geoPoint parameter)."""
    alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit, ch, even, out = [16, 8, 4, 2, 1], 0, 0, True, []
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if val > mid:
            ch |= bits[bit]
            rng[0] = mid
        else:
            rng[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(alphabet[ch])
            bit, ch = 0, 0
    return "".join(out)


def fetch_page(key: str, page: int) -> dict:
    params = {
        "apikey": key,
        "classificationName": "music",
        "geoPoint": geohash(*PHOENIX),
        "radius": RADIUS_MILES,
        "unit": "miles",
        "size": PAGE_SIZE,
        "page": page,
        "sort": "date,asc",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            remaining = r.headers.get("Rate-Limit-Available")
            body = json.load(r)
            body["_quota_remaining"] = remaining
            return body
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("401 Unauthorized: the key was rejected. Check TICKETMASTER_API_KEY in .env.")
        if e.code == 429:
            sys.exit("429 Too Many Requests: rate limit hit. Wait a bit and retry.")
        sys.exit(f"HTTP {e.code}: {e.read()[:300]!r}")


def summarize(event: dict) -> dict:
    venue = (event.get("_embedded", {}).get("venues") or [{}])[0]
    artists = [a.get("name") for a in event.get("_embedded", {}).get("attractions", [])]
    return {
        "name": event.get("name"),
        "date": event.get("dates", {}).get("start", {}).get("localDate"),
        "venue": venue.get("name"),
        "city": venue.get("city", {}).get("name"),
        "artists": artists,
        "price_ranges": event.get("priceRanges"),
        "status": event.get("dates", {}).get("status", {}).get("code"),
        "on_sale": event.get("sales", {}).get("public", {}).get("startDateTime"),
    }


def main() -> None:
    key = load_key()
    events, total, quota = [], None, None
    for page in range(MAX_PAGES):
        body = fetch_page(key, page)
        total = body.get("page", {}).get("totalElements", 0)
        quota = body.get("_quota_remaining")
        batch = body.get("_embedded", {}).get("events", [])
        events.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.3)  # stay under 5 requests/second

    rows = [summarize(e) for e in events]
    out = ROOT / "data" / "phoenix_events.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"total": total, "events": events}, indent=2))

    with_price = [r for r in rows if r["price_ranges"]]
    with_artist = [r for r in rows if r["artists"]]
    price_types = Counter(p.get("type") for r in with_price for p in r["price_ranges"])
    pct = lambda n: f"{100 * n / max(len(rows), 1):.0f}%"

    print(f"\nPhoenix-area music events: {total} total, {len(rows)} fetched")
    print(f"  with price ranges : {len(with_price)} ({pct(len(with_price))})  types: {dict(price_types)}")
    print(f"  with artist info  : {len(with_artist)} ({pct(len(with_artist))})")
    print(f"  venues            : {len({r['venue'] for r in rows})}")
    print(f"  statuses          : {dict(Counter(r['status'] for r in rows))}")
    print(f"  quota remaining   : {quota}")

    print("\nSample events WITH prices:")
    for r in with_price[:8]:
        p = r["price_ranges"][0]
        print(f"  {r['date']}  {p.get('min')}-{p.get('max')} {p.get('currency')}  {r['name'][:45]:45}  @ {r['venue']}")
    print("\nSample events WITHOUT prices:")
    for r in [r for r in rows if not r["price_ranges"]][:5]:
        print(f"  {r['date']}  {r['name'][:55]:55}  @ {r['venue']}")
    print(f"\nRaw data saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
