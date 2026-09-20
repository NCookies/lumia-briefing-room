# 루미아 브리핑룸 (Lumia Briefing Room)

이터널 리턴 교전 클립 자동 추출기. 설계 문서는 [docs/](docs/) 에 있다.

- [docs/SPEC.md](docs/SPEC.md) — 설계 결정과 근거
- [docs/research.md](docs/research.md) — 0단계 조사 결과(실측)
- [docs/plan.md](docs/plan.md) — 검출기 구현 계획 및 진행 상태
- [docs/plan-pipeline.md](docs/plan-pipeline.md) — 파이프라인 자동화(SPEC 2단계) 구현 계획 및 진행 상태
- [docs/plan-ui.md](docs/plan-ui.md) — 열람 UI(SPEC 3단계) 구현 계획 및 진행 상태
- [docs/plan-pvp.md](docs/plan-pvp.md) — PvP 판별(SPEC 4단계) 구현 계획 및 진행 상태

## 개발 환경

**반드시 가상환경을 쓴다.** 시스템 파이썬에 직접 설치하지 말 것 — 이 PC에는 다른 프로젝트(ultralytics 등)가 이미 깔려 있어 의존성이 충돌한다.

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell/cmd
# 또는: source .venv/Scripts/activate   # git bash

pip install -e ".[dev]"
```

## 테스트

```bash
pytest
```

ffmpeg 를 찾을 수 없으면 ffmpeg 통합 테스트는 자동으로 skip 된다(제품 코드 실행에는 ffmpeg 가 필수지만, 순수 로직 테스트는 ffmpeg 없이도 전부 돈다). ffmpeg 위치를 지정하려면:

```bash
export LUMIA_FFMPEG=/path/to/ffmpeg.exe   # git bash
$env:LUMIA_FFMPEG = "C:\path\to\ffmpeg.exe"   # PowerShell
```

## 실행 방법

> 코드가 바뀌어 아래 내용이 실제와 달라지면 그때그때 이 섹션을 같이 고친다
> ([CLAUDE.md](CLAUDE.md) 참고).

### 0. 가장 간편한 방법 — `run.bat` 더블클릭

가상환경 활성화 없이 [run.bat](run.bat) 을 더블클릭(또는 PowerShell 에서 `.\run.bat`)하면
1번(트레이 상주)이 `--open-ui` 로 실행돼 열람 UI 도 바로 브라우저로 열린다.
UI 를 보려면 먼저 `cd frontend && npm install && npm run build` 를 한 번 해둘 것.
프로그램은 트레이 아이콘(작업표시줄 우측 `^` 숨겨진 아이콘 안일 수 있음)으로 상주하며,
터미널 창은 로그용이라 닫으면 프로그램도 종료된다.

### 1. 실사용 — 트레이 상주 (평소에 쓰는 방법)

트레이 아이콘으로 상주하면서 `Player.log` 를 실시간 감시하다 매치가 끝날 때마다
자동으로 클립을 뽑는다. 트레이 메뉴의 "열기"가 열람 UI 를 브라우저로 열고,
"감시 중" 토글로 감시를 정지/재개할 수 있다. `ui.autoStart` 설정에 따라
윈도우 로그인 시 자동 실행되도록 레지스트리에 등록된다.

**녹화 폴더(`--recording-root`)는 보통 지정할 필요가 없다** — 스팀 레지스트리와
`localconfig.vdf` 의 배경 녹화 설정(`BackgroundRecordPath`)을 읽어 자동으로
찾는다(`steam_paths.py`). 스팀이 이 계정에 없거나 배경 녹화를 한 번도 켠 적이
없어서 자동으로 못 찾을 때만 아래처럼 직접 지정한다.

```bash
python -m lumia_briefing_room.cli.app \
  [--recording-root "H:\steam video\video"] \
  [--config PATH] [--ffmpeg PATH] [--player-log-dir PATH] \
  [--game-mode battle_royale|cobalt] \
  [--k-templates PATH] [--a-templates PATH] [--hwaccel d3d11va] [--open-ui]
```

`--open-ui` 를 주지 않으면 UI 는 자동으로 열리지 않고 트레이 메뉴 "열기" 로 연다
(`ui.startMinimized=false` 로 설정해도 시작 시 자동으로 열린다).

### 2. 열람 UI만 독립 실행

트레이/자동 감시 없이 열람 UI만 띄운다. `frontend/dist` 가 있으면 그 빌드
산출물과 API 를 한 프로세스에서 같이 서빙하며 pywebview 창(실패 시 기본
브라우저)을 연다. 없으면 API만 뜬다 — 먼저 `cd frontend && npm run build` 필요.

```bash
python -m lumia_briefing_room.cli.serve [--config PATH] [--host 127.0.0.1] [--port 8000]
```

### 3. 프론트엔드 개발 (핫 리로드)

```bash
# 터미널 1 — 백엔드(API)
python -m lumia_briefing_room.cli.serve --port 8000

