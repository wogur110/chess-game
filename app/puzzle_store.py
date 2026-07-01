"""Personal tactics deck: puzzles mined from your own mistakes.

Each puzzle is one position you misplayed in a real game: the FEN before
your move, the engine's verified best line as the solution, and Leitner-box
scheduling state so solved puzzles come back at expanding intervals.
The deck lives in a small JSON file under the user's application-data
directory (never inside the install folder).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths

STORE_VERSION = 1
# Leitner review intervals in days, indexed by box (fail -> box 0).
BOX_INTERVALS = [1, 3, 7, 21, 60]


def default_store_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    directory = Path(base) if base else Path.home() / ".chess-studio"
    return directory / "puzzles.json"


@dataclass
class Puzzle:
    key: str                  # "{epd}|{played_uci}" — dedups across reviews
    fen: str                  # position before the mistake (solver to move)
    solution: list            # UCI moves: solver, opponent, solver, …
    solution_san: list
    category: str             # miss | mistake | blunder
    played_san: str           # the move you actually played
    source: dict = field(default_factory=dict)   # date/white/black/move_no/mover
    box: int = 0
    due: str = ""             # ISO date of the next review; "" = new, due now
    attempts: list = field(default_factory=list)  # [iso_date, solved, clean]

    @property
    def solved(self) -> bool:
        return any(a[1] for a in self.attempts)

    def is_due(self, today: Optional[date] = None) -> bool:
        if not self.due:
            return True
        return date.fromisoformat(self.due) <= (today or date.today())


class PuzzleStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_store_path()
        self._puzzles: dict[str, Puzzle] = {}
        self._load()

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for entry in raw.get("puzzles", []):
            try:
                puzzle = Puzzle(**entry)
            except TypeError:
                continue   # unknown schema — skip rather than crash
            self._puzzles[puzzle.key] = puzzle

    def save(self):
        payload = {"version": STORE_VERSION,
                   "puzzles": [asdict(p) for p in self._puzzles.values()]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        except OSError:
            pass   # a failed save must never take the app down

    # ---- deck access ----

    def add(self, puzzles: list) -> int:
        """Add new puzzles (existing keys are kept untouched); returns how
        many were actually new."""
        added = 0
        for puzzle in puzzles:
            if puzzle.key not in self._puzzles:
                self._puzzles[puzzle.key] = puzzle
                added += 1
        if added:
            self.save()
        return added

    def remove(self, key: str):
        if self._puzzles.pop(key, None) is not None:
            self.save()

    def get(self, key: str) -> Optional[Puzzle]:
        return self._puzzles.get(key)

    def all(self) -> list:
        return list(self._puzzles.values())

    def due_puzzles(self, today: Optional[date] = None) -> list:
        """Puzzles scheduled for review today, oldest due date first."""
        today = today or date.today()
        due = [p for p in self._puzzles.values() if p.is_due(today)]
        due.sort(key=lambda p: (p.due or "0000-00-00",
                                p.source.get("date", "")))
        return due

    # ---- spaced repetition ----

    def record_attempt(self, key: str, solved: bool, clean: bool,
                       today: Optional[date] = None):
        """Move the puzzle up a Leitner box on a clean first-try solve, back
        to box 0 otherwise; either way schedule the next review."""
        puzzle = self._puzzles.get(key)
        if puzzle is None:
            return
        today = today or date.today()
        puzzle.attempts.append([today.isoformat(), bool(solved), bool(clean)])
        if solved and clean:
            puzzle.box = min(puzzle.box + 1, len(BOX_INTERVALS) - 1)
        else:
            puzzle.box = 0
        puzzle.due = (today + timedelta(days=BOX_INTERVALS[puzzle.box])).isoformat()
        self.save()
