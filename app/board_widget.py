"""Custom-painted chess board: pieces, highlights, drag & drop, hint arrows."""

from __future__ import annotations

import math
from typing import Optional

import chess
import chess.svg
from PySide6.QtCore import (QByteArray, QEasingCurve, QPoint, QPointF, QRect,
                            QRectF, QSize, Qt, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from . import theme
from .i18n import tr
from .sounds import player as sound_player


# ---- Piece sprites -----------------------------------------------------------

class PieceSprites:
    """Renders python-chess's built-in SVG pieces to cached pixmaps."""

    def __init__(self):
        self._renderers: dict[str, QSvgRenderer] = {}
        self._cache: dict[tuple[str, int, int], QPixmap] = {}

    def _renderer(self, symbol: str) -> QSvgRenderer:
        renderer = self._renderers.get(symbol)
        if renderer is None:
            svg = chess.svg.piece(chess.Piece.from_symbol(symbol))
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            self._renderers[symbol] = renderer
        return renderer

    def pixmap(self, piece: chess.Piece, size: int, dpr: float = 1.0) -> QPixmap:
        key = (piece.symbol(), size, int(dpr * 100))
        pix = self._cache.get(key)
        if pix is None:
            px_size = max(1, int(size * dpr))
            pix = QPixmap(px_size, px_size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            self._renderer(piece.symbol()).render(painter, QRectF(0, 0, px_size, px_size))
            painter.end()
            pix.setDevicePixelRatio(dpr)
            self._cache[key] = pix
        return pix


_SPRITES: Optional[PieceSprites] = None


def sprites() -> PieceSprites:
    global _SPRITES
    if _SPRITES is None:
        _SPRITES = PieceSprites()
    return _SPRITES


# ---- Promotion dialog ----------------------------------------------------------

class PromotionDialog(QDialog):
    def __init__(self, color: chess.Color, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Promotion"))
        self.setModal(True)
        self.choice: Optional[chess.PieceType] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        label = QLabel(tr("Promote to:"))
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(8)
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            button = QToolButton(self)
            button.setIconSize(QSize(56, 56))
            button.setFixedSize(QSize(72, 72))
            button.setIcon(sprites().pixmap(chess.Piece(piece_type, color), 56,
                                            self.devicePixelRatioF()))
            button.clicked.connect(lambda _=False, pt=piece_type: self._pick(pt))
            row.addWidget(button)
        layout.addLayout(row)

    def _pick(self, piece_type: chess.PieceType):
        self.choice = piece_type
        self.accept()


# ---- Board widget ----------------------------------------------------------------

class BoardWidget(QWidget):
    moveRequested = Signal(object)   # chess.Move
    backRequested = Signal()         # right-click: step one move back

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setMouseTracking(True)

        self._board = chess.Board()
        self._orientation: chess.Color = chess.WHITE
        self._last_move: Optional[chess.Move] = None
        self._movable: list[chess.Color] = [chess.WHITE]
        self._suggestions: list = []
        self._show_hints = True
        self._coach_arrow: Optional[chess.Move] = None
        self._threat_moves: list = []
        self._show_threats = False

        self._selected: Optional[chess.Square] = None
        self._legal_targets: set[chess.Square] = set()

        self._dragging = False
        self._drag_from: Optional[chess.Square] = None
        self._drag_pos = QPointF()
        self._hover_square: Optional[chess.Square] = None

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(lambda _: self.update())
        self._anim.finished.connect(self._on_anim_done)
        self._anim_move: Optional[chess.Move] = None
        self._anim_piece: Optional[chess.Piece] = None

    # ---- Public API ----

    @staticmethod
    def _sound_for(prev: chess.Board, move: chess.Move) -> str:
        """'capture' or 'move', judged against the pre-move board."""
        moving = prev.piece_at(move.from_square)
        captured = prev.piece_at(move.to_square)
        if moving is not None and captured is not None and \
                captured.color != moving.color:
            return "capture"
        if moving is not None and moving.piece_type == chess.PAWN and \
                captured is None and \
                chess.square_file(move.from_square) != chess.square_file(move.to_square):
            return "capture"   # en passant
        return "move"

    def set_position(self, board: chess.Board, last_move: Optional[chess.Move],
                     animate: bool):
        prev = self._board
        self._board = board.copy(stack=False)
        self._last_move = last_move
        self._coach_arrow = None
        self._threat_moves = []   # stale for the new position; re-sent by analysis
        if last_move is not None and prev.piece_at(last_move.from_square) is not None:
            sound_player().play(self._sound_for(prev, last_move))
        self._clear_selection()
        self._anim.stop()
        self._anim_move = None
        self._anim_piece = None
        if animate and last_move is not None:
            piece = self._board.piece_at(last_move.to_square)
            moved_from_prev = prev.piece_at(last_move.from_square)
            if piece is not None and moved_from_prev is not None:
                self._anim_move = last_move
                self._anim_piece = piece
                self._anim.setStartValue(0.0)
                self._anim.setEndValue(1.0)
                self._anim.start()
        self.update()

    def set_orientation(self, color: chess.Color):
        if self._orientation != color:
            self._orientation = color
            self._clear_selection()
            self.update()

    def orientation(self) -> chess.Color:
        return self._orientation

    def flip(self):
        self.set_orientation(not self._orientation)

    def set_movable_colors(self, colors: list):
        self._movable = list(colors)
        if self._selected is not None:
            piece = self._board.piece_at(self._selected)
            if piece is None or piece.color not in self._movable:
                self._clear_selection()
        self.update()

    def set_suggestions(self, suggestions: list):
        self._suggestions = list(suggestions)[:3]
        self.update()

    def set_show_hints(self, show: bool):
        self._show_hints = show
        self.update()

    def set_coach_arrow(self, move: Optional[chess.Move]):
        """A red arrow showing the refutation of the player's last move."""
        self._coach_arrow = move
        self.update()

    def set_threats(self, moves: list):
        """Opponent threat moves (shown as red arrows while threats are on)."""
        self._threat_moves = list(moves)[:2]
        self.update()

    def set_show_threats(self, show: bool):
        self._show_threats = show
        if not show:
            self._threat_moves = []
        self.update()

    # ---- Geometry ----

    def _square_size(self) -> int:
        return max(1, min(self.width(), self.height()) // 8)

    def _board_origin(self) -> QPoint:
        s = self._square_size()
        return QPoint((self.width() - s * 8) // 2, (self.height() - s * 8) // 2)

    def _square_rect(self, square: chess.Square) -> QRect:
        s = self._square_size()
        origin = self._board_origin()
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)
        if self._orientation == chess.WHITE:
            x = file_idx
            y = 7 - rank_idx
        else:
            x = 7 - file_idx
            y = rank_idx
        return QRect(origin.x() + x * s, origin.y() + y * s, s, s)

    def _square_at(self, pos: QPointF) -> Optional[chess.Square]:
        s = self._square_size()
        origin = self._board_origin()
        x = int((pos.x() - origin.x()) // s)
        y = int((pos.y() - origin.y()) // s)
        if not (0 <= x < 8 and 0 <= y < 8):
            return None
        if self._orientation == chess.WHITE:
            return chess.square(x, 7 - y)
        return chess.square(7 - x, y)

    # ---- Interaction ----

    def _clear_selection(self):
        self._selected = None
        self._legal_targets = set()
        self._dragging = False
        self._drag_from = None
        self._hover_square = None

    def _select(self, square: chess.Square):
        self._selected = square
        self._legal_targets = {
            move.to_square for move in self._board.legal_moves
            if move.from_square == square
        }

    def _can_grab(self, square: chess.Square) -> bool:
        piece = self._board.piece_at(square)
        return (piece is not None and piece.color == self._board.turn
                and piece.color in self._movable)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # With a piece selected or mid-drag, right-click just cancels;
            # otherwise it steps one move back (same as the Left arrow key).
            had_selection = self._selected is not None or self._dragging
            self._clear_selection()
            self.update()
            if not had_selection:
                self.backRequested.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        square = self._square_at(event.position())
        if square is None:
            self._clear_selection()
            self.update()
            return
        if self._selected is not None and square in self._legal_targets:
            self._attempt_move(self._selected, square)
            return
        if self._can_grab(square):
            self._select(square)
            self._dragging = True
            self._drag_from = square
            self._drag_pos = event.position()
        else:
            self._clear_selection()
        self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._drag_pos = event.position()
            self._hover_square = self._square_at(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._hover_square = None
        drop = self._square_at(event.position())
        origin = self._drag_from
        self._drag_from = None
        if drop is None or origin is None or drop == origin:
            # Treat as a click: keep the selection for click-click moving.
            self.update()
            return
        if drop in self._legal_targets:
            self._attempt_move(origin, drop)
        else:
            self._clear_selection()
        self.update()

    def _attempt_move(self, from_sq: chess.Square, to_sq: chess.Square):
        move = chess.Move(from_sq, to_sq)
        piece = self._board.piece_at(from_sq)
        if piece is not None and piece.piece_type == chess.PAWN and \
                chess.square_rank(to_sq) in (0, 7):
            dialog = PromotionDialog(piece.color, self.window())
            if dialog.exec() != QDialog.Accepted or dialog.choice is None:
                self._clear_selection()
                self.update()
                return
            move = chess.Move(from_sq, to_sq, promotion=dialog.choice)
        self._clear_selection()
        if move in self._board.legal_moves:
            self.moveRequested.emit(move)
        self.update()

    def _on_anim_done(self):
        self._anim_move = None
        self._anim_piece = None
        self.update()

    # ---- Painting ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        s = self._square_size()
        origin = self._board_origin()

        light = QColor(theme.SQ_LIGHT)
        dark = QColor(theme.SQ_DARK)

        # Squares
        for square in chess.SQUARES:
            rect = self._square_rect(square)
            is_light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            painter.fillRect(rect, light if is_light else dark)

        # Last move highlight
        if self._last_move is not None:
            color = QColor(theme.SQ_LAST_MOVE)
            color.setAlpha(95)
            painter.fillRect(self._square_rect(self._last_move.from_square), color)
            painter.fillRect(self._square_rect(self._last_move.to_square), color)

        # Check highlight
        if self._board.is_check():
            king_sq = self._board.king(self._board.turn)
            if king_sq is not None:
                rect = QRectF(self._square_rect(king_sq))
                gradient = QRadialGradient(rect.center(), s * 0.62)
                center_color = QColor(theme.SQ_CHECK)
                center_color.setAlpha(190)
                edge_color = QColor(theme.SQ_CHECK)
                edge_color.setAlpha(0)
                gradient.setColorAt(0.0, center_color)
                gradient.setColorAt(1.0, edge_color)
                painter.fillRect(rect, QBrush(gradient))

        # Selected square
        if self._selected is not None:
            color = QColor(theme.SQ_SELECTED)
            color.setAlpha(110)
            painter.fillRect(self._square_rect(self._selected), color)

        # Hover target while dragging
        if self._dragging and self._hover_square is not None \
                and self._hover_square in self._legal_targets:
            pen = QPen(QColor(255, 255, 255, 190), max(2.0, s * 0.045))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(self._square_rect(self._hover_square)).adjusted(2, 2, -2, -2)
            painter.drawRect(rect)

        # Coordinates (inside edge squares, lichess-style)
        self._paint_coordinates(painter, s, origin)

        # Legal move hints
        if self._selected is not None:
            for target in self._legal_targets:
                rect = QRectF(self._square_rect(target))
                center = rect.center()
                painter.setPen(Qt.NoPen)
                if self._board.piece_at(target) is not None or self._board.is_en_passant(
                        chess.Move(self._selected, target)):
                    pen = QPen(QColor(20, 24, 28, 110), max(3.0, s * 0.075))
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    radius = s * 0.44
                    painter.drawEllipse(center, radius, radius)
                else:
                    painter.setBrush(QColor(20, 24, 28, 100))
                    radius = s * 0.16
                    painter.drawEllipse(center, radius, radius)

        # Pieces
        dpr = self.devicePixelRatioF()
        skip: set[chess.Square] = set()
        if self._dragging and self._drag_from is not None:
            skip.add(self._drag_from)
        animating = self._anim_move is not None and self._anim.state() == QVariantAnimation.Running
        if animating:
            skip.add(self._anim_move.to_square)
        for square in chess.SQUARES:
            if square in skip:
                continue
            piece = self._board.piece_at(square)
            if piece is None:
                continue
            rect = self._square_rect(square)
            painter.drawPixmap(rect.topLeft(), sprites().pixmap(piece, s, dpr))

        # Suggestion arrows above the pieces (so they stay readable)
        if self._show_hints and self._suggestions and not self._dragging:
            self._paint_suggestions(painter, s)

        # Threat radar: opponent threats (red arrows) + hanging pieces (rings)
        if self._show_threats and not self._dragging:
            for rank in range(len(self._threat_moves) - 1, -1, -1):
                color = QColor(theme.THREAT_ARROW)
                color.setAlpha(190 if rank == 0 else 115)
                width = s * (0.15 if rank == 0 else 0.11)
                self._paint_arrow(painter, self._threat_moves[rank], color, width)
            self._paint_hanging_rings(painter, s)

        # Coach refutation arrow (red, on top of the suggestions)
        if self._coach_arrow is not None and not self._dragging:
            color = QColor(theme.BAD)
            color.setAlpha(215)
            self._paint_arrow(painter, self._coach_arrow, color, s * 0.17)

        # Animated piece
        if animating and self._anim_piece is not None:
            t = float(self._anim.currentValue())
            start = QRectF(self._square_rect(self._anim_move.from_square))
            end = QRectF(self._square_rect(self._anim_move.to_square))
            x = start.x() + (end.x() - start.x()) * t
            y = start.y() + (end.y() - start.y()) * t
            painter.drawPixmap(QPointF(x, y), sprites().pixmap(self._anim_piece, s, dpr))

        # Dragged piece on top, centered on the cursor
        if self._dragging and self._drag_from is not None:
            piece = self._board.piece_at(self._drag_from)
            if piece is not None:
                pix = sprites().pixmap(piece, int(s * 1.05), dpr)
                painter.drawPixmap(
                    QPointF(self._drag_pos.x() - s * 0.525, self._drag_pos.y() - s * 0.525),
                    pix)

        painter.end()

    def _paint_coordinates(self, painter: QPainter, s: int, origin: QPoint):
        font = QFont(self.font())
        font.setPixelSize(max(9, int(s * 0.17)))
        font.setBold(True)
        painter.setFont(font)
        files = "abcdefgh" if self._orientation == chess.WHITE else "hgfedcba"
        ranks = "12345678" if self._orientation == chess.WHITE else "87654321"
        light = QColor(theme.SQ_LIGHT)
        dark = QColor(theme.SQ_DARK)
        for i in range(8):
            # File letters along the bottom edge: bottom-row squares alternate
            # dark, light, … from the left, so use the opposite color.
            x = origin.x() + i * s
            y = origin.y() + 7 * s
            painter.setPen(light if i % 2 == 0 else dark)
            painter.drawText(QRectF(x, y, s - s * 0.08, s - s * 0.04),
                             Qt.AlignRight | Qt.AlignBottom, files[i])
            # Rank numbers along the left edge: left-column squares alternate
            # light, dark, … from the top.
            y2 = origin.y() + i * s
            painter.setPen(dark if i % 2 == 0 else light)
            painter.drawText(QRectF(origin.x() + s * 0.08, y2 + s * 0.04, s, s),
                             Qt.AlignLeft | Qt.AlignTop, ranks[7 - i])

    def _paint_suggestions(self, painter: QPainter, s: int):
        # Draw lowest-ranked first so the best arrow ends up on top.
        for rank in range(len(self._suggestions) - 1, -1, -1):
            suggestion = self._suggestions[rank]
            color = QColor(theme.ARROW_COLORS[min(rank, len(theme.ARROW_COLORS) - 1)])
            alpha = 200 if rank == 0 else 150
            color.setAlpha(alpha)
            width = s * (0.17 if rank == 0 else 0.13)
            self._paint_arrow(painter, suggestion.move, color, width)
        for rank, suggestion in enumerate(self._suggestions):
            self._paint_probability_badge(painter, suggestion, rank, s)

    _RING_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                   chess.ROOK: 5, chess.QUEEN: 9}

    def _hanging_squares(self) -> list:
        """Side-to-move pieces that are en prise: attacked while undefended,
        or attacked by something cheaper than they are."""
        board = self._board
        out: list = []
        for square, piece in board.piece_map().items():
            if piece.color != board.turn or piece.piece_type == chess.KING:
                continue
            attackers = board.attackers(not piece.color, square)
            if not attackers:
                continue
            defenders = board.attackers(piece.color, square)
            cheapest = min(self._RING_VALUE.get(
                board.piece_at(a).piece_type, 99) for a in attackers)
            if not defenders or cheapest < self._RING_VALUE[piece.piece_type]:
                out.append(square)
        return out

    def _paint_hanging_rings(self, painter: QPainter, s: int):
        color = QColor(theme.THREAT_ARROW)
        color.setAlpha(200)
        painter.setPen(QPen(color, max(2.5, s * 0.055)))
        painter.setBrush(Qt.NoBrush)
        radius = s * 0.44
        for square in self._hanging_squares():
            center = QRectF(self._square_rect(square)).center()
            painter.drawEllipse(center, radius, radius)

    def _paint_arrow(self, painter: QPainter, move: chess.Move, color: QColor,
                     width: float):
        start = QPointF(QRectF(self._square_rect(move.from_square)).center())
        end = QPointF(QRectF(self._square_rect(move.to_square)).center())
        direction = end - start
        length = math.hypot(direction.x(), direction.y())
        if length < 1:
            return
        unit = QPointF(direction.x() / length, direction.y() / length)
        s = self._square_size()
        start = start + unit * (s * 0.22)
        head_len = width * 2.2
        shaft_end = end - unit * head_len

        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(start, shaft_end)

        normal = QPointF(-unit.y(), unit.x())
        head = QPolygonF([
            end,
            shaft_end + normal * (width * 1.15),
            shaft_end - normal * (width * 1.15),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(head)

    def _paint_probability_badge(self, painter: QPainter, suggestion, rank: int, s: int):
        start = QPointF(QRectF(self._square_rect(suggestion.move.from_square)).center())
        end = QPointF(QRectF(self._square_rect(suggestion.move.to_square)).center())
        # Place the badge 70% of the way to the destination.
        t = 0.68
        pos = QPointF(start.x() + (end.x() - start.x()) * t,
                      start.y() + (end.y() - start.y()) * t)
        text = f"{suggestion.rec_prob * 100:.0f}%"
        font = QFont(self.font())
        font.setPixelSize(max(10, int(s * 0.21)))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        pad_x, pad_y = s * 0.09, s * 0.045
        rect = QRectF(pos.x() - text_width / 2 - pad_x,
                      pos.y() - metrics.height() / 2 - pad_y,
                      text_width + pad_x * 2,
                      metrics.height() + pad_y * 2)
        badge = QColor(theme.ARROW_COLORS[min(rank, len(theme.ARROW_COLORS) - 1)])
        badge.setAlpha(235)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(Qt.NoPen)
        painter.fillPath(path, badge)
        painter.setPen(QColor("#10151a"))
        painter.drawText(rect, Qt.AlignCenter, text)

    def sizeHint(self) -> QSize:
        return QSize(640, 640)
