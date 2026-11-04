"""Group listings that are the same performance.

Ticketmaster often lists one show several times: a ticket-only listing plus a
ticket + hotel package, a separate all-ages and 21+ listing from two ticketing
systems, or a VIP add-on. Meanwhile the same artist can genuinely play twice in
one day (early and late sets). The rules:

1. Only listings at the same venue (by name; IDs differ per ticketing system) on the same date can match.
2. Start times must be within MAX_START_GAP minutes. Early/late sets are usually
   1.5 to 2+ hours apart, so they stay separate.
3. The acts must match: shared Ticketmaster artist IDs, or headliner names that
   are near-identical once case, accents and punctuation are folded away.

Matches are merged with union-find, so A~B and B~C put A, B and C in one show.
"""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

from .listing import Listing, fold

MAX_START_GAP = 60  # minutes
NAME_SIMILARITY = 0.85


def _names_match(a: str, b: str) -> bool:
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return False
    if fa == fb or fa.startswith(fb + " ") or fb.startswith(fa + " "):
        return True
    return SequenceMatcher(None, fa, fb).ratio() >= NAME_SIMILARITY


def same_show(a: Listing, b: Listing) -> bool:
    if a.venue_key != b.venue_key or a.local_date != b.local_date:
        return False
    if a.minutes is not None and b.minutes is not None and abs(a.minutes - b.minutes) > MAX_START_GAP:
        return False
    if set(a.artist_ids) & set(b.artist_ids):
        return True
    return _names_match(a.headliner, b.headliner) or _names_match(a.clean.headliner, b.clean.headliner)


def group_shows(listings: list[Listing]) -> list[list[Listing]]:
    """Cluster listings into shows. Each show's primary (ticket-only) listing comes first."""
    parent = list(range(len(listings)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Only compare within a venue+date bucket: O(n * bucket) instead of O(n^2).
    buckets: dict[tuple[str, str | None], list[int]] = defaultdict(list)
    for i, listing in enumerate(listings):
        buckets[(listing.venue_key, listing.local_date)].append(i)
    for idxs in buckets.values():
        for x, i in enumerate(idxs):
            for j in idxs[x + 1 :]:
                if same_show(listings[i], listings[j]):
                    parent[find(i)] = find(j)

    groups: dict[int, list[Listing]] = defaultdict(list)
    for i, listing in enumerate(listings):
        groups[find(i)].append(listing)

    def rank(listing: Listing) -> tuple:
        # Prefer a plain ticket listing with real prices and artist data as the primary.
        return (listing.clean.is_addon, listing.clean.is_package, listing.price_max is None, not listing.artists)

    shows = [sorted(g, key=rank) for g in groups.values()]
    shows.sort(key=lambda g: (g[0].local_date or "9999", g[0].local_time or "", g[0].venue))
    return shows
