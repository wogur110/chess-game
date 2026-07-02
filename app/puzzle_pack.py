"""Bundled tactics starter pack: curated Lichess CC0 puzzles, fully offline.

Data file: app/data/puzzles_rush.json.gz, produced by
tools/build_puzzle_pack.py. Separate from the personal mistake deck
(puzzle_store.py) on purpose — spaced repetition stays personal, the pack
provides volume (rush) and motif-focused practice from day one.

Every puzzle is stored solver-to-move (the opponent's setup move was
pre-applied at build time) with the full solution in UCI + SAN, so solving
needs no engine at all.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Lichess theme tag -> English display label (translated via i18n.tr at
# display time). Order defines the theme dropdown.
THEME_LABELS = {
    "mateIn1": "Mate in 1",
    "mateIn2": "Mate in 2",
    "backRankMate": "Back-rank mate",
    "fork": "Fork",
    "pin": "Pin",
    "skewer": "Skewer",
    "discoveredAttack": "Discovered attack",
    "hangingPiece": "Hanging piece",
    "deflection": "Deflection",
    "sacrifice": "Sacrifice",
}


@dataclass(frozen=True)
class PackPuzzle:
    fen: str                    # solver to move
    solution: tuple             # UCI moves: solver, opponent, solver, …
    solution_san: tuple
    rating: int
    themes: tuple               # lichess theme keys


class PuzzlePack:
    def __init__(self, data: dict):
        self.source: str = data.get("source", "")
        self.theme_counts: dict[str, int] = data.get("themes", {})
        self.puzzles: list[PackPuzzle] = [
            PackPuzzle(fen, tuple(ucis), tuple(sans), rating, tuple(themes))
            for fen, ucis, sans, rating, themes in data.get("puzzles", [])
        ]
        self.puzzles.sort(key=lambda p: p.rating)

    def __len__(self) -> int:
        return len(self.puzzles)

    def by_theme(self, theme: Optional[str] = None) -> list:
        """Puzzles carrying `theme` (all puzzles when None), easiest first."""
        if theme is None:
            return list(self.puzzles)
        return [p for p in self.puzzles if theme in p.themes]

    def in_rating_window(self, low: int, high: int,
                         exclude: set) -> list:
        """Unused puzzles with low <= rating < high (for rush escalation)."""
        return [p for p in self.puzzles
                if low <= p.rating < high and p not in exclude]


def _data_path() -> Optional[Path]:
    rel = Path("app") / "data" / "puzzles_rush.json.gz"
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / rel)
    candidates.append(Path(__file__).resolve().parent / "data" / "puzzles_rush.json.gz")
    candidates.append(Path.cwd() / rel)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


_PACK: Optional[PuzzlePack] = None
_LOAD_FAILED = False


def load_pack() -> Optional[PuzzlePack]:
    """Load (once) and return the bundled pack, or None if missing."""
    global _PACK, _LOAD_FAILED
    if _PACK is not None or _LOAD_FAILED:
        return _PACK
    path = _data_path()
    if path is None:
        _LOAD_FAILED = True
        return None
    try:
        with gzip.open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        _PACK = PuzzlePack(data)
    except Exception:
        _LOAD_FAILED = True
        return None
    return _PACK
