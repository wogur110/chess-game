"""Build app/data/puzzles_rush.json.gz — the bundled tactics starter pack.

Dev-only (needs network + the `zstandard` package). Regular users never run
this: the resulting pack (~1 MB) is committed to the repository.

Source: the Lichess puzzle database (CC0), ~5M puzzles:
    https://database.lichess.org/lichess_db_puzzle.csv.zst

Selection: well-tested puzzles (high popularity/plays, low rating deviation)
carrying at least one of the themes the app surfaces, reservoir-sampled per
(200-Elo band x primary theme) bucket so both easy and hard puzzles of every
motif make the cut. The Lichess convention stores the position BEFORE the
opponent's setup move (Moves[0]); we pre-apply that move at build time so the
app can present every puzzle solver-to-move, matching the Tactics tab flow.

Usage:  python tools/build_puzzle_pack.py
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import random
import sys
import urllib.request
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "cache"
DUMP_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
DUMP_PATH = CACHE / "lichess_db_puzzle.csv.zst"
OUT_PATH = ROOT / "app" / "data" / "puzzles_rush.json.gz"

# Themes surfaced in the app, in priority order: a puzzle's primary theme is
# the first of these it carries. Keys are Lichess theme tags.
THEMES = ["mateIn1", "mateIn2", "backRankMate", "fork", "pin", "skewer",
          "discoveredAttack", "hangingPiece", "deflection", "sacrifice"]

RATING_MIN, RATING_MAX, BAND = 600, 2400, 200
PER_BUCKET = 40                # reservoir size per (band, theme) bucket
MAX_SOLUTION_PLIES = 9         # keep lines solvable in the tab's UI
MIN_POPULARITY = 85
MIN_PLAYS = 500
MAX_DEVIATION = 90
SEED = 20260702                # reproducible sampling


def download():
    if DUMP_PATH.is_file():
        print(f"using cached {DUMP_PATH.name} "
              f"({DUMP_PATH.stat().st_size / 1e6:.0f} MB)")
        return
    CACHE.mkdir(exist_ok=True)
    print(f"downloading {DUMP_URL} …")
    urllib.request.urlretrieve(DUMP_URL, DUMP_PATH)
    print(f"done ({DUMP_PATH.stat().st_size / 1e6:.0f} MB)")


def sample_rows() -> dict:
    """One streaming pass with per-bucket reservoir sampling."""
    import zstandard

    rng = random.Random(SEED)
    reservoirs: dict[tuple, list] = {}
    seen: dict[tuple, int] = {}
    rows = kept = 0

    with open(DUMP_PATH, "rb") as fh:
        stream = zstandard.ZstdDecompressor().stream_reader(fh)
        text = io.TextIOWrapper(stream, encoding="utf-8", newline="")
        reader = csv.reader(text)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}
        for row in reader:
            rows += 1
            if rows % 1_000_000 == 0:
                print(f"  scanned {rows:,} rows, sampled {kept:,}")
            try:
                rating = int(row[col["Rating"]])
                if not RATING_MIN <= rating < RATING_MAX:
                    continue
                if int(row[col["Popularity"]]) < MIN_POPULARITY:
                    continue
                if int(row[col["NbPlays"]]) < MIN_PLAYS:
                    continue
                if int(row[col["RatingDeviation"]]) > MAX_DEVIATION:
                    continue
                moves = row[col["Moves"]].split()
                if not 2 <= len(moves) <= MAX_SOLUTION_PLIES + 1:
                    continue
                tags = row[col["Themes"]].split()
                theme = next((t for t in THEMES if t in tags), None)
                if theme is None:
                    continue
            except (ValueError, IndexError):
                continue
            bucket = ((rating - RATING_MIN) // BAND, theme)
            entry = (row[col["FEN"]], moves, rating,
                     [t for t in THEMES if t in tags])
            n = seen.get(bucket, 0) + 1
            seen[bucket] = n
            pool = reservoirs.setdefault(bucket, [])
            if len(pool) < PER_BUCKET:
                pool.append(entry)
                kept += 1
            else:
                j = rng.randrange(n)
                if j < PER_BUCKET:
                    pool[j] = entry
    print(f"scanned {rows:,} rows, sampled {kept:,} candidates")
    return reservoirs


def build(reservoirs: dict) -> list:
    """Validate with python-chess and pre-apply the opponent's setup move."""
    out = []
    dropped = 0
    for pool in reservoirs.values():
        for fen, moves, rating, themes in pool:
            try:
                board = chess.Board(fen)
                setup = chess.Move.from_uci(moves[0])
                if setup not in board.legal_moves:
                    dropped += 1
                    continue
                board.push(setup)
                start_fen = board.fen()
                sans = []
                for uci in moves[1:]:
                    move = chess.Move.from_uci(uci)
                    if move not in board.legal_moves:
                        raise ValueError(uci)
                    sans.append(board.san(move))
                    board.push(move)
            except (ValueError, AssertionError):
                dropped += 1
                continue
            out.append([start_fen, moves[1:], sans, rating, themes])
    out.sort(key=lambda p: p[3])
    print(f"validated {len(out):,} puzzles ({dropped} dropped)")
    return out


def main() -> int:
    download()
    puzzles = build(sample_rows())
    counts: dict[str, int] = {}
    for p in puzzles:
        for theme in p[4]:
            counts[theme] = counts.get(theme, 0) + 1
    payload = {"version": 1, "source": "lichess_db_puzzle (CC0)",
               "themes": counts, "puzzles": puzzles}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_PATH, "wb", compresslevel=9) as fh:
        fh.write(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.2f} MB, "
          f"{len(puzzles):,} puzzles)")
    for theme in THEMES:
        print(f"  {theme:18} {counts.get(theme, 0):5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
