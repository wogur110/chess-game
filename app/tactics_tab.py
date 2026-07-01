"""Tactics tab: re-solve the mistakes from your own games.

Puzzles are mined automatically when a game review finishes (see
GameController._mine_puzzles): every miss/mistake/blunder you played whose
position has a verified, clearly-best answer becomes a card in your deck.
Solving needs no engine at all — opponent replies come from the stored
solution line.
"""

from __future__ import annotations

from typing import Optional

import chess
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea,
                               QSplitter, QVBoxLayout, QWidget)

from . import theme
from .board_widget import BoardWidget
from .eval_utils import MOVE_LABELS, MOVE_SYMBOLS
from .puzzle_store import Puzzle, PuzzleStore
from .sidebar import CATEGORY_COLORS

WRONG_FLASH_MS = 650
REPLY_DELAY_MS = 450


class _Hint:
    """Duck-typed stand-in for the Suggestion objects BoardWidget paints."""

    def __init__(self, move: chess.Move, rec_prob: float):
        self.move = move
        self.rec_prob = rec_prob


class TacticsTab(QWidget):
    def __init__(self, store: PuzzleStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self._puzzle: Optional[Puzzle] = None
        self._board = chess.Board()
        self._step = 0
        self._wrong = 0
        self._used_hint = False
        self._finished = False
        self._generation = 0

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
        title = QLabel("MY MISTAKES")
        title.setObjectName("SectionTitle")
        deck_layout.addWidget(title)
        self.deck_list = QListWidget()
        self.deck_list.itemClicked.connect(self._on_item_clicked)
        deck_layout.addWidget(self.deck_list, 1)
        self.deck_label = QLabel("")
        self.deck_label.setObjectName("SubtleLabel")
        self.deck_label.setWordWrap(True)
        deck_layout.addWidget(self.deck_label)
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
        self.hint_button = QPushButton("Hint")
        self.hint_button.setToolTip("Show the next move of the solution "
                                    "(the attempt no longer counts as clean)")
        self.hint_button.clicked.connect(self._on_hint)
        buttons.addWidget(self.hint_button)
        self.solution_button = QPushButton("Show solution")
        self.solution_button.clicked.connect(self._on_show_solution)
        buttons.addWidget(self.solution_button)
        side.addLayout(buttons)

        self.next_button = QPushButton("Next puzzle →")
        self.next_button.setObjectName("PrimaryButton")
        self.next_button.clicked.connect(self._on_next)
        side.addWidget(self.next_button)

        self.remove_button = QPushButton("Remove this puzzle")
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
        """Rebuild the deck list (called after new puzzles are mined)."""
        current = self._puzzle.key if self._puzzle else None
        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        puzzles = sorted(self.store.all(),
                         key=lambda p: (p.solved, p.source.get("date", "")),
                         )
        for puzzle in puzzles:
            symbol = MOVE_SYMBOLS.get(puzzle.category, "?")
            label = MOVE_LABELS.get(puzzle.category, puzzle.category)
            mover = puzzle.source.get("mover", "?")
            move_no = puzzle.source.get("move_no", "?")
            date = puzzle.source.get("date", "")
            mark = "✓ " if puzzle.solved else ""
            item = QListWidgetItem(
                f"{mark}{label} {symbol} — {mover} move {move_no} · {date}")
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
            f"{total} puzzle{'s' if total != 1 else ''} · {solved} solved · "
            f"{due} due for review")

    def _set_idle_state(self):
        if self.store.all():
            self.status_label.setText("Pick a puzzle on the left.")
        else:
            self.status_label.setText("No puzzles yet.")
            self.origin_label.setText(
                "Play a game and run “Analyze game” — every mistake with a "
                "clear best answer becomes a puzzle here, so you retrain on "
                "exactly the positions you misplayed.")
        for button in (self.hint_button, self.solution_button,
                       self.remove_button):
            button.setEnabled(False)
        self.next_button.setEnabled(bool(self.store.all()))

    # ---- solving ----

    def _on_item_clicked(self, item: QListWidgetItem):
        puzzle = self.store.get(item.data(Qt.UserRole))
        if puzzle is not None:
            self._start_puzzle(puzzle)

    def _start_puzzle(self, puzzle: Puzzle):
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
        side_name = "White" if solver == chess.WHITE else "Black"
        symbol = MOVE_SYMBOLS.get(puzzle.category, "?")
        label = MOVE_LABELS.get(puzzle.category, puzzle.category)
        self.status_label.setText(f"{side_name} to move — find the best move.")
        source = puzzle.source
        self.origin_label.setText(
            f"{label} {symbol} from your game {source.get('white', '?')} vs "
            f"{source.get('black', '?')} ({source.get('date', '?')}), move "
            f"{source.get('move_no', '?')} — you played {puzzle.played_san}.")
        self.solution_label.setVisible(False)
        for button in (self.hint_button, self.solution_button,
                       self.remove_button):
            button.setEnabled(True)
        self.next_button.setEnabled(True)

    def _on_board_move(self, move: chess.Move):
        puzzle = self._puzzle
        if puzzle is None or self._finished or \
                self._step >= len(puzzle.solution):
            return
        if move.uci() == puzzle.solution[self._step]:
            self._accept_move(move)
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
        self.status_label.setText("✓ Correct — the reply is coming…")
        generation = self._generation
        QTimer.singleShot(REPLY_DELAY_MS, lambda: self._play_reply(generation))

    def _play_reply(self, generation: int):
        if generation != self._generation or self._puzzle is None:
            return
        move = chess.Move.from_uci(self._puzzle.solution[self._step])
        self._board.push(move)
        self._step += 1
        self.board_widget.set_position(self._board, move, animate=True)
        self.status_label.setText("Your move — continue the line.")

    def _reject_move(self, move: chess.Move):
        self._wrong += 1
        san = self._board.san(move)
        # Show the wrong move briefly, then rewind it.
        self._board.push(move)
        self.board_widget.set_position(self._board, move, animate=False)
        self.status_label.setText(f"✗ {san} isn’t it — try again.")
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
        clean = solved and self._wrong == 0 and not self._used_hint
        self.store.record_attempt(puzzle.key, solved, clean)
        if solved:
            self.status_label.setText(
                "★ Solved — first try!" if clean else
                f"★ Solved (after {self._wrong} wrong "
                f"tr{'ies' if self._wrong != 1 else 'y'}"
                f"{' and a hint' if self._used_hint else ''}).")
        line = " ".join(puzzle.solution_san)
        self.solution_label.setText(f"Solution: {line}")
        self.solution_label.setVisible(True)
        self.hint_button.setEnabled(False)
        self.solution_button.setEnabled(False)
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
        self.status_label.setText("Solution revealed — counted as a fail; "
                                  "it will come back tomorrow.")
        self._wrong += 1
        self._finish(solved=False)

    def _on_next(self):
        """Jump to the first unsolved puzzle (other than the current one)."""
        current = self._puzzle.key if self._puzzle else None
        candidates = [p for p in self.store.due_puzzles()
                      if p.key != current] or \
                     [p for p in self.store.all()
                      if not p.solved and p.key != current]
        if candidates:
            self._start_puzzle(candidates[0])
            self.refresh()
        else:
            self.status_label.setText(
                "Deck clear — nothing due. Analyze more games to add puzzles.")

    def _on_remove(self):
        if self._puzzle is None:
            return
        self.store.remove(self._puzzle.key)
        self._puzzle = None
        self._generation += 1
        self.board_widget.set_movable_colors([])
        self.refresh()
        self._set_idle_state()
