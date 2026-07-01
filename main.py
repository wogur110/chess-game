"""Chess Studio — entry point.

Run with:  python main.py
"""

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import APP_NAME
from app.i18n import set_language
from app.theme import build_palette, build_stylesheet


def main() -> int:
    if "--smoke" in sys.argv:
        # Headless self-check used by CI to verify the packaged build works.
        from app.smoke import run_smoke
        return run_smoke()

    app = QApplication(sys.argv)
    app.setOrganizationName("ChessStudio")
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(build_palette())
    app.setStyleSheet(build_stylesheet())
    # The language must be set before any window is built — widgets read
    # their labels through tr() exactly once, at construction time.
    set_language(str(QSettings().value("language") or "en"))

    # Imported here so every module-level default already sees the language.
    from app.engine_manager import EngineManager
    from app.main_window import MainWindow

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
