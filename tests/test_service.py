from datetime import datetime, timezone

from showradar import service
from showradar.store import apply_sync

from .conftest import make_event

T1, T2 = "2030-01-01T00:00:00+00:00", "2030-01-02T00:00:00+00:00"


def test_shows_merge_duplicates_and_search(store):
    apply_sync(store, [
        make_event("WAR", id="a", artists=("WAR",)),
        make_event("WAR  | Official Ticket + Hotel Packages", id="b", artists=("WAR",)),
        make_event("The War on Drugs", id="c", artists=("The War on Drugs",), venue="Arizona Financial Theatre"),
    ], T1)
    rows = service.shows(store)
    assert len(rows) == 2
    war = next(s for s in rows if s["title"] == "WAR")
    assert [x["kind"] for x in war["listings"]] == ["tickets", "hotel package"]
    assert [s["title"] for s in service.shows(store, q="financial")] == ["The War on Drugs"]


def test_follow_is_exact_not_prefix(store):
    apply_sync(store, [
        make_event("WAR", id="a", artists=("WAR",)),
        make_event("The War on Drugs", id="c", artists=("The War on Drugs",)),
    ], T1)
    store.follow("War")
    assert [s["title"] for s in service.shows(store, followed_only=True)] == ["WAR"]


def test_follow_matches_supporting_act_and_accents(store):
    apply_sync(store, [make_event("6LACK Tour", id="a", artists=("6LACK", "Eem Triplin")),
                       make_event("VALÉ", id="b", artists=())], T1)
    store.follow("eem triplin")
    store.follow("Vale")
    assert len(service.shows(store, followed_only=True)) == 2


def test_alerts_only_for_followed_and_once_per_show(store):
    apply_sync(store, [make_event("Kansas", id="k", artists=("Kansas",))], T1)
    store.follow("Kansas")
    apply_sync(store, [
        make_event("Kansas", id="k", artists=("Kansas",), status="cancelled"),
        make_event("Kansas | Official Ticket + Hotel Packages", id="k2", artists=("Kansas",)),
        make_event("Someone Else", id="s", artists=("Someone Else",), time="23:00:00"),
    ], T2)
    feed = service.alerts(store, now=datetime(2030, 1, 2, tzinfo=timezone.utc))
    assert sorted(a["kind"] for a in feed) == ["new", "status"]
    assert all(a["show"]["headliner"] == "Kansas" for a in feed)
    assert "cancelled" in service.describe(next(a for a in feed if a["kind"] == "status"))


def test_onsale_soon_alert(store):
    apply_sync(store, [make_event("Gilla Band", id="g", artists=("Gilla Band",), onsale="2030-01-02T17:00:00Z")], T1)
    store.follow("Gilla Band")
    soon = service.alerts(store, now=datetime(2030, 1, 1, 12, tzinfo=timezone.utc))
    assert [a["kind"] for a in soon] == ["onsale_soon"]
    later = service.alerts(store, now=datetime(2030, 1, 3, tzinfo=timezone.utc))
    assert later == []
