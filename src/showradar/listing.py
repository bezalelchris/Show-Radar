"""Turn a raw Ticketmaster event into a clean Listing.

Event names in the wild carry a lot of clutter:
    "Jason DeRulo | Official Ticket + Hotel Packages"
    "SUPERTASTE - Ages 21+"
    "OLIVIA O'BRIEN : THE PIXIE TOUR *POSTPONED TO 2027*"
    "Syd - Early Entry VIP Upgrade"
`clean_name` pulls that clutter out into structured fields so listings can be
compared, deduplicated and displayed properly.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

PACKAGE_RE = re.compile(r"\s*\|\s*official\b.*\bpackages?\b.*$", re.IGNORECASE)
ADDON_RE = re.compile(r"\s*[-:|]?\s*\b(?:early entry|vip|upgrade|parking|meet\s*&?\s*greet)\b.*$", re.IGNORECASE)
AGE_RES = [
    re.compile(r"\s*[-–(]?\s*ages?\s*(\d{2})\s*\+?\s*\)?", re.IGNORECASE),
    re.compile(r"\s*\(\s*(\d{2})\s*\+?\s*(?:event)?\s*\)", re.IGNORECASE),
    re.compile(r"\s*\(\s*(\d{2})\s*(?:and|&)\s*over\s*\)", re.IGNORECASE),
    re.compile(r"\s*[-–]\s*(\d{2})\s*\+", re.IGNORECASE),
]
FLAG_RE = re.compile(r"\s*\*+\s*([^*]+?)\s*\*+", re.IGNORECASE)
TOUR_SPLIT_RE = re.compile(r"\s+[-–:]\s+|:\s+|\s+w/\s+", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


@dataclass
class CleanName:
    title: str  # display title with clutter removed
    headliner: str  # best guess at the main act from the name alone
    min_age: int | None = None
    is_package: bool = False  # ticket + hotel bundle
    is_addon: bool = False  # VIP / early-entry upgrade, not a ticket on its own
    flags: list[str] = field(default_factory=list)  # e.g. ["sold out", "postponed to 2027"]


def fold(text: str) -> str:
    """Case- and accent-insensitive comparison key: 'VALÉ' -> 'vale'."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return SPACE_RE.sub(" ", re.sub(r"[^\w&+ ]", " ", no_accents.casefold())).strip()


def clean_name(name: str) -> CleanName:
    s = name.replace("’", "'").replace("???", "'")
    flags = [m.group(1).strip().lower() for m in FLAG_RE.finditer(s)]
    s = FLAG_RE.sub(" ", s)

    is_package = bool(PACKAGE_RE.search(s))
    s = PACKAGE_RE.sub("", s)

    is_addon = bool(ADDON_RE.search(s))
    s = ADDON_RE.sub("", s)

    min_age = None
    for rx in AGE_RES:
        if m := rx.search(s):
            min_age = int(m.group(1))
            s = rx.sub("", s, count=1)
            break

    title = SPACE_RE.sub(" ", s).strip(" -–:|,")
    headliner = TOUR_SPLIT_RE.split(title, maxsplit=1)[0].strip(" -–:|,") or title
    return CleanName(title, headliner, min_age, is_package, is_addon, flags)


@dataclass
class Listing:
    id: str
    name: str
    url: str
    venue: str
    venue_id: str
    city: str
    local_date: str | None
    local_time: str | None
    status: str
    onsale_start: str | None  # UTC ISO timestamp of the public on-sale
    price_min: float | None
    price_max: float | None
    genre: str | None
    artists: list[str]
    artist_ids: list[str]
    clean: CleanName

    @property
    def headliner(self) -> str:
        """Structured artist data beats parsing the name, when Ticketmaster has it."""
        return self.artists[0] if self.artists else self.clean.headliner

    @property
    def venue_key(self) -> str:
        """Venue identity across ticketing systems.

        Ticketmaster, TicketWeb and Eventim each assign their own venue ID, so one room
        shows up under several IDs. The folded venue name is the stable key.
        """
        return fold(self.venue)

    @property
    def minutes(self) -> int | None:
        if not self.local_time:
            return None
        h, m, *_ = (int(x) for x in self.local_time.split(":"))
        return h * 60 + m


def _real_prices(event: dict) -> tuple[float | None, float | None]:
    ranges = [r for r in event.get("priceRanges") or [] if (r.get("max") or 0) > 0]
    if not ranges:
        return None, None  # $0-$0 ranges are placeholders, not free shows
    return min(r.get("min") or r["max"] for r in ranges), max(r["max"] for r in ranges)


def from_event(event: dict) -> Listing:
    emb = event.get("_embedded", {})
    venue = (emb.get("venues") or [{}])[0]
    attractions = emb.get("attractions") or []
    start = event.get("dates", {}).get("start", {})
    genre = ((event.get("classifications") or [{}])[0].get("genre") or {}).get("name")
    pmin, pmax = _real_prices(event)
    return Listing(
        id=event["id"],
        name=event.get("name", ""),
        url=event.get("url", ""),
        venue=venue.get("name", "Unknown venue"),
        venue_id=venue.get("id", ""),
        city=(venue.get("city") or {}).get("name", ""),
        local_date=start.get("localDate"),
        local_time=start.get("localTime"),
        status=event.get("dates", {}).get("status", {}).get("code", "unknown"),
        onsale_start=event.get("sales", {}).get("public", {}).get("startDateTime"),
        price_min=pmin,
        price_max=pmax,
        genre=None if genre in (None, "Undefined", "Other") else genre,
        artists=[a.get("name", "") for a in attractions if a.get("name")],
        artist_ids=[a["id"] for a in attractions if a.get("id")],
        clean=clean_name(event.get("name", "")),
    )
