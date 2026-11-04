import itertools

import pytest

from showradar.store import Store

_ids = itertools.count(1)


def make_event(
    name="Test Artist",
    *,
    id=None,
    venue="Crescent Ballroom",
    venue_id="V1",
    date="2030-01-10",
    time="20:00:00",
    status="onsale",
    onsale="2029-12-01T17:00:00Z",
    price=None,
    artists=("Test Artist",),
    genre="Rock",
):
    """A Ticketmaster Discovery event with only the fields Show Radar reads."""
    e = {
        "id": id or f"E{next(_ids)}",
        "name": name,
        "url": "https://www.ticketmaster.com/event/x",
        "dates": {"start": {"localDate": date, "localTime": time}, "status": {"code": status}},
        "sales": {"public": {"startDateTime": onsale}},
        "classifications": [{"genre": {"name": genre}}],
        "_embedded": {
            "venues": [{"id": venue_id, "name": venue, "city": {"name": "Phoenix"}}],
            "attractions": [{"id": f"A-{a}", "name": a} for a in artists],
        },
    }
    if price is not None:
        e["priceRanges"] = [{"type": "standard", "currency": "USD", "min": price[0], "max": price[1]}]
    return e


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()
