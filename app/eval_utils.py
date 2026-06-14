"""Score conversion helpers: engine scores -> win probabilities and labels."""

from __future__ import annotations

import math
from typing import Optional, Sequence

import chess
import chess.engine


def score_to_expectation_white(score: chess.engine.PovScore, ply: int = 30) -> float:
    """White's expected game score in [0, 1] (win=1, draw=0.5, loss=0).

    Uses Stockfish's WDL model when possible, falling back to a logistic
    curve on centipawns (lichess formula).
    """
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        if mate is not None:
            return 1.0 if mate > 0 else 0.0
    try:
        wdl = score.wdl(model="sf", ply=ply)
        return wdl.white().expectation()
    except Exception:
        pass
    cp = white.score(mate_score=10000)
    if cp is None:
        return 0.5
    # Lichess winning-chances curve.
    cp = max(-4000, min(4000, cp))
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


def expectation_for(color: chess.Color, expectation_white: float) -> float:
    return expectation_white if color == chess.WHITE else 1.0 - expectation_white


def recommendation_probs(expectations_mover: Sequence[float], temperature: float = 0.06) -> list[float]:
    """Turn per-move expectations (mover POV, 0..1) into a probability
    distribution over the candidate moves via softmax."""
    if not expectations_mover:
        return []
    mx = max(expectations_mover)
    weights = [math.exp((e - mx) / temperature) for e in expectations_mover]
    total = sum(weights)
    return [w / total for w in weights]


# ---- Move-quality classification (for game review) --------------------------

# Symbols shown next to a move in the move list.
MOVE_SYMBOLS = {
    "blunder": "??",
    "mistake": "?",
    "inaccuracy": "?!",
    "good": "",
}


def classify_loss(win_loss: float) -> str:
    """Classify a move by the mover's drop in winning chances (0..1)."""
    if win_loss >= 0.20:
        return "blunder"
    if win_loss >= 0.10:
        return "mistake"
    if win_loss >= 0.05:
        return "inaccuracy"
    return "good"


def move_accuracy(before_pct: float, after_pct: float) -> float:
    """Single-move accuracy in [0, 100] from the mover's winning percentages
    before and after the move (each 0..100). Lichess' accuracy curve."""
    drop = max(0.0, before_pct - after_pct)
    accuracy = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return max(0.0, min(100.0, accuracy))


def format_score_white(score: Optional[chess.engine.PovScore]) -> str:
    """Human-readable eval from White's POV, e.g. '+0.8', '-2.3', '#5', '#-3'."""
    if score is None:
        return "—"
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        if mate is None:
            return "—"
        return f"#{mate}" if mate > 0 else f"#-{abs(mate)}"
    cp = white.score()
    if cp is None:
        return "—"
    pawns = cp / 100.0
    return f"{pawns:+.1f}"
