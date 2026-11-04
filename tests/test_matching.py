from pathlib import Path

from showradar.evaluate import exact_name_baseline, load_pairs, score
from showradar.listing import from_event
from showradar.matching import group_shows, same_show

from .conftest import make_event

EVAL = Path(__file__).parent.parent / "eval" / "listing_pairs.jsonl"


def L(*args, **kw):
    return from_event(make_event(*args, **kw))


def test_package_and_age_listings_merge():
    plain = L("Jason Derulo", artists=("Jason Derulo",), venue_id="tm")
    package = L("Jason DeRulo | Official Ticket + Hotel Packages", artists=("Jason Derulo",), venue_id="tm")
    age = L("JASON DERULO - Ages 21+", artists=(), venue_id="tw")
    assert same_show(plain, package) and same_show(plain, age)


def test_early_and_late_sets_stay_separate():
    early = L("Steep Canyon Rangers", time="18:30:00", artists=("Steep Canyon Rangers",))
    late = L("Steep Canyon Rangers", time="20:30:00", artists=("Steep Canyon Rangers",))
    assert not same_show(early, late)


def test_different_acts_same_night_stay_separate():
    assert not same_show(L("OBSKUROS", artists=()), L("LATIN NIGHT WITH DJ RECO", artists=(), time="22:00:00"))


def test_different_day_or_venue_never_match():
    a = L("Gary Numan", artists=("Gary Numan",))
    assert not same_show(a, L("Gary Numan", artists=("Gary Numan",), date="2030-01-11"))
    assert not same_show(a, L("Gary Numan", artists=("Gary Numan",), venue="Marquee Theatre"))


def test_group_shows_puts_ticket_listing_first():
    listings = [
        L("Kansas | Official Ticket + Hotel Packages", artists=("Kansas",)),
        L("Kansas", artists=("Kansas",), price=(45, 90)),
        L("Somebody Else", artists=("Somebody Else",), time="22:30:00"),
    ]
    shows = group_shows(listings)
    assert len(shows) == 2
    kansas = next(g for g in shows if g[0].headliner == "Kansas")
    assert [x.clean.is_package for x in kansas] == [False, True]


def test_matcher_on_labeled_real_listings():
    """Regression gate on the hand-labeled pairs from a real Phoenix sync."""
    pairs = load_pairs(EVAL)
    assert len(pairs) >= 75
    ours, _ = score(pairs, same_show)
    baseline, _ = score(pairs, exact_name_baseline)
    assert ours.precision >= 0.95 and ours.recall >= 0.95
    assert ours.f1 > baseline.f1
