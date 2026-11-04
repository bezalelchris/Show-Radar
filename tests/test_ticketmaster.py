import pytest

from showradar.ticketmaster import PAGE_SIZE, TicketmasterError, fetch_music_events, geohash

from .conftest import make_event


def test_geohash_known_value():
    assert geohash(57.64911, 10.40744, 11) == "u4pruydqqvj"


def test_paginates_filters_test_events_and_throttles():
    pages = [
        {"_embedded": {"events": [make_event() for _ in range(PAGE_SIZE - 1)] + [{**make_event(), "test": True}]},
         "page": {"totalPages": 2}},
        {"_embedded": {"events": [make_event() for _ in range(5)]}, "page": {"totalPages": 2}},
    ]
    urls, sleeps = [], []

    def get(url):
        urls.append(url)
        return pages[len(urls) - 1]

    events = fetch_music_events("KEY", 33.4, -112.0, get=get, sleep=sleeps.append)
    assert len(events) == PAGE_SIZE - 1 + 5
    assert len(urls) == 2 and "classificationName=music" in urls[0] and "page=1" in urls[1]
    assert sleeps == [0.25]


def test_missing_key_is_a_clear_error():
    with pytest.raises(TicketmasterError, match="TICKETMASTER_API_KEY"):
        fetch_music_events("", 0, 0, get=lambda u: {})
