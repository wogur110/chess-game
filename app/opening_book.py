"""Bundled opening database: named lines (ECO) + masters win-rate stats.

Data file: app/data/openings.json.gz, produced by tools/build_opening_data.py.
Positions are keyed by EPD so transpositions resolve naturally.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chess


@dataclass(frozen=True)
class OpeningLine:
    eco: str
    name: str
    ucis: tuple[str, ...]

    @property
    def variation(self) -> str:
        """The part of the name after the family prefix."""
        if ":" in self.name:
            return self.name.split(":", 1)[1].strip()
        return "Main line"


@dataclass
class BookMove:
    uci: str
    san: str
    white: int = 0
    draws: int = 0
    black: int = 0

    @property
    def total(self) -> int:
        return self.white + self.draws + self.black

    @property
    def has_stats(self) -> bool:
        return self.total > 0


@dataclass
class PositionInfo:
    white: int
    draws: int
    black: int
    moves: list[BookMove]

    @property
    def total(self) -> int:
        return self.white + self.draws + self.black


def _data_path() -> Optional[Path]:
    rel = Path("app") / "data" / "openings.json.gz"
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / rel)
    candidates.append(Path(__file__).resolve().parent / "data" / "openings.json.gz")
    candidates.append(Path.cwd() / rel)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class OpeningBook:
    def __init__(self, data: dict):
        self._names: dict[str, list] = data.get("names", {})
        self._book: dict[str, list] = data.get("book", {})
        self._stats: dict[str, list] = data.get("stats", {})
        self.source: str = data.get("source", "")
        self.games_used: int = data.get("games_used", 0)
        self.families: dict[str, list[OpeningLine]] = {}
        for family, lines in data.get("families", {}).items():
            self.families[family] = [
                OpeningLine(eco, name, tuple(ucis.split()))
                for eco, name, ucis in lines
            ]

    # ---- queries ----

    def name_for_epd(self, epd: str) -> Optional[tuple[str, str]]:
        entry = self._names.get(epd)
        return (entry[0], entry[1]) if entry else None

    def name_for_history(self, boards_epds: list[str]) -> Optional[tuple[str, str]]:
        """Deepest named position along the game so far (lichess convention)."""
        for epd in reversed(boards_epds):
            entry = self._names.get(epd)
            if entry:
                return (entry[0], entry[1])
        return None

    def position_info(self, board: chess.Board) -> Optional[PositionInfo]:
        """Stats + candidate moves for a position; None if entirely unknown."""
        epd = board.epd()
        stats = self._stats.get(epd)
        moves: dict[str, BookMove] = {}
        white = draws = black = 0
        if stats:
            white, draws, black, move_stats = stats
            for uci, (san, mw, md, mb) in move_stats.items():
                moves[uci] = BookMove(uci, san, mw, md, mb)
        # Named-line edges without game stats still belong in the book.
        for uci in self._book.get(epd, []):
            if uci not in moves:
                try:
                    san = board.san(chess.Move.from_uci(uci))
                except Exception:
                    continue
                moves[uci] = BookMove(uci, san)
        if not moves and not stats:
            return None
        ordered = sorted(moves.values(), key=lambda m: (-m.total, m.san))
        return PositionInfo(white, draws, black, ordered)

    def book_replies(self, board: chess.Board) -> list[BookMove]:
        """Moves a drill opponent may play: known book moves, stats-weighted."""
        info = self.position_info(board)
        if info is None:
            return []
        legal = {m.uci() for m in board.legal_moves}
        return [m for m in info.moves if m.uci in legal]


_BOOK: Optional[OpeningBook] = None
_LOAD_FAILED = False


def load_book() -> Optional[OpeningBook]:
    """Load (once) and return the bundled opening book, or None if missing."""
    global _BOOK, _LOAD_FAILED
    if _BOOK is not None or _LOAD_FAILED:
        return _BOOK
    path = _data_path()
    if path is None:
        _LOAD_FAILED = True
        return None
    try:
        with gzip.open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        _BOOK = OpeningBook(data)
    except Exception:
        _LOAD_FAILED = True
        return None
    return _BOOK
