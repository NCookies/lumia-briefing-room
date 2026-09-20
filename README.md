# 루미아 브리핑룸 (Lumia Briefing Room)

이터널 리턴 교전 클립 자동 추출기. 설계 문서는 [docs/](docs/) 에 있다.

- [docs/SPEC.md](docs/SPEC.md) — 설계 결정과 근거
- [docs/research.md](docs/research.md) — 0단계 조사 결과(실측)
- [docs/plan.md](docs/plan.md) — 검출기 구현 계획 및 진행 상태
- [docs/plan-pipeline.md](docs/plan-pipeline.md) — 파이프라인 자동화(SPEC 2단계) 구현 계획 및 진행 상태
- [docs/plan-ui.md](docs/plan-ui.md) — 열람 UI(SPEC 3단계) 구현 계획 및 진행 상태

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

### 1. 실사용 — 트레이 상주 (평소에 쓰는 방법)

트레이 아이콘으로 상주하면서 `Player.log` 를 실시간 감시하다 매치가 끝날 때마다
자동으로 클립을 뽑는다. 트레이 메뉴의 "열기"가 열람 UI 를 브라우저로 열고,
"감시 중" 토글로 감시를 정지/재개할 수 있다. `ui.autoStart` 설정에 따라
윈도우 로그인 시 자동 실행되도록 레지스트리에 등록된다.

```bash
python -m lumia_briefing_room.cli.app \
  --recording-root "H:\steam video\video" \
  [--config PATH] [--ffmpeg PATH] [--player-log-dir PATH] \
  [--game-mode battle_royale|cobalt] \
  [--k-templates PATH] [--a-templates PATH] [--hwaccel d3d11va]
```

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

```bash
python -m lumia_briefing_room.cli.watch --recording-root "H:\steam video\video" [옵션은 1번과 동일]
```

### 5. 매치 하나만 수동으로 처리 (백로그 복구 / 디버깅용)

세션 폴더와 매치 시작/종료 시각(UTC ISO)을 직접 넣어 검출→필터→컷→썸네일→
메타데이터까지 한 번에 돌린다.

```bash
python -m lumia_briefing_room.cli.process_match \
  "<세션 폴더>" "<시작 ISO>" "<종료 ISO>" \
  --ffmpeg "<ffmpeg 경로>" --clips-dir "<출력 폴더>" \
  [--config PATH] [--game-mode battle_royale|cobalt] \
  [--k-templates PATH] [--a-templates PATH] [--hwaccel d3d11va]
```

### 6. 검출기만 (클립 생성 없이 분석 결과만, 개발용)

매치 하나를 분석해 교전 구간을 JSON 으로 출력한다.

```bash
python -m lumia_briefing_room.cli.detect_match \
  "<세션 폴더>" "<시작 ISO>" "<종료 ISO>" \
  --ffmpeg "<ffmpeg 경로>" --hwaccel d3d11va \
  --k-templates data/templates/digits/2560x1440.npz
```

## 개발 도구 (tools/)

`scripts/probe/` 와 달리 실사용하며 계속 돌리는 도구다.

| 도구 | 용도 |
|---|---|
| `tools/collect_frames.py` | 라벨링용 프레임 수집 |
| `tools/label_combat.py` | 검출기 결과로 라벨 초안 생성 |
| `tools/build_templates.py` | 라벨셋 → 숫자 본보기(npz) |
| `tools/eval_detect.py` | 라벨셋 대비 검출 정확도 리포트 |

가상환경을 활성화한 상태에서 실행할 것.
