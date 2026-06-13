"""Chess Studio — entry point.

Run with:  python main.py
"""

import sys

from PySide6.QtWidgets import QApplication

from app import APP_NAME
from app.engine_manager import EngineManager
from app.main_window import MainWindow
from app.theme import build_stylesheet


def main() -> int:
    if "--smoke" in sys.argv:
        # Headless self-check used by CI to verify the packaged build works.
        from app.smoke import run_smoke
        return run_smoke()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())

    engine = EngineManager()
    window = MainWindow(engine)
    window.show()
    # Start the engine only after the window exists so that error signals
    # (e.g. missing Stockfish binary) reach the warning dialog.
    engine.start()
    window.controller.refresh_analysis()

    exit_code = app.exec()
    engine.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
