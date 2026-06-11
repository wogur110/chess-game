@echo off
REM Build a Windows executable for Chess Studio.
REM Run this on Windows from the project root:
REM   build_windows.bat
REM The result is dist\ChessStudio\ChessStudio.exe (distribute the whole folder).

setlocal
set PY=python
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python not found on PATH. Install Python 3.10+ first.
        exit /b 1
    )
    set PY=py -3
)

if not exist "engines\windows\stockfish.exe" (
    echo engines\windows\stockfish.exe is missing.
    echo Run:  %PY% download_stockfish.py
    exit /b 1
)

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller

%PY% -m PyInstaller --noconfirm chess_studio.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Done. Run dist\ChessStudio\ChessStudio.exe
endlocal
