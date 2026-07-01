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
from .eval_utils import (KEY_CATEGORIES, MOVE_LABELS, classify_loss,
                         classify_move, expectation_for, format_score_white,
                         move_accuracy, recommendation_probs,
                         score_to_expectation_white)
from .opening_book import load_book

# Piece values (pawns) for the sacrifice heuristic.
_PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _is_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    """True if `move` offers >= 3 points of material on its destination square
    (an accepted-or-offered sacrifice), via a light static exchange check."""
    moved = board.piece_at(move.from_square)
    if moved is None:
        return False
    # The piece left en prise is the promoted piece on a promotion.
    moved_v = _PIECE_VALUE[move.promotion] if move.promotion \
        else _PIECE_VALUE[moved.piece_type]
    if board.is_en_passant(move):
        captured_v = _PIECE_VALUE[chess.PAWN]
    else:
        captured = board.piece_at(move.to_square)
        captured_v = _PIECE_VALUE[captured.piece_type] if captured else 0
    after = board.copy(stack=False)
    after.push(move)
    to = move.to_square
    attackers = after.attackers(not moved.color, to)
    if not attackers:
        # The piece lands on a safe square — not a sacrifice.
        return False
    defenders = after.attackers(moved.color, to)
    recapture_gain = 0
    if defenders:
        recapture_gain = min(_PIECE_VALUE[after.piece_at(a).piece_type]
                             for a in attackers)
    return moved_v - captured_v - recapture_gain >= 3


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


@dataclass
class PosBest:
    """The engine's verdict for one position (filled by analysis)."""
    move: chess.Move
    san: str
    second_white_exp: Optional[float] = None   # 2nd-best line, white expectation


@dataclass
class ColorReview:
    accuracy: Optional[float]   # 0..100, None if no scored moves
    scored: int
    counts: dict = field(default_factory=dict)   # category -> count


@dataclass
class CoachAlert:
    """Coach-mode verdict on the human's last move (emitted before the AI
    is allowed to reply)."""
    category: str                 # "mistake" | "blunder"
    loss: float                   # mover's drop in win expectation (0..1)
    before_exp: float             # mover POV, with best play
    after_exp: float              # mover POV, after the played move
    best_san: Optional[str]       # the better move, when known
    refutation_move: Optional[chess.Move]   # opponent's strongest reply
    refutation_san: list          # SAN line the opponent now has


