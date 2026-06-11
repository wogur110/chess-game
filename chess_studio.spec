# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Chess Studio.
# Build on the target OS:  pyinstaller --noconfirm chess_studio.spec

import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")

# Ship Stockfish via `binaries` (not `datas`) so the execute bit survives
# on Linux; harmless on Windows.
if IS_WINDOWS:
    engine_binaries = [("engines/windows/stockfish.exe", "engines/windows")]
else:
    engine_binaries = [("engines/linux/stockfish", "engines/linux")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=engine_binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim Qt modules the app does not use to keep the build small.
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtMultimedia", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtPdf", "PySide6.Qt3DCore",
        "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChessStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChessStudio",
)
