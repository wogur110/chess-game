"""Opening study tab: browse named openings, demo them, drill them,
and explore variations with masters win-rate statistics."""

from __future__ import annotations

import random
from enum import Enum
from typing import Optional

import chess
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSplitter, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from . import theme
from .board_widget import BoardWidget
from .i18n import tr
from .opening_book import BookMove, OpeningBook, OpeningLine, load_book

DRAW_COLOR = "#8b95a5"


class _Hint:
    """Light stand-in for the Suggestion objects BoardWidget paints."""

    def __init__(self, move: chess.Move, rec_prob: float):
        self.move = move
        self.rec_prob = rec_prob


class Mode(Enum):
    EXPLORE = "explore"
    DEMO = "demo"
    DRILL = "drill"


# ---- Win/draw/loss bar ---------------------------------------------------------

class TriBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self._values: Optional[tuple[int, int, int]] = None

    def set_values(self, white: int, draws: int, black: int):
        total = white + draws + black
        self._values = (white, draws, black) if total > 0 else None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)
        if self._values is None:
            painter.fillRect(rect, QColor(theme.BG_PANEL_LIGHT))
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(rect, Qt.AlignCenter, tr("no data"))
            painter.end()
            return
        white, draws, black = self._values
        total = white + draws + black
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        x = rect.x()
        for share, color, text_color in (
            (white / total, theme.EVALBAR_WHITE, "#10151a"),
            (draws / total, DRAW_COLOR, "#10151a"),
            (black / total, theme.EVALBAR_BLACK, "#c8cdd5"),
        ):
            width = rect.width() * share
            seg = QRectF(x, rect.y(), width, rect.height())
            painter.fillRect(seg, QColor(color))
            if width > 34:
                painter.setPen(QColor(text_color))
                painter.drawText(seg, Qt.AlignCenter, f"{share * 100:.0f}%")
            x += width
        painter.end()


# ---- Book moves list -------------------------------------------------------------

class BookMovesPanel(QWidget):
    moveClicked = Signal(str)   # uci

    ROW_H = 30

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._moves: list[BookMove] = []
        self._hover = -1
        self.setMinimumHeight(self.ROW_H)

    def set_moves(self, moves: list[BookMove]):
        self._moves = moves
        self._hover = -1
        self.setFixedHeight(max(self.ROW_H, len(moves) * self.ROW_H))
        self.update()

    def _row_at(self, y: float) -> int:
        row = int(y // self.ROW_H)
        return row if 0 <= row < len(self._moves) else -1

    def mouseMoveEvent(self, event):
        row = self._row_at(event.position().y())
        if row != self._hover:
            self._hover = row
            self.setCursor(Qt.PointingHandCursor if row >= 0 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()

    def mousePressEvent(self, event):
        row = self._row_at(event.position().y())
        if row >= 0:
            self.moveClicked.emit(self._moves[row].uci)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        if not self._moves:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             tr("Out of book — no known moves"))
            painter.end()
            return
        font = QFont(self.font())
        for i, move in enumerate(self._moves):
            top = i * self.ROW_H
            row_rect = QRectF(0, top + 1, width, self.ROW_H - 2)
            if i == self._hover:
                path = QPainterPath()
                path.addRoundedRect(row_rect, 5, 5)
                painter.fillPath(path, QColor(theme.BG_PANEL_HOVER))

            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(QRectF(8, top, 64, self.ROW_H),
                             Qt.AlignLeft | Qt.AlignVCenter, move.san)

            font.setPixelSize(11)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(theme.TEXT_MUTED))
            games = f"{move.total:,}" if move.has_stats else "—"
            painter.drawText(QRectF(70, top, 58, self.ROW_H),
                             Qt.AlignRight | Qt.AlignVCenter, games)

            bar = QRectF(138, top + (self.ROW_H - 14) / 2, max(40.0, width - 148), 14)
            path = QPainterPath()
            path.addRoundedRect(bar, 4, 4)
            painter.setClipPath(path)
            if move.has_stats:
                x = bar.x()
                font.setPixelSize(9)
                font.setBold(True)
                painter.setFont(font)
                for count, color, text_color in (
                    (move.white, theme.EVALBAR_WHITE, "#10151a"),
                    (move.draws, DRAW_COLOR, "#10151a"),
                    (move.black, theme.EVALBAR_BLACK, "#c8cdd5"),
                ):
                    share = count / move.total
                    seg = QRectF(x, bar.y(), bar.width() * share, bar.height())
                    painter.fillRect(seg, QColor(color))
                    if seg.width() > 26:
                        painter.setPen(QColor(text_color))
                        painter.drawText(seg, Qt.AlignCenter, f"{share * 100:.0f}")
                    x += seg.width()
            else:
                painter.fillRect(bar, QColor(theme.BG_PANEL_LIGHT))
                painter.setPen(QColor(theme.TEXT_DIM))
                painter.drawText(bar, Qt.AlignCenter, tr("book line"))
            painter.setClipping(False)
        painter.end()


