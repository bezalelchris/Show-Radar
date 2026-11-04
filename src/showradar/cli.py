"""Command line interface.

    showradar sync                  pull the latest Phoenix-area music events
    showradar follow "Tyler, The Creator"
    showradar shows --followed
    showradar alerts
    showradar serve                 web UI at http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys

from . import service
from .config import Settings
from .store import Store
from .ticketmaster import TicketmasterError


def _price(s: dict) -> str:
    if s["price_max"] is None:
        return ""
    lo, hi = s["price_min"], s["price_max"]
    return f"${lo:.0f}" if lo == hi else f"${lo:.0f}-{hi:.0f}"


def _print_shows(rows: list[dict]) -> None:
    if not rows:
        print("No shows found.")
        return
    for s in rows:
        star = "*" if s["followed"] else " "
        extra = [x for x in (_price(s), s["status"] if s["status"] != "onsale" else "", *s["flags"]) if x]
        n = len(s["listings"]) - 1
        dupes = f" (+{n} listing{'s' if n > 1 else ''})" if n else ""
        print(f"{star} {s['date']} {s['time'] or '     '}  {s['title'][:42]:42}  {s['venue'][:28]:28}  "
              f"{' | '.join(extra)}{dupes}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="showradar", description="Phoenix concert alerts from Ticketmaster.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="fetch events and detect changes")
    p = sub.add_parser("shows", help="list upcoming shows (duplicates merged)")
    p.add_argument("query", nargs="?", help="search artist, title or venue")
    p.add_argument("--followed", action="store_true", help="only artists you follow")
    p.add_argument("--genre")
    p = sub.add_parser("follow", help="follow an artist")
    p.add_argument("artist")
    p = sub.add_parser("unfollow", help="stop following an artist")
    p.add_argument("artist")
    sub.add_parser("follows", help="list followed artists")
    sub.add_parser("alerts", help="changes for artists you follow")
    p = sub.add_parser("serve", help="run the web UI")
    p.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    settings = Settings.from_env()
    store = Store(settings.db_path)

    if args.cmd == "sync":
        try:
            changes = service.sync(store, settings)
        except TicketmasterError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        run = store.last_sync()
        counts: dict[str, int] = {}
        for c in changes:
            counts[c["kind"]] = counts.get(c["kind"], 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no changes"
        print(f"Synced {run['fetched']} listings: {summary}.")
        new_alerts = [a for a in service.alerts(store) if a["detected_at"] == run["synced_at"]]
        for a in new_alerts:
            print(f"  ! {service.describe(a)}")
        return 0

    if args.cmd == "shows":
        _print_shows(service.shows(store, q=args.query, followed_only=args.followed, genre=args.genre))
        return 0

    if args.cmd == "follow":
        store.follow(args.artist)
        upcoming = service.shows(store, followed_only=True)
        print(f"Following {args.artist}. {len(upcoming)} upcoming show(s) from artists you follow.")
        return 0

    if args.cmd == "unfollow":
        print("Unfollowed." if store.unfollow(args.artist) else f"You weren't following {args.artist}.")
        return 0

    if args.cmd == "follows":
        follows = store.follows()
        print("\n".join(f["display"] for f in follows) if follows else "Not following anyone yet.")
        return 0

    if args.cmd == "alerts":
        feed = service.alerts(store)
        if not feed:
            print("No alerts yet. Follow some artists, then sync again later.")
        for a in feed:
            print(f"{a['detected_at'][:16]}  {service.describe(a)}")
        return 0

    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(store, settings), host="127.0.0.1", port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
