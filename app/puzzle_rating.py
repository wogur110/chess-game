"""Estimated puzzle rating: Elo-style tracking of your pack-puzzle results.

Every rush or practice attempt against a rated pack puzzle updates the
estimate (win = clean solve, loss = any wrong move / hint / reveal), exactly
like the Lichess puzzle rating. The estimate plus the full attempt history
persist in puzzle_rating.json under the application-data directory, so the
number reflects your accumulated record across sessions. Personal-deck
puzzles carry no rating and are ignored.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths

STORE_VERSION = 1
START_RATING = 1000.0
PROVISIONAL_ATTEMPTS = 10   # show "~" until this many attempts
K_EARLY, K_LATE = 40.0, 24.0
K_SWITCH_AT = 20            # attempts after which the K factor settles
RATING_FLOOR, RATING_CEIL = 100.0, 3500.0


def default_rating_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    directory = Path(base) if base else Path.home() / ".chess-studio"
    return directory / "puzzle_rating.json"


class PuzzleRating:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_rating_path()
        self._rating = START_RATING
        self._attempts: list = []   # [iso_date, puzzle_rating, solved, rating]
        self._load()

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        try:
            self._rating = float(raw.get("rating", START_RATING))
        except (TypeError, ValueError):
            self._rating = START_RATING
        self._attempts = list(raw.get("attempts", []))

    def save(self):
        payload = {"version": STORE_VERSION, "rating": self._rating,
                   "attempts": self._attempts}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass   # a failed save must never take the app down

    @property
    def rating(self) -> int:
        return round(self._rating)

    @property
    def attempt_count(self) -> int:
        return len(self._attempts)

    @property
    def provisional(self) -> bool:
        return len(self._attempts) < PROVISIONAL_ATTEMPTS

    def record(self, puzzle_rating: int, solved: bool,
               today: Optional[date] = None) -> int:
        """Elo update for one attempt; returns the new (rounded) rating."""
        k = K_EARLY if len(self._attempts) < K_SWITCH_AT else K_LATE
        expected = 1.0 / (1.0 + 10 ** ((puzzle_rating - self._rating) / 400.0))
        self._rating += k * ((1.0 if solved else 0.0) - expected)
        self._rating = max(RATING_FLOOR, min(RATING_CEIL, self._rating))
        self._attempts.append([(today or date.today()).isoformat(),
                               int(puzzle_rating), bool(solved), self.rating])
        self.save()
        return self.rating
