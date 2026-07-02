"""Move sounds: a tiny, lazily-initialized player around QtMultimedia.

Sounds are OFF by default (Options → Sound). QSoundEffect objects are only
created the first time a sound is actually needed, so machines without an
audio backend (headless CI, bare WSL) never touch the audio stack unless
the user turns sounds on — and even then every call degrades gracefully.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:                    # stripped-down build — stay silent
    QSoundEffect = None                # type: ignore[assignment]

SOUND_NAMES = ("move", "capture")


def _sounds_dir() -> Optional[Path]:
    rel = Path("app") / "data" / "sounds"
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / rel)
    candidates.append(Path(__file__).resolve().parent / "data" / "sounds")
    candidates.append(Path.cwd() / rel)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


class SoundPlayer:
    def __init__(self):
        self.enabled = False
        self.volume = 0.5              # 0.0 .. 1.0
        self._effects: dict = {}
        self._init_failed = False

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))
        for effect in self._effects.values():
            if effect is not None:
                effect.setVolume(self.volume)

    def play(self, name: str):
        if not self.enabled:
            return
        effect = self._effect(name)
        if effect is None:
            return
        try:
            effect.play()
        except Exception:
            pass                       # never let audio take the app down

    def _effect(self, name: str):
        if name in self._effects:
            return self._effects[name]
        effect = None
        if QSoundEffect is not None and not self._init_failed:
            directory = _sounds_dir()
            path = directory / f"{name}.wav" if directory else None
            if path is not None and path.is_file():
                try:
                    effect = QSoundEffect()
                    effect.setSource(QUrl.fromLocalFile(str(path)))
                    effect.setVolume(self.volume)
                except Exception:
                    effect = None
                    self._init_failed = True
        self._effects[name] = effect
        return effect


_PLAYER: Optional[SoundPlayer] = None


def player() -> SoundPlayer:
    global _PLAYER
    if _PLAYER is None:
        _PLAYER = SoundPlayer()
    return _PLAYER
