"""Sidebar widgets: win-probability bars, AI suggestions, move list, controls."""

from __future__ import annotations

from typing import Optional

import chess
from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QSlider,
                               QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme
from .engine_manager import DIFFICULTY_LEVELS
from .game_controller import PlayerKind


# ---- Vertical eval bar (sits next to the board) -------------------------------

class EvalBar(QWidget):
    """Lichess-style vertical bar: the white share grows from White's side."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(26)
        self._value: Optional[float] = 0.5      # white expectation, 0..1
        self._shown = 0.5
        self._text = ""
        self._orientation: chess.Color = chess.WHITE
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def set_value(self, expectation_white: Optional[float], text: str):
        self._text = text
        if expectation_white is None:
            # Keep showing the previous share while analysis is pending,
            # but repaint so the text updates.
            self.update()
            return
        self._value = expectation_white
        self._anim.stop()
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(expectation_white)
        self._anim.start()

    def set_orientation(self, color: chess.Color):
        self._orientation = color
        self.update()

    def _on_anim(self, value):
        self._shown = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)

        white_share = max(0.02, min(0.98, self._shown))
        white_px = rect.height() * white_share
        if self._orientation == chess.WHITE:
            white_rect = QRectF(rect.x(), rect.bottom() - white_px, rect.width(), white_px)
            black_rect = QRectF(rect.x(), rect.y(), rect.width(), rect.height() - white_px)
        else:
            white_rect = QRectF(rect.x(), rect.y(), rect.width(), white_px)
            black_rect = QRectF(rect.x(), rect.y() + white_px, rect.width(),
                                rect.height() - white_px)
        painter.fillRect(black_rect, QColor(theme.EVALBAR_BLACK))
        painter.fillRect(white_rect, QColor(theme.EVALBAR_WHITE))

        # Midline marker
        painter.setPen(QPen(QColor(theme.ACCENT), 1))
        mid_y = rect.y() + rect.height() / 2
        painter.drawLine(int(rect.x()), int(mid_y), int(rect.right()), int(mid_y))

        # Eval text at the edge of the stronger side
        if self._text:
            font = QFont(self.font())
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            if self._shown >= 0.5:
                target, color = white_rect, QColor("#10151a")
                align = Qt.AlignBottom if self._orientation == chess.WHITE else Qt.AlignTop
            else:
                target, color = black_rect, QColor("#c8cdd5")
                align = Qt.AlignTop if self._orientation == chess.WHITE else Qt.AlignBottom
            painter.setPen(color)
            painter.drawText(target.adjusted(0, 3, 0, -3), Qt.AlignHCenter | align,
                             self._text)
        painter.end()


# ---- Horizontal win-probability bar -------------------------------------------

class WinBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self._value: float = 0.5
        self._shown: float = 0.5
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def set_value(self, expectation_white: Optional[float]):
        if expectation_white is None:
            return
        self._value = expectation_white
        self._anim.stop()
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(expectation_white)
        self._anim.start()

    def _on_anim(self, value):
        self._shown = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)
        painter.setClipPath(path)

        share = max(0.04, min(0.96, self._shown))
        split_x = rect.x() + rect.width() * share
        white_rect = QRectF(rect.x(), rect.y(), split_x - rect.x(), rect.height())
        black_rect = QRectF(split_x, rect.y(), rect.right() - split_x, rect.height())
        painter.fillRect(white_rect, QColor(theme.EVALBAR_WHITE))
        painter.fillRect(black_rect, QColor(theme.EVALBAR_BLACK))

        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        white_pct = f"{self._value * 100:.0f}%"
        black_pct = f"{(1 - self._value) * 100:.0f}%"
        painter.setPen(QColor("#10151a"))
        painter.drawText(white_rect.adjusted(8, 0, -4, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, white_pct)
        painter.setPen(QColor("#c8cdd5"))
        painter.drawText(black_rect.adjusted(4, 0, -8, 0),
                         Qt.AlignRight | Qt.AlignVCenter, black_pct)
        painter.end()


# ---- AI suggestions panel -------------------------------------------------------

class SuggestionsPanel(QWidget):
    suggestionClicked = Signal(object)   # chess.Move

    ROW_H = 40

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(self.ROW_H * 3 + 4)
        self.setMouseTracking(True)
        self._suggestions: list = []
        self._hover_row = -1

    def set_suggestions(self, suggestions: list):
        self._suggestions = list(suggestions)[:3]
        tooltip_lines = []
        for i, s in enumerate(self._suggestions):
            pv = " ".join(s.pv_san)
            tooltip_lines.append(f"{i + 1}. {s.san}  ({s.score_text})   {pv}")
        self.setToolTip("\n".join(tooltip_lines))
        self.update()

    def _row_at(self, y: float) -> int:
        row = int(y // self.ROW_H)
        if 0 <= row < len(self._suggestions):
            return row
        return -1

    def mouseMoveEvent(self, event):
        row = self._row_at(event.position().y())
        if row != self._hover_row:
            self._hover_row = row
            self.setCursor(Qt.PointingHandCursor if row >= 0 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover_row = -1
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        row = self._row_at(event.position().y())
        if row >= 0:
            self.suggestionClicked.emit(self._suggestions[row].move)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()

        if not self._suggestions:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignCenter, "Analyzing position…")
            painter.end()
            return

        for i, s in enumerate(self._suggestions):
            top = i * self.ROW_H
            row_rect = QRectF(0, top + 2, width, self.ROW_H - 4)
            if i == self._hover_row:
                path = QPainterPath()
                path.addRoundedRect(row_rect, 6, 6)
                painter.fillPath(path, QColor(theme.BG_PANEL_HOVER))

            color = QColor(theme.ARROW_COLORS[min(i, len(theme.ARROW_COLORS) - 1)])

            # Rank badge
            badge_r = 9.0
            cx, cy = 16.0, top + self.ROW_H / 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2))
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#10151a"))
            painter.drawText(QRectF(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2),
                             Qt.AlignCenter, str(i + 1))

            # SAN
            font.setPixelSize(14)
            painter.setFont(font)
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(QRectF(34, top, 74, self.ROW_H),
                             Qt.AlignLeft | Qt.AlignVCenter, s.san)

            # Recommendation probability bar
            bar_x, bar_right = 110.0, width - 64.0
            bar_w = max(30.0, bar_right - bar_x)
            bar_h = 8.0
            track = QRectF(bar_x, cy - bar_h / 2, bar_w, bar_h)
            path = QPainterPath()
            path.addRoundedRect(track, 4, 4)
            painter.setPen(Qt.NoPen)
            painter.fillPath(path, QColor(theme.BG_PANEL_LIGHT))
            fill = QRectF(track)
            fill.setWidth(max(6.0, track.width() * s.rec_prob))
            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill, 4, 4)
            painter.fillPath(fill_path, color)

            # rec% on the bar, win% at the right edge
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(QRectF(bar_x, top + 1, bar_w, self.ROW_H / 2),
                             Qt.AlignLeft | Qt.AlignBottom,
                             f"{s.rec_prob * 100:.0f}%")
            painter.setPen(QColor(theme.TEXT_MUTED))
            painter.drawText(QRectF(width - 60, top, 56, self.ROW_H),
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"win {s.win_prob_mover * 100:.0f}%")
        painter.end()


# ---- Move list -------------------------------------------------------------------

class MovesTable(QTableWidget):
    plyClicked = Signal(int)   # navigate target = ply index + 1

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 3, parent)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setSelectionBehavior(QTableWidget.SelectItems)
        self.setFocusPolicy(Qt.NoFocus)
        self.setColumnWidth(0, 38)
        self.horizontalHeader().setStretchLastSection(True)
        self.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.cellClicked.connect(self._on_cell_clicked)
        self._offset = 0

    def rebuild(self, san_history: list, base_fullmove: int, base_turn: chess.Color):
        self.blockSignals(True)
        self.clearContents()
        self._offset = 1 if base_turn == chess.BLACK else 0
        total_slots = len(san_history) + self._offset
        rows = (total_slots + 1) // 2
        self.setRowCount(rows)
        for row in range(rows):
            number_item = QTableWidgetItem(f"{base_fullmove + row}.")
            number_item.setForeground(QColor(theme.TEXT_DIM))
            number_item.setFlags(Qt.ItemIsEnabled)
            self.setItem(row, 0, number_item)
            self.setRowHeight(row, 26)
        if self._offset == 1:
            placeholder = QTableWidgetItem("…")
            placeholder.setForeground(QColor(theme.TEXT_DIM))
            placeholder.setFlags(Qt.ItemIsEnabled)
            self.setItem(0, 1, placeholder)
        for i, san in enumerate(san_history):
            slot = i + self._offset
            row, col = slot // 2, 1 + slot % 2
            item = QTableWidgetItem(san)
            item.setData(Qt.UserRole, i)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.setItem(row, col, item)
        self.blockSignals(False)

    def set_current(self, view_index: int):
        self.blockSignals(True)
        if view_index <= 0:
            self.clearSelection()
            self.setCurrentItem(None)
        else:
            slot = (view_index - 1) + self._offset
            row, col = slot // 2, 1 + slot % 2
            item = self.item(row, col)
            if item is not None:
                self.setCurrentItem(item)
                self.scrollToItem(item)
        self.blockSignals(False)

    def _on_cell_clicked(self, row: int, col: int):
        item = self.item(row, col)
        if item is None:
            return
        ply = item.data(Qt.UserRole)
        if ply is not None:
            self.plyClicked.emit(int(ply) + 1)


# ---- Section helpers ---------------------------------------------------------------

def _section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


# ---- The sidebar --------------------------------------------------------------------

class Sidebar(QWidget):
    playerChanged = Signal(bool, object)        # color (chess.WHITE/BLACK), PlayerKind
    difficultyChanged = Signal(int)
    newGameClicked = Signal()
    undoClicked = Signal()
    saveClicked = Signal()
    loadClicked = Signal()
    navigateClicked = Signal(str)               # "start" | "back" | "fwd" | "end"
    autoplayToggled = Signal(bool)
    hintsToggled = Signal(bool)
    flipClicked = Signal()
    suggestionClicked = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Status
        self.status_label = QLabel("White to move")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Win probability
        layout.addWidget(_section_label("Win probability"))
        self.win_bar = WinBar()
        layout.addWidget(self.win_bar)
        eval_row = QHBoxLayout()
        self.eval_label = QLabel("Eval: —")
        self.eval_label.setObjectName("SubtleLabel")
        eval_row.addWidget(self.eval_label)
        eval_row.addStretch(1)
        layout.addLayout(eval_row)

        # Players
        layout.addWidget(_section_label("Players"))
        players_grid = QGridLayout()
        players_grid.setHorizontalSpacing(8)
        players_grid.setVerticalSpacing(6)
        self.white_combo = self._player_combo()
        self.black_combo = self._player_combo()
        self.white_turn_dot = QLabel("●")
        self.black_turn_dot = QLabel("●")
        for dot in (self.white_turn_dot, self.black_turn_dot):
            dot.setStyleSheet(f"color: {theme.ACCENT}; font-size: 10px;")
            dot.setFixedWidth(12)
        white_label = QLabel("⚪ White")
        black_label = QLabel("⚫ Black")
        players_grid.addWidget(self.white_turn_dot, 0, 0)
        players_grid.addWidget(white_label, 0, 1)
        players_grid.addWidget(self.white_combo, 0, 2)
        players_grid.addWidget(self.black_turn_dot, 1, 0)
        players_grid.addWidget(black_label, 1, 1)
        players_grid.addWidget(self.black_combo, 1, 2)
        players_grid.setColumnStretch(2, 1)
        layout.addLayout(players_grid)
        self.white_combo.currentIndexChanged.connect(
            lambda idx: self.playerChanged.emit(chess.WHITE, self._kind_for(idx)))
        self.black_combo.currentIndexChanged.connect(
            lambda idx: self.playerChanged.emit(chess.BLACK, self._kind_for(idx)))

        # Difficulty
        layout.addWidget(_section_label("AI difficulty"))
        self.difficulty_slider = QSlider(Qt.Horizontal)
        self.difficulty_slider.setRange(1, 10)
        self.difficulty_slider.setPageStep(1)
        self.difficulty_label = QLabel("")
        self.difficulty_label.setObjectName("SubtleLabel")
        layout.addWidget(self.difficulty_slider)
        layout.addWidget(self.difficulty_label)
        self.difficulty_slider.valueChanged.connect(self._on_difficulty)

        # Suggestions
        suggestions_header = QHBoxLayout()
        suggestions_header.addWidget(_section_label("AI suggestions"))
        suggestions_header.addStretch(1)
        self.hints_checkbox = QCheckBox("Arrows")
        self.hints_checkbox.setChecked(True)
        self.hints_checkbox.toggled.connect(self.hintsToggled)
        suggestions_header.addWidget(self.hints_checkbox)
        layout.addLayout(suggestions_header)
        self.suggestions_panel = SuggestionsPanel()
        self.suggestions_panel.suggestionClicked.connect(self.suggestionClicked)
        layout.addWidget(self.suggestions_panel)

        # Move list
        layout.addWidget(_section_label("Moves"))
        self.moves_table = MovesTable()
        self.moves_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.moves_table, 1)

        # Navigation
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)
        self.nav_buttons = {}
        for key, text, tip in (("start", "⏮", "Go to start (Home)"),
                               ("back", "◀", "Back (←)"),
                               ("fwd", "▶", "Forward (→)"),
                               ("end", "⏭", "Go to end (End)")):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setFixedWidth(46)
            button.clicked.connect(lambda _=False, k=key: self.navigateClicked.emit(k))
            self.nav_buttons[key] = button
            nav_row.addWidget(button)
        nav_row.addStretch(1)
        self.autoplay_button = QToolButton()
        self.autoplay_button.setText("⏸ Pause AI")
        self.autoplay_button.setCheckable(True)
        self.autoplay_button.setToolTip("Pause / resume AI vs AI play")
        self.autoplay_button.toggled.connect(self._on_autoplay_toggled)
        nav_row.addWidget(self.autoplay_button)
        layout.addLayout(nav_row)

        # Action buttons
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        self.new_button = QPushButton("New game")
        self.undo_button = QPushButton("↩ Undo")
        self.save_button = QPushButton("Save…")
        self.load_button = QPushButton("Load…")
        self.flip_button = QPushButton("Flip board")
        self.new_button.setObjectName("PrimaryButton")
        actions.addWidget(self.new_button, 0, 0)
        actions.addWidget(self.undo_button, 0, 1)
        actions.addWidget(self.save_button, 1, 0)
        actions.addWidget(self.load_button, 1, 1)
        actions.addWidget(self.flip_button, 2, 0, 1, 2)
        layout.addLayout(actions)
        self.new_button.clicked.connect(self.newGameClicked)
        self.undo_button.clicked.connect(self.undoClicked)
        self.save_button.clicked.connect(self.saveClicked)
        self.load_button.clicked.connect(self.loadClicked)
        self.flip_button.clicked.connect(self.flipClicked)

    # ---- helpers ----

    @staticmethod
    def _player_combo() -> QComboBox:
        combo = QComboBox()
        combo.addItem("Human")
        combo.addItem("AI · Stockfish")
        return combo

    @staticmethod
    def _kind_for(index: int) -> PlayerKind:
        return PlayerKind.HUMAN if index == 0 else PlayerKind.AI

    def _on_difficulty(self, value: int):
        self.update_difficulty_label(value)
        self.difficultyChanged.emit(value)

    def _on_autoplay_toggled(self, paused: bool):
        self.autoplay_button.setText("▶ Resume AI" if paused else "⏸ Pause AI")
        self.autoplayToggled.emit(not paused)

    # ---- update slots (called from the main window) ----

    def update_difficulty_label(self, value: int):
        level = DIFFICULTY_LEVELS[value]
        self.difficulty_label.setText(f"Level {value} — {level.label}")

    def sync_players(self, white_kind: PlayerKind, black_kind: PlayerKind):
        for combo, kind in ((self.white_combo, white_kind), (self.black_combo, black_kind)):
            combo.blockSignals(True)
            combo.setCurrentIndex(0 if kind == PlayerKind.HUMAN else 1)
            combo.blockSignals(False)
        both_ai = white_kind == PlayerKind.AI and black_kind == PlayerKind.AI
        self.autoplay_button.setEnabled(both_ai)

    def set_turn(self, turn: Optional[chess.Color]):
        self.white_turn_dot.setVisible(turn == chess.WHITE)
        self.black_turn_dot.setVisible(turn == chess.BLACK)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_eval(self, expectation_white, text: str):
        self.win_bar.set_value(expectation_white)
        self.eval_label.setText(f"Eval: {text}")

    def set_nav_state(self, view_index: int, total: int):
        self.nav_buttons["start"].setEnabled(view_index > 0)
        self.nav_buttons["back"].setEnabled(view_index > 0)
        self.nav_buttons["fwd"].setEnabled(view_index < total)
        self.nav_buttons["end"].setEnabled(view_index < total)
        self.undo_button.setEnabled(total > 0)
