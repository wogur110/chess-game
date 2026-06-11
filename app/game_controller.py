"""Game state: move history, players, difficulty, navigation, save/load.

The controller is the single source of truth. It lives on the GUI thread;
engine results arrive via queued signal delivery. Every state change bumps
a generation counter so in-flight engine results for stale positions are
discarded.

View model: `_moves` is the full game line, `_view` is the index of the
currently displayed position (0 = initial position, len(_moves) = live
position). Navigating back is non-destructive; making a move while
viewing the past truncates the remainder ("branch and continue"); the
Undo button destructively removes moves.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import chess
import chess.engine
import chess.pgn
from PySide6.QtCore import QObject, QTimer, Signal

from .engine_manager import DEFAULT_DIFFICULTY, DIFFICULTY_LEVELS, EngineManager
from .eval_utils import (expectation_for, format_score_white,
                         recommendation_probs, score_to_expectation_white)


class PlayerKind(Enum):
    HUMAN = "Human"
    AI = "AI"


@dataclass
class Suggestion:
    move: chess.Move
    san: str
    rec_prob: float           # recommendation probability among candidates
    win_prob_mover: float     # mover's expected score after this move
    score_text: str           # eval string, white POV
    pv_san: list[str] = field(default_factory=list)


class GameController(QObject):
    positionChanged = Signal(object, object, bool)   # board, last_move|None, animate
    movesChanged = Signal()                          # history structure changed
    viewChanged = Signal(int, int)                   # view index, total moves
    playersChanged = Signal()
    statusChanged = Signal(str)
    evalChanged = Signal(object, str)                # expectation_white|None, eval text
    suggestionsChanged = Signal(list)                # list[Suggestion]
    aiThinkingChanged = Signal(bool)
    engineMissing = Signal(str)

    AI_DELAY_MS = 150
    AI_VS_AI_DELAY_MS = 450

    def __init__(self, engine: EngineManager, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.engine.moveReady.connect(self._on_engine_move)
        self.engine.analysisReady.connect(self._on_analysis)
        self.engine.engineError.connect(self.engineMissing)

        self._base = chess.Board()
        self._moves: list[chess.Move] = []
        self._san: list[str] = []
        self._scores: list[Optional[chess.engine.PovScore]] = [None]  # per position index
        self._view = 0
        self._generation = 0

        self.players: dict[chess.Color, PlayerKind] = {
            chess.WHITE: PlayerKind.HUMAN,
            chess.BLACK: PlayerKind.AI,
        }
        self.difficulty = DEFAULT_DIFFICULTY
        self.autoplay = True          # gates AI-vs-AI continuous play
        self._ai_thinking = False

    # ---- Derived state -------------------------------------------------------

    def board_at(self, index: int) -> chess.Board:
        board = self._base.copy()
        for move in self._moves[:index]:
            board.push(move)
        return board

    def view_board(self) -> chess.Board:
        return self.board_at(self._view)

    def live_board(self) -> chess.Board:
        return self.board_at(len(self._moves))

    @property
    def is_live(self) -> bool:
        return self._view == len(self._moves)

    @property
    def view_index(self) -> int:
        return self._view

    @property
    def total_moves(self) -> int:
        return len(self._moves)

    @property
    def san_history(self) -> list[str]:
        return list(self._san)

    @property
    def base_fullmove(self) -> int:
        return self._base.fullmove_number

    @property
    def base_turn(self) -> chess.Color:
        return self._base.turn

    def score_at(self, index: int) -> Optional[chess.engine.PovScore]:
        if 0 <= index < len(self._scores):
            return self._scores[index]
        return None

    def outcome(self, board: Optional[chess.Board] = None) -> Optional[chess.Outcome]:
        board = board or self.view_board()
        return board.outcome(claim_draw=True)

    def human_colors(self) -> list[chess.Color]:
        return [c for c in (chess.WHITE, chess.BLACK) if self.players[c] == PlayerKind.HUMAN]

    def movable_colors(self) -> list[chess.Color]:
        """Colors the user may move right now on the viewed board."""
        board = self.view_board()
        if self.outcome(board) is not None:
            return []
        if self.players[board.turn] == PlayerKind.HUMAN:
            return [board.turn]
        return []

    def preferred_orientation(self) -> chess.Color:
        """Human side at the bottom; white at the bottom otherwise."""
        humans = self.human_colors()
        if len(humans) == 1:
            return humans[0]
        return chess.WHITE

    # ---- Actions ---------------------------------------------------------------

    def make_move(self, move: chess.Move) -> bool:
        """A move made by the user on the board."""
        return self._apply_move(move, animate=False)

    def _apply_move(self, move: chess.Move, animate: bool) -> bool:
        board = self.view_board()
        if move not in board.legal_moves:
            return False
        if not self.is_live:
            # Branch from the reviewed position: discard the rest of the line.
            del self._moves[self._view:]
            del self._san[self._view:]
            del self._scores[self._view + 1:]
        self._san.append(board.san(move))
        self._moves.append(move)
        self._scores.append(None)
        self._view = len(self._moves)
        self._generation += 1
        self._set_thinking(False)
        self.movesChanged.emit()
        self._after_position_change(move, animate)
        return True

    def undo(self):
        """Destructively take back the last move; against an AI opponent,
        rewind to the human's previous turn."""
        if not self._moves:
            return
        self._generation += 1
        self._set_thinking(False)
        self._pop_once()
        humans = self.human_colors()
        if len(humans) == 1:
            human = humans[0]
            while self._moves and self.live_board().turn != human:
                self._pop_once()
        self._view = len(self._moves)
        self.movesChanged.emit()
        last = self._moves[-1] if self._moves else None
        self._after_position_change(last, animate=True)

    def _pop_once(self):
        self._moves.pop()
        self._san.pop()
        del self._scores[len(self._moves) + 1:]

    def navigate(self, index: int):
        index = max(0, min(len(self._moves), index))
        if index == self._view:
            return
        self._view = index
        self._generation += 1
        self._set_thinking(False)
        last = self._moves[index - 1] if index > 0 else None
        self._after_position_change(last, animate=True)

    def step(self, delta: int):
        self.navigate(self._view + delta)

    def new_game(self):
        self._generation += 1
        self._set_thinking(False)
        self._base = chess.Board()
        self._moves = []
        self._san = []
        self._scores = [None]
        self._view = 0
        self.movesChanged.emit()
        self._after_position_change(None, animate=False)

    def start_from(self, moves: list, human_color: chess.Color):
        """Start a game from the standard position with `moves` pre-played
        (e.g. an opening line); the human takes `human_color`, the AI the other."""
        self._generation += 1
        self._set_thinking(False)
        self._base = chess.Board()
        replay = chess.Board()
        san: list[str] = []
        applied: list[chess.Move] = []
        for move in moves:
            if move not in replay.legal_moves:
                break
            san.append(replay.san(move))
            replay.push(move)
            applied.append(move)
        self._moves = applied
        self._san = san
        self._scores = [None] * (len(applied) + 1)
        self._view = len(applied)
        self.players[human_color] = PlayerKind.HUMAN
        self.players[not human_color] = PlayerKind.AI
        self.playersChanged.emit()
        self.movesChanged.emit()
        last = applied[-1] if applied else None
        self._after_position_change(last, animate=False)

    def set_player(self, color: chess.Color, kind: PlayerKind):
        if self.players[color] == kind:
            return
        self._generation += 1
        self._set_thinking(False)
        self.players[color] = kind
        self.playersChanged.emit()
        self._refresh_engine_requests()
        self._emit_status()

    def set_difficulty(self, level: int):
        self.difficulty = max(1, min(10, level))

    def set_autoplay(self, enabled: bool):
        self.autoplay = enabled
        if enabled:
            self._maybe_start_ai()
        self._emit_status()

    def difficulty_label(self) -> str:
        return DIFFICULTY_LEVELS[self.difficulty].label

    # ---- Engine round-trips ------------------------------------------------------

    def refresh_analysis(self):
        """Re-request analysis / AI move for the current position. Call after
        the engine becomes ready or when player settings change externally."""
        self._refresh_engine_requests()

    def _after_position_change(self, last_move: Optional[chess.Move], animate: bool):
        board = self.view_board()
        self.positionChanged.emit(board, last_move, animate)
        self.viewChanged.emit(self._view, len(self._moves))
        self.suggestionsChanged.emit([])
        self._refresh_engine_requests(board)
        self._emit_status()

    def _refresh_engine_requests(self, board: Optional[chess.Board] = None):
        board = board or self.view_board()
        outcome = self.outcome(board)
        if outcome is not None:
            exp = {None: 0.5, chess.WHITE: 1.0, chess.BLACK: 0.0}[outcome.winner]
            self.evalChanged.emit(exp, outcome.result())
            self.suggestionsChanged.emit([])
        else:
            cached = self._scores[self._view] if self._view < len(self._scores) else None
            if cached is not None:
                self.evalChanged.emit(
                    score_to_expectation_white(cached, ply=board.ply()),
                    format_score_white(cached),
                )
            else:
                self.evalChanged.emit(None, "…")
            self.engine.request_analysis(board, self._generation, self._view)
        self._maybe_start_ai(board)

    def _maybe_start_ai(self, board: Optional[chess.Board] = None):
        if not self.engine.available or not self.is_live:
            return
        board = board or self.view_board()
        if self.outcome(board) is not None:
            return
        if self.players[board.turn] != PlayerKind.AI:
            return
        both_ai = not self.human_colors()
        if both_ai and not self.autoplay:
            return
        if self._ai_thinking:
            return
        self._set_thinking(True)
        delay = self.AI_VS_AI_DELAY_MS if both_ai else self.AI_DELAY_MS
        generation = self._generation
        QTimer.singleShot(delay, lambda: self._request_ai(generation))

    def _request_ai(self, generation: int):
        if generation != self._generation or not self.is_live:
            return
        board = self.view_board()
        if self.outcome(board) is not None or self.players[board.turn] != PlayerKind.AI:
            self._set_thinking(False)
            return
        self.engine.request_move(board, generation, self.difficulty)

    def _on_engine_move(self, generation: int, move: chess.Move):
        if generation != self._generation or not self.is_live:
            return
        self._set_thinking(False)
        self._apply_move(move, animate=True)

    def _on_analysis(self, generation: int, ctx: int, result):
        if generation != self._generation:
            return
        if 0 <= ctx < len(self._scores):
            self._scores[ctx] = result.lines[0].score
        if ctx != self._view:
            return
        board = self.view_board()
        best = result.lines[0]
        self.evalChanged.emit(best.expectation_white, format_score_white(best.score))
        mover = board.turn
        mover_exps = [expectation_for(mover, line.expectation_white) for line in result.lines]
        recs = recommendation_probs(mover_exps)
        suggestions = [
            Suggestion(
                move=line.move,
                san=line.san,
                rec_prob=rec,
                win_prob_mover=exp,
                score_text=format_score_white(line.score),
                pv_san=line.pv_san,
            )
            for line, rec, exp in zip(result.lines, recs, mover_exps)
        ]
        self.suggestionsChanged.emit(suggestions)

    def _set_thinking(self, value: bool):
        if self._ai_thinking != value:
            self._ai_thinking = value
            self.aiThinkingChanged.emit(value)

    @property
    def ai_thinking(self) -> bool:
        return self._ai_thinking

    # ---- Status line ---------------------------------------------------------

    def _emit_status(self):
        self.statusChanged.emit(self.status_text())

    def status_text(self) -> str:
        board = self.view_board()
        outcome = self.outcome(board)
        if outcome is not None:
            return self._outcome_text(outcome)
        turn_name = "White" if board.turn == chess.WHITE else "Black"
        if not self.is_live:
            return f"Reviewing — position after move {self._view} of {len(self._moves)}"
        if self.players[board.turn] == PlayerKind.AI:
            both_ai = not self.human_colors()
            if both_ai and not self.autoplay:
                return f"{turn_name} to move — AI paused"
            return f"{turn_name} to move — Stockfish is thinking…"
        return f"{turn_name} to move — your turn"

    @staticmethod
    def _outcome_text(outcome: chess.Outcome) -> str:
        reasons = {
            chess.Termination.CHECKMATE: "Checkmate",
            chess.Termination.STALEMATE: "Stalemate",
            chess.Termination.INSUFFICIENT_MATERIAL: "Insufficient material",
            chess.Termination.FIFTY_MOVES: "Fifty-move rule",
            chess.Termination.THREEFOLD_REPETITION: "Threefold repetition",
            chess.Termination.SEVENTYFIVE_MOVES: "75-move rule",
            chess.Termination.FIVEFOLD_REPETITION: "Fivefold repetition",
        }
        reason = reasons.get(outcome.termination, outcome.termination.name.title())
        if outcome.winner is None:
            return f"Draw — {reason} ({outcome.result()})"
        winner = "White" if outcome.winner == chess.WHITE else "Black"
        return f"{reason} — {winner} wins ({outcome.result()})"

    # ---- Save / load -----------------------------------------------------------

    def _player_name(self, color: chess.Color) -> str:
        if self.players[color] == PlayerKind.HUMAN:
            return "Human"
        return f"Stockfish (level {self.difficulty})"

    def save_pgn(self, path: str):
        game = chess.pgn.Game()
        if self._base.fen() != chess.STARTING_FEN:
            game.setup(self._base)
        game.headers["Event"] = "Chess Studio game"
        game.headers["Site"] = "Offline"
        game.headers["Date"] = datetime.date.today().strftime("%Y.%m.%d")
        game.headers["Round"] = "-"
        game.headers["White"] = self._player_name(chess.WHITE)
        game.headers["Black"] = self._player_name(chess.BLACK)
        outcome = self.outcome(self.live_board())
        game.headers["Result"] = outcome.result() if outcome else "*"

        node: chess.pgn.GameNode = game
        for i, move in enumerate(self._moves):
            node = node.add_variation(move)
            score = self._scores[i + 1]
            if score is not None:
                node.set_eval(score)
        with open(path, "w", encoding="utf-8") as fh:
            print(game, file=fh)

    def load_pgn(self, path: str) -> int:
        """Load the first game of a PGN file; returns the number of moves."""
        with open(path, "r", encoding="utf-8") as fh:
            game = chess.pgn.read_game(fh)
        if game is None:
            raise ValueError("No game found in this PGN file.")
        base = game.board()
        moves: list[chess.Move] = []
        san: list[str] = []
        scores: list[Optional[chess.engine.PovScore]] = [None]
        replay = base.copy()
        for node in game.mainline():
            move = node.move
            san.append(replay.san(move))
            replay.push(move)
            moves.append(move)
            scores.append(node.eval())

        self._generation += 1
        self._set_thinking(False)
        self._base = base
        self._moves = moves
        self._san = san
        self._scores = scores
        self._view = 0
        self.movesChanged.emit()
        self._after_position_change(None, animate=False)
        return len(moves)