class GameController(QObject):
    positionChanged = Signal(object, object, bool)   # board, last_move|None, animate
    movesChanged = Signal()                          # history structure changed
    viewChanged = Signal(int, int)                   # view index, total moves
    playersChanged = Signal()
    statusChanged = Signal(str)
    evalChanged = Signal(object, str)                # expectation_white|None, eval text
    suggestionsChanged = Signal(list)                # list[Suggestion]
    aiThinkingChanged = Signal(bool)
    openingChanged = Signal(str)                     # opening name for the view
    reviewChanged = Signal()                         # eval series / annotations changed
    reviewProgress = Signal(int, int)                # done, total (0,0 = idle)
    engineMissing = Signal(str)
    coachAlert = Signal(object)                      # CoachAlert

    AI_DELAY_MS = 150
    AI_VS_AI_DELAY_MS = 450
    COACH_LOSS_THRESHOLD = 0.10   # warn on mistakes (>=10%) and blunders
    COACH_TIMEOUT_MS = 4000       # never hold the AI longer than this

    def __init__(self, engine: EngineManager, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.engine.moveReady.connect(self._on_engine_move)
        self.engine.analysisReady.connect(self._on_analysis)
        self.engine.fullAnalysisLine.connect(self._on_full_line)
        self.engine.fullAnalysisDone.connect(self._on_full_done)
        self.engine.engineError.connect(self.engineMissing)
        self._book = load_book()

        self._base = chess.Board()
        self._moves: list[chess.Move] = []
        self._san: list[str] = []
        self._scores: list[Optional[chess.engine.PovScore]] = [None]  # per position index
        self._best: list[Optional[PosBest]] = [None]                  # parallel to _scores
        self._view = 0
        self._generation = 0
        self._game_id = 0     # changes when the move list changes (not on navigation)
        self._review_done = 0
        self._review_total = 0
        self._review_pending = False   # coalesces reviewChanged during analysis

        self.players: dict[chess.Color, PlayerKind] = {
            chess.WHITE: PlayerKind.HUMAN,
            chess.BLACK: PlayerKind.AI,
        }
        self.difficulty: dict[chess.Color, int] = {
            chess.WHITE: DEFAULT_DIFFICULTY,
            chess.BLACK: DEFAULT_DIFFICULTY,
        }
        self.autoplay = True          # gates AI-vs-AI continuous play
        self._ai_thinking = False

        # Coach mode: after a human move (vs an AI opponent) the AI reply is
        # held until the fresh analysis judges the move; a big drop raises a
        # CoachAlert and keeps holding until the user decides.
        self.coach_enabled = False
        self._coach_wait: Optional[dict] = None    # {"index", "generation"}
        self._coach_alert: Optional[CoachAlert] = None

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
    def moves(self) -> list[chess.Move]:
        return list(self._moves)

    def base_board(self) -> chess.Board:
        return self._base.copy()

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

    def _bump_game(self):
        """Mark the move list as changed (cancels any whole-game review)."""
        self._game_id += 1
        self.engine.cancel_full_analysis()
        self._review_done = self._review_total = 0
        self.reviewProgress.emit(0, 0)

    def _apply_move(self, move: chess.Move, animate: bool) -> bool:
        board = self.view_board()
        if move not in board.legal_moves:
            return False
        mover = board.turn
        if not self.is_live:
            # Branch from the reviewed position: discard the rest of the line.
            del self._moves[self._view:]
            del self._san[self._view:]
            del self._scores[self._view + 1:]
            del self._best[self._view + 1:]
        self._san.append(board.san(move))
        self._moves.append(move)
        self._scores.append(None)
        self._best.append(None)
        self._view = len(self._moves)
        self._generation += 1
        self._bump_game()
        self._set_thinking(False)
        self._arm_coach(mover)
        self.movesChanged.emit()
        self._after_position_change(move, animate)
        return True

    def _arm_coach(self, mover: chess.Color):
        """Hold the AI reply until analysis judges the human's move."""
        self._coach_wait = None
        if not (self.coach_enabled and self.engine.available
                and self.players[mover] == PlayerKind.HUMAN
                and self.players[not mover] == PlayerKind.AI
                and self.outcome(self.live_board()) is None):
            return
        self._coach_wait = {"index": len(self._moves) - 1,
                            "generation": self._generation}
        generation = self._generation
        QTimer.singleShot(self.COACH_TIMEOUT_MS,
                          lambda: self._coach_timeout(generation))

    def _coach_timeout(self, generation: int):
        """Analysis never arrived — release the held AI reply."""
        wait = self._coach_wait
        if wait and wait["generation"] == generation == self._generation:
            self._coach_wait = None
            self._maybe_start_ai()

    def undo(self):
        """Destructively take back the last move; against an AI opponent,
        rewind to the human's previous turn."""
        if not self._moves:
            return
        self._generation += 1
        self._bump_game()
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
        del self._best[len(self._moves) + 1:]

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
        self._bump_game()
        self._set_thinking(False)
        self._base = chess.Board()
        self._moves = []
        self._san = []
        self._scores = [None]
        self._best = [None]
        self._view = 0
        self.movesChanged.emit()
        self._after_position_change(None, animate=False)

    def start_from(self, moves: list, human_color: chess.Color,
                   base: Optional[chess.Board] = None):
        """Start a game from `base` (standard position by default) with `moves`
        pre-played (e.g. an opening line, or a game up to a mistake); the human
        takes `human_color`, the AI the other."""
        self._generation += 1
        self._bump_game()
        self._set_thinking(False)
        self._base = base.copy() if base is not None else chess.Board()
        replay = self._base.copy()
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
        self._best = [None] * (len(applied) + 1)
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

    def set_difficulty(self, level: int, color: Optional[chess.Color] = None):
        level = max(1, min(10, level))
        if color is None:
            self.difficulty[chess.WHITE] = level
            self.difficulty[chess.BLACK] = level
        else:
            self.difficulty[color] = level

    def difficulty_for(self, color: chess.Color) -> int:
        return self.difficulty[color]

    def set_autoplay(self, enabled: bool):
        self.autoplay = enabled
        if enabled:
            self._maybe_start_ai()
        self._emit_status()

    def difficulty_label(self, color: chess.Color) -> str:
        return DIFFICULTY_LEVELS[self.difficulty[color]].label

    # ---- Engine round-trips ------------------------------------------------------

    def refresh_analysis(self):
        """Re-request analysis / AI move for the current position. Call after
        the engine becomes ready or when player settings change externally."""
        self._refresh_engine_requests()

    def _emit_review_soon(self):
        """Coalesce a burst of review updates (e.g. one per analyzed position)
        into a single reviewChanged on the next event-loop tick."""
        if not self._review_pending:
            self._review_pending = True
            QTimer.singleShot(100, self._flush_review)

    def _flush_review(self):
        if self._review_pending:
            self._review_pending = False
            self.reviewChanged.emit()

    # ---- Opening identification ------------------------------------------------

    def opening_name(self) -> str:
        """Name of the deepest known opening along the line up to the view."""
        if self._book is None:
            return ""
        board = self._base.copy()
        epds = [board.epd()]
        for move in self._moves[:self._view]:
            board.push(move)
            epds.append(board.epd())
        named = self._book.name_for_history(epds)
        return f"{named[0]} · {named[1]}" if named else ""

    # ---- Game review (move quality, accuracy, eval graph) ----------------------

    def eval_series(self) -> list:
        """White-POV win expectation (0..1) per position; None where unknown."""
        base_ply = self._base.ply()
        return [None if s is None
                else score_to_expectation_white(s, ply=base_ply + i)
                for i, s in enumerate(self._scores)]

    def _classify_at(self, board: chess.Board, i: int, move: chess.Move):
        """Rich category for move i, or None if positions i / i+1 lack evals.
        `board` must be the position BEFORE move i."""
        before = self._scores[i]
        after = self._scores[i + 1] if i + 1 < len(self._scores) else None
        if before is None or after is None:
            return None
        base_ply = self._base.ply()
        mover = board.turn
        best_exp = expectation_for(
            mover, score_to_expectation_white(before, ply=base_ply + i))
        achieved = expectation_for(
            mover, score_to_expectation_white(after, ply=base_ply + i + 1))
        loss = max(0.0, best_exp - achieved)

        best = self._best[i]
        is_best = best is not None and best.move == move
        is_book = self._book is not None and any(
            m.uci == move.uci() for m in self._book.book_replies(board))
        only_move = False
        # "Great" only when the single good move keeps a real, still-contested
        # advantage — not when mopping up an already-won (or lost) position.
        if is_best and best.second_white_exp is not None and \
                board.legal_moves.count() > 1 and 0.2 <= best_exp <= 0.85:
            second_exp = expectation_for(mover, best.second_white_exp)
            only_move = (best_exp - second_exp) >= 0.15
        is_sac = is_best and achieved >= 0.55 and _is_sacrifice(board, move)
        return classify_move(loss, is_book=is_book, is_best=is_best,
                             is_sacrifice=is_sac, only_move=only_move,
                             best_exp=best_exp, achieved_exp=achieved)

    def move_annotations(self) -> list:
        """Per-ply rich quality class, or None where not yet evaluated."""
        board = self._base.copy()
        out: list = []
        for i, move in enumerate(self._moves):
            out.append(self._classify_at(board, i, move))
            board.push(move)
        return out

    def accuracy_summary(self) -> dict:
        base_ply = self._base.ply()
        board = self._base.copy()
        reviews = {chess.WHITE: ColorReview(None, 0), chess.BLACK: ColorReview(None, 0)}
        accs = {chess.WHITE: [], chess.BLACK: []}
        for i, move in enumerate(self._moves):
            before = self._scores[i]
            after = self._scores[i + 1] if i + 1 < len(self._scores) else None
            mover = board.turn
            klass = self._classify_at(board, i, move)
            if before is not None and after is not None:
                before_pct = expectation_for(
                    mover, score_to_expectation_white(before, ply=base_ply + i)) * 100
                after_pct = expectation_for(
                    mover, score_to_expectation_white(after, ply=base_ply + i + 1)) * 100
                accs[mover].append(move_accuracy(before_pct, after_pct))
                if klass:
                    counts = reviews[mover].counts
                    counts[klass] = counts.get(klass, 0) + 1
            board.push(move)
        for color in (chess.WHITE, chess.BLACK):
            vals = accs[color]
            reviews[color].scored = len(vals)
            reviews[color].accuracy = (sum(vals) / len(vals)) if vals else None
        return reviews

    def key_moments(self) -> list:
        """List of (position_index, category) for the notable moves — used to
        mark the eval graph and let the user jump to them."""
        board = self._base.copy()
        moments: list = []
        for i, move in enumerate(self._moves):
            klass = self._classify_at(board, i, move)
            if klass in KEY_CATEGORIES:
                moments.append((i + 1, klass))
            board.push(move)
        return moments

    def review_data(self):
        """Single game replay producing everything the review UI needs:
        (eval_series, annotations, reviews, key_moments). Cheaper than calling
        move_annotations / accuracy_summary / key_moments separately."""
        base_ply = self._base.ply()
        series = self.eval_series()
        board = self._base.copy()
        annotations: list = []
        reviews = {chess.WHITE: ColorReview(None, 0), chess.BLACK: ColorReview(None, 0)}
        accs = {chess.WHITE: [], chess.BLACK: []}
        moments: list = []
        for i, move in enumerate(self._moves):
            klass = self._classify_at(board, i, move)
            annotations.append(klass)
            before = self._scores[i]
            after = self._scores[i + 1] if i + 1 < len(self._scores) else None
            mover = board.turn
            if before is not None and after is not None:
                before_pct = expectation_for(
                    mover, score_to_expectation_white(before, ply=base_ply + i)) * 100
                after_pct = expectation_for(
                    mover, score_to_expectation_white(after, ply=base_ply + i + 1)) * 100
                accs[mover].append(move_accuracy(before_pct, after_pct))
                if klass:
                    reviews[mover].counts[klass] = reviews[mover].counts.get(klass, 0) + 1
            if klass in KEY_CATEGORIES:
                moments.append((i + 1, klass))
            board.push(move)
        for color in (chess.WHITE, chess.BLACK):
            vals = accs[color]
            reviews[color].scored = len(vals)
            reviews[color].accuracy = (sum(vals) / len(vals)) if vals else None
        return series, annotations, reviews, moments

    def best_alternative(self, view_index: int):
        """For the move that led to `view_index`, the engine's best SAN if the
        played move was not itself the best move; otherwise None."""
        i = view_index - 1
        if i < 0 or i >= len(self._moves):
            return None
        best = self._best[i] if i < len(self._best) else None
        if best is None or best.move == self._moves[i]:
            return None
        return best.san

    def scored_positions(self) -> int:
        return sum(1 for s in self._scores if s is not None)

    def analyze_game(self):
        """Evaluate every position so move annotations and accuracy are complete."""
        if not self.engine.available or not self._moves:
            return
        indexed: list = []
        board = self._base.copy()
        indexed.append((0, board.copy()))
        for i, move in enumerate(self._moves):
            board.push(move)
            indexed.append((i + 1, board.copy()))
        self._review_done = 0
        # Terminal positions are skipped by the engine loop; don't count them
        # or the progress bar would never reach 100%.
        self._review_total = sum(1 for _, b in indexed if not b.is_game_over())
        self.reviewProgress.emit(0, self._review_total)
        self.engine.request_full_analysis(indexed, self._game_id)

    def _on_full_line(self, game_id: int, line):
        if game_id != self._game_id:
            return
        index = line.index
        if 0 <= index < len(self._scores):
            self._scores[index] = line.score
            self._best[index] = PosBest(line.best_move, line.best_san,
                                        line.second_white_exp)
        self._review_done += 1
        self.reviewProgress.emit(self._review_done, self._review_total)
        if index == self._view:
            board = self.view_board()
            self.evalChanged.emit(
                score_to_expectation_white(line.score, ply=board.ply()),
                format_score_white(line.score))
        self._emit_review_soon()

    def _on_full_done(self, game_id: int, completed: bool):
        if game_id != self._game_id:
            return
        self._review_done = self._review_total
        self.reviewProgress.emit(self._review_total, self._review_total)
        self._review_pending = True
        self._flush_review()

    def _after_position_change(self, last_move: Optional[chess.Move], animate: bool):
        self._coach_alert = None   # any position change resolves a pending alert
        board = self.view_board()
        self.positionChanged.emit(board, last_move, animate)
        self.viewChanged.emit(self._view, len(self._moves))
        self.suggestionsChanged.emit([])
        self.openingChanged.emit(self.opening_name())
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
        if self._coach_hold_active():
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
        self.engine.request_move(board, generation, self.difficulty[board.turn])

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
            best = result.lines[0]
            second_exp = result.lines[1].expectation_white if len(result.lines) > 1 else None
            self._best[ctx] = PosBest(best.move, best.san, second_exp)
            self._emit_review_soon()
        self._maybe_coach_judge(ctx, result)
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

    # ---- Coach mode ------------------------------------------------------------

    def _coach_hold_active(self) -> bool:
        if self._coach_alert is not None:
            return True
        wait = self._coach_wait
        return wait is not None and wait["generation"] == self._generation

    def _maybe_coach_judge(self, ctx: int, result):
        """Fresh analysis arrived — if it evaluates the position right after a
        held human move, judge that move and either alert or release the AI."""
        wait = self._coach_wait
        if wait is None or wait["generation"] != self._generation:
            return
        if ctx != wait["index"] + 1:
            return
        self._coach_wait = None
        i = wait["index"]
        before = self._scores[i] if i < len(self._scores) else None
        if before is None:
            # The pre-move position was never analysed (very fast play) —
            # nothing to compare against, so just let the AI reply.
            self._maybe_start_ai()
            return
        base_ply = self._base.ply()
        mover = not self.live_board().turn
        best_exp = expectation_for(
            mover, score_to_expectation_white(before, ply=base_ply + i))
        achieved = expectation_for(
            mover, score_to_expectation_white(result.lines[0].score,
                                              ply=base_ply + i + 1))
        loss = max(0.0, best_exp - achieved)
        if loss < self.COACH_LOSS_THRESHOLD:
            self._maybe_start_ai()
            return
        best = self._best[i] if i < len(self._best) else None
        best_san = None
        if best is not None and i < len(self._moves) and best.move != self._moves[i]:
            best_san = best.san
        refutation = result.lines[0]
        self._coach_alert = CoachAlert(
            category=classify_loss(loss), loss=loss,
            before_exp=best_exp, after_exp=achieved, best_san=best_san,
            refutation_move=refutation.move,
            refutation_san=list(refutation.pv_san))
        self._emit_status()
        self.coachAlert.emit(self._coach_alert)

    def coach_play_on(self):
        """User chose to keep the flagged move — let the AI reply."""
        self._coach_alert = None
        self._emit_status()
        self._maybe_start_ai()

    def set_coach_enabled(self, enabled: bool):
        self.coach_enabled = enabled
        if not enabled:
            self._coach_wait = None
            if self._coach_alert is not None:
                self._coach_alert = None
                self._emit_status()
            self._maybe_start_ai()

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
        if self._coach_alert is not None:
            label = MOVE_LABELS.get(self._coach_alert.category, "Mistake")
            return f"Coach — that looks like a {label.lower()}. Take back or keep it?"
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
        return f"Stockfish (level {self.difficulty[color]})"

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
        self._bump_game()
        self._set_thinking(False)
        self._base = base
        self._moves = moves
        self._san = san
        self._scores = scores
        self._best = [None] * len(scores)
        self._view = 0
        self.movesChanged.emit()
        self._after_position_change(None, animate=False)
        return len(moves)
