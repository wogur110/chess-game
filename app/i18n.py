"""Lightweight UI translation: English source strings -> selected language.

Usage:  from .i18n import tr
        label.setText(tr("Analyze game"))
        status.setText(tr("Saved to {path}", path=path))

The English string is the lookup key (and the fallback), so untranslated or
brand-new strings degrade gracefully to English. The language is chosen once
at startup (main.py reads the "language" QSettings key before any window is
built); switching in the Options menu takes effect on the next launch.
"""

from __future__ import annotations

LANGUAGES = {"en": "English", "ko": "한국어"}

_current = "en"


def set_language(code: str):
    global _current
    _current = code if code in LANGUAGES else "en"


def current_language() -> str:
    return _current


def tr(text: str, /, **kwargs) -> str:
    translated = TRANSLATIONS.get(_current, {}).get(text, text)
    return translated.format(**kwargs) if kwargs else translated


TRANSLATIONS: dict[str, dict[str, str]] = {"ko": {
    # ---- shared ----
    "White": "백",
    "Black": "흑",
    "Human": "사람",

    # ---- game controller: status line ----
    "Reviewing — position after move {view} of {total}":
        "복기 중 — {total}수 중 {view}수 이후 포지션",
    "Coach — that looks like a {label}. Take back or keep it?":
        "코치 — {label}(으)로 보입니다. 무를까요, 그대로 둘까요?",
    "{turn} to move — AI paused": "{turn} 차례 — AI 일시정지됨",
    "{turn} to move — Stockfish is thinking…": "{turn} 차례 — Stockfish가 생각 중…",
    "{turn} to move — your turn": "{turn} 차례 — 당신의 차례입니다",
    "Checkmate": "체크메이트",
    "Stalemate": "스테일메이트",
    "Insufficient material": "기물 부족",
    "Fifty-move rule": "50수 규칙",
    "Threefold repetition": "3회 동형반복",
    "75-move rule": "75수 규칙",
    "Fivefold repetition": "5회 동형반복",
    "Draw — {reason} ({result})": "무승부 — {reason} ({result})",
    "{reason} — {winner} wins ({result})": "{reason} — {winner} 승리 ({result})",

    # ---- move-quality labels ----
    "Brilliant": "브릴리언트",
    "Great": "훌륭한 수",
    "Best": "최선",
    "Book": "북 무브",
    "Good": "좋은 수",
    "Inaccuracy": "부정확",
    "Miss": "놓침",
    "Mistake": "실수",
    "Blunder": "블런더",

    # ---- difficulty labels ----
    "Beginner · ~800": "입문 · ~800",
    "Casual · 1320": "캐주얼 · 1320",
    "Club · 1500": "클럽 · 1500",
    "Club+ · 1700": "클럽+ · 1700",
    "Strong · 1900": "강함 · 1900",
    "Expert · 2100": "전문가 · 2100",
    "Master · 2300": "마스터 · 2300",
    "IM · 2500": "IM · 2500",
    "GM · 2800": "GM · 2800",
    "Maximum · 3200+": "최대 · 3200+",

    # ---- sidebar ----
    "White to move": "백 차례",
    "Win probability": "승률",
    "Game review": "게임 리뷰",
    "Players": "플레이어",
    "AI difficulty": "AI 난이도",
    "AI suggestions": "AI 추천 수",
    "Moves": "기보",
    "Eval: {text}": "평가: {text}",
    "Analyze game": "게임 분석",
    "Analyzing… {done}/{total}": "분석 중… {done}/{total}",
    "Evaluate every move so accuracy and ?!/?/?? annotations are complete":
        "모든 수를 평가해 정확도와 ?!/?/?? 주석을 완성합니다",
    "Coach": "코치",
    "Warn immediately when your move throws away 10%+ win chance,\n"
    "holding the AI reply so you can take the move back and retry":
        "승률을 10% 이상 잃는 수를 두면 즉시 경고하고,\n"
        "AI 응수를 보류해 무르고 다시 시도할 수 있게 합니다",
    "Threats": "위협",
    "Show what the opponent is threatening (red arrows) and your\n"
    "hanging pieces (red rings). Tip: hold T to peek instead — first\n"
    "find the threats yourself, then check":
        "상대가 노리는 수(빨간 화살표)와 잡힐 위기의 내 기물(빨간 원)을\n"
        "표시합니다. 팁: 항상 켜는 대신 T 키를 눌러 잠깐 확인하세요 —\n"
        "먼저 스스로 위협을 찾은 뒤 검산하는 습관이 좋습니다",
    "Arrows": "화살표",
    "⚪ White": "⚪ 백",
    "⚫ Black": "⚫ 흑",
    "AI · Stockfish": "AI · Stockfish",
    "No AI players — set White or Black to AI.":
        "AI 플레이어가 없습니다 — 백 또는 흑을 AI로 설정하세요.",
    "⚪ White AI": "⚪ 백 AI",
    "⚫ Black AI": "⚫ 흑 AI",
    "{name} — Level {value} · {label}": "{name} — 레벨 {value} · {label}",
    "Go to start (Home)": "처음으로 (Home)",
    "Back (←)": "뒤로 (←)",
    "Forward (→)": "앞으로 (→)",
    "Go to end (End)": "끝으로 (End)",
    "⏸ Pause AI": "⏸ AI 일시정지",
    "▶ Resume AI": "▶ AI 재개",
    "Pause / resume AI vs AI play": "AI 대 AI 대국 일시정지/재개",
    "New game": "새 게임",
    "↩ Undo": "↩ 무르기",
    "Save…": "저장…",
    "Load…": "불러오기…",
    "Flip board": "보드 뒤집기",
    "⟲ Replay from here": "⟲ 여기서 다시 두기",
    "Rewind to just before this mistake and play the position out "
    "against the engine — the current game is backed up first":
        "이 실수 직전으로 되감아 엔진을 상대로 다시 둡니다 — "
        "현재 게임은 먼저 백업됩니다",
    "best was {alt}": "최선은 {alt}",
    "Accuracy: — (analyze the game for a full report)":
        "정확도: — (전체 리포트는 게임 분석을 실행하세요)",
    "Accuracy:  ⚪ {white}   ⚫ {black}": "정확도:  ⚪ {white}   ⚫ {black}",
    "Win probability over the game — click to jump to a move":
        "게임 전체의 승률 그래프 — 클릭하면 해당 수로 이동합니다",
    "Play or analyze a game": "게임을 두거나 분석하세요",
    "Analyzing position…": "포지션 분석 중…",
    "win {p}%": "승률 {p}%",

    # ---- main window ----
    "&File": "파일(&F)",
    "&New game": "새 게임(&N)",
    "&Save game…": "게임 저장(&S)…",
    "&Open game…": "게임 열기(&O)…",
    "E&xit": "종료(&X)",
    "&Options": "옵션(&O)",
    "Language / 언어": "Language / 언어",
    "♟  Play": "♟  대국",
    "📖  Opening Study": "📖  오프닝 학습",
    "🧩  Tactics": "🧩  전술",
    "🧩  Tactics ({due} due)": "🧩  전술 ({due} 복습)",
    "↩ Take back": "↩ 무르기",
    "Show why": "이유 보기",
    "Keep move": "그대로 두기",
    "{label} {symbol} — your win chance fell {before}% → {after}%.":
        "{label} {symbol} — 승률이 {before}% → {after}%로 떨어졌습니다.",
    "Best was {san}.": "최선은 {san}였습니다.",
    "Punished by: {line}": "응징 수순: {line}",
    "Start a new game? The current game will be discarded "
    "unless you have saved it.":
        "새 게임을 시작할까요? 저장하지 않은 현재 게임은 사라집니다.",
    "Save game": "게임 저장",
    "Open game": "게임 열기",
    "PGN files (*.pgn);;All files (*)": "PGN 파일 (*.pgn);;모든 파일 (*)",
    "Could not save the game:\n{error}": "게임을 저장할 수 없습니다:\n{error}",
    "Could not load the game:\n{error}": "게임을 불러올 수 없습니다:\n{error}",
    "Saved to {path}": "{path}에 저장했습니다",
    "Loaded {name} — {count} moves. Use ◀ ▶ to replay.":
        "{name} 불러옴 — {count}수. ◀ ▶로 재생하세요.",
    "Continuing from the opening — good luck!":
        "오프닝에서 이어서 대국합니다 — 행운을 빕니다!",
    "Could not back up the current game. Replay anyway? "
    "The rest of the line will be discarded.":
        "현재 게임을 백업할 수 없습니다. 그래도 다시 둘까요? "
        "이후 수순은 사라집니다.",
    "Replaying from before {san} — find a better move!{note}":
        "{san} 직전부터 다시 둡니다 — 더 나은 수를 찾아보세요!{note}",
    " (game backed up to {name})": " (게임을 {name}에 백업했습니다)",
    "Added {added} puzzle(s) from this game's mistakes — "
    "retrain them in the Tactics tab":
        "이 게임의 실수에서 퍼즐 {added}개를 추가했습니다 — "
        "전술 탭에서 다시 훈련하세요",

    # ---- board widget ----
    "Promotion": "프로모션",
    "Promote to:": "승격할 기물:",

    # ---- opening tab ----
    "Out of book — no known moves": "북 범위 밖 — 알려진 수 없음",
    "book line": "북 라인",
    "no data": "자료 없음",
    "Search openings…  (e.g. Sicilian)": "오프닝 검색…  (예: Sicilian)",
    "OPENINGS": "오프닝",
    "Starting position": "시작 포지션",
    "Unnamed position": "이름 없는 포지션",
    "  ·  out of book": "  ·  북 범위 밖",
    "MASTERS RESULTS  ·  W / D / B": "마스터 전적  ·  백 / 무 / 흑",
    "White wins / draws / Black wins": "백 승 / 무승부 / 흑 승",
    "{total} master games from this position":
        "이 포지션에서 마스터 게임 {total}판",
    "No master-game statistics here": "이 포지션의 마스터 게임 통계 없음",
    "BOOK MOVES": "북 무브",
    "Line start": "라인 처음",
    "Next line move (→)": "라인 다음 수 (→)",
    "Line end": "라인 끝",
    "↩ Back": "↩ 무르기",
    "Take back the last move": "마지막 수를 무릅니다",
    "Drill as": "드릴 진영",
    "Start drill": "드릴 시작",
    "Stop drill": "드릴 중지",
    "Pick an opening on the left, or just move pieces.":
        "왼쪽에서 오프닝을 고르거나 자유롭게 기물을 움직여 보세요.",
    "Reset board": "보드 초기화",
    "Continue vs AI →": "AI와 이어서 →",
    "Take this position into the Play tab and finish the game "
    "against Stockfish":
        "이 포지션을 대국 탭으로 가져가 Stockfish를 상대로 게임을 끝냅니다",
    "Opening data not found": "오프닝 데이터를 찾을 수 없음",
    "app/data/openings.json.gz is missing — run tools/build_opening_data.py.":
        "app/data/openings.json.gz가 없습니다 — "
        "tools/build_opening_data.py를 실행하세요.",
    "Demo: {name} — step through with ▶, or start a drill.":
        "데모: {name} — ▶로 한 수씩 재생하거나 드릴을 시작하세요.",
    "Drill: {name} — you play {side}, exactly along the line.":
        "드릴: {name} — {side}을(를) 잡고 라인을 그대로 둡니다.",
    "Drill: you play {side}. Any book move counts; the opponent "
    "follows master-game popularity.":
        "드릴: {side}을(를) 잡습니다. 어떤 북 무브든 정답이며, "
        "상대는 마스터 게임 빈도를 따릅니다.",
    "Drill stopped — free exploration.": "드릴 중지 — 자유 탐색 모드.",
    "✗ {san} is not the line move — the arrow shows it (misses: {misses}).":
        "✗ {san}은(는) 라인의 수가 아닙니다 — 화살표를 확인하세요 "
        "(실패: {misses}).",
    "✗ {san} is not a book move here — try one of the arrows "
    "(misses: {misses}).":
        "✗ {san}은(는) 여기서 북 무브가 아닙니다 — 화살표 중 하나를 "
        "시도하세요 (실패: {misses}).",
    "✓ Book move!": "✓ 북 무브!",
    "✓ Book move!  (misses so far: {misses})":
        "✓ 북 무브!  (지금까지 실패: {misses})",
    "★ Line complete after {ply} plies — {name}, misses: {misses}. "
    "Continue against the AI to finish the game!":
        "★ {ply}수 만에 라인 완주 — {name}, 실패 {misses}회. "
        "AI와 이어서 게임을 끝내 보세요!",
    "Board reset — pick an opening or explore freely.":
        "보드 초기화 — 오프닝을 고르거나 자유롭게 탐색하세요.",

    # ---- tactics tab ----
    "MY MISTAKES": "내 실수",
    "Review due": "복습하기",
    "Review due ({due})": "복습하기 ({due})",
    "Work through every puzzle scheduled for today, oldest first "
    "(spaced repetition: clean solves come back later, fails tomorrow)":
        "오늘 예정된 퍼즐을 오래된 것부터 차례로 풉니다 "
        "(간격 반복: 깔끔하게 풀면 더 나중에, 실패하면 내일 다시)",
    "Pick a puzzle on the left.": "왼쪽에서 퍼즐을 고르세요.",
    "No puzzles yet.": "아직 퍼즐이 없습니다.",
    "Play a game and run “Analyze game” — every mistake with a "
    "clear best answer becomes a puzzle here, so you retrain on "
    "exactly the positions you misplayed.":
        "게임을 두고 “게임 분석”을 실행하세요 — 명확한 정답이 있는 실수가 "
        "모두 퍼즐이 되어, 실제로 틀렸던 바로 그 포지션을 다시 훈련할 수 "
        "있습니다.",
    "Hint": "힌트",
    "Show the next move of the solution "
    "(the attempt no longer counts as clean)":
        "정답의 다음 수를 보여줍니다 "
        "(이번 시도는 첫 시도 성공으로 인정되지 않습니다)",
    "Show solution": "정답 보기",
    "Next puzzle →": "다음 퍼즐 →",
    "Next due ({left} left) →": "다음 복습 ({left}개 남음) →",
    "Finish session →": "세션 마치기 →",
    "Remove this puzzle": "이 퍼즐 삭제",
    "{side} to move — find the best move.": "{side} 차례 — 최선의 수를 찾으세요.",
    "{label} {symbol} from your game {white} vs {black} ({date}), "
    "move {move_no} — you played {played}.":
        "{white} vs {black} ({date}) 게임의 {label} {symbol}, "
        "{move_no}수째 — 당신은 {played}를 두었습니다.",
    "✓ Correct — the reply is coming…": "✓ 정답 — 상대 응수가 나옵니다…",
    "Your move — continue the line.": "당신 차례 — 수순을 이어가세요.",
    "✗ {san} isn’t it — try again.": "✗ {san}이(가) 아닙니다 — 다시 시도하세요.",
    "★ Solved — first try!": "★ 해결 — 첫 시도 성공!",
    "★ Solved (wrong tries: {wrong}).": "★ 해결 (오답 {wrong}회).",
    "★ Solved (wrong tries: {wrong}, hint used).":
        "★ 해결 (오답 {wrong}회, 힌트 사용).",
    "Solution: {line}": "정답: {line}",
    "Solution revealed — counted as a fail; it will come back tomorrow.":
        "정답 공개 — 실패로 기록되며 내일 다시 나옵니다.",
    "Deck clear — nothing due. Analyze more games to add puzzles.":
        "덱 클리어 — 복습할 퍼즐이 없습니다. 게임을 더 분석해 퍼즐을 "
        "추가하세요.",
    "★ Review done — {clean}/{total} clean. Failed cards come back "
    "tomorrow; clean ones moved up a box.":
        "★ 복습 완료 — {clean}/{total} 첫 시도 성공. 실패한 카드는 내일 "
        "다시, 성공한 카드는 다음 박스로 올라갑니다.",
    "· due now": "· 지금 복습",
    "· next {due}": "· 다음 {due}",
    "{mover} move {move_no}": "{mover} {move_no}수째",
    "{total} puzzle(s) · {solved} solved · {due} due for review":
        "퍼즐 {total}개 · 해결 {solved} · 복습 대기 {due}",
    "Boxes ({days} days): {counts}": "박스 ({days}일): {counts}",
    "Leitner boxes: how many puzzles sit at each review interval — "
    "the further right, the better you know them":
        "라이트너 박스: 각 복습 간격에 있는 퍼즐 수 — 오른쪽일수록 "
        "잘 아는 문제입니다",

    # ---- puzzle rush / themed practice ----
    "PUZZLE RUSH": "퍼즐 러시",
    "All themes": "모든 테마",
    "Mate in 1": "1수 메이트",
    "Mate in 2": "2수 메이트",
    "Back-rank mate": "백랭크 메이트",
    "Fork": "포크",
    "Pin": "핀",
    "Skewer": "스큐어",
    "Discovered attack": "디스커버드 어택",
    "Hanging piece": "매달린 기물",
    "Deflection": "디플렉션",
    "Sacrifice": "희생",
    "Start rush": "러시 시작",
    "Practice": "테마 연습",
    "Stop rush": "러시 중지",
    "3 strikes or 3 minutes — puzzles get harder as you solve. "
    "A wrong move fails the puzzle.":
        "3스트라이크 또는 3분 — 풀수록 어려워집니다. "
        "오답을 두면 그 퍼즐은 실패입니다.",
    "Practice the selected theme untimed, easiest first.":
        "선택한 테마를 시간 제한 없이 쉬운 것부터 연습합니다.",
    "Best: {best}": "최고 기록: {best}",
    "⏱ {time} · Score {score} · ✗ {strikes}/3":
        "⏱ {time} · 점수 {score} · ✗ {strikes}/3",
    "Solved! Next…": "정답! 다음 문제…",
    "✗ Wrong — the answer was {line}.": "✗ 오답 — 정답은 {line}였습니다.",
    "Rush over — score {score} (best {best}).":
        "러시 종료 — 점수 {score} (최고 기록 {best}).",
    "No more puzzles in this theme — pick another.":
        "이 테마의 퍼즐을 모두 풀었습니다 — 다른 테마를 골라 보세요.",
    "Rating {rating}": "레이팅 {rating}",
    "Rating {rating} · {themes}": "레이팅 {rating} · {themes}",
    "Puzzle pack not found — run tools/build_puzzle_pack.py.":
        "퍼즐 팩이 없습니다 — tools/build_puzzle_pack.py를 실행하세요.",
}}
