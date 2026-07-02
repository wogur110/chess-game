"""Tactics tab: re-solve the mistakes from your own games.

Puzzles are mined automatically when a game review finishes (see
GameController._mine_puzzles): every miss/mistake/blunder you played whose
position has a verified, clearly-best answer becomes a card in your deck.
Solving needs no engine at all — opponent replies come from the stored
solution line.
"""

from __future__ import annotations

import random
from typing import Optional

import chess
from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from . import theme
from .board_widget import BoardWidget
from .eval_utils import MOVE_LABELS, MOVE_SYMBOLS
from .i18n import tr
from .puzzle_pack import THEME_LABELS, load_pack
from .puzzle_store import BOX_INTERVALS, Puzzle, PuzzleStore
from .sidebar import CATEGORY_COLORS

WRONG_FLASH_MS = 650
REPLY_DELAY_MS = 450

# Puzzle rush: 3 strikes or 3 minutes, difficulty escalates per solve.
RUSH_SECONDS = 180
RUSH_START_RATING = 750
RUSH_STEP = 60
RUSH_STRIKES = 3


class _Hint:
    """Duck-typed stand-in for the Suggestion objects BoardWidget paints."""

    def __init__(self, move: chess.Move, rec_prob: float):
        self.move = move
        self.rec_prob = rec_prob


