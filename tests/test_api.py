import pytest
from fastapi.testclient import TestClient

from showradar.api import create_app
from showradar.store import apply_sync

from .conftest import make_event


@pytest.fixture
def client(store):
    apply_sync(store, [
        make_event("Kansas", id="k", artists=("Kansas",), price=(40, 80)),
        make_event("Kansas | Official Ticket + Hotel Packages", id="k2", artists=("Kansas",)),
        make_event("Bombargo", id="b", artists=("Bombargo",), genre="Alternative", time="22:00:00"),
    ], "2030-01-01T00:00:00+00:00")
    return TestClient(create_app(store))


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Show Radar" in r.text


def test_shows_and_filters(client):
    body = client.get("/api/shows").json()
    assert body["total"] == 2 and body["genres"] == ["Alternative", "Rock"]
    assert client.get("/api/shows", params={"genre": "alternative"}).json()["total"] == 1
    assert client.get("/api/shows", params={"q": "kansas"}).json()["shows"][0]["price_max"] == 80


def test_follow_flow(client):
    assert client.post("/api/follows", json={"artist": "Kansas"}).status_code == 201
    assert client.get("/api/follows").json() == [{"key": "kansas", "display": "Kansas"}]
    assert client.get("/api/shows", params={"followed": True}).json()["total"] == 1
    assert client.delete("/api/follows/kansas").status_code == 204
    assert client.delete("/api/follows/kansas").status_code == 404


def test_follow_validation(client):
    assert client.post("/api/follows", json={"artist": ""}).status_code == 422
    assert client.post("/api/follows", json={"artist": "x" * 500}).status_code == 422


def test_sync_without_settings_is_503(client):
    assert client.post("/api/sync").status_code == 503
