"""Main window: wires the board, eval bar, sidebar and game controller."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import chess
from PySide6.QtCore import QByteArray, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from . import APP_NAME, theme
from .board_widget import BoardWidget, sprites
from .engine_manager import EngineManager
from .eval_utils import MOVE_LABELS, MOVE_SYMBOLS
from .game_controller import GameController, PlayerKind
from .opening_tab import OpeningStudyTab
from .sidebar import CATEGORY_COLORS, EvalBar, Sidebar


def _default_save_dir() -> Path:
    # Anchor saves next to the executable in frozen builds so games end up in
    # a predictable place no matter where the app is launched from.
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    directory = base / "saves"
    try:
        directory.mkdir(exist_ok=True)
        if not os.access(directory, os.W_OK):
            raise OSError("not writable")
    except OSError:
        directory = Path.home()
    return directory


class CoachBanner(QFrame):
    """Slides in over the Play tab when coach mode flags the player's move."""

    takeBackClicked = Signal()
    showWhyClicked = Signal()
    playOnClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CoachBanner")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.take_back_button = QPushButton("↩ Take back")
        self.take_back_button.setObjectName("PrimaryButton")
        self.why_button = QPushButton("Show why")
        self.play_on_button = QPushButton("Keep move")
        for button, signal in ((self.take_back_button, self.takeBackClicked),
                               (self.why_button, self.showWhyClicked),
                               (self.play_on_button, self.playOnClicked)):
            button.clicked.connect(signal)
            layout.addWidget(button)

    def show_alert(self, alert):
        label = MOVE_LABELS.get(alert.category, "Mistake")
        symbol = MOVE_SYMBOLS.get(alert.category, "?")
        text = (f"<b>{label} {symbol}</b> — your win chance fell "
                f"{alert.before_exp * 100:.0f}% → {alert.after_exp * 100:.0f}%.")
        if alert.best_san:
            text += f"  Best was <b>{alert.best_san}</b>."
        self.label.setText(text)
        color = CATEGORY_COLORS.get(alert.category, theme.BAD)
        self.setStyleSheet(
            f"QFrame#CoachBanner {{ background-color: {theme.BG_PANEL};"
            f" border: 1px solid {color}; border-radius: 8px; }}")
        self.why_button.setEnabled(True)
        self.setVisible(True)

    def reveal_refutation(self, pv_san: list):
        if pv_san:
            line = " ".join(pv_san[:4])
            self.label.setText(self.label.text() + f"  Punished by: <b>{line}</b>")
        self.why_button.setEnabled(False)

    def hide_alert(self):
        self.setVisible(False)


