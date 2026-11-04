import pytest

from showradar.listing import clean_name, fold, from_event

from .conftest import make_event


@pytest.mark.parametrize(
    "raw,title,headliner,age,package,addon,flags",
    [
        ("Jason DeRulo | Official Ticket + Hotel Packages", "Jason DeRulo", "Jason DeRulo", None, True, False, []),
        ("Leann Rimes | Official Caesars Ticket + Hotel Packages", "Leann Rimes", "Leann Rimes", None, True, False, []),
        ("SUPERTASTE - Ages 21+", "SUPERTASTE", "SUPERTASTE", 21, False, False, []),
        ("Zingara (21+ Event)", "Zingara", "Zingara", 21, False, False, []),
        ("Gus Dapperton (16 and Over)", "Gus Dapperton", "Gus Dapperton", 16, False, False, []),
        ("Syd - Early Entry VIP Upgrade", "Syd", "Syd", None, False, True, []),
        ("STELLA LEFTY: LEFTY LIVE *SOLD OUT*", "STELLA LEFTY: LEFTY LIVE", "STELLA LEFTY", None, False, False, ["sold out"]),
        ("OLIVIA O'BRIEN : THE PIXIE TOUR *POSTPONED TO 2027*", "OLIVIA O'BRIEN : THE PIXIE TOUR", "OLIVIA O'BRIEN",
         None, False, False, ["postponed to 2027"]),
        ("Harry Styles w/ Tinashe", "Harry Styles w/ Tinashe", "Harry Styles", None, False, False, []),
        ("An Acoustic Evening of Classic ???90s Country", "An Acoustic Evening of Classic '90s Country",
         "An Acoustic Evening of Classic '90s Country", None, False, False, []),
    ],
)
def test_clean_name(raw, title, headliner, age, package, addon, flags):
    c = clean_name(raw)
    assert (c.title, c.headliner, c.min_age, c.is_package, c.is_addon, c.flags) == (
        title, headliner, age, package, addon, flags
    )


def test_fold_ignores_case_accents_punctuation():
    assert fold("VALÉ") == fold("Vale") == "vale"
    assert fold("Tyler, The Creator") == "tyler the creator"


def test_zero_price_range_is_treated_as_missing():
    assert from_event(make_event(price=(0.0, 0.0))).price_max is None
    listing = from_event(make_event(price=(25.5, 40.0)))
    assert (listing.price_min, listing.price_max) == (25.5, 40.0)


def test_structured_artist_beats_parsed_name():
    listing = from_event(make_event("10 Years of 6LACK Tour", artists=("6LACK", "Eem Triplin")))
    assert listing.headliner == "6LACK"
    assert from_event(make_event("Liana Flores", artists=())).headliner == "Liana Flores"


def test_venue_key_is_shared_across_ticketing_systems():
    a = from_event(make_event(venue="Valley Bar", venue_id="ticketweb-1"))
    b = from_event(make_event(venue="Valley Bar", venue_id="ticketmaster-9"))
    assert a.venue_key == b.venue_key
