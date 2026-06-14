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
from .eval_utils import MOVE_LABELS, MOVE_SYMBOLS
from .game_controller import PlayerKind

# Colours per move-quality category (move list + eval-graph dots).
CATEGORY_COLORS = {
    "brilliant": "#27c2a0",
    "great": "#5b9bd5",
    "best": "#81b64c",
    "book": "#a98a64",
    "good": theme.TEXT,
    "inaccuracy": "#e8c468",
    "miss": "#f0a35e",
    "mistake": "#e8943b",
    "blunder": "#e06c75",
}


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


# ---- Eval graph (game review) -------------------------------------------------

class EvalGraph(QWidget):
    """White-POV win-expectation across the game; click to jump to a move."""

    plyClicked = Signal(int)   # position index

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Win probability over the game — click to jump to a move")
        self._series: list = []      # white expectation 0..1 or None per position
        self._view = 0
        self._markers: list = []     # (position_index, category)

    def set_series(self, series: list, view_index: int, markers: list = None):
        self._series = list(series)
        self._view = view_index
        self._markers = list(markers or [])
        self.update()

    def _x_for(self, index: int, rect: QRectF) -> float:
        n = max(1, len(self._series) - 1)
        return rect.x() + rect.width() * (index / n)

    def mousePressEvent(self, event):
        if not self._series:
            return
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        n = max(1, len(self._series) - 1)
        frac = (event.position().x() - rect.x()) / max(1.0, rect.width())
        index = round(frac * n)
        self.plyClicked.emit(max(0, min(len(self._series) - 1, index)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor(theme.EVALBAR_BLACK))

        known = [i for i, v in enumerate(self._series) if v is not None]
        if len(known) < 2:
            painter.setClipping(False)
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(rect, Qt.AlignCenter, "Play or analyze a game")
            painter.end()
            return

        def y_for(exp: float) -> float:
            return rect.y() + rect.height() * (1.0 - max(0.0, min(1.0, exp)))

        # Only draw across the analyzed span [first known, last known]. Interior
        # gaps carry the previous value; the unanalyzed tail stays blank so it is
        # not mistaken for a confident flat evaluation.
        first, last_idx = known[0], known[-1]
        last = self._series[first]
        pts = []
        for i in range(first, last_idx + 1):
            exp = self._series[i]
            if exp is not None:
                last = exp
            pts.append((self._x_for(i, rect), y_for(last)))

        area = QPainterPath()
        area.moveTo(pts[0][0], rect.bottom())
        for x, y in pts:
            area.lineTo(x, y)
        area.lineTo(pts[-1][0], rect.bottom())
        area.closeSubpath()
        painter.fillPath(area, QColor(theme.EVALBAR_WHITE))

        # Midline
        mid_y = rect.y() + rect.height() / 2
        painter.setPen(QPen(QColor(theme.ACCENT), 1, Qt.DashLine))
        painter.drawLine(int(rect.x()), int(mid_y), int(rect.right()), int(mid_y))

        # Curve
        line = QPainterPath()
        line.moveTo(*pts[0])
        for x, y in pts[1:]:
            line.lineTo(x, y)
        painter.setPen(QPen(QColor("#10151a"), 1.4))
        painter.drawPath(line)

        # Key-moment dots (brilliancies, mistakes, blunders…)
        for index, klass in self._markers:
            if not (first <= index <= last_idx):
                continue
            exp = self._series[index]
            if exp is None:
                continue
            cx, cy = self._x_for(index, rect), y_for(exp)
            painter.setPen(QPen(QColor("#10151a"), 1))
            painter.setBrush(QColor(CATEGORY_COLORS.get(klass, theme.TEXT_MUTED)))
            painter.drawEllipse(QRectF(cx - 3.5, cy - 3.5, 7, 7))

        # View marker
        painter.setClipping(False)
        mx = self._x_for(self._view, rect)
        painter.setPen(QPen(QColor(theme.ACCENT), 2))
        painter.drawLine(int(mx), int(rect.y()), int(mx), int(rect.bottom()))
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
        self._san_list: list = []

    def rebuild(self, san_history: list, base_fullmove: int, base_turn: chess.Color):
        self.blockSignals(True)
        self.clearContents()
        self._san_list = list(san_history)
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

    def set_annotations(self, annotations: list):
        """Colour each move and append its quality symbol (!!, !, ?!, ?, ??…)."""
        for i, san in enumerate(self._san_list):
            slot = i + self._offset
            row, col = slot // 2, 1 + slot % 2
            item = self.item(row, col)
            if item is None:
                continue
            klass = annotations[i] if i < len(annotations) else None
            symbol = MOVE_SYMBOLS.get(klass, "")
            item.setText(f"{san}{symbol}")
            item.setForeground(QColor(CATEGORY_COLORS.get(klass, theme.TEXT)))

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
    difficultyChanged = Signal(bool, int)       # color, level
    newGameClicked = Signal()
    undoClicked = Signal()
    saveClicked = Signal()
    loadClicked = Signal()
    navigateClicked = Signal(str)               # "start" | "back" | "fwd" | "end"
    autoplayToggled = Signal(bool)
    hintsToggled = Signal(bool)
    flipClicked = Signal()
    suggestionClicked = Signal(object)
    analyzeClicked = Signal()
    evalGraphClicked = Signal(int)              # position index

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(290)
        self.setMaximumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Status
        self.status_label = QLabel("White to move")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.opening_label = QLabel("")
        self.opening_label.setObjectName("SubtleLabel")
        self.opening_label.setWordWrap(True)
        self.opening_label.setVisible(False)
        layout.addWidget(self.opening_label)

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

        # Game review
        layout.addWidget(_section_label("Game review"))
        self.eval_graph = EvalGraph()
        self.eval_graph.plyClicked.connect(self.evalGraphClicked)
        layout.addWidget(self.eval_graph)
        self.move_detail_label = QLabel("")
        self.move_detail_label.setWordWrap(True)
        self.move_detail_label.setVisible(False)
        layout.addWidget(self.move_detail_label)
        self.accuracy_label = QLabel("Accuracy: —")
        self.accuracy_label.setObjectName("SubtleLabel")
        self.accuracy_label.setWordWrap(True)
        layout.addWidget(self.accuracy_label)
        self.analyze_button = QPushButton("Analyze game")
        self.analyze_button.setToolTip(
            "Evaluate every move so accuracy and ?!/?/?? annotations are complete")
        self.analyze_button.clicked.connect(self.analyzeClicked)
        layout.addWidget(self.analyze_button)

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

        # Difficulty — one row per AI side (shown only for sides played by AI).
        layout.addWidget(_section_label("AI difficulty"))
        (self.white_diff_row, self.white_diff_slider,
         self.white_diff_label) = self._make_diff_row(chess.WHITE, "⚪ White AI")
        (self.black_diff_row, self.black_diff_slider,
         self.black_diff_label) = self._make_diff_row(chess.BLACK, "⚫ Black AI")
        layout.addWidget(self.white_diff_row)
        layout.addWidget(self.black_diff_row)
        self.no_ai_label = QLabel("No AI players — set White or Black to AI.")
        self.no_ai_label.setObjectName("SubtleLabel")
        self.no_ai_label.setWordWrap(True)
        self.no_ai_label.setVisible(False)
        layout.addWidget(self.no_ai_label)

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

    def _make_diff_row(self, color: bool, name: str):
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(3)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(1, 10)
        slider.setPageStep(1)
        label = QLabel(name)
        label.setObjectName("SubtleLabel")
        row_layout.addWidget(slider)
        row_layout.addWidget(label)
        slider.valueChanged.connect(
            lambda value, c=color: self._on_difficulty(c, value))
        return row, slider, label

    def _on_difficulty(self, color: bool, value: int):
        self._update_diff_label(color, value)
        self.difficultyChanged.emit(color, value)

    def _update_diff_label(self, color: bool, value: int):
        level = DIFFICULTY_LEVELS[value]
        label = self.white_diff_label if color == chess.WHITE else self.black_diff_label
        name = "⚪ White AI" if color == chess.WHITE else "⚫ Black AI"
        label.setText(f"{name} — Level {value} · {level.label}")

    def _on_autoplay_toggled(self, paused: bool):
        self.autoplay_button.setText("▶ Resume AI" if paused else "⏸ Pause AI")
        self.autoplayToggled.emit(not paused)

    # ---- update slots (called from the main window) ----

    def sync_difficulty(self, white_level: int, black_level: int):
        for slider, level in ((self.white_diff_slider, white_level),
                              (self.black_diff_slider, black_level)):
            slider.blockSignals(True)
            slider.setValue(level)
            slider.blockSignals(False)
        self._update_diff_label(chess.WHITE, white_level)
        self._update_diff_label(chess.BLACK, black_level)

    def sync_players(self, white_kind: PlayerKind, black_kind: PlayerKind):
        for combo, kind in ((self.white_combo, white_kind), (self.black_combo, black_kind)):
            combo.blockSignals(True)
            combo.setCurrentIndex(0 if kind == PlayerKind.HUMAN else 1)
            combo.blockSignals(False)
        white_ai = white_kind == PlayerKind.AI
        black_ai = black_kind == PlayerKind.AI
        self.white_diff_row.setVisible(white_ai)
        self.black_diff_row.setVisible(black_ai)
        self.no_ai_label.setVisible(not white_ai and not black_ai)
        self.autoplay_button.setEnabled(white_ai and black_ai)

    def set_opening(self, name: str):
        self.opening_label.setText(f"📖 {name}" if name else "")
        self.opening_label.setVisible(bool(name))

    def set_review(self, series: list, view_index: int, annotations: list,
                   reviews: dict, markers: list = None, best_alt: str = None):
        self.eval_graph.set_series(series, view_index, markers)
        self.moves_table.set_annotations(annotations)
        self.accuracy_label.setText(self._accuracy_text(reviews))
        self._set_move_detail(view_index, annotations, best_alt)

    def _set_move_detail(self, view_index: int, annotations: list, best_alt: str):
        klass = (annotations[view_index - 1]
                 if 1 <= view_index <= len(annotations) else None)
        if klass is None:
            self.move_detail_label.setVisible(False)
            return
        color = CATEGORY_COLORS.get(klass, theme.TEXT)
        label = MOVE_LABELS.get(klass, "")
        symbol = MOVE_SYMBOLS.get(klass, "")
        text = f"{label} {symbol}".strip()
        if best_alt and klass not in ("brilliant", "great", "best", "book"):
            text += f"  ·  best was {best_alt}"
        self.move_detail_label.setText(text)
        self.move_detail_label.setStyleSheet(
            f"color: {color}; font-weight: 600; background: transparent;")
        self.move_detail_label.setVisible(True)

    @staticmethod
    def _accuracy_text(reviews: dict) -> str:
        order = [("brilliant", "!!"), ("great", "!"), ("miss", "✕"),
                 ("mistake", "?"), ("blunder", "??")]

        def fmt(review) -> str:
            if review.accuracy is None:
                return "—"
            flaws = [f"{review.counts[k]}{sym}" for k, sym in order
                     if review.counts.get(k)]
            tail = f"  ({' '.join(flaws)})" if flaws else ""
            return f"{review.accuracy:.0f}%{tail}"
        white = reviews[chess.WHITE]
        black = reviews[chess.BLACK]
        if white.accuracy is None and black.accuracy is None:
            return "Accuracy: — (analyze the game for a full report)"
        return f"Accuracy:  ⚪ {fmt(white)}   ⚫ {fmt(black)}"

    def set_review_progress(self, done: int, total: int):
        if total > 0 and done < total:
            self.analyze_button.setEnabled(False)
            self.analyze_button.setText(f"Analyzing… {done}/{total}")
        else:
            self.analyze_button.setEnabled(True)
            self.analyze_button.setText("Analyze game")

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
