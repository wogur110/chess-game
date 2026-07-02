"""Game library: finished games are archived automatically as PGN.

The library lives at saves/library/ next to the executable (the same anchor
logic as manual saves), so games survive reinstalls and are plain PGN files
the user can copy anywhere. The Library tab lists them newest-first and can
reopen any of them in the Play tab.
"""

from __future__ import annotations

import datetime
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chess.pgn


def default_library_dir() -> Path:
    # Same anchoring as the manual save dialog: next to the executable in
    # frozen builds, the working directory otherwise.
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    directory = base / "saves" / "library"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not os.access(directory, os.W_OK):
            raise OSError("not writable")
    except OSError:
        directory = Path.home() / ".chess-studio" / "library"
        directory.mkdir(parents=True, exist_ok=True)
    return directory


@dataclass
class GameEntry:
    path: Path
    white: str
    black: str
    result: str
    date: str
    opening: str
    plies: int


class GameLibrary:
    def __init__(self, directory: Optional[Path] = None):
        self.directory = Path(directory) if directory else default_library_dir()

    def auto_save(self, controller) -> Optional[Path]:
        """Archive the controller's current game; returns the path or None."""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.directory / f"game_{stamp}.pgn"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            controller.save_pgn(str(path))
        except OSError:
            return None
        return path

    def list_games(self) -> list:
        """Header-only scan of the library, newest first."""
        entries: list = []
        try:
            files = sorted(self.directory.glob("*.pgn"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return entries
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    headers = chess.pgn.read_headers(fh)
            except (OSError, ValueError):
                continue
            if headers is None:
                continue
            try:
                plies = int(headers.get("PlyCount", 0))
            except ValueError:
                plies = 0
            entries.append(GameEntry(
                path=path,
                white=headers.get("White", "?"),
                black=headers.get("Black", "?"),
                result=headers.get("Result", "*"),
                date=headers.get("Date", "").replace(".", "-"),
                opening=headers.get("Opening", ""),
                plies=plies,
            ))
        return entries

    def delete(self, path: Path) -> bool:
        try:
            Path(path).unlink()
            return True
        except OSError:
            return False
