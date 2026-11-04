"""Measure duplicate detection against hand-labeled listing pairs.

    python -m showradar.evaluate eval/listing_pairs.jsonl

The pairs are every same-venue, same-day pair from a real Phoenix-area sync,
each labeled "same performance" or "different performance".
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .listing import Listing, fold, from_event
from .matching import same_show


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def accuracy(self) -> float:
        n = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / n if n else 0.0


def exact_name_baseline(a: Listing, b: Listing) -> bool:
    """What you'd get without cleanup: same venue, same day, same name (ignoring case)."""
    return a.venue_key == b.venue_key and a.local_date == b.local_date and fold(a.name) == fold(b.name)


def load_pairs(path: str | Path) -> list[tuple[Listing, Listing, bool]]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(from_event(r["a"]), from_event(r["b"]), r["same_show"]) for r in rows]


def score(pairs, matcher: Callable[[Listing, Listing], bool]) -> tuple[Score, list]:
    s, errors = Score(), []
    for a, b, truth in pairs:
        pred = matcher(a, b)
        if pred and truth:
            s.tp += 1
        elif pred:
            s.fp += 1
            errors.append(("false match", a, b))
        elif truth:
            s.fn += 1
            errors.append(("missed match", a, b))
        else:
            s.tn += 1
    return s, errors


def main(argv: list[str] | None = None) -> int:
    path = (argv or sys.argv[1:] or ["eval/listing_pairs.jsonl"])[0]
    pairs = load_pairs(path)
    same = sum(t for *_, t in pairs)
    print(f"{len(pairs)} labeled pairs ({same} same show, {len(pairs) - same} different)\n")
    print(f"{'matcher':<22}{'precision':>10}{'recall':>8}{'F1':>7}{'accuracy':>10}")
    for label, fn in (("exact-name baseline", exact_name_baseline), ("show radar", same_show)):
        s, errors = score(pairs, fn)
        print(f"{label:<22}{s.precision:>10.1%}{s.recall:>8.1%}{s.f1:>7.2f}{s.accuracy:>10.1%}")
    _, errors = score(pairs, same_show)
    if errors:
        print("\nshow radar errors:")
        for kind, a, b in errors:
            print(f"  {kind}: {a.name!r} {a.local_time} <> {b.name!r} {b.local_time} @ {a.venue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
