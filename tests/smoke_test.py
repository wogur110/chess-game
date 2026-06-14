"""Headless smoke test: drives the real app (offscreen) through a full loop.

    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import chess
from PySide6.QtCore import QDeadlineTimer, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.engine_manager import EngineManager
from app.game_controller import PlayerKind
from app.main_window import MainWindow
from app.theme import build_stylesheet

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    status = "ok" if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        FAILURES.append(name)


def wait_until(predicate, timeout_ms: int = 15000) -> bool:
    app = QApplication.instance()
    deadline = QDeadlineTimer(timeout_ms)
    while not predicate():
        if deadline.hasExpired():
            return False
        app.processEvents(QEventLoop.AllEvents, 50)
    return True


def main() -> int:
    app = QApplication(sys.argv)
    # Isolated, empty settings so the run is deterministic and does not inherit
    # (or pollute) a real install's persisted players/difficulty.
    app.setOrganizationName("ChessStudioSmokeTest")
    app.setApplicationName("Chess Studio Smoke Test")
    from PySide6.QtCore import QSettings
    QSettings().clear()
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()
    check("stockfish found", engine.available, str(engine.engine_path))
    engine.start()

    window = MainWindow(engine)
    window.show()
    c = window.controller
    # Start from a known player configuration regardless of any saved state.
    c.set_player(chess.WHITE, PlayerKind.HUMAN)
    c.set_player(chess.BLACK, PlayerKind.AI)

    # 1. Analysis arrives for the initial position (suggestions + eval).
    seen = {"suggestions": None, "eval": None}
    c.suggestionsChanged.connect(
        lambda s: seen.__setitem__("suggestions", s) if s else None)
    c.evalChanged.connect(
        lambda exp, text: seen.__setitem__("eval", (exp, text)) if exp is not None else None)
    check("initial analysis", wait_until(lambda: seen["suggestions"] is not None))
    if seen["suggestions"]:
        s = seen["suggestions"]
        total = sum(x.rec_prob for x in s)
        check("suggestion probs sum to 1", abs(total - 1.0) < 1e-6, f"sum={total:.4f}")
        check("suggestions have SAN", all(x.san for x in s))
    check("eval received", seen["eval"] is not None, str(seen["eval"]))

    # 2. Human plays e4; the AI (black) must reply.
    check("human move accepted", c.make_move(chess.Move.from_uci("e2e4")))
    check("AI replied", wait_until(lambda: c.total_moves >= 2), f"moves={c.total_moves}")
    check("history SAN", c.san_history[0] == "e4", str(c.san_history))

    # 3. Undo rewinds to the human's turn (start position).
    c.undo()
    check("undo rewinds to human turn", c.total_moves == 0, f"moves={c.total_moves}")

    # 4. AI vs AI: both engines play; autoplay pause stops the game.
    c.set_player(chess.WHITE, PlayerKind.AI)
    check("orientation default for AIvAI", c.preferred_orientation() == chess.WHITE)
    check("AI vs AI produced moves", wait_until(lambda: c.total_moves >= 2),
          f"moves={c.total_moves}")
    c.set_autoplay(False)
    moves_at_pause = None
    def settled():
        nonlocal moves_at_pause
        if not c.ai_thinking:
            moves_at_pause = c.total_moves
            return True
        return False
    wait_until(settled, 8000)
    app.processEvents()
    check("pause holds", c.total_moves - (moves_at_pause or 0) <= 1)

    # 5. Switch black to human mid-game: board should orient to black.
    c.set_player(chess.BLACK, PlayerKind.HUMAN)
    check("orientation follows human (black)", c.preferred_orientation() == chess.BLACK)

    # 6. Navigation (review) works and is non-destructive.
    total_before = c.total_moves
    c.navigate(0)
    check("navigate to start", c.view_index == 0 and c.total_moves == total_before)
    c.navigate(total_before)
    check("navigate to end", c.is_live)

    # 7. Save -> load round trip preserves the game.
    with tempfile.TemporaryDirectory() as tmp:
        pgn_path = str(Path(tmp) / "test.pgn")
        c.save_pgn(pgn_path)
        check("pgn written", Path(pgn_path).stat().st_size > 0)
        san_before = c.san_history
        count = c.load_pgn(pgn_path)
        check("pgn round trip", count == total_before and c.san_history == san_before,
              f"{count} vs {total_before}")
        check("loaded game starts at ply 0", c.view_index == 0)
        c.navigate(count)

    # 8. Screenshot for visual inspection.
    out = Path(__file__).resolve().parent / "screenshot_offscreen.png"
    app.processEvents()
    window.grab().save(str(out))
    check("screenshot saved", out.exists(), str(out))

    window.close()
    app.processEvents()

    print()
    if FAILURES:
        print(f"SMOKE TEST FAILED: {len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