class TacticsTab(QWidget):
    dueCountChanged = Signal(int)   # drives the "(N due)" tab badge

    def __init__(self, store: PuzzleStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.pack = load_pack()
        self._puzzle = None                 # Puzzle (deck) or PackPuzzle
        self._mode = "deck"                 # "deck" | "rush" | "practice"
        self._board = chess.Board()
        self._step = 0
        self._wrong = 0
        self._used_hint = False
        self._finished = False
        self._generation = 0
        self._session_queue: list = []      # keys still to review this session
        self._session_total = 0
        self._session_clean = 0
        self._rush_score = 0
        self._rush_strikes = 0
        self._rush_target = RUSH_START_RATING
        self._rush_seconds = 0
        self._rush_used: set = set()
        self._rush_timer = QTimer(self)
        self._rush_timer.setInterval(1000)
        self._rush_timer.timeout.connect(self._rush_tick)
        self._practice_list: list = []
        self._practice_index = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        root.addWidget(splitter)

        # Left: the deck
        deck_panel = QWidget()
        deck_panel.setMinimumWidth(210)
        deck_layout = QVBoxLayout(deck_panel)
        deck_layout.setContentsMargins(0, 0, 0, 0)
        deck_layout.setSpacing(8)
        title = QLabel(tr("MY MISTAKES"))
        title.setObjectName("SectionTitle")
        deck_layout.addWidget(title)
        self.review_button = QPushButton(tr("Review due"))
        self.review_button.setObjectName("PrimaryButton")
        self.review_button.setToolTip(tr(
            "Work through every puzzle scheduled for today, oldest first "
            "(spaced repetition: clean solves come back later, fails tomorrow)"))
        self.review_button.clicked.connect(self._start_session)
        deck_layout.addWidget(self.review_button)
        self.deck_list = QListWidget()
        self.deck_list.itemClicked.connect(self._on_item_clicked)
        deck_layout.addWidget(self.deck_list, 1)
        self.deck_label = QLabel("")
        self.deck_label.setObjectName("SubtleLabel")
        self.deck_label.setWordWrap(True)
        deck_layout.addWidget(self.deck_label)
        self.boxes_label = QLabel("")
        self.boxes_label.setObjectName("SubtleLabel")
        self.boxes_label.setWordWrap(True)
        self.boxes_label.setToolTip(tr(
            "Leitner boxes: how many puzzles sit at each review interval — "
            "the further right, the better you know them"))
        deck_layout.addWidget(self.boxes_label)

        # Puzzle rush / themed practice (bundled starter pack)
        rush_title = QLabel(tr("PUZZLE RUSH"))
        rush_title.setObjectName("SectionTitle")
        deck_layout.addWidget(rush_title)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("All themes"), None)
        if self.pack is not None:
            for key, label in THEME_LABELS.items():
                if self.pack.theme_counts.get(key):
                    self.theme_combo.addItem(tr(label), key)
        deck_layout.addWidget(self.theme_combo)
        rush_row = QHBoxLayout()
        rush_row.setSpacing(8)
        self.rush_button = QPushButton(tr("Start rush"))
        self.rush_button.setToolTip(tr(
            "3 strikes or 3 minutes — puzzles get harder as you solve. "
            "A wrong move fails the puzzle."))
        self.rush_button.clicked.connect(self._start_rush)
        rush_row.addWidget(self.rush_button)
        self.practice_button = QPushButton(tr("Practice"))
        self.practice_button.setToolTip(tr(
            "Practice the selected theme untimed, easiest first."))
        self.practice_button.clicked.connect(self._start_practice)
        rush_row.addWidget(self.practice_button)
        deck_layout.addLayout(rush_row)
        self.rush_best_label = QLabel("")
        self.rush_best_label.setObjectName("SubtleLabel")
        deck_layout.addWidget(self.rush_best_label)
        if self.pack is None:
            self.rush_best_label.setText(tr(
                "Puzzle pack not found — run tools/build_puzzle_pack.py."))
            for widget in (self.theme_combo, self.rush_button,
                           self.practice_button):
                widget.setEnabled(False)
        else:
            self._update_rush_best_label()
        splitter.addWidget(deck_panel)

        # Center: board
        self.board_widget = BoardWidget()
        self.board_widget.set_movable_colors([])
        self.board_widget.moveRequested.connect(self._on_board_move)
        splitter.addWidget(self.board_widget)

        # Right: solve panel
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(420)
        panel_outer = QVBoxLayout(panel)
        panel_outer.setContentsMargins(0, 0, 0, 0)
        panel_content = QWidget()
        panel_content.setStyleSheet("background: transparent;")
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QScrollArea.NoFrame)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel_scroll.setWidget(panel_content)
        panel_scroll.viewport().setStyleSheet("background: transparent;")
        panel_outer.addWidget(panel_scroll)
        side = QVBoxLayout(panel_content)
        side.setContentsMargins(16, 14, 16, 14)
        side.setSpacing(9)

        self.rush_info_label = QLabel("")
        self.rush_info_label.setObjectName("StatusLabel")
        self.rush_info_label.setVisible(False)
        side.addWidget(self.rush_info_label)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        side.addWidget(self.status_label)

        self.origin_label = QLabel("")
        self.origin_label.setObjectName("SubtleLabel")
        self.origin_label.setWordWrap(True)
        side.addWidget(self.origin_label)

        self.solution_label = QLabel("")
        self.solution_label.setObjectName("SubtleLabel")
        self.solution_label.setWordWrap(True)
        self.solution_label.setVisible(False)
        side.addWidget(self.solution_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.hint_button = QPushButton(tr("Hint"))
        self.hint_button.setToolTip(tr("Show the next move of the solution "
                                       "(the attempt no longer counts as clean)"))
        self.hint_button.clicked.connect(self._on_hint)
        buttons.addWidget(self.hint_button)
        self.solution_button = QPushButton(tr("Show solution"))
        self.solution_button.clicked.connect(self._on_show_solution)
        buttons.addWidget(self.solution_button)
        side.addLayout(buttons)

        self.next_button = QPushButton(tr("Next puzzle →"))
        self.next_button.setObjectName("PrimaryButton")
        self.next_button.clicked.connect(self._on_next)
        side.addWidget(self.next_button)

        self.remove_button = QPushButton(tr("Remove this puzzle"))
        self.remove_button.clicked.connect(self._on_remove)
        side.addWidget(self.remove_button)
        side.addStretch(1)

        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 520, 340])

        self.refresh()
        self._set_idle_state()

    # ---- deck list ----

    def refresh(self):
        """Rebuild the deck list (after mining, solving or scheduling)."""
        current = getattr(self._puzzle, "key", None)
        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        puzzles = sorted(self.store.all(),
                         key=lambda p: (not p.is_due(), p.solved,
                                        p.due or "0000-00-00",
                                        p.source.get("date", "")))
        for puzzle in puzzles:
            symbol = MOVE_SYMBOLS.get(puzzle.category, "?")
            label = tr(MOVE_LABELS.get(puzzle.category, puzzle.category))
            mover = tr(puzzle.source.get("mover", "?"))
            move_no = puzzle.source.get("move_no", "?")
            date = puzzle.source.get("date", "")
            mark = "✓ " if puzzle.solved else ""
            when = (tr("· due now") if puzzle.is_due()
                    else tr("· next {due}", due=puzzle.due))
            where = tr("{mover} move {move_no}", mover=mover, move_no=move_no)
            item = QListWidgetItem(
                f"{mark}{label} {symbol} — {where} · {date} {when}")
            item.setData(Qt.UserRole, puzzle.key)
            item.setForeground(QColor(CATEGORY_COLORS.get(puzzle.category,
                                                          theme.TEXT)))
            self.deck_list.addItem(item)
            if puzzle.key == current:
                self.deck_list.setCurrentItem(item)
        self.deck_list.blockSignals(False)
        total = len(puzzles)
        solved = sum(1 for p in puzzles if p.solved)
        due = len(self.store.due_puzzles())
        self.deck_label.setText(
            tr("{total} puzzle(s) · {solved} solved · {due} due for review",
               total=total, solved=solved, due=due))
        counts = [0] * len(BOX_INTERVALS)
        for puzzle in puzzles:
            counts[max(0, min(puzzle.box, len(counts) - 1))] += 1
        days = "/".join(str(d) for d in BOX_INTERVALS)
        self.boxes_label.setText(
            tr("Boxes ({days} days): {counts}", days=days,
               counts=" · ".join(str(c) for c in counts)))
        self.review_button.setText(tr("Review due ({due})", due=due) if due
                                   else tr("Review due"))
        self.review_button.setEnabled(due > 0)
        self.dueCountChanged.emit(due)

    def _set_idle_state(self):
        if self.store.all():
            self.status_label.setText(tr("Pick a puzzle on the left."))
        else:
            self.status_label.setText(tr("No puzzles yet."))
            self.origin_label.setText(tr(
                "Play a game and run “Analyze game” — every mistake with a "
                "clear best answer becomes a puzzle here, so you retrain on "
                "exactly the positions you misplayed."))
        for button in (self.hint_button, self.solution_button,
                       self.remove_button):
            button.setEnabled(False)
        self.next_button.setEnabled(bool(self.store.all()))

    # ---- review session (spaced repetition) ----

    def _start_session(self):
        """Serve every puzzle due today, oldest first."""
        due = self.store.due_puzzles()
        if not due:
            return
        self._exit_pack_modes()
        self._session_queue = [p.key for p in due]
        self._session_total = len(due)
        self._session_clean = 0
        self._serve_next_due()

    def _serve_next_due(self):
        while self._session_queue:
            puzzle = self.store.get(self._session_queue.pop(0))
            if puzzle is not None:
                self._start_puzzle(puzzle)
                left = len(self._session_queue)
                done = self._session_total - left
                self.status_label.setText(
                    f"[{done}/{self._session_total}] " +
                    self.status_label.text())
                self.next_button.setText(
                    tr("Next due ({left} left) →", left=left) if left
                    else tr("Finish session →"))
                return
        self._end_session()

    def _end_session(self):
        total = self._session_total
        self._session_queue = []
        self._session_total = 0
        self.next_button.setText(tr("Next puzzle →"))
        self.status_label.setText(
            tr("★ Review done — {clean}/{total} clean. Failed cards come back "
               "tomorrow; clean ones moved up a box.",
               clean=self._session_clean, total=total))

    @property
    def _in_session(self) -> bool:
        return self._session_total > 0

    # ---- solving ----

    def _on_item_clicked(self, item: QListWidgetItem):
        # Picking a puzzle by hand leaves any running session or rush.
        self._exit_pack_modes()
        self._session_queue = []
        self._session_total = 0
        self.next_button.setText(tr("Next puzzle →"))
        puzzle = self.store.get(item.data(Qt.UserRole))
        if puzzle is not None:
            self._start_puzzle(puzzle)

    def _begin_solving(self, puzzle):
        """Shared setup for deck puzzles and pack puzzles alike — `puzzle`
        only needs .fen / .solution / .solution_san."""
        self._generation += 1
        self._puzzle = puzzle
        self._board = chess.Board(puzzle.fen)
        self._step = 0
        self._wrong = 0
        self._used_hint = False
        self._finished = False
        solver = self._board.turn
        self.board_widget.set_position(self._board, None, animate=False)
        self.board_widget.set_orientation(solver)
        self.board_widget.set_movable_colors([solver])
        self.board_widget.set_suggestions([])
        side_name = tr("White") if solver == chess.WHITE else tr("Black")
        self.status_label.setText(
            tr("{side} to move — find the best move.", side=side_name))
        self.solution_label.setVisible(False)
        in_rush = self._mode == "rush"
        self.hint_button.setEnabled(not in_rush)
        self.solution_button.setEnabled(not in_rush)
        self.remove_button.setEnabled(self._mode == "deck")
        self.next_button.setEnabled(True)

    def _start_puzzle(self, puzzle: Puzzle):
        self._exit_pack_modes()
        self._begin_solving(puzzle)
        symbol = MOVE_SYMBOLS.get(puzzle.category, "?")
        label = tr(MOVE_LABELS.get(puzzle.category, puzzle.category))
        source = puzzle.source
        self.origin_label.setText(
            tr("{label} {symbol} from your game {white} vs {black} ({date}), "
               "move {move_no} — you played {played}.",
               label=label, symbol=symbol,
               white=source.get("white", "?"), black=source.get("black", "?"),
               date=source.get("date", "?"),
               move_no=source.get("move_no", "?"), played=puzzle.played_san))

    def _on_board_move(self, move: chess.Move):
        puzzle = self._puzzle
        if puzzle is None or self._finished or \
                self._step >= len(puzzle.solution):
            return
        if move.uci() == puzzle.solution[self._step]:
            self._accept_move(move)
        elif self._mode == "rush":
            self._rush_fail(move)
        else:
            self._reject_move(move)

    def _accept_move(self, move: chess.Move):
        self._board.push(move)
        self._step += 1
        self.board_widget.set_position(self._board, move, animate=True)
        self.board_widget.set_suggestions([])
        if self._step >= len(self._puzzle.solution):
            self._finish(solved=True)
            return
        self.status_label.setText(tr("✓ Correct — the reply is coming…"))
        generation = self._generation
        QTimer.singleShot(REPLY_DELAY_MS, lambda: self._play_reply(generation))

    def _play_reply(self, generation: int):
        if generation != self._generation or self._puzzle is None:
            return
        move = chess.Move.from_uci(self._puzzle.solution[self._step])
        self._board.push(move)
        self._step += 1
        self.board_widget.set_position(self._board, move, animate=True)
        self.status_label.setText(tr("Your move — continue the line."))

    def _reject_move(self, move: chess.Move):
        self._wrong += 1
        san = self._board.san(move)
        # Show the wrong move briefly, then rewind it.
        self._board.push(move)
        self.board_widget.set_position(self._board, move, animate=False)
        self.status_label.setText(tr("✗ {san} isn’t it — try again.", san=san))
        generation = self._generation
        QTimer.singleShot(WRONG_FLASH_MS, lambda: self._revert_wrong(generation))

    def _revert_wrong(self, generation: int):
        if generation != self._generation:
            return
        self._board.pop()
        last = self._board.move_stack[-1] if self._board.move_stack else None
        self.board_widget.set_position(self._board, last, animate=False)

    def _finish(self, solved: bool):
        puzzle = self._puzzle
        self._finished = True
        self.board_widget.set_movable_colors([])
        if self._mode == "rush":
            self._rush_solved()   # a rush puzzle only finishes by solving
            return
        clean = solved and self._wrong == 0 and not self._used_hint
        if self._mode == "deck":
            self.store.record_attempt(puzzle.key, solved, clean)
        if clean:
            self._session_clean += 1 if self._in_session else 0
        if solved:
            if clean:
                text = tr("★ Solved — first try!")
            elif self._used_hint:
                text = tr("★ Solved (wrong tries: {wrong}, hint used).",
                          wrong=self._wrong)
            else:
                text = tr("★ Solved (wrong tries: {wrong}).", wrong=self._wrong)
            self.status_label.setText(text)
        line = " ".join(puzzle.solution_san)
        self.solution_label.setText(tr("Solution: {line}", line=line))
        self.solution_label.setVisible(True)
        self.hint_button.setEnabled(False)
        self.solution_button.setEnabled(False)
        if self._mode == "deck":
            self.refresh()

    def _on_hint(self):
        puzzle = self._puzzle
        if puzzle is None or self._finished or \
                self._step >= len(puzzle.solution):
            return
        self._used_hint = True
        move = chess.Move.from_uci(puzzle.solution[self._step])
        self.board_widget.set_suggestions([_Hint(move, 1.0)])

    def _on_show_solution(self):
        if self._puzzle is None or self._finished:
            return
        self.status_label.setText(tr(
            "Solution revealed — counted as a fail; it will come back tomorrow."))
        self._wrong += 1
        self._finish(solved=False)

    def _on_next(self):
        """Serve the session queue while reviewing, the next practice puzzle
        while practicing, stop a rush — otherwise jump to the first
        due/unsolved deck puzzle other than the current one."""
        if self._mode == "rush":
            self._end_rush()
            return
        if self._mode == "practice":
            self._practice_index += 1
            self._serve_practice()
            return
        if self._in_session:
            self._serve_next_due()
            self.refresh()
            return
        current = getattr(self._puzzle, "key", None)
        candidates = [p for p in self.store.due_puzzles()
                      if p.key != current] or \
                     [p for p in self.store.all()
                      if not p.solved and p.key != current]
        if candidates:
            self._start_puzzle(candidates[0])
            self.refresh()
        else:
            self.status_label.setText(tr(
                "Deck clear — nothing due. Analyze more games to add puzzles."))

    def _on_remove(self):
        if self._puzzle is None or self._mode != "deck":
            return
        self.store.remove(self._puzzle.key)
        self._puzzle = None
        self._generation += 1
        self.board_widget.set_movable_colors([])
        self.refresh()
        self._set_idle_state()

    # ---- puzzle rush / themed practice (bundled starter pack) ----

    def _exit_pack_modes(self):
        """Leave rush/practice (stopping the clock) and return to deck mode."""
        if self._mode == "rush":
            self._rush_timer.stop()
            self.rush_info_label.setVisible(False)
        self._mode = "deck"
        self.next_button.setText(tr("Next puzzle →"))

    def _update_rush_best_label(self):
        best = int(QSettings().value("rush_best", 0))
        self.rush_best_label.setText(tr("Best: {best}", best=best))

    def _set_pack_origin(self, puzzle, with_themes: bool):
        themes = ", ".join(tr(THEME_LABELS[t]) for t in puzzle.themes
                           if t in THEME_LABELS)
        # In a rush the motif would be a spoiler — show the rating only.
        self.origin_label.setText(
            tr("Rating {rating} · {themes}", rating=puzzle.rating,
               themes=themes) if with_themes else
            tr("Rating {rating}", rating=puzzle.rating))

    # -- rush --

    def _start_rush(self):
        if self.pack is None or not len(self.pack):
            return
        self._exit_pack_modes()
        self._session_queue = []
        self._session_total = 0
        self._mode = "rush"
        self._rush_score = 0
        self._rush_strikes = 0
        self._rush_target = RUSH_START_RATING
        self._rush_seconds = RUSH_SECONDS
        self._rush_used = set()
        self._rush_timer.start()
        self.rush_info_label.setVisible(True)
        self._update_rush_info()
        self._serve_rush_puzzle()

    def _serve_rush_puzzle(self):
        pool = self.pack.in_rating_window(
            self._rush_target - 100, self._rush_target + 150, self._rush_used)
        if not pool:
            unused = [p for p in self.pack.puzzles if p not in self._rush_used]
            if not unused:
                self._end_rush()
                return
            pool = sorted(unused,
                          key=lambda p: abs(p.rating - self._rush_target))[:20]
        puzzle = random.choice(pool)
        self._rush_used.add(puzzle)
        self._begin_solving(puzzle)
        self._set_pack_origin(puzzle, with_themes=False)
        self.next_button.setText(tr("Stop rush"))

    def _rush_solved(self):
        self._rush_score += 1
        self._rush_target += RUSH_STEP
        self._update_rush_info()
        self.status_label.setText(tr("Solved! Next…"))
        generation = self._generation
        QTimer.singleShot(600, lambda: self._rush_advance(generation))

    def _rush_fail(self, move: chess.Move):
        """In a rush the first wrong move fails the puzzle — no retries."""
        self._finished = True
        self._rush_strikes += 1
        self.board_widget.set_movable_colors([])
        correct = chess.Move.from_uci(self._puzzle.solution[self._step])
        self.board_widget.set_suggestions([_Hint(correct, 1.0)])
        line = " ".join(self._puzzle.solution_san)
        self.status_label.setText(
            tr("✗ Wrong — the answer was {line}.", line=line))
        self._update_rush_info()
        generation = self._generation
        QTimer.singleShot(1400, lambda: self._rush_advance(generation))

    def _rush_advance(self, generation: int):
        if generation != self._generation or self._mode != "rush":
            return
        if self._rush_strikes >= RUSH_STRIKES or self._rush_seconds <= 0:
            self._end_rush()
        else:
            self._serve_rush_puzzle()

    def _rush_tick(self):
        if self._mode != "rush":
            self._rush_timer.stop()
            return
        self._rush_seconds -= 1
        self._update_rush_info()
        if self._rush_seconds <= 0:
            self._end_rush()

    def _update_rush_info(self):
        minutes, seconds = divmod(max(0, self._rush_seconds), 60)
        self.rush_info_label.setText(
            tr("⏱ {time} · Score {score} · ✗ {strikes}/3",
               time=f"{minutes}:{seconds:02d}", score=self._rush_score,
               strikes=self._rush_strikes))

    def _end_rush(self):
        self._rush_timer.stop()
        self._generation += 1          # cancel any pending advance/reply
        self._mode = "deck"
        self._puzzle = None
        self._finished = True
        self.board_widget.set_movable_colors([])
        self.board_widget.set_suggestions([])
        self.rush_info_label.setVisible(False)
        self.next_button.setText(tr("Next puzzle →"))
        best = int(QSettings().value("rush_best", 0))
        if self._rush_score > best:
            best = self._rush_score
            QSettings().setValue("rush_best", best)
        self._update_rush_best_label()
        self.status_label.setText(
            tr("Rush over — score {score} (best {best}).",
               score=self._rush_score, best=best))
        self.origin_label.setText("")
        self.solution_label.setVisible(False)
        for button in (self.hint_button, self.solution_button,
                       self.remove_button):
            button.setEnabled(False)

    # -- themed practice --

    def _start_practice(self):
        if self.pack is None or not len(self.pack):
            return
        self._exit_pack_modes()
        self._session_queue = []
        self._session_total = 0
        theme = self.theme_combo.currentData()
        self._practice_list = self.pack.by_theme(theme)
        if not self._practice_list:
            return
        self._mode = "practice"
        self._practice_index = 0
        self._serve_practice()

    def _serve_practice(self):
        if self._practice_index >= len(self._practice_list):
            self._puzzle = None
            self.board_widget.set_movable_colors([])
            self.status_label.setText(
                tr("No more puzzles in this theme — pick another."))
            return
        puzzle = self._practice_list[self._practice_index]
        self._begin_solving(puzzle)
        self._set_pack_origin(puzzle, with_themes=True)
