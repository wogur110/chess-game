"""Headless self-check for the packaged executable:  ChessStudio --smoke

Exits 0 only if the bundled Stockfish engine and opening database actually
load and a real engine round-trip works. CI uses this to verify the built
.exe is functional.

A plain "did the process stay alive?" check is not enough: the app degrades
gracefully when Stockfish is missing (it shows a warning and keeps running),
so a broken bundle would otherwise pass. This mode turns "engine reachable
and replying" and "opening data loaded" into a process exit code.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _log_path() -> Path:
    base = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False) else Path.cwd())
    return base / "smoke_error.log"


def run_smoke(timeout_ms: int = 30000) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import chess
        from PySide6.QtCore import QDeadlineTimer, QEventLoop
        from PySide6.QtWidgets import QApplication

        from app.engine_manager import EngineManager
        from app.game_controller import PlayerKind
        from app.main_window import MainWindow

        app = QApplication(sys.argv)
        engine = EngineManager()
        if not engine.available:
            raise RuntimeError(
                "bundled Stockfish not found — find_stockfish() returned None")

        window = MainWindow(engine)
        # Force the player config so the round-trip works regardless of any
        # persisted settings (white human plays, black AI must reply).
        window.controller.set_player(chess.WHITE, PlayerKind.HUMAN)
        window.controller.set_player(chess.BLACK, PlayerKind.AI)
        engine.start()
        window.controller.refresh_analysis()

        if window.opening_tab.book is None:
            raise RuntimeError(
                "opening database (app/data/openings.json.gz) failed to load")
        if window.tactics_tab.pack is None or not len(window.tactics_tab.pack):
            raise RuntimeError(
                "puzzle pack (app/data/puzzles_rush.json.gz) failed to load")

        controller = window.controller
        # White (human) plays e4; the AI (black) must reply — a real round-trip
        # through the bundled engine process.
        if not controller.make_move(chess.Move.from_uci("e2e4")):
            raise RuntimeError("could not make the opening move e2e4")
        deadline = QDeadlineTimer(timeout_ms)
        while controller.total_moves < 2 and not deadline.hasExpired():
            app.processEvents(QEventLoop.AllEvents, 50)
        if controller.total_moves < 2:
            raise RuntimeError(
                "engine did not reply within the timeout — engine not working")

        engine.shutdown()
        return 0
    except Exception:
        report = traceback.format_exc()
        try:
            _log_path().write_text(report, encoding="utf-8")
        except Exception:
            pass
        try:
            sys.stderr.write(report)
        except Exception:
            pass
        return 1