# ---- Opening browser (left column) ------------------------------------------------

class OpeningBrowser(QWidget):
    lineSelected = Signal(object)   # OpeningLine

    def __init__(self, book: Optional[OpeningBook], parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search openings…  (e.g. Sicilian)"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.tree, 1)

        if book is not None:
            for family, lines in book.families.items():
                family_item = QTreeWidgetItem([f"{family}  ({len(lines)})"])
                family_item.setFlags(Qt.ItemIsEnabled)
                for line in lines:
                    child = QTreeWidgetItem([f"{line.eco}  {line.variation}"])
                    child.setData(0, Qt.UserRole, line)
                    child.setToolTip(0, line.name)
                    family_item.addChild(child)
                self.tree.addTopLevelItem(family_item)

        self.search.textChanged.connect(self._filter)
        self.tree.itemClicked.connect(self._on_item)

    def _on_item(self, item: QTreeWidgetItem, column: int):
        line = item.data(0, Qt.UserRole)
        if line is not None:
            self.lineSelected.emit(line)

    def _filter(self, text: str):
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            family_item = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(family_item.childCount()):
                child = family_item.child(j)
                line: OpeningLine = child.data(0, Qt.UserRole)
                visible = needle in line.name.lower() or needle in line.eco.lower()
                child.setHidden(bool(needle) and not visible)
                any_visible = any_visible or visible
            family_match = needle in family_item.text(0).lower()
            family_item.setHidden(bool(needle) and not (any_visible or family_match))
            family_item.setExpanded(bool(needle) and any_visible)


# ---- The study tab ------------------------------------------------------------------

class OpeningStudyTab(QWidget):
    continueRequested = Signal(list, bool)   # list[chess.Move], human color

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.book = load_book()

        self._board = chess.Board()
        self._history: list[chess.Move] = []
        self._epds: list[str] = [self._board.epd()]
        self._mode = Mode.EXPLORE
        self._line: Optional[OpeningLine] = None
        self._line_index = 0
        self._drill_side: chess.Color = chess.WHITE
        self._drill_line: Optional[OpeningLine] = None
        self._drill_mistakes = 0
        self._generation = 0
        self._show_arrows = True

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        root.addWidget(splitter)

        # Left: browser
        browser_panel = QWidget()
        browser_panel.setMinimumWidth(190)
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(8)
        title = QLabel(tr("OPENINGS"))
        title.setObjectName("SectionTitle")
        browser_layout.addWidget(title)
        self.browser = OpeningBrowser(self.book)
        browser_layout.addWidget(self.browser, 1)
        splitter.addWidget(browser_panel)

        # Center: board
        self.board_widget = BoardWidget()
        self.board_widget.set_movable_colors([chess.WHITE, chess.BLACK])
        splitter.addWidget(self.board_widget)

        # Right: explorer panel (scrollable so the window can shrink vertically)
        panel = QFrame()
        panel.setObjectName("SidePanel")
        # Wide enough for the panel content's own minimum (~316px) plus the
        # scrollbar, so nothing gets clipped horizontally.
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(440)
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

        self.name_label = QLabel(tr("Starting position"))
        self.name_label.setObjectName("StatusLabel")
        self.name_label.setWordWrap(True)
        side.addWidget(self.name_label)

        self.line_label = QLabel("")
        self.line_label.setObjectName("SubtleLabel")
        self.line_label.setWordWrap(True)
        side.addWidget(self.line_label)

        stats_title = QLabel(tr("MASTERS RESULTS  ·  W / D / B"))
        stats_title.setObjectName("SectionTitle")
        stats_title.setToolTip(tr("White wins / draws / Black wins"))
        side.addWidget(stats_title)
        self.tri_bar = TriBar()
        side.addWidget(self.tri_bar)
        self.games_label = QLabel("")
        self.games_label.setObjectName("SubtleLabel")
        side.addWidget(self.games_label)

        moves_title = QLabel(tr("BOOK MOVES"))
        moves_title.setObjectName("SectionTitle")
        side.addWidget(moves_title)
        self.moves_panel = BookMovesPanel()
        self.moves_panel.setStyleSheet("background: transparent;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self.moves_panel)
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        side.addWidget(scroll, 1)

        # Demo navigation
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)
        self.nav_buttons = {}
        for key, text, tip in (("start", "⏮", tr("Line start")),
                               ("back", "◀", tr("Back (←)")),
                               ("fwd", "▶", tr("Next line move (→)")),
                               ("end", "⏭", tr("Line end"))):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setFixedWidth(44)
            button.clicked.connect(lambda _=False, k=key: self._nav(k))
            self.nav_buttons[key] = button
            nav_row.addWidget(button)
        nav_row.addStretch(1)
        self.back_button = QToolButton()
        self.back_button.setText(tr("↩ Back"))
        self.back_button.setToolTip(tr("Take back the last move"))
        self.back_button.clicked.connect(self.step_back)
        nav_row.addWidget(self.back_button)
        side.addLayout(nav_row)

        # Drill controls
        drill_row = QHBoxLayout()
        drill_row.setSpacing(8)
        drill_label = QLabel(tr("Drill as"))
        drill_row.addWidget(drill_label)
        self.side_combo = QComboBox()
        self.side_combo.addItems([tr("White"), tr("Black")])
        drill_row.addWidget(self.side_combo)
        self.drill_button = QPushButton(tr("Start drill"))
        self.drill_button.setObjectName("PrimaryButton")
        self.drill_button.clicked.connect(self._toggle_drill)
        drill_row.addWidget(self.drill_button, 1)
        side.addLayout(drill_row)

        self.feedback_label = QLabel(
            tr("Pick an opening on the left, or just move pieces."))
        self.feedback_label.setObjectName("SubtleLabel")
        self.feedback_label.setWordWrap(True)
        side.addWidget(self.feedback_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        self.reset_button = QPushButton(tr("Reset board"))
        self.reset_button.clicked.connect(self.reset_board)
        bottom_row.addWidget(self.reset_button)
        self.continue_button = QPushButton(tr("Continue vs AI →"))
        self.continue_button.setToolTip(tr(
            "Take this position into the Play tab and finish the game "
            "against Stockfish"))
        self.continue_button.clicked.connect(self._continue_vs_ai)
        bottom_row.addWidget(self.continue_button)
        side.addLayout(bottom_row)

        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 520, 360])

        self.board_widget.moveRequested.connect(self._on_board_move)
        self.board_widget.backRequested.connect(self.step_back)
        self.moves_panel.moveClicked.connect(self._on_book_move_clicked)
        self.browser.lineSelected.connect(self._on_line_selected)

        if self.book is None:
            self.name_label.setText(tr("Opening data not found"))
            self.feedback_label.setText(tr(
                "app/data/openings.json.gz is missing — run tools/build_opening_data.py."))
        self._refresh(animate=False)

    # ---- helpers ----

    def _bump(self):
        self._generation += 1

    def _push(self, move: chess.Move, animate: bool = True):
        self._board.push(move)
        self._history.append(move)
        self._epds.append(self._board.epd())
        self._refresh(last_move=move, animate=animate)

    def _pop(self) -> Optional[chess.Move]:
        if not self._history:
            return None
        move = self._history.pop()
        self._board.pop()
        self._epds.pop()
        return move

    def current_moves(self) -> list[chess.Move]:
        return list(self._history)

    # ---- refresh / explorer panel ----

    def _refresh(self, last_move: Optional[chess.Move] = None, animate: bool = False):
        self.board_widget.set_position(self._board, last_move, animate)
        info = self.book.position_info(self._board) if self.book else None

        named = self.book.name_for_history(self._epds) if self.book else None
        if named:
            eco, name = named
            in_book = self.book.name_for_epd(self._epds[-1]) is not None or \
                (info is not None and info.moves)
            suffix = "" if in_book else tr("  ·  out of book")
            self.name_label.setText(f"{eco} — {name}{suffix}")
        else:
            self.name_label.setText(tr("Starting position") if not self._history
                                    else tr("Unnamed position"))

        self.line_label.setText(self._san_breadcrumb())

        if info is not None and info.total > 0:
            self.tri_bar.set_values(info.white, info.draws, info.black)
            self.games_label.setText(tr("{total} master games from this position",
                                        total=f"{info.total:,}"))
        else:
            self.tri_bar.set_values(0, 0, 0)
            self.games_label.setText(tr("No master-game statistics here"))

        moves = info.moves if info is not None else []
        self.moves_panel.set_moves(moves)
        self._update_arrows(moves)
        self._update_nav_state()
        self.back_button.setEnabled(bool(self._history))
        self.continue_button.setEnabled(not self._board.is_game_over())

    def _san_breadcrumb(self) -> str:
        if not self._history:
            return "—"
        board = chess.Board()
        parts = []
        for i, move in enumerate(self._history):
            if i % 2 == 0:
                parts.append(f"{i // 2 + 1}.")
            parts.append(board.san(move))
            board.push(move)
        return " ".join(parts)

    def _update_arrows(self, moves: list[BookMove]):
        if not self._show_arrows or self._mode == Mode.DRILL:
            self.board_widget.set_suggestions([])
            return
        top = [m for m in moves if m.has_stats][:3] or moves[:3]
        total = sum(m.total for m in top)
        hints = []
        for m in top:
            share = (m.total / total) if total else 1.0 / max(1, len(top))
            try:
                hints.append(_Hint(chess.Move.from_uci(m.uci), share))
            except Exception:
                continue
        self.board_widget.set_suggestions(hints)

    def set_show_arrows(self, show: bool):
        self._show_arrows = show
        self._refresh()

    # ---- browser / demo ----

    def _on_line_selected(self, line: OpeningLine):
        self._bump()
        self._stop_drill(silent=True)
        self._mode = Mode.DEMO
        self._line = line
        self._line_index = 0
        self._board = chess.Board()
        self._history = []
        self._epds = [self._board.epd()]
        self.feedback_label.setText(
            tr("Demo: {name} — step through with ▶, or start a drill.",
               name=line.name))
        self._refresh(animate=False)

    def _nav(self, key: str):
        if self._line is None or self._mode == Mode.DRILL:
            return
        targets = {"start": 0, "back": self._line_index - 1,
                   "fwd": self._line_index + 1, "end": len(self._line.ucis)}
        target = max(0, min(len(self._line.ucis), targets[key]))
        if target == self._line_index and self._line_matches():
            return
        self._bump()
        self._mode = Mode.DEMO
        board = chess.Board()
        history = []
        for uci in self._line.ucis[:target]:
            move = chess.Move.from_uci(uci)
            history.append(move)
            board.push(move)
        self._board = board
        self._history = history
        self._epds = [chess.Board().epd()]
        replay = chess.Board()
        for move in history:
            replay.push(move)
            self._epds.append(replay.epd())
        self._line_index = target
        last = history[-1] if history else None
        self._refresh(last_move=last, animate=True)

    def _line_matches(self) -> bool:
        if self._line is None:
            return False
        prefix = [chess.Move.from_uci(u) for u in self._line.ucis[:self._line_index]]
        return prefix == self._history

    def _update_nav_state(self):
        demo_ok = self._line is not None and self._mode != Mode.DRILL
        on_line = demo_ok and self._line_matches()
        self.nav_buttons["start"].setEnabled(demo_ok)
        self.nav_buttons["end"].setEnabled(demo_ok)
        self.nav_buttons["back"].setEnabled(demo_ok and on_line and self._line_index > 0)
        self.nav_buttons["fwd"].setEnabled(
            demo_ok and on_line and self._line is not None
            and self._line_index < len(self._line.ucis))

    # ---- moves from the board / book list ----

    def _on_board_move(self, move: chess.Move):
        if self._mode == Mode.DRILL:
            self._handle_drill_move(move)
            return
        # Free exploration; deviating from a demo line just leaves the line.
        if self._mode == Mode.DEMO and self._line_matches() and \
                self._line_index < len(self._line.ucis) and \
                move.uci() == self._line.ucis[self._line_index]:
            self._line_index += 1
        else:
            self._mode = Mode.EXPLORE
        self._push(move, animate=False)

    def _on_book_move_clicked(self, uci: str):
        if self._mode == Mode.DRILL:
            return   # no shortcuts while drilling
        move = chess.Move.from_uci(uci)
        if move in self._board.legal_moves:
            self._on_board_move(move)

    # ---- drill ----

    def _toggle_drill(self):
        if self._mode == Mode.DRILL:
            self._stop_drill()
        else:
            self._start_drill()

    def _start_drill(self):
        if self.book is None:
            return
        self._bump()
        self._mode = Mode.DRILL
        self._drill_line = self._line          # None -> free book drill
        self._drill_side = chess.WHITE if self.side_combo.currentIndex() == 0 else chess.BLACK
        self._drill_mistakes = 0
        self._board = chess.Board()
        self._history = []
        self._epds = [self._board.epd()]
        self.drill_button.setText(tr("Stop drill"))
        side_name = tr("White") if self._drill_side == chess.WHITE else tr("Black")
        self.board_widget.set_orientation(self._drill_side)
        self.board_widget.set_movable_colors([self._drill_side])
        if self._drill_line is not None:
            self.feedback_label.setText(
                tr("Drill: {name} — you play {side}, exactly along the line.",
                   name=self._drill_line.name, side=side_name))
        else:
            self.feedback_label.setText(
                tr("Drill: you play {side}. Any book move counts; the opponent "
                   "follows master-game popularity.", side=side_name))
        self._refresh(animate=False)
        if self._board.turn != self._drill_side:
            self._schedule_reply()

    def _stop_drill(self, silent: bool = False):
        if self._mode != Mode.DRILL:
            return
        self._bump()
        self._mode = Mode.EXPLORE
        self._drill_line = None
        self.drill_button.setText(tr("Start drill"))
        self.board_widget.set_movable_colors([chess.WHITE, chess.BLACK])
        if not silent:
            self.feedback_label.setText(tr("Drill stopped — free exploration."))
            self._refresh()

    def _expected_line_move(self) -> Optional[str]:
        """Next move of the drilled line, or None if the line is exhausted."""
        if self._drill_line is None:
            return None
        index = len(self._history)
        if index < len(self._drill_line.ucis):
            return self._drill_line.ucis[index]
        return None

    def _handle_drill_move(self, move: chess.Move):
        if self._drill_line is not None:
            expected = self._expected_line_move()
            if expected is None:
                self._finish_drill()
                return
            if move.uci() == expected:
                self._drill_clear_hints()
                self._push(move, animate=False)
                if self._expected_line_move() is not None:
                    self._schedule_reply()
                else:
                    self._finish_drill()
            else:
                self._drill_mistakes += 1
                share = self._masters_share(expected)
                self.board_widget.set_suggestions(
                    [_Hint(chess.Move.from_uci(expected), share)])
                self.feedback_label.setText(
                    tr("✗ {san} is not the line move — the arrow shows it "
                       "(misses: {misses}).",
                       san=self._board.san(move), misses=self._drill_mistakes))
            return

        replies = self.book.book_replies(self._board) if self.book else []
        book_ucis = {m.uci for m in replies}
        if not book_ucis:
            self._finish_drill()
            return
        if move.uci() in book_ucis:
            self._drill_clear_hints()
            self._push(move, animate=False)
            if self.book.book_replies(self._board):
                self._schedule_reply()
            else:
                self._finish_drill()
        else:
            self._drill_mistakes += 1
            total = sum(m.total for m in replies)
            hints = []
            for m in replies[:3]:
                share = (m.total / total) if total else 1.0 / len(replies[:3])
                hints.append(_Hint(chess.Move.from_uci(m.uci), share))
            self.board_widget.set_suggestions(hints)
            self.feedback_label.setText(
                tr("✗ {san} is not a book move here — try one of the arrows "
                   "(misses: {misses}).",
                   san=self._board.san(move), misses=self._drill_mistakes))

    def _masters_share(self, uci: str) -> float:
        """How often masters chose `uci` here (for the hint badge)."""
        info = self.book.position_info(self._board) if self.book else None
        if info is None or info.total == 0:
            return 1.0
        for m in info.moves:
            if m.uci == uci and m.has_stats:
                return m.total / info.total
        return 1.0

    def _drill_clear_hints(self):
        self.board_widget.set_suggestions([])
        if self._drill_mistakes == 0:
            self.feedback_label.setText(tr("✓ Book move!"))
        else:
            self.feedback_label.setText(tr("✓ Book move!  (misses so far: {misses})",
                                           misses=self._drill_mistakes))

    def _schedule_reply(self):
        generation = self._generation
        QTimer.singleShot(450, lambda: self._play_reply(generation))

    def _play_reply(self, generation: int):
        if generation != self._generation or self._mode != Mode.DRILL:
            return
        if self._board.turn == self._drill_side:
            return
        if self._drill_line is not None:
            expected = self._expected_line_move()
            if expected is None:
                self._finish_drill()
                return
            self._push(chess.Move.from_uci(expected), animate=True)
            if self._expected_line_move() is None:
                self._finish_drill()
            return
        replies = self.book.book_replies(self._board) if self.book else []
        if not replies:
            self._finish_drill()
            return
        weights = [max(1, m.total) for m in replies]
        choice = random.choices(replies, weights=weights, k=1)[0]
        self._push(chess.Move.from_uci(choice.uci), animate=True)
        if not (self.book and self.book.book_replies(self._board)):
            self._finish_drill()

    def _finish_drill(self):
        ply = len(self._history)
        misses = self._drill_mistakes
        line = self._drill_line
        self._stop_drill(silent=True)
        if line is not None:
            name = line.name
        else:
            named = self.book.name_for_history(self._epds) if self.book else None
            name = f"{named[0]} {named[1]}" if named else tr("Unnamed position")
        self.feedback_label.setText(
            tr("★ Line complete after {ply} plies — {name}, misses: {misses}. "
               "Continue against the AI to finish the game!",
               ply=ply, name=name, misses=misses))
        self._refresh()

    # ---- shared actions ----

    def reset_board(self):
        self._bump()
        self._stop_drill(silent=True)
        self._mode = Mode.EXPLORE
        self._line = None
        self._line_index = 0
        self._board = chess.Board()
        self._history = []
        self._epds = [self._board.epd()]
        self.board_widget.set_movable_colors([chess.WHITE, chess.BLACK])
        self.feedback_label.setText(
            tr("Board reset — pick an opening or explore freely."))
        self._refresh(animate=False)

    def _continue_vs_ai(self):
        if self._mode == Mode.DRILL:
            human = self._drill_side
        else:
            human = self._board.turn
        moves = self.current_moves()
        self._stop_drill(silent=True)
        self.continueRequested.emit(moves, bool(human))

    # ---- keyboard hooks (wired from the main window) ----

    def step_back(self):
        self._bump()
        if self._mode == Mode.DRILL:
            # Take back the opponent reply plus our move.
            popped = self._pop()
            if popped is not None and self._board.turn != self._drill_side:
                self._pop()
            self.board_widget.set_suggestions([])
            self._refresh(animate=True)
            return
        if self._mode == Mode.DEMO and self._line_matches() and self._line_index > 0:
            self._nav("back")
            return
        if self._pop() is not None:
            self._mode = Mode.EXPLORE if self._line is None else self._mode
            last = self._history[-1] if self._history else None
            self._refresh(last_move=last, animate=True)

    def step_forward(self):
        if self._mode != Mode.DRILL:
            self._nav("fwd")
