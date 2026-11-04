"""Application logic shared by the CLI and the web API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import Settings
from .listing import Listing, fold
from .matching import group_shows
from .store import Store, apply_sync
from .ticketmaster import fetch_music_events

ONSALE_SOON = timedelta(hours=72)
# Event dates are Phoenix-local. Arizona doesn't observe DST, so a fixed offset is exact
# (and avoids needing the tzdata package on Windows).
PHOENIX_TZ = timezone(timedelta(hours=-7))


def sync(store: Store, settings: Settings) -> list[dict]:
    events = fetch_music_events(
        settings.api_key, settings.lat, settings.lon, settings.radius_miles, settings.max_pages
    )
    return apply_sync(store, events)


def _kind(listing: Listing) -> str:
    if listing.clean.is_addon:
        return "add-on"
    if listing.clean.is_package:
        return "hotel package"
    return "tickets"


def _matches_follow(show_names: set[str], follow_keys: set[str]) -> bool:
    # Exact match on folded names only: a prefix match would make "WAR" follow "War on Drugs".
    return bool(show_names & follow_keys)


def show_to_dict(group: list[Listing], follow_keys: set[str]) -> dict:
    primary = group[0]
    artists: list[str] = []
    for listing in group:
        for a in listing.artists:
            if fold(a) not in {fold(x) for x in artists}:
                artists.append(a)
    priced = [x for x in group if x.price_max is not None]
    names = {fold(a) for a in artists} | {fold(x.headliner) for x in group} | {fold(x.clean.headliner) for x in group}
    ages = sorted({x.clean.min_age for x in group if x.clean.min_age})
    flags = sorted({f for x in group for f in x.clean.flags})
    return {
        "id": primary.id,
        "title": primary.clean.title,
        "headliner": primary.headliner,
        "artists": artists,
        "venue": primary.venue,
        "city": primary.city,
        "date": primary.local_date,
        "time": primary.local_time[:5] if primary.local_time else None,
        "status": primary.status,
        "onsale_start": primary.onsale_start,
        "price_min": min((x.price_min for x in priced), default=None),
        "price_max": max((x.price_max for x in priced), default=None),
        "ages": ages,
        "flags": flags,
        "genre": next((x.genre for x in group if x.genre), None),
        "url": primary.url,
        "followed": _matches_follow(names, follow_keys),
        "listings": [{"id": x.id, "kind": _kind(x), "url": x.url, "name": x.name} for x in group],
    }


def shows(
    store: Store,
    q: str | None = None,
    followed_only: bool = False,
    genre: str | None = None,
    include_past: bool = False,
) -> list[dict]:
    follow_keys = {f["key"] for f in store.follows()}
    today = datetime.now(PHOENIX_TZ).date().isoformat()
    out = []
    for group in group_shows(store.listings()):
        s = show_to_dict(group, follow_keys)
        if not include_past and s["date"] and s["date"] < today:
            continue
        if followed_only and not s["followed"]:
            continue
        if genre and (s["genre"] or "").lower() != genre.lower():
            continue
        if q:
            hay = fold(" ".join([s["title"], s["venue"], *s["artists"]]))
            if not all(term in hay for term in fold(q).split()):
                continue
        out.append(s)
    return out


def alerts(store: Store, limit: int = 100, now: datetime | None = None) -> list[dict]:
    """Changes and upcoming on-sales for shows by artists you follow, newest first."""
    now = now or datetime.now(timezone.utc)
    followed = shows(store, followed_only=True, include_past=True)
    by_listing = {l["id"]: s for s in followed for l in s["listings"]}
    feed = []
    for c in store.changes(limit=1000):
        show = by_listing.get(c["listing_id"])
        if show is None:
            continue
        feed.append({**c, "show": show})
    for s in followed:
        if not s["onsale_start"]:
            continue
        start = datetime.fromisoformat(s["onsale_start"].replace("Z", "+00:00"))
        if now <= start <= now + ONSALE_SOON:
            feed.append({"kind": "onsale_soon", "detected_at": now.isoformat(), "old": None,
                         "new": s["onsale_start"], "listing_id": s["id"], "show": s})
    feed.sort(key=lambda a: a["detected_at"], reverse=True)
    # One alert per show per kind per sync: duplicate listings would otherwise repeat it.
    seen, unique = set(), []
    for a in feed:
        key = (a["show"]["id"], a["kind"], a["detected_at"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique[:limit]


def describe(alert: dict) -> str:
    s, k = alert["show"], alert["kind"]
    where = f"{s['title']} @ {s['venue']} on {s['date']}"
    return {
        "new": f"New show: {where}",
        "status": f"Status {alert['old']} -> {alert['new']}: {where}",
        "onsale": f"On-sale time changed to {alert['new']}: {where}",
        "onsale_soon": f"Tickets go on sale {alert['new']}: {where}",
        "rescheduled": f"Rescheduled {alert['old']} -> {alert['new']}: {s['title']} @ {s['venue']}",
        "price": f"Price {alert['old'] or 'n/a'} -> {alert['new']}: {where}",
        "removed": f"Listing removed: {where}",
    }.get(k, f"{k}: {where}")
