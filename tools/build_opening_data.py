"""Build the bundled opening database (tree + masters win-rate stats).

One-time data pipeline (network needed only here; the app stays offline):

    python tools/build_opening_data.py tree         # parse ECO TSVs -> tree.json
    python tools/build_opening_data.py fetch-twic   # download TWIC PGN zips
    python tools/build_opening_data.py stats        # count W/D/B from TWIC games
    python tools/build_opening_data.py emit         # write app/data/openings.json.gz
    python tools/build_opening_data.py all          # everything above in order

Sources:
  * Opening names/lines: lichess-org/chess-openings (CC0), a.tsv..e.tsv
  * Game statistics: The Week in Chess (theweekinchess.com) PGN archives,
    filtered to games where both players are rated >= 2200.
"""

from __future__ import annotations

import argparse
import io
import json
import gzip
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / "cache"
TWIC_DIR = CACHE / "twic"
OUT_PATH = ROOT / "app" / "data" / "openings.json.gz"

TSV_FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]
TSV_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/{}"
TWIC_URL = "https://theweekinchess.com/zips/twic{}g.zip"
TWIC_FROM, TWIC_TO = 1549, 1648          # ~2 years of weekly master games
MIN_ELO = 2200
MAX_PLIES = 30                           # only count positions this deep
MIN_GAMES_FOR_STATS = 5

USER_AGENT = "ChessStudio-data-builder/1.0 (one-time build; contact: wogur110@gmail.com)"


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def epd_of(board: chess.Board) -> str:
    return board.epd()


# ---- Step 1: opening tree from the ECO TSVs -----------------------------------

def build_tree() -> dict:
    families: dict[str, list] = defaultdict(list)
    names: dict[str, list] = {}
    book: dict[str, list] = defaultdict(list)
    interest: set[str] = set()

    start_epd = epd_of(chess.Board())
    interest.add(start_epd)

    count = 0
    for tsv in TSV_FILES:
        path = CACHE / tsv
        if not path.exists():
            print(f"[tree] downloading {tsv}")
            path.write_bytes(_get(TSV_URL.format(tsv)))
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            eco, name, movetext = parts
            board = chess.Board()
            ucis = []
            ok = True
            for token in movetext.split():
                if token.endswith("."):
                    continue
                try:
                    move = board.parse_san(token)
                except ValueError:
                    ok = False
                    break
                prev = epd_of(board)
                uci = move.uci()
                if uci not in book[prev]:
                    book[prev].append(uci)
                board.push(move)
                ucis.append(uci)
                interest.add(epd_of(board))
            if not ok or not ucis:
                continue
            final = epd_of(board)
            if final not in names or len(names[final][1]) > len(name):
                names[final] = [eco, name]
            family = name.split(":")[0].strip()
            families[family].append([eco, name, " ".join(ucis)])
            count += 1

    interest.update(book.keys())
    tree = {
        "families": {k: sorted(v, key=lambda x: (x[0], x[1])) for k, v in sorted(families.items())},
        "names": names,
        "book": {k: v for k, v in book.items()},
        "interest": sorted(interest),
    }
    (CACHE / "tree.json").write_text(json.dumps(tree))
    print(f"[tree] {count} named lines, {len(tree['families'])} families, "
          f"{len(names)} name positions, {len(book)} book positions, "
          f"{len(interest)} interest positions")
    return tree


# ---- Step 2: download TWIC archives --------------------------------------------

def fetch_twic(start: int = TWIC_FROM, end: int = TWIC_TO):
    TWIC_DIR.mkdir(parents=True, exist_ok=True)
    for issue in range(start, end + 1):
        dest = TWIC_DIR / f"twic{issue}g.zip"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = TWIC_URL.format(issue)
        try:
            payload = _get(url, timeout=120)
            dest.write_bytes(payload)
            print(f"[twic] {issue}: {len(payload) // 1024} KB")
        except Exception as exc:
            print(f"[twic] {issue}: FAILED ({exc})")
        time.sleep(1.2)   # be polite to the server
    have = len(list(TWIC_DIR.glob("twic*.zip")))
    print(f"[twic] done, {have} archives present")


# ---- Step 3: count statistics ----------------------------------------------------
#
# Runs archives in parallel worker processes and checkpoints merged counts
# after every archive, so an interrupted run resumes where it left off.

CHECKPOINT = CACHE / "stats_checkpoint.json"

_RESULT_INDEX = {"1-0": 0, "1/2-1/2": 1, "0-1": 2}
_WORKER_INTEREST: set = set()


def _worker_init(interest_path: str):
    global _WORKER_INTEREST
    tree = json.loads(Path(interest_path).read_text())
    _WORKER_INTEREST = set(tree["interest"])
    # python-chess logs broken PGNs loudly; keep worker output clean.
    import logging
    logging.getLogger("chess.pgn").setLevel(logging.CRITICAL)