class MainWindow(QMainWindow):
    def __init__(self, engine: EngineManager):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(sprites().pixmap(
            chess.Piece(chess.KNIGHT, chess.WHITE), 64, self.devicePixelRatioF())))

        self.engine = engine
        self.controller = GameController(engine, self)
        self._auto_orient = True
        self._coach_alert = None

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        play_page = QWidget()
        root = QHBoxLayout(play_page)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        self.eval_bar = EvalBar()
        root.addWidget(self.eval_bar)

        board_col = QVBoxLayout()
        board_col.setSpacing(10)
        self.coach_banner = CoachBanner()
        board_col.addWidget(self.coach_banner)
        self.board = BoardWidget()
        board_col.addWidget(self.board, 1)
        root.addLayout(board_col, 1)

        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar = Sidebar()
        # Scrollable so the window can shrink vertically below the sidebar's
        # natural height.
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QScrollArea.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setWidget(self.sidebar)
        sidebar_scroll.viewport().setStyleSheet("background: transparent;")
        sidebar_scroll.setMinimumWidth(300)
        sidebar_scroll.setMaximumWidth(430)
        panel_layout.addWidget(sidebar_scroll)
        root.addWidget(panel)

        self.opening_tab = OpeningStudyTab()
        self.tabs.addTab(play_page, "♟  Play")
        self.tabs.addTab(self.opening_tab, "📖  Opening Study")
        self.opening_tab.continueRequested.connect(self._on_continue_from_opening)

        self._build_menu()
        self._connect_controller()
        self._connect_sidebar()
        self._install_shortcuts()

        self.setMinimumSize(820, 600)
        self.resize(1180, 780)
        self._sync_initial_state()

    # ---- Setup ----

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        for text, shortcut, slot in (
            ("&New game", QKeySequence.New, self._new_game),
            ("&Save game…", QKeySequence.Save, self._save_game),
            ("&Open game…", QKeySequence.Open, self._load_game),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _connect_controller(self):
        c = self.controller
        c.positionChanged.connect(self._on_position_changed)
        c.movesChanged.connect(self._on_moves_changed)
        c.viewChanged.connect(self._on_view_changed)
        c.playersChanged.connect(self._on_players_changed)
        c.statusChanged.connect(self.sidebar.set_status)
        c.evalChanged.connect(self._on_eval_changed)
        c.suggestionsChanged.connect(self._on_suggestions_changed)
        c.openingChanged.connect(self.sidebar.set_opening)
        c.reviewChanged.connect(self._refresh_review)
        c.reviewProgress.connect(self.sidebar.set_review_progress)
        c.engineMissing.connect(self._on_engine_error)
        c.coachAlert.connect(self._on_coach_alert)
        self.coach_banner.takeBackClicked.connect(self._on_coach_take_back)
        self.coach_banner.showWhyClicked.connect(self._on_coach_show_why)
        self.coach_banner.playOnClicked.connect(self._on_coach_play_on)

    def _connect_sidebar(self):
        s = self.sidebar
        s.playerChanged.connect(self._on_player_combo)
        s.difficultyChanged.connect(
            lambda color, level: self.controller.set_difficulty(level, bool(color)))
        s.newGameClicked.connect(self._new_game)
        s.undoClicked.connect(self.controller.undo)
        s.saveClicked.connect(self._save_game)
        s.loadClicked.connect(self._load_game)
        s.navigateClicked.connect(self._on_navigate)
        s.autoplayToggled.connect(self.controller.set_autoplay)
        s.hintsToggled.connect(self.board.set_show_hints)
        s.coachToggled.connect(self._on_coach_toggled)
        s.flipClicked.connect(self._on_flip)
        s.suggestionClicked.connect(self._on_suggestion_clicked)
        s.analyzeClicked.connect(self.controller.analyze_game)
        s.evalGraphClicked.connect(self.controller.navigate)
        s.replayClicked.connect(self._on_replay_from)
        self.board.moveRequested.connect(self._on_board_move)
        self.board.backRequested.connect(lambda: self.controller.step(-1))

    def _install_shortcuts(self):
        bindings = (
            (Qt.Key_Left, lambda: self.controller.step(-1), self.opening_tab.step_back),
            (Qt.Key_Right, lambda: self.controller.step(1), self.opening_tab.step_forward),
            (Qt.Key_Home, lambda: self.controller.navigate(0), None),
            (Qt.Key_End,
             lambda: self.controller.navigate(self.controller.total_moves), None),
        )
        for key, play_slot, opening_slot in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(
                lambda p=play_slot, o=opening_slot: self._route_shortcut(p, o))
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(
            lambda: self._route_shortcut(self.controller.undo,
                                         self.opening_tab.step_back))

    def _route_shortcut(self, play_slot, opening_slot):
        if self.tabs.currentWidget() is self.opening_tab:
            if opening_slot is not None:
                opening_slot()
        else:
            play_slot()

    def _sync_initial_state(self):
        c = self.controller
        self.sidebar.sync_difficulty(c.difficulty_for(chess.WHITE),
                                     c.difficulty_for(chess.BLACK))
        self.sidebar.sync_players(c.players[chess.WHITE], c.players[chess.BLACK])
        self._apply_orientation()
        board = c.view_board()
        self.board.set_position(board, None, animate=False)
        self.board.set_movable_colors(c.movable_colors())
        self.sidebar.set_turn(board.turn)
        self.sidebar.set_status(c.status_text())
        self.sidebar.set_opening(c.opening_name())
        self.sidebar.set_nav_state(c.view_index, c.total_moves)
        self.sidebar.moves_table.rebuild(c.san_history, c.base_fullmove, c.base_turn)
        self._refresh_review()
        self.statusBar().setSizeGripEnabled(False)
        self._load_settings()
        # No-op if the engine has not been started yet; main() refreshes again
        # right after engine.start().
        c.refresh_analysis()

    def _refresh_review(self):
        c = self.controller
        series, annotations, reviews, moments = c.review_data()
        self.sidebar.set_review(series, c.view_index, annotations, reviews,
                                moments, c.best_alternative(c.view_index))

    # ---- Controller events ----

    def _on_position_changed(self, board: chess.Board, last_move, animate: bool):
        self.board.set_position(board, last_move, animate)
        self.board.set_movable_colors(self.controller.movable_colors())
        self.sidebar.set_turn(board.turn if self.controller.outcome(board) is None else None)

    def _on_moves_changed(self):
        c = self.controller
        self.sidebar.moves_table.rebuild(c.san_history, c.base_fullmove, c.base_turn)
        self.sidebar.analyze_button.setEnabled(c.total_moves > 0)
        self._refresh_review()

    def _on_view_changed(self, view_index: int, total: int):
        self.sidebar.moves_table.set_current(view_index)
        self.sidebar.set_nav_state(view_index, total)
        self._dismiss_coach_banner()
        self._refresh_review()

    def _on_players_changed(self):
        c = self.controller
        self.sidebar.sync_players(c.players[chess.WHITE], c.players[chess.BLACK])
        self._auto_orient = True
        self._apply_orientation()
        self.board.set_movable_colors(c.movable_colors())

    def _on_eval_changed(self, expectation_white, text: str):
        self.eval_bar.set_value(expectation_white, text)
        self.sidebar.set_eval(expectation_white, text)

    def _on_suggestions_changed(self, suggestions: list):
        self.sidebar.suggestions_panel.set_suggestions(suggestions)
        self.board.set_suggestions(suggestions)

    def _on_engine_error(self, message: str):
        QMessageBox.warning(self, APP_NAME, message)

    # ---- Coach mode ----

    def _on_coach_toggled(self, enabled: bool):
        self.controller.set_coach_enabled(enabled)
        if not enabled:
            self._dismiss_coach_banner()

    def _on_coach_alert(self, alert):
        self._coach_alert = alert
        self.coach_banner.show_alert(alert)

    def _on_coach_take_back(self):
        self._dismiss_coach_banner()
        self.controller.undo()

    def _on_coach_show_why(self):
        alert = getattr(self, "_coach_alert", None)
        if alert is None:
            return
        self.board.set_coach_arrow(alert.refutation_move)
        self.coach_banner.reveal_refutation(alert.refutation_san)

    def _on_coach_play_on(self):
        self._dismiss_coach_banner()
        self.controller.coach_play_on()

    def _dismiss_coach_banner(self):
        self._coach_alert = None
        self.coach_banner.hide_alert()
        self.board.set_coach_arrow(None)

    # ---- Sidebar events ----

    def _on_player_combo(self, color, kind: PlayerKind):
        self.controller.set_player(bool(color), kind)

    def _on_navigate(self, where: str):
        c = self.controller
        if where == "start":
            c.navigate(0)
        elif where == "back":
            c.step(-1)
        elif where == "fwd":
            c.step(1)
        elif where == "end":
            c.navigate(c.total_moves)

    def _on_flip(self):
        self._auto_orient = False
        self.board.flip()
        self.eval_bar.set_orientation(self.board.orientation())

    def _on_board_move(self, move: chess.Move):
        self.controller.make_move(move)

    def _on_suggestion_clicked(self, move: chess.Move):
        c = self.controller
        if c.view_board().turn in c.movable_colors():
            c.make_move(move)

    def _on_continue_from_opening(self, moves: list, human_color: bool):
        self.controller.start_from(moves, bool(human_color))
        self._auto_orient = True
        self._apply_orientation()
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage(
            "Continuing from the opening — good luck!", 5000)

    def _on_replay_from(self, view_index: int):
        """Rewind to just before the mistake at `view_index` and play it out
        (the mistake's side becomes human, the other side AI)."""
        c = self.controller
        i = view_index - 1
        if i < 0 or i >= c.total_moves:
            return
        san = c.san_history[i]
        mover = c.board_at(i).turn
        # Back up the full game first — replaying truncates the line.
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = _default_save_dir() / f"replay_backup_{stamp}.pgn"
        note = ""
        try:
            c.save_pgn(str(backup))
            note = f" (game backed up to {backup.name})"
        except OSError:
            answer = QMessageBox.question(
                self, APP_NAME,
                "Could not back up the current game. Replay anyway? "
                "The rest of the line will be discarded.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        c.start_from(c.moves[:i], mover, base=c.base_board())
        self._auto_orient = True
        self._apply_orientation()
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage(
            f"Replaying from before {san} — find a better move!{note}", 8000)

    def _apply_orientation(self):
        if not self._auto_orient:
            return
        orientation = self.controller.preferred_orientation()
        self.board.set_orientation(orientation)
        self.eval_bar.set_orientation(orientation)

    # ---- File actions ----

    def _new_game(self):
        if self.controller.total_moves > 0:
            answer = QMessageBox.question(
                self, APP_NAME,
                "Start a new game? The current game will be discarded "
                "unless you have saved it.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return
        self.controller.new_game()

    def _save_game(self):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested = str(_default_save_dir() / f"game_{stamp}.pgn")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save game", suggested, "PGN files (*.pgn);;All files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".pgn"
        try:
            self.controller.save_pgn(path)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save the game:\n{exc}")
            return
        self.statusBar().showMessage(f"Saved to {path}", 5000)

    def _load_game(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open game", str(_default_save_dir()),
            "PGN files (*.pgn);;All files (*)")
        if not path:
            return
        try:
            count = self.controller.load_pgn(path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not load the game:\n{exc}")
            return
        self.statusBar().showMessage(
            f"Loaded {Path(path).name} — {count} moves. Use ◀ ▶ to replay.", 8000)

    # ---- Settings persistence ----

    @staticmethod
    def _as_bool(value, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes")

    def _load_settings(self):
        s = QSettings()
        c = self.controller
        for color, key in ((chess.WHITE, "players/white"),
                           (chess.BLACK, "players/black")):
            val = s.value(key)
            if val in ("Human", "AI"):
                c.set_player(color, PlayerKind.HUMAN if val == "Human" else PlayerKind.AI)
        for color, key in ((chess.WHITE, "difficulty/white"),
                           (chess.BLACK, "difficulty/black")):
            val = s.value(key)
            if val is not None:
                try:
                    c.set_difficulty(int(val), color)
                except (ValueError, TypeError):
                    pass
        self.sidebar.sync_difficulty(c.difficulty_for(chess.WHITE),
                                     c.difficulty_for(chess.BLACK))
        self.sidebar.sync_players(c.players[chess.WHITE], c.players[chess.BLACK])

        hints = self._as_bool(s.value("hints"), True)
        self.sidebar.hints_checkbox.setChecked(hints)   # drives the board too
        coach = self._as_bool(s.value("coach"), False)
        self.sidebar.coach_checkbox.setChecked(coach)   # drives the controller too

        tab = s.value("tab")
        if tab is not None:
            try:
                self.tabs.setCurrentIndex(int(tab))
            except (ValueError, TypeError):
                pass

        geometry = s.value("geometry")
        if isinstance(geometry, (QByteArray, bytes, bytearray)):
            try:
                self.restoreGeometry(geometry)
            except (TypeError, ValueError):
                pass

        self._auto_orient = True
        self._apply_orientation()
        self.board.set_movable_colors(c.movable_colors())

    def _save_settings(self):
        s = QSettings()
        c = self.controller
        s.setValue("geometry", self.saveGeometry())
        s.setValue("players/white", c.players[chess.WHITE].value)
        s.setValue("players/black", c.players[chess.BLACK].value)
        s.setValue("difficulty/white", c.difficulty_for(chess.WHITE))
        s.setValue("difficulty/black", c.difficulty_for(chess.BLACK))
        s.setValue("hints", self.sidebar.hints_checkbox.isChecked())
        s.setValue("coach", self.sidebar.coach_checkbox.isChecked())
        s.setValue("tab", self.tabs.currentIndex())

    # ---- Shutdown ----

    def closeEvent(self, event):
        self._save_settings()
        self.engine.shutdown()
        event.accept()
