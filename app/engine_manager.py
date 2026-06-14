"""Stockfish lifecycle and background workers.

Two engine processes are used:
  * a *play* engine, strength-limited according to the difficulty level,
    which produces the moves AI players actually make;
  * an *analysis* engine, always at full strength, which evaluates the
    current position (win probability, top-3 suggested moves).

Each engine lives on its own daemon thread; requests go through a
latest-wins queue, results come back via Qt signals (queued delivery to
the GUI thread). Every request carries a generation number — the
controller bumps it whenever the position changes, so stale results are
simply dropped.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import chess
import chess.engine
from PySide6.QtCore import QObject, Signal

from .eval_utils import score_to_expectation_white

# ---- Difficulty levels -------------------------------------------------------

@dataclass(frozen=True)
class DifficultyLevel:
    label: str
    options: dict
    movetime: float


DIFFICULTY_LEVELS: dict[int, DifficultyLevel] = {
    1: DifficultyLevel("Beginner · ~800", {"UCI_LimitStrength": False, "Skill Level": 0}, 0.08),
    2: DifficultyLevel("Casual · 1320", {"UCI_LimitStrength": True, "UCI_Elo": 1320, "Skill Level": 20}, 0.15),
    3: DifficultyLevel("Club · 1500", {"UCI_LimitStrength": True, "UCI_Elo": 1500, "Skill Level": 20}, 0.20),
    4: DifficultyLevel("Club+ · 1700", {"UCI_LimitStrength": True, "UCI_Elo": 1700, "Skill Level": 20}, 0.30),
    5: DifficultyLevel("Strong · 1900", {"UCI_LimitStrength": True, "UCI_Elo": 1900, "Skill Level": 20}, 0.40),
    6: DifficultyLevel("Expert · 2100", {"UCI_LimitStrength": True, "UCI_Elo": 2100, "Skill Level": 20}, 0.50),
    7: DifficultyLevel("Master · 2300", {"UCI_LimitStrength": True, "UCI_Elo": 2300, "Skill Level": 20}, 0.70),
    8: DifficultyLevel("IM · 2500", {"UCI_LimitStrength": True, "UCI_Elo": 2500, "Skill Level": 20}, 0.90),
    9: DifficultyLevel("GM · 2800", {"UCI_LimitStrength": True, "UCI_Elo": 2800, "Skill Level": 20}, 1.20),
    10: DifficultyLevel("Maximum · 3200+", {"UCI_LimitStrength": False, "Skill Level": 20}, 1.60),
}

DEFAULT_DIFFICULTY = 5
ANALYSIS_LIMIT = chess.engine.Limit(depth=22, time=0.9)
# Shorter per-position budget for whole-game review (dozens of positions).
FULL_ANALYSIS_LIMIT = chess.engine.Limit(depth=16, time=0.25)
MULTIPV = 3


# ---- Engine discovery --------------------------------------------------------

def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parent.parent)
    roots.append(Path.cwd())
    return roots


def find_stockfish() -> Optional[str]:
    rel = Path("engines") / ("windows/stockfish.exe" if os.name == "nt" else "linux/stockfish")
    for root in _candidate_roots():
        candidate = root / rel
        if candidate.is_file():
            return str(candidate)
    import shutil
    return shutil.which("stockfish")


def _popen_kwargs() -> dict:
    if os.name == "nt":
        # Prevent a console window from flashing up in --windowed builds.
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---- Result payloads ---------------------------------------------------------

@dataclass
class AnalysisLine:
    move: chess.Move
    san: str
    score: chess.engine.PovScore
    expectation_white: float
    pv_san: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    lines: list[AnalysisLine]
    ply: int


@dataclass
class ReviewLine:
    index: int                              # position index in the game
    score: chess.engine.PovScore            # best-play eval (white POV)
    best_move: chess.Move
    best_san: str
    second_white_exp: Optional[float] = None  # 2nd-best line, white expectation


_STOP = object()


class _Worker:
    """A daemon thread owning one Stockfish process and a latest-wins queue."""

    def __init__(self, name: str, path: str, base_options: dict, on_error):
        self.name = name
        self.path = path
        self.base_options = base_options
        self.on_error = on_error
        self.queue: queue.Queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._configured: dict = {}

    def start(self):
        self.thread.start()

    def submit(self, job):
        self.queue.put(job)

    def stop(self):
        self.queue.put(_STOP)

    # -- thread body --

    def _spawn(self) -> chess.engine.SimpleEngine:
        engine = chess.engine.SimpleEngine.popen_uci(self.path, **_popen_kwargs())
        engine.configure(self.base_options)
        self._configured = {}
        return engine

    def _run(self):
        try:
            engine = self._spawn()
        except Exception as exc:
            self.on_error(f"Failed to start Stockfish ({self.name}): {exc}")
            return
        try:
            while True:
                job = self.queue.get()
                # Latest-wins for ordinary jobs, but a "keep" job (whole-game
                # review) must never be discarded by a newer interactive job.
                pending_keep = None
                if job is not _STOP and getattr(job, "keep", False):
                    pending_keep, job = job, None
                stop = job is _STOP
                while True:
                    try:
                        nxt = self.queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is _STOP:
                        stop = True
                    elif getattr(nxt, "keep", False):
                        pending_keep = nxt
                    else:
                        job = nxt
                if stop:
                    break
                # Run the interactive job first (keeps the view fresh), then the
                # long review job.
                for task in (job, pending_keep):
                    if task is None:
                        continue
                    engine = self._execute(task, engine)
                    if engine is None:
                        return
        finally:
            if engine is not None:
                try:
                    engine.quit()
                except Exception:
                    pass

    def _execute(self, job, engine):
        """Run one job, restarting the engine once if it crashed. Returns the
        engine to keep using, or None if it could not be restarted."""
        try:
            job(engine, self)
        except chess.engine.EngineTerminatedError:
            try:
                engine = self._spawn()
                job(engine, self)
            except Exception as exc:
                self.on_error(f"Stockfish ({self.name}) crashed: {exc}")
                return None
        except Exception as exc:
            self.on_error(f"Engine error ({self.name}): {exc}")
        return engine

    def configure_cached(self, engine: chess.engine.SimpleEngine, options: dict):
        delta = {k: v for k, v in options.items() if self._configured.get(k) != v}
        if delta:
            engine.configure(delta)
            self._configured.update(delta)


class EngineManager(QObject):
    """Owns both engine workers; all public methods are GUI-thread-only."""

    analysisReady = Signal(int, int, object)   # generation, ctx, AnalysisResult
    moveReady = Signal(int, object)            # generation, chess.Move
    fullAnalysisLine = Signal(int, object)       # game_id, ReviewLine
    fullAnalysisDone = Signal(int, bool)         # game_id, completed
    engineError = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._path = find_stockfish()
        self._play: Optional[_Worker] = None
        self._analysis: Optional[_Worker] = None
        self._full_gen = 0   # bumped to cancel an in-flight whole-game review

    @property
    def available(self) -> bool:
        return self._path is not None

    @property
    def engine_path(self) -> Optional[str]:
        return self._path

    def start(self):
        if not self._path:
            self.engineError.emit(
                "Stockfish binary not found. Expected it under 'engines/' next to the application."
            )
            return
        threads = max(1, min(2, (os.cpu_count() or 2) // 2))
        self._play = _Worker("stockfish-play", self._path,
                             {"Threads": 1, "Hash": 64}, self._emit_error)
        self._analysis = _Worker("stockfish-analysis", self._path,
                                 {"Threads": threads, "Hash": 128}, self._emit_error)
        self._play.start()
        self._analysis.start()

    def _emit_error(self, message: str):
        self.engineError.emit(message)

    # -- requests --

    def request_move(self, board: chess.Board, generation: int, level: int):
        if not self._play:
            return
        diff = DIFFICULTY_LEVELS.get(level, DIFFICULTY_LEVELS[DEFAULT_DIFFICULTY])
        snapshot = board.copy(stack=True)

        def job(engine: chess.engine.SimpleEngine, worker: _Worker):
            worker.configure_cached(engine, diff.options)
            result = engine.play(snapshot, chess.engine.Limit(time=diff.movetime))
            if result.move is not None:
                self.moveReady.emit(generation, result.move)

        self._play.submit(job)

    def request_analysis(self, board: chess.Board, generation: int, ctx: int,
                         multipv: int = MULTIPV):
        if not self._analysis or board.is_game_over():
            return
        snapshot = board.copy(stack=False)

        def job(engine: chess.engine.SimpleEngine, worker: _Worker):
            infos = engine.analyse(snapshot, ANALYSIS_LIMIT, multipv=multipv)
            if isinstance(infos, dict):
                infos = [infos]
            lines: list[AnalysisLine] = []
            for info in infos:
                pv = info.get("pv")
                score = info.get("score")
                if not pv or score is None:
                    continue
                move = pv[0]
                try:
                    san = snapshot.san(move)
                except Exception:
                    continue
                pv_san = []
                pv_board = snapshot.copy(stack=False)
                for m in pv[:8]:
                    try:
                        pv_san.append(pv_board.san(m))
                        pv_board.push(m)
                    except Exception:
                        break
                lines.append(AnalysisLine(
                    move=move,
                    san=san,
                    score=score,
                    expectation_white=score_to_expectation_white(score, ply=snapshot.ply()),
                    pv_san=pv_san,
                ))
            if lines:
                self.analysisReady.emit(generation, ctx, AnalysisResult(lines=lines, ply=snapshot.ply()))

        self._analysis.submit(job)

    def cancel_full_analysis(self):
        """Stop an in-flight whole-game review (its loop checks this token)."""
        self._full_gen += 1

    def request_full_analysis(self, indexed_boards: list, game_id: int):
        """Evaluate every position of a game. `indexed_boards` is a list of
        (position_index, board); results stream back via fullAnalysisLine."""
        if not self._analysis:
            return
        self._full_gen += 1
        token = self._full_gen
        snapshots = [(idx, b.copy(stack=False)) for idx, b in indexed_boards]

        def job(engine: chess.engine.SimpleEngine, worker: _Worker):
            completed = True
            for idx, board in snapshots:
                if self._full_gen != token:
                    completed = False
                    break
                if board.is_game_over():
                    continue
                try:
                    infos = engine.analyse(board, FULL_ANALYSIS_LIMIT, multipv=2)
                except Exception:
                    continue
                if isinstance(infos, dict):
                    infos = [infos]
                best = infos[0]
                pv = best.get("pv")
                score = best.get("score")
                if not pv or score is None:
                    continue
                best_move = pv[0]
                try:
                    best_san = board.san(best_move)
                except Exception:
                    continue
                second_exp = None
                if len(infos) > 1 and infos[1].get("score") is not None:
                    second_exp = score_to_expectation_white(
                        infos[1]["score"], ply=board.ply())
                self.fullAnalysisLine.emit(game_id, ReviewLine(
                    index=idx, score=score, best_move=best_move,
                    best_san=best_san, second_white_exp=second_exp))
            self.fullAnalysisDone.emit(game_id, completed)

        job.keep = True   # don't let the latest-wins drain discard this
        self._analysis.submit(job)

    def shutdown(self):
        self._full_gen += 1
        for worker in (self._play, self._analysis):
            if worker:
                worker.stop()
        for worker in (self._play, self._analysis):
            if worker and worker.thread.is_alive():
                worker.thread.join(timeout=3.0)
        self._play = None
        self._analysis = None
