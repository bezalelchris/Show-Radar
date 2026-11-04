from showradar.store import apply_sync

from .conftest import make_event

T1, T2, T3 = "2030-01-01T00:00:00+00:00", "2030-01-02T00:00:00+00:00", "2030-01-03T00:00:00+00:00"


def kinds(changes):
    return sorted(c["kind"] for c in changes)


def test_first_sync_records_without_flooding_alerts(store):
    assert apply_sync(store, [make_event(id="a"), make_event(id="b")], T1) == []
    assert len(store.listings()) == 2
    assert store.last_sync()["fetched"] == 2


def test_detects_new_status_onsale_reschedule_and_price(store):
    apply_sync(store, [make_event(id="a"), make_event(id="b", price=(30, 30))], T1)
    changes = apply_sync(
        store,
        [
            make_event(id="a", status="rescheduled", date="2030-02-01", onsale="2029-12-05T17:00:00Z"),
            make_event(id="b", price=(25, 30)),
            make_event(id="c"),
        ],
        T2,
    )
    assert kinds(changes) == ["new", "onsale", "price", "rescheduled", "status"]
    price = next(c for c in changes if c["kind"] == "price")
    assert (price["old"], price["new"]) == ("$30.00", "$25.00-$30.00")


def test_unchanged_sync_is_quiet(store):
    events = [make_event(id="a", price=(20, 40))]
    apply_sync(store, events, T1)
    assert apply_sync(store, events, T2) == []


def test_price_disappearing_is_not_a_change(store):
    apply_sync(store, [make_event(id="a", price=(20, 40))], T1)
    assert apply_sync(store, [make_event(id="a")], T2) == []


def test_removed_and_reappearing_listing(store):
    apply_sync(store, [make_event(id="a"), make_event(id="b")], T1)
    assert kinds(apply_sync(store, [make_event(id="a")], T2)) == ["removed"]
    assert [x.id for x in store.listings()] == ["a"]
    assert apply_sync(store, [make_event(id="a"), make_event(id="b")], T3) == []
    assert len(store.listings()) == 2


def test_duplicate_ids_in_one_feed_are_ignored(store):
    apply_sync(store, [make_event(id="a"), make_event(id="a")], T1)
    assert len(store.listings()) == 1


def test_price_history(store):
    apply_sync(store, [make_event(id="a", price=(30, 30))], T1)
    apply_sync(store, [make_event(id="a", price=(25, 30))], T2)
    assert [h["price_min"] for h in store.price_history("a")] == [30, 25]
