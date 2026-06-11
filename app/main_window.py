"""Main window: wires the board, eval bar, sidebar and game controller."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import chess
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QMainWindow,
                               QMessageBox, QVBoxLayout, QWidget)

from . import APP_NAME
from .board_widget import BoardWidget, sprites
from .engine_manager import EngineManager
from .game_controller import GameController, PlayerKind
from .sidebar import EvalBar, Sidebar


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


class MainWindow(QMainWindow):
    def __init__(self, engine: EngineManager):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(sprites().pixmap(
            chess.Piece(chess.KNIGHT, chess.WHITE), 64, self.devicePixelRatioF())))

        self.engine = engine
        self.controller = GameController(engine, self)
        self._auto_orient = True

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        self.eval_bar = EvalBar()
        root.addWidget(self.eval_bar)

        self.board = BoardWidget()
        root.addWidget(self.board, 1)

        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar = Sidebar()
        panel_layout.addWidget(self.sidebar)
        root.addWidget(panel)

        self._build_menu()
        self._connect_controller()
        self._connect_sidebar()
        self._install_shortcuts()

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
        c.engineMissing.connect(self._on_engine_error)

    def _connect_sidebar(self):
        s = self.sidebar
        s.playerChanged.connect(self._on_player_combo)
        s.difficultyChanged.connect(self.controller.set_difficulty)
        s.newGameClicked.connect(self._new_game)
        s.undoClicked.connect(self.controller.undo)
        s.saveClicked.connect(self._save_game)
        s.loadClicked.connect(self._load_game)
        s.navigateClicked.connect(self._on_navigate)
        s.autoplayToggled.connect(self.controller.set_autoplay)
        s.hintsToggled.connect(self.board.set_show_hints)
        s.flipClicked.connect(self._on_flip)
        s.suggestionClicked.connect(self._on_suggestion_clicked)
        self.board.moveRequested.connect(self._on_board_move)

    def _install_shortcuts(self):
        bindings = (
            (Qt.Key_Left, lambda: self.controller.step(-1)),
            (Qt.Key_Right, lambda: self.controller.step(1)),
            (Qt.Key_Home, lambda: self.controller.navigate(0)),
            (Qt.Key_End, lambda: self.controller.navigate(self.controller.total_moves)),
        )
        for key, slot in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(slot)
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.controller.undo)

    def _sync_initial_state(self):
        c = self.controller
        self.sidebar.difficulty_slider.setValue(c.difficulty)
        self.sidebar.update_difficulty_label(c.difficulty)
        self.sidebar.sync_players(c.players[chess.WHITE], c.players[chess.BLACK])
        self._apply_orientation()
        board = c.view_board()
        self.board.set_position(board, None, animate=False)
        self.board.set_movable_colors(c.movable_colors())
        self.sidebar.set_turn(board.turn)
        self.sidebar.set_status(c.status_text())
        self.sidebar.set_nav_state(c.view_index, c.total_moves)
        self.sidebar.moves_table.rebuild(c.san_history, c.base_fullmove, c.base_turn)
        self.statusBar().setSizeGripEnabled(False)
        # No-op if the engine has not been started yet; main() refreshes again
        # right after engine.start().
        c.refresh_analysis()

    # ---- Controller events ----

    def _on_position_changed(self, board: chess.Board, last_move, animate: bool):
        self.board.set_position(board, last_move, animate)
        self.board.set_movable_colors(self.controller.movable_colors())
        self.sidebar.set_turn(board.turn if self.controller.outcome(board) is None else None)

    def _on_moves_changed(self):
        c = self.controller
        self.sidebar.moves_table.rebuild(c.san_history, c.base_fullmove, c.base_turn)

    def _on_view_changed(self, view_index: int, total: int):
        self.sidebar.moves_table.set_current(view_index)
        self.sidebar.set_nav_state(view_index, total)

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

    # ---- Shutdown ----

    def closeEvent(self, event):
        self.engine.shutdown()
        event.accept()
