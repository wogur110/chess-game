#!/usr/bin/env bash
# Build a Linux executable for Chess Studio.
# Result: dist/ChessStudio/ChessStudio (distribute the whole folder).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f engines/linux/stockfish ]]; then
    echo "engines/linux/stockfish is missing. Run: python3 download_stockfish.py" >&2
    exit 1
fi

python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm chess_studio.spec

echo
echo "Done. Run dist/ChessStudio/ChessStudio"