# 터미널 2 — 프론트(핫 리로드), /api 는 vite.config.ts 설정으로 위 백엔드에 프록시된다
cd frontend
npm install        # 최초 1회
npm run dev -- --port 5173
```

### 4. 감시만 (트레이 없이, 콘솔 포그라운드로)

`--recording-root` 는 1번과 마찬가지로 자동 탐지되므로 보통 생략해도 된다. `--once` 를 주면 백로그만 처리하고 종료한다(클립을 지우고 다시 만들 때).

```bash
python -m lumia_briefing_room.cli.watch [--recording-root "H:\steam video\video"] [나머지 옵션은 1번과 동일]
```

### 5. 매치 하나만 수동으로 처리 (백로그 복구 / 디버깅용)

세션 폴더와 매치 시작/종료 시각(UTC ISO)을 직접 넣어 검출→필터→컷→썸네일→
메타데이터까지 한 번에 돌린다.

```bash
python -m lumia_briefing_room.cli.process_match \
  "<세션 폴더>" "<시작 ISO>" "<종료 ISO>" \
  --clips-dir "<출력 폴더>" \
  [--config PATH] [--ffmpeg PATH] [--game-mode battle_royale|cobalt] \
  [--k-templates PATH] [--a-templates PATH] [--hwaccel d3d11va]
```

### 6. 검출기만 (클립 생성 없이 분석 결과만, 개발용)

매치 하나를 분석해 교전 구간을 JSON 으로 출력한다.

```bash
python -m lumia_briefing_room.cli.detect_match \
  "<세션 폴더>" "<시작 ISO>" "<종료 ISO>" \
  --k-templates data/templates/digits/2560x1440.npz \
  [--ffmpeg PATH] [--hwaccel d3d11va]
```

### 7. 교전 라벨링 — 사냥 클립 걸러내기

열람 UI 의 클립 카드와 플레이어 모달에서 **교전 / 사냥**을 찍는다. 모달은 라벨링 모드다:
`1` 교전 · `2` 사냥 · `0` 해제 · `←`/`→` 이동 · `Esc` 닫기. 라벨하면 다음 "안 한" 클립으로 자동 이동한다.
필터에서 "라벨 안 한 것"만 보고, 정렬은 "교전 가능성순"(기본)이다.

**기준: 클립에 사람과의 교전이 *포함*되어 있으면 "교전".** 사냥하다 교전하거나, 교전 뒤에 야생동물·오브젝트(알파/오메가/위클라인)를 잡는 클립도 교전이다.
야생동물·보스만 상대했으면 "사냥", 판단이 안 되면 안 찍고 넘어간다. 자세한 표는 [plan-pvp.md §4-0](docs/plan-pvp.md).

```bash
python tools/eval_pvp.py          # 라벨로 점수를 평가: 오탐, 적 링 분포, 임계별 정밀도/재현율
python tools/rescore_clips.py     # 가중치를 고친 뒤 점수를 다시 계산 (사용자 라벨은 보존)
```

## 개발 도구 (tools/)

`scripts/probe/` 와 달리 실사용하며 계속 돌리는 도구다.

| 도구 | 용도 |
|---|---|
| `tools/collect_frames.py` | 라벨링용 프레임 수집 |
| `tools/label_combat.py` | 검출기 결과로 라벨 초안 생성 |
| `tools/build_templates.py` | 라벨셋 → 숫자 본보기(npz) |
| `tools/build_regions.py` | 라벨셋 → 지역명 본보기(npz) |
| `tools/backfill_day.py` | 이미 만든 클립의 일차·제목을 재처리 없이 채움 (클립 영상의 HUD 에서 읽음) |
| `tools/rescore_clips.py` | 저장된 클립 메타데이터의 교전 점수를 재검출 없이 다시 계산 |
| `tools/eval_pvp.py` | UI 에서 찍은 교전/사냥 라벨로 점수를 평가 (가중치·임계 튜닝) |
| `tools/eval_detect.py` | 라벨셋 대비 검출 정확도 리포트 |

가상환경을 활성화한 상태에서 실행할 것.