def _count_archive(archive_path_str: str):
    """Count one TWIC archive; returns small JSON-able partial sums."""
    archive_path = Path(archive_path_str)
    stats: dict[str, list] = {}
    san: dict[str, str] = {}
    games_seen = games_used = 0
    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile:
        return archive_path.name, 0, 0, stats, san
    for member in archive.namelist():
        if not member.lower().endswith(".pgn"):
            continue
        text = archive.read(member).decode("latin-1", errors="replace")
        stream = io.StringIO(text)
        while True:
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            games_seen += 1
            headers = game.headers
            result = headers.get("Result", "*")
            if result not in _RESULT_INDEX:
                continue
            try:
                if int(headers.get("WhiteElo", 0)) < MIN_ELO or \
                   int(headers.get("BlackElo", 0)) < MIN_ELO:
                    continue
            except ValueError:
                continue
            if headers.get("FEN"):
                continue              # only standard-start games
            ridx = _RESULT_INDEX[result]
            board = game.board()
            games_used += 1
            for ply, move in enumerate(game.mainline_moves()):
                if ply >= MAX_PLIES:
                    break
                epd = epd_of(board)
                if epd in _WORKER_INTEREST:
                    entry = stats.get(epd)
                    if entry is None:
                        entry = [0, 0, 0, {}]
                        stats[epd] = entry
                    entry[ridx] += 1
                    uci = move.uci()
                    move_entry = entry[3].get(uci)
                    if move_entry is None:
                        move_entry = [0, 0, 0]
                        entry[3][uci] = move_entry
                        san.setdefault(f"{epd}|{uci}", board.san(move))
                    move_entry[ridx] += 1
                try:
                    board.push(move)
                except Exception:
                    break
    return archive_path.name, games_seen, games_used, stats, san


def _merge_counts(total: dict, partial_stats: dict, partial_san: dict):
    stats = total["stats"]
    for epd, (w, d, b, moves) in partial_stats.items():
        entry = stats.get(epd)
        if entry is None:
            stats[epd] = [w, d, b, dict(moves)]
            continue
        entry[0] += w
        entry[1] += d
        entry[2] += b
        for uci, (mw, md, mb) in moves.items():
            move_entry = entry[3].get(uci)
            if move_entry is None:
                entry[3][uci] = [mw, md, mb]
            else:
                move_entry[0] += mw
                move_entry[1] += md
                move_entry[2] += mb
    for key, value in partial_san.items():
        total["san"].setdefault(key, value)


def count_stats():
    import multiprocessing as mp

    archives = sorted(TWIC_DIR.glob("twic*.zip"))
    if not archives:
        sys.exit("[stats] no TWIC archives found; run fetch-twic first")

    if CHECKPOINT.exists():
        total = json.loads(CHECKPOINT.read_text())
        print(f"[stats] resuming: {len(total['done'])} archives already counted")
    else:
        total = {"done": [], "games_seen": 0, "games_used": 0, "stats": {}, "san": {}}

    done = set(total["done"])
    pending = [str(p) for p in archives if p.name not in done]
    start_time = time.time()

    if pending:
        workers = max(2, min(8, (mp.cpu_count() or 4) - 1))
        print(f"[stats] counting {len(pending)} archives on {workers} workers")
        with mp.Pool(workers, initializer=_worker_init,
                     initargs=(str(CACHE / "tree.json"),)) as pool:
            for i, (name, seen, used, pstats, psan) in enumerate(
                    pool.imap_unordered(_count_archive, pending), 1):
                total["games_seen"] += seen
                total["games_used"] += used
                _merge_counts(total, pstats, psan)
                total["done"].append(name)
                if i % 5 == 0 or i == len(pending):
                    CHECKPOINT.write_text(json.dumps(total))
                elapsed = time.time() - start_time
                print(f"[stats] {name}: +{used} games "
                      f"(total {total['games_used']}, {len(total['stats'])} positions, "
                      f"{i}/{len(pending)}, {elapsed:.0f}s)", flush=True)

    payload = {
        "games_used": total["games_used"],
        "stats": total["stats"],
        "san": total["san"],
    }
    (CACHE / "stats.json").write_text(json.dumps(payload))
    print(f"[stats] done: {total['games_used']} games of {total['games_seen']} seen, "
          f"{len(total['stats'])} positions with data")


# ---- Step 4: emit the bundled database -------------------------------------------

def emit():
    tree = json.loads((CACHE / "tree.json").read_text())
    counted = json.loads((CACHE / "stats.json").read_text())
    stats_in = counted["stats"]
    san_map = counted["san"]

    stats_out: dict[str, list] = {}
    for epd, (white, draws, black, moves) in stats_in.items():
        total = white + draws + black
        if total < MIN_GAMES_FOR_STATS:
            continue
        moves_out = {}
        for uci, (mw, md, mb) in moves.items():
            san = san_map.get(f"{epd}|{uci}", uci)
            moves_out[uci] = [san, mw, md, mb]
        stats_out[epd] = [white, draws, black, moves_out]

    data = {
        "version": 1,
        "source": f"TWIC {TWIC_FROM}-{TWIC_TO} (both players >= {MIN_ELO})",
        "games_used": counted["games_used"],
        "families": tree["families"],
        "names": tree["names"],
        "book": tree["book"],
        "stats": stats_out,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    with gzip.open(OUT_PATH, "wb", compresslevel=9) as fh:
        fh.write(raw)
    print(f"[emit] {OUT_PATH}: {len(raw) // 1024} KB raw, "
          f"{OUT_PATH.stat().st_size // 1024} KB gzipped, "
          f"{len(stats_out)} positions with stats")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["tree", "fetch-twic", "stats", "emit", "all"])
    parser.add_argument("--from", dest="start", type=int, default=TWIC_FROM)
    parser.add_argument("--to", dest="end", type=int, default=TWIC_TO)
    args = parser.parse_args()

    if args.step in ("tree", "all"):
        build_tree()
    if args.step in ("fetch-twic", "all"):
        fetch_twic(args.start, args.end)
    if args.step in ("stats", "all"):
        count_stats()
    if args.step in ("emit", "all"):
        emit()


if __name__ == "__main__":
    main()
