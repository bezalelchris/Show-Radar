"""Settings from environment variables, with a tiny .env loader (no extra dependency)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    api_key: str
    db_path: Path
    lat: float
    lon: float
    radius_miles: int
    max_pages: int

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            api_key=os.environ.get("TICKETMASTER_API_KEY", "").strip(),
            db_path=Path(os.environ.get("SHOWRADAR_DB", "data/showradar.db")),
            lat=float(os.environ.get("SHOWRADAR_LAT", "33.4484")),  # Phoenix
            lon=float(os.environ.get("SHOWRADAR_LON", "-112.0740")),
            radius_miles=int(os.environ.get("SHOWRADAR_RADIUS_MILES", "40")),
            max_pages=int(os.environ.get("SHOWRADAR_MAX_PAGES", "5")),
        )
