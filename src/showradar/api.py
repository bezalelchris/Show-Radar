"""JSON API + the single-page web UI. Runs locally (127.0.0.1)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import service
from .config import Settings
from .store import Store
from .ticketmaster import TicketmasterError

STATIC = Path(__file__).parent / "static"


class FollowRequest(BaseModel):
    artist: str = Field(min_length=1, max_length=120)


def create_app(store: Store, settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Show Radar", version="0.1.0")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        return {"last_sync": store.last_sync(), "follows": len(store.follows())}

    @app.get("/api/shows")
    def shows(
        q: str | None = Query(None, max_length=100),
        followed: bool = False,
        genre: str | None = Query(None, max_length=40),
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict:
        rows = service.shows(store, q=q, followed_only=followed, genre=genre)
        genres = sorted({s["genre"] for s in service.shows(store) if s["genre"]})
        return {"total": len(rows), "genres": genres, "shows": rows[:limit]}

    @app.get("/api/follows")
    def follows() -> list[dict]:
        return store.follows()

    @app.post("/api/follows", status_code=201)
    def follow(req: FollowRequest) -> dict:
        try:
            key = store.follow(req.artist)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"key": key, "display": req.artist.strip()}

    @app.delete("/api/follows/{key}", status_code=204)
    def unfollow(key: str) -> None:
        if not store.unfollow(key):
            raise HTTPException(404, "Not following that artist")

    @app.get("/api/alerts")
    def alerts(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
        return [{**a, "message": service.describe(a)} for a in service.alerts(store, limit=limit)]

    @app.post("/api/sync")
    def sync() -> dict:
        if settings is None:
            raise HTTPException(503, "Sync is not configured")
        try:
            changes = service.sync(store, settings)
        except TicketmasterError as e:
            raise HTTPException(502, str(e))
        return {"changes": len(changes), "last_sync": store.last_sync()}

    return app
