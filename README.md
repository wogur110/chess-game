# Chess Studio

오프라인 전용 체스 GUI입니다. Stockfish 18을 내장하여 AI 대국, 추천수 확률 표시,
실시간 승률 분석, 난이도 조절, 복기(리플레이) 기능을 제공합니다.

![다크 모던 테마, PySide6 기반]

## 주요 기능

- **다크 모던 GUI** — PySide6(Qt) 기반, 드래그 & 드롭 / 클릭으로 착수
- **AI 추천수 확률 표시** — 매 수마다 상위 3개 후보 수를 화살표 + 확률(%)로 표시
  - 추천 확률(rec %): 후보 수 간 상대적 추천 강도
  - 승리 확률(win %): 그 수를 두었을 때 두는 쪽의 기대 승률
- **승률 사이드바** — 매 착수 후 백/흑 승률을 게이지와 수치로 표시 (보드 옆 세로 평가 바 포함)
- **AI 난이도 조절** — 슬라이더 10단계 (초보 ~800 Elo부터 풀 파워 3200+까지)
- **모드 전환 (대국 중에도 가능)** — 백/흑 각각 Human / AI 선택
  - Human vs AI, AI vs AI, Human vs Human 모두 가능
  - 사람이 한 명일 때는 항상 사람 진영이 화면 아래쪽에 오도록 보드가 자동으로 뒤집힘
  - AI vs AI는 일시정지 / 재개 가능
- **뒤로 가기(Undo)** — AI 상대 시 사람 차례까지 자동으로 되돌림
- **복기 / 저장** — PGN 형식으로 저장(평가값 포함), 불러온 뒤 ◀ ▶ 로 한 수씩 재생.
  과거 장면에서 새 수를 두면 그 지점부터 이어서 둘 수 있음
- **오프닝 학습 탭** — ECO 전체 트리(명명된 라인 3,726개, 148개 패밀리) 내장
  - 오프닝 검색/선택 → ▶ 로 기보를 따라가는 **데모**
  - **드릴 모드** — 선택한 오프닝을 직접 두면서 외우기 (백/흑 선택, 상대 수는 자동 진행,
    틀리면 정답 화살표 표시 + 실수 카운트). 오프닝 미선택 시 전체 북 자유 드릴
  - **변형(variation)과 승률** — 매 포지션마다 마스터 대국(TWIC, 양측 Elo 2200+)
    기반 백승/무/흑승 비율과 게임 수, 후보 수별 통계 막대 표시. 트랜스포지션은
    포지션 기준(EPD)으로 자동 인식
  - **북 종료 후 AI와 이어두기** — 라인이 끝난 지점에서 버튼 한 번으로 Play 탭으로
    넘어가 현재 난이도의 Stockfish와 대국 계속
- 사운드 없음, 네트워크 연결 불필요 (완전 오프라인)

## 실행 방법 (개발 환경)

```bash
pip install -r requirements.txt
python download_stockfish.py   # 최초 1회: Stockfish 18 바이너리 다운로드
python main.py
```

Stockfish 바이너리(~110 MB)는 GitHub 파일 크기 한도 때문에 저장소에 포함되어
있지 않습니다. `download_stockfish.py`가 `engines/linux/stockfish` (Linux) /
`engines/windows/stockfish.exe` (Windows)에 받아줍니다.
없으면 시스템 PATH의 `stockfish`를 대신 사용합니다. 다운로드 후에는 완전
오프라인으로 동작합니다.

## Windows 실행파일 빌드

Windows PC에서 프로젝트 폴더를 통째로 복사한 뒤:

```bat
build_windows.bat
```

빌드가 끝나면 `dist\ChessStudio\ChessStudio.exe`가 생성됩니다.
배포할 때는 `dist\ChessStudio` 폴더 전체를 복사하면 됩니다 (Stockfish 포함, 오프라인 동작).

> PyInstaller는 크로스 컴파일을 지원하지 않으므로 Windows 실행파일은 Windows에서
> 빌드해야 합니다. Linux용은 `./build_linux.sh`를 사용하세요.

## 조작법

| 동작 | 방법 |
|---|---|
| 착수 | 기물 드래그 또는 클릭 → 목적지 클릭 |
| 한 수 앞/뒤로 (복기) | `←` / `→` 또는 사이드바 ◀ ▶ |
| 처음/끝으로 | `Home` / `End` |
| 되돌리기 (Undo) | `Ctrl+Z` 또는 Undo 버튼 |
| 새 게임 / 저장 / 불러오기 | `Ctrl+N` / `Ctrl+S` / `Ctrl+O` |
| 추천 화살표 켜기/끄기 | 사이드바 "Arrows" 체크박스 |
| 추천수 바로 두기 | 사이드바 추천수 행 클릭 |
| 오프닝 학습 | Opening Study 탭 → 좌측에서 오프닝 선택 |
| 오프닝 데모 진행 | ▶ 버튼 또는 `→` (북 무브 행 클릭도 가능) |
| 오프닝 드릴 | 진영 선택 후 "Start drill" |

## 구조

```
main.py                  실행 진입점
app/
  theme.py               다크 테마 팔레트 + Qt 스타일시트
  eval_utils.py          엔진 점수 → 승률 변환 (Stockfish WDL 모델)
  engine_manager.py      Stockfish 프로세스 2개 관리 (착수용 / 분석용)
  game_controller.py     게임 상태, 모드, 되돌리기, 저장/복기
  board_widget.py        보드 렌더링, 드래그&드롭, 추천 화살표
  sidebar.py             승률 바, 추천수 패널, 기보 목록, 컨트롤
  opening_book.py        내장 오프닝 DB 로더 (EPD 키, 트랜스포지션 인식)
  opening_tab.py         오프닝 학습 탭 (브라우저, 데모/드릴, 승률 패널)
  data/openings.json.gz  오프닝 트리 + 마스터 대국 통계 (저장소에 포함)
  main_window.py         전체 조립 (Play / Opening Study 탭)
tools/
  build_opening_data.py  오프닝 DB 재생성 파이프라인 (개발용, 네트워크 필요)
engines/                 Stockfish 18 바이너리 (Linux / Windows)
saves/                   저장된 게임 (PGN)
```

## 오프닝 데이터 출처

- 오프닝 이름/라인: [lichess-org/chess-openings](https://github.com/lichess-org/chess-openings) (CC0)
- 승률 통계: [The Week in Chess](https://theweekinchess.com) 주간 PGN 아카이브
  (TWIC 1549–1648, 약 2년치)에서 양측 Elo 2200 이상 대국만 집계.
  TWIC의 무료 공개 정책에 감사드립니다.
- `app/data/openings.json.gz`가 저장소에 포함되어 있으므로 일반 사용자는 재생성할
  필요가 없습니다. 갱신하려면 `python tools/build_opening_data.py all`.

분석 엔진은 난이도와 무관하게 항상 풀 파워로 동작하므로, 낮은 난이도로 두더라도
승률 표시와 추천수는 정확합니다.
