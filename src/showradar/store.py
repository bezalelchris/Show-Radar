"""SQLite storage: current listings, a snapshot per sync, detected changes, and follows."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .listing import Listing, fold, from_event

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    raw TEXT NOT NULL,             -- full API payload, so cleanup can be re-run without re-fetching
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    removed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS snapshots (
    listing_id TEXT NOT NULL REFERENCES listings(id),
    synced_at TEXT NOT NULL,
    status TEXT,
    onsale_start TEXT,
    local_date TEXT,
    local_time TEXT,
    price_min REAL,
    price_max REAL,
    PRIMARY KEY (listing_id, synced_at)
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL REFERENCES listings(id),
    detected_at TEXT NOT NULL,
    kind TEXT NOT NULL,            -- new | status | onsale | rescheduled | price | removed
    old TEXT,
    new TEXT
);
CREATE INDEX IF NOT EXISTS idx_changes_time ON changes(detected_at);
CREATE TABLE IF NOT EXISTS follows (
    key TEXT PRIMARY KEY,          -- folded artist name
    display TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_runs (
    synced_at TEXT PRIMARY KEY,
    fetched INTEGER NOT NULL,
    changes INTEGER NOT NULL
);
"""

TRACKED = ("status", "onsale_start", "local_date", "local_time", "price_min", "price_max")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ listings
    def listings(self, include_removed: bool = False) -> list[Listing]:
        sql = "SELECT raw FROM listings" + ("" if include_removed else " WHERE removed = 0")
        return [from_event(json.loads(r["raw"])) for r in self.conn.execute(sql)]

    def latest_snapshots(self) -> dict[str, sqlite3.Row]:
        rows = self.conn.execute(
            """SELECT s.* FROM snapshots s
               JOIN (SELECT listing_id, MAX(synced_at) AS t FROM snapshots GROUP BY listing_id) m
                 ON s.listing_id = m.listing_id AND s.synced_at = m.t"""
        )
        return {r["listing_id"]: r for r in rows}

    def price_history(self, listing_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT synced_at, price_min, price_max FROM snapshots WHERE listing_id = ? ORDER BY synced_at",
            (listing_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ changes
    def changes(self, since: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM changes"
        args: tuple = ()
        if since:
            sql, args = sql + " WHERE detected_at >= ?", (since,)
        sql += " ORDER BY detected_at DESC, id DESC LIMIT ?"
        return [dict(r) for r in self.conn.execute(sql, (*args, limit))]

    def last_sync(self) -> dict | None:
        r = self.conn.execute("SELECT * FROM sync_runs ORDER BY synced_at DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    # ------------------------------------------------------------------ follows
    def follow(self, name: str) -> str:
        key = fold(name)
        if not key:
            raise ValueError("Artist name is empty")
        self.conn.execute(
            "INSERT INTO follows (key, display, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET display = excluded.display",
            (key, name.strip(), now_iso()),
        )
        self.conn.commit()
        return key

    def unfollow(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM follows WHERE key = ?", (fold(name),))
        self.conn.commit()
        return cur.rowcount > 0

    def follows(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT key, display FROM follows ORDER BY display")]

    def close(self) -> None:
        self.conn.close()


def _snapshot(listing: Listing) -> dict:
    return {k: getattr(listing, k) for k in TRACKED}


def _price(min_: float | None, max_: float | None) -> str | None:
    if max_ is None:
        return None
    return f"${min_:.2f}" if min_ == max_ else f"${min_:.2f}-${max_:.2f}"


def _diff(prev, snap: dict) -> list[tuple[str, str | None, str | None]]:
    """(kind, old, new) for each tracked field that changed between two snapshots."""
    out = []
    if prev["status"] != snap["status"]:
        out.append(("status", prev["status"], snap["status"]))
    if prev["onsale_start"] != snap["onsale_start"]:
        out.append(("onsale", prev["onsale_start"], snap["onsale_start"]))
    old_when = f"{prev['local_date']} {prev['local_time'] or ''}".strip()
    new_when = f"{snap['local_date']} {snap['local_time'] or ''}".strip()
    if old_when != new_when:
        out.append(("rescheduled", old_when, new_when))
    old_p, new_p = _price(prev["price_min"], prev["price_max"]), _price(snap["price_min"], snap["price_max"])
    # A price that vanishes from the feed isn't a price change; it's missing data.
    if new_p is not None and old_p != new_p:
        out.append(("price", old_p, new_p))
    return out


def apply_sync(store: Store, events: list[dict], synced_at: str | None = None) -> list[dict]:
    """Record one sync. Returns the changes detected against the previous sync.

    The first sync of an empty database records listings without emitting a "new"
    change for each, so a fresh install doesn't flood the alert feed.
    """
    synced_at = synced_at or now_iso()
    conn = store.conn
    known = {r["id"]: bool(r["removed"]) for r in conn.execute("SELECT id, removed FROM listings")}
    first_sync = not known
    previous = store.latest_snapshots()
    changes: list[tuple[str, str, str | None, str | None]] = []
    seen: set[str] = set()

    with conn:
        for event in events:
            listing = from_event(event)
            if listing.id in seen:
                continue
            seen.add(listing.id)
            snap = _snapshot(listing)

            if listing.id not in known:
                conn.execute(
                    "INSERT INTO listings (id, raw, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                    (listing.id, json.dumps(event), synced_at, synced_at),
                )
                if not first_sync:
                    changes.append((listing.id, "new", None, listing.status))
            else:
                conn.execute(
                    "UPDATE listings SET raw = ?, last_seen = ?, removed = 0 WHERE id = ?",
                    (json.dumps(event), synced_at, listing.id),
                )
                prev = previous.get(listing.id)
                if prev is not None:
                    changes.extend((listing.id, *c) for c in _diff(prev, snap))

            conn.execute(
                f"INSERT OR REPLACE INTO snapshots (listing_id, synced_at, {', '.join(TRACKED)}) "
                f"VALUES (?, ?, {', '.join('?' for _ in TRACKED)})",
                (listing.id, synced_at, *snap.values()),
            )

        # Listings that disappeared from the feed (past, pulled, or moved out of range).
        for lid, removed in known.items():
            if lid not in seen and not removed:
                conn.execute("UPDATE listings SET removed = 1 WHERE id = ?", (lid,))
                changes.append((lid, "removed", None, None))

        conn.executemany(
            "INSERT INTO changes (listing_id, detected_at, kind, old, new) VALUES (?, ?, ?, ?, ?)",
            [(lid, synced_at, kind, old, new) for lid, kind, old, new in changes],
        )
        conn.execute("INSERT OR REPLACE INTO sync_runs VALUES (?, ?, ?)", (synced_at, len(seen), len(changes)))

    return [{"listing_id": lid, "kind": k, "old": o, "new": n, "detected_at": synced_at} for lid, k, o, n in changes]
