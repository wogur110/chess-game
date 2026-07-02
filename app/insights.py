"""Cross-game mistake insights: classify your errors and spot the patterns.

Whenever a game review completes, every human miss/mistake/blunder is
classified offline (python-chess board inspection + the cached engine
scores — no extra engine work) into a phase (opening/middlegame/endgame)
and pattern tags ("hung a piece", "missed a mate", …), then appended to a
persistent log under the user's application-data directory. The Library
tab aggregates the log into "you keep doing X" style insights.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import chess
from PySide6.QtCore import QStandardPaths

LOG_VERSION = 1

# Pattern tags, in display order. Keys are stable identifiers; values are the
# English labels (translated via i18n.tr at display time).
TAG_LABELS = {
    "hanging_piece": "Hung a piece",
    "allowed_mate": "Allowed a mate",
    "missed_mate": "Missed a mate",
    "missed_capture": "Missed a free capture",
    "missed_fork": "Missed a fork",
    "other": "Other",
}

PHASE_LABELS = {
    "opening": "Opening",
    "middlegame": "Middlegame",
    "endgame": "Endgame",
}

_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
          chess.ROOK: 5, chess.QUEEN: 9}


def game_phase(board: chess.Board) -> str:
    """Rough phase of the position the mistake was played in."""
    if board.ply() < 16:
        return "opening"
    non_pawn = sum(_VALUE[p.piece_type] for p in board.piece_map().values()
                   if p.piece_type not in (chess.PAWN, chess.KING))
    return "endgame" if non_pawn <= 13 else "middlegame"


def _hanging_squares(board: chess.Board, color: chess.Color) -> set:
    """`color`'s pieces that are en prise: attacked while undefended, or
    attacked by something cheaper (same heuristic as the threat radar)."""
    out = set()
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(not color, square)
        if not attackers:
            continue
        defenders = board.attackers(color, square)
        cheapest = min(_VALUE.get(board.piece_at(a).piece_type, 99)
                       for a in attackers)
        if not defenders or cheapest < _VALUE[piece.piece_type]:
            out.add(square)
    return out


def _mate_for(score, color: chess.Color) -> Optional[int]:
    if score is None:
        return None
    pov = score.pov(color)
    return pov.mate() if pov.is_mate() else None


def classify_tags(board_before: chess.Board, played: chess.Move,
                  best_move: Optional[chess.Move],
                  score_before, score_after) -> list:
    """Pattern tags for one graded human mistake. `board_before` is the
    position the mover faced; scores are the cached PovScores of the
    positions before and after the played move."""
    mover = board_before.turn
    tags: list = []

    mate_before = _mate_for(score_before, mover)
    mate_after = _mate_for(score_after, mover)
    if mate_before is not None and mate_before > 0:
        tags.append("missed_mate")
    if mate_after is not None and mate_after < 0 and \
            not (mate_before is not None and mate_before < 0):
        tags.append("allowed_mate")

    # Did the move leave (or put) one of the mover's pieces en prise?
    after = board_before.copy(stack=False)
    after.push(played)
    if _hanging_squares(after, mover) - _hanging_squares(board_before, mover):
        tags.append("hanging_piece")

    if best_move is not None and best_move != played:
        # Missed free capture: the best move grabbed material for free
        # (undefended target, or worth more than the capturer).
        if board_before.is_capture(best_move):
            victim = (chess.PAWN if board_before.is_en_passant(best_move)
                      else board_before.piece_at(best_move.to_square).piece_type)
            capturer = board_before.piece_at(best_move.from_square).piece_type
            defenders = board_before.attackers(not mover, best_move.to_square)
            if not defenders or _VALUE[victim] > _VALUE.get(capturer, 0):
                tags.append("missed_capture")
        # Missed fork: the best move attacks two or more valuable or
        # undefended enemy pieces at once.
        b2 = board_before.copy(stack=False)
        b2.push(best_move)
        moved = b2.piece_at(best_move.to_square)
        if moved is not None and moved.piece_type != chess.KING:
            forked = 0
            for square in b2.attacks(best_move.to_square):
                target = b2.piece_at(square)
                if target is None or target.color == mover:
                    continue
                if target.piece_type == chess.KING:
                    forked += 1
                    continue
                defenders = b2.attackers(not mover, square)
                if not defenders or \
                        _VALUE[target.piece_type] > _VALUE[moved.piece_type]:
                    forked += 1
            if forked >= 2:
                tags.append("missed_fork")

    return tags or ["other"]


def default_log_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    directory = Path(base) if base else Path.home() / ".chess-studio"
    return directory / "mistakes.json"


class MistakeLog:
    """Persistent, deduplicated log of classified mistakes across games."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_log_path()
        self._records: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for record in raw.get("mistakes", []):
            key = record.get("key")
            if key:
                self._records[key] = record

    def save(self):
        payload = {"version": LOG_VERSION,
                   "mistakes": list(self._records.values())}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=1),
                                 encoding="utf-8")
        except OSError:
            pass   # a failed save must never take the app down

    def add(self, records: list) -> int:
        """Add records ({key, date, category, phase, tags}); re-analysing the
        same game is a no-op thanks to the EPD|move keys."""
        added = 0
        for record in records:
            key = record.get("key")
            if key and key not in self._records:
                self._records[key] = record
                added += 1
        if added:
            self.save()
        return added

    def all(self) -> list:
        return list(self._records.values())

    def summary(self) -> dict:
        by_category: dict = {}
        by_phase: dict = {}
        by_tag: dict = {}
        for record in self._records.values():
            category = record.get("category", "?")
            by_category[category] = by_category.get(category, 0) + 1
            phase = record.get("phase", "?")
            by_phase[phase] = by_phase.get(phase, 0) + 1
            for tag in record.get("tags", []):
                by_tag[tag] = by_tag.get(tag, 0) + 1
        return {"total": len(self._records), "by_category": by_category,
                "by_phase": by_phase, "by_tag": by_tag}
