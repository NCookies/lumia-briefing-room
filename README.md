# 루미아 브리핑룸 (Lumia Briefing Room)

이터널 리턴 교전 클립 자동 추출기. 설계 문서는 [docs/](docs/) 에 있다.

- [docs/SPEC.md](docs/SPEC.md) — 설계 결정과 근거
- [docs/research.md](docs/research.md) — 0단계 조사 결과(실측)
- [docs/plan.md](docs/plan.md) — 검출기 구현 계획 및 진행 상태
- [docs/plan-pipeline.md](docs/plan-pipeline.md) — 파이프라인 자동화(SPEC 2단계) 구현 계획 및 진행 상태
- [docs/plan-ui.md](docs/plan-ui.md) — 열람 UI(SPEC 3단계) 구현 계획 및 진행 상태
- [docs/plan-pvp.md](docs/plan-pvp.md) — PvP 판별(SPEC 4단계) 구현 계획 및 진행 상태
- [docs/plan-vod.md](docs/plan-vod.md) — 다시보기(VOD) 클립(SPEC 5단계) 설계 및 진행 상태. 분석·클립 생성, API, UI 탭("다시보기")까지 구현됐다(아래 "실행 방법 8")

## 개발 환경

**반드시 가상환경을 쓴다.** 시스템 파이썬에 직접 설치하지 말 것 — 이 PC에는 다른 프로젝트(ultralytics 등)가 이미 깔려 있어 의존성이 충돌한다.

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell/cmd
# 또는: source .venv/Scripts/activate   # git bash

pip install -e ".[dev]"
pip install --no-deps rapidocr    # 결과 화면 OCR (아래 참고)
```

`rapidocr` 는 `opencv-python` 을 요구해 이미 깔린 `opencv-python-headless` 와 충돌하므로 **`--no-deps` 로 따로 설치**한다(나머지 의존성은 `pyproject.toml` 에 들어 있다). 첫 실행 때 OCR 모델(한국어/중국어, 합쳐 수십 MB)을 내려받는다. rapidocr 가 없거나 OCR 이 실패해도 클립은 그대로 만들어지고 순위 정보만 빈다.

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

### 0-1. 개발용 — 코드 저장 시 자동 재시작 (`dev.bat`)

[dev.bat](dev.bat) (= `python tools/dev_run.py [cli.app 옵션]`)은 `src/` 아래 `.py` 를 저장할 때마다 앱(트레이 + 서버)을 껐다가 다시 띄운다.
브라우저는 첫 기동에만 열리고, 재시작 뒤에는 열려 있는 탭을 새로고침하면 된다(포트가 고정이라 origin 이 그대로다).
트레이 "종료"로 앱을 끄면 `dev.bat` 도 끝나고, 앱이 오류로 죽으면 다음 저장까지 기다린다.
`watchfiles` 가 필요하다(`pip install -e ".[dev]"`). 프론트(`frontend/src`)는 재시작 대상이 아니므로 `npm run build` 후 새로고침한다. 평소 실사용은 그대로 `run.bat`.

### 1. 실사용 — 트레이 상주 (평소에 쓰는 방법)

트레이 아이콘으로 상주하면서 `Player.log` 를 1초마다 훑으며(처리 이력에 없는 끝난 경기를 찾는 폴링 방식이라 분석이 오래 걸리는 동안 끝난 경기, 게임 재실행, 앱을 켜기 전 경기도 놓치지 않는다) 매치가 끝날 때마다
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
필터에서 "라벨 없음"만 볼 수 있다. 목록은 게임(경기) 단위로 묶여, dak.gg 전적처럼 **접힌 한 줄**(`#순위 · 랭크 · 시작 시각 · 캐릭터 · TK/K/A · 클립 수`)로 보이고 ▾ 를 누르면 영상들이 펼쳐진다("모두 펼치기/접기" 버튼도 있다). 결과를 못 읽은 게임은 `게임 N · 결과 미확인` 으로 나온다. 순위 옆에 팀 수·`실험 종료` 같은 문구는 쓰지 않고 탈출만 표시한다. 정렬은 **게임 순서**에만 적용된다: "최신 순"(기본) / "오래된 순" / "교전 가능성순"(게임의 최고 점수가 높은 순). **게임 안의 클립은 항상 오름차순**(시간 순)이다. 영상 볼륨/음소거는 브라우저 localStorage 에 저장돼 다음 영상·재접속에서도 유지된다.

**팀원 캐릭터**: 결과 화면 뒤 `순위표` 탭이 녹화에 잡히면(사용자가 그 탭을 눌러 본 경기) 내 팀원의 캐릭터를 읽어 게임 행 캐릭터 아래에 작게 보여주고, 자동 제목에 `· 내 캐릭터, 팀원` 으로 붙인다. 순위표 탭이 없으면 팀원은 비어 있다. 기존 클립은 `python tools/backfill_result.py --force` 로 다시 채운다.

**클립 이름 수정**: 카드 제목 옆 ✎ 버튼(또는 제목을 더블클릭), 플레이어 제목 옆 ✎ 버튼으로 바꾼다. 직접 바꾼 제목은 자동 제목 갱신에서 제외된다.

**휴지통 비우기**: 휴지통 탭 위쪽 "휴지통 비우기(N개 · 용량)" 버튼이 휴지통의 모든 클립을 한 번에 완전 삭제한다(항상 확인창이 뜬다).

**삭제 확인**: 클립·게임을 삭제(휴지통 이동)하면 확인 창이 뜬다. 창의 "다시 확인하지 않기" 를 체크하거나 옵션 → 일반 → "클립을 삭제할 때 확인 창 표시" 를 끄면 바로 휴지통으로 간다(`ui.confirmDelete`). 완전 삭제·자르기·정리 실행은 이 설정과 관계없이 항상 확인한다. 휴지통 탭의 썸네일/영상과 여러 클립 동시 삭제가 정상 동작한다.

**영상 자르기**: 플레이어 하단 "✂ 자르기" → **시작 위치는 자르기를 켠 순간의 재생 위치**로 잡히고(끝 근처면 처음부터), 두 손잡이(또는 "현재 위치를 시작/끝으로")로 남길 구간을 고르고 "▶ 구간 미리보기" 로 확인한 뒤 "구간만 남기고 나머지 삭제" 를 누르면 그 클립 파일이 잘린 것으로 **교체되고 나머지는 삭제된다(되돌릴 수 없다, 확인창이 뜬다)**. `ffmpeg -c copy` 라 재인코딩이 없어 636MB 클립도 1초 남짓 걸리고 화질 손실이 없다. 최소 1초. 잘린 클립은 메타데이터에 `trimmed`/`originalDurationSec` 가 남고 썸네일이 다시 만들어진다. 시작 앞 키프레임까지(최대 3초)는 화면에 안 보이는 채 파일에 남는다.

**게임 다시 분석**: 게임 행의 "다시 분석" 버튼이 그 게임을 스팀 원본 녹화에서 처음부터 다시 분석해 클립을 새로 만든다(검출 규칙이 고쳐졌을 때나 결과가 이상할 때). 기존 클립은 **휴지통으로 이동**되고(클립 이름 수정 등 편집 내용은 새 클립에 이어지지 않는다), 분석이 실패하면 자동으로 되돌린다. **교전/사냥 라벨은 시간이 겹치는 새 클립으로 자동 이관**된다(`labelSource=migrated`; 겹치는 옛 클립 중 하나라도 교전이면 교전, 교전·사냥이 섞이면 교전으로 옮기고 `labelConflict` 로 확인 표시, 이관이 실패해도 새 클립은 라벨 없이 유지). 옛 클립 폴더끼리 옮기는 수동 도구는 `python tools/migrate_labels.py <옛> <새>`. 원본이 링버퍼에서 이미 지워졌으면 이유를 알려 주고 아무것도 바꾸지 않는다(스팀은 새 녹화가 쌓이면 옛 세그먼트를 지우므로 가능한 한 빨리 해야 한다). 분석은 백그라운드로 돌고(경기 길이에 따라 2~6분) 끝나면 목록이 자동 갱신된다. 다음부터 클립 메타데이터에 `matchEndUtc` 가 남아 로그 없이도 가능하다.

**라벨 보관소**: 영상을 완전히 지워도(휴지통 비우기·완전 삭제·보관 기간이 지난 자동 삭제·즉시 삭제 모드) **교전/사냥 라벨이 붙은 클립의 근거·라벨은 `clips/.labels/<클립ID>.json` 에 남는다**(영상·썸네일·결과 이미지 경로는 빼고 수 KB). 라벨이 없는 클립은 남기지 않는다. `tools/eval_pvp.py` 가 보관소도 같이 읽어(같은 ID 의 지금 클립이 있으면 그쪽이 우선) 용량 때문에 영상을 정리해도 라벨링이 쌓인다.

**게임 단위 삭제**: 게임 행 오른쪽 "게임 삭제" 로 그 게임의 클립을 한꺼번에 휴지통으로 보낸다(휴지통 탭에서는 "게임 복구"/"게임 완전 삭제"). 접힌 게임 행에는 클립 수와 **총 용량**이 같이 표시된다. 휴지통에서 게임의 마지막 클립을 완전 삭제하면 결과표 이미지도 함께 지워진다.

**자동 정리**: 헤더 "⚙ 옵션" → "자동 정리" 탭에서 켠다(기본 꺼짐). 앱(트레이)이 1시간마다 설정 파일을 다시 읽어, 경기한 지 N일 지난 클립 / 클립 N개 초과 / 총 N GB 초과분을 오래된 것부터 휴지통으로(또는 즉시 삭제) 옮기고, 휴지통에서 N일(기본 30)이 지난 것을 영구 삭제한다. 고정한 클립과 선택한 태그(기본 사망)는 보호된다. "저장하고 정리될 항목 확인" 으로 미리보고 "지금 정리 실행" 으로 바로 돌릴 수 있다. 꺼져 있으면 클립도 휴지통도 영원히 남는다.

**영상 저장(내보내기)**: 카드/플레이어의 "저장" 버튼 → 폴더를 골라(서버가 폴더 목록을 보여준다, "새 폴더"도 가능) 파일 이름과 함께 복사한다. 같은 이름이 있으면 `(2)` 를 붙여 덮어쓰지 않는다. 마지막에 저장한 폴더가 `paths.exportDefault` 로 기억돼 다음 저장 창의 시작 위치가 된다. 헤더의 "⚙ 옵션" 에서 이 기본 폴더를 직접 바꿀 수 있다. 실행 방법은 그대로다(프론트를 고쳤으면 `npm run build`).

**게임 결과(순위·랭크 여부)**: 경기가 끝날 때 나오는 결과 화면(`4/7 실험 종료`)을 OCR 로 읽어 클립 메타데이터의 `matchResult`(`matchType` rank/normal, `placement`, `total`, `outcome`, `nickname`)에 넣고, 게임 행에 `#4 랭크 … 13 / 3 / 6` 으로 표시한다. 원본 녹화가 남아 있는 새 경기부터 채워진다. 이미 저장된 클립은 영상에 결과 화면이 없어서, 원본이 아직 남은 경기만 `python tools/backfill_result.py [clips_dir] [--recording-root DIR] [--force]` 로 채운다(게임별로 마지막 클립 뒤에서 원본을 훑어 첫 결과 화면을 읽는다. 링버퍼가 지운 경기는 건너뛴다). 결과 화면은 1280px JPEG 로 `clips/.thumbs/<경기시작>_result.jpg` 에 저장돼 게임 섹션의 첫 칸에 썸네일처럼 보이고(클릭하면 크게), 이미 저장된 경기는 `backfill_result.py` 가 같이 만든다. 내 캐릭터는 결과 화면 오른쪽 세로 영문 이름을 읽어 `data/characters.json`(영문→한글, 없는 이름은 여기에 추가)으로 한글 이름을 찾는다. 닉네임은 첫 결과 화면에서 자동으로 읽어 설정에 저장하고(비어 있을 때만), 헤더 "⚙ 옵션" 에서 직접 고칠 수 있다.

**기준: 클립에 사람과의 교전이 *포함*되어 있으면 "교전".** 사냥하다 교전하거나, 교전 뒤에 야생동물·오브젝트(알파/오메가/위클라인)를 잡는 클립도 교전이다.
야생동물·보스만 상대했으면 "사냥", 판단이 안 되면 안 찍고 넘어간다. 자세한 표는 [plan-pvp.md §4-0](docs/plan-pvp.md).

```bash
python tools/eval_pvp.py          # 라벨로 점수를 평가: 오탐, 적 링 분포, 임계별 정밀도/재현율
python tools/rescore_clips.py     # 가중치를 고친 뒤 점수를 다시 계산 (사용자 라벨은 보존)
```

### 8. 다시보기(VOD) 영상 분석 — 스트리머 방송에서 교전 클립 뽑기

받아 둔 다시보기 영상(mp4)에서 게임을 화면으로 나누고, 게임마다 교전 클립·썸네일·결과(순위·캐릭터·K/A)를 만든다.
클립은 스팀 클립과 **다른 폴더**(`paths.vodClips`, 기본 `%USERPROFILE%\Videos\LumiaBriefingRoom\vod`)에 생기고 원본 영상은 읽기만 한다.
**화면에서 쓰는 법**: 열람 UI 헤더의 **`다시보기` 탭** → 옵션(⚙) → "다시보기" 에서 영상 파일이나 폴더를 추가 → 영상 행의 **분석 시작**. 진행 막대가 보이고 취소하면 다음에 이어서 한다. 끝나면 영상 섹션 안에 게임별 행과 클립이 나오고 라벨·플레이어·자르기·저장은 "내 녹화" 와 같다. 스트리머 이름은 영상 행에서 바로 고친다. 프론트를 고쳤으면 `cd frontend && npm run build`.

**명령줄로 돌리려면**:

```bash
python -m lumia_briefing_room.cli.analyze_vod "<영상.mp4>" \
  [--config PATH] [--ffmpeg PATH] [--clips-dir PATH] [--streamer 이름] [--hwaccel d3d11va] \
  [--force] [--rebuild]
```

- 진행률이 단계(`decode`/`games`/`cut`)별로 출력된다. 8시간 영상은 디코딩·판독에 수십 분이 걸린다(3시간 18분 영상 기준 실측은 plan-vod.md).
- **Ctrl+C 로 멈춰도 된다.** 판독은 120프레임마다 `<클립폴더>/.vods/<영상id>.states.jsonl.gz` 에 저장되고, 같은 명령을 다시 실행하면 저장된 시각부터 이어간다. 영상 id 는 파일 내용(크기 + 앞뒤 1MiB)이라 파일을 옮겨도 이어진다.
- 이미 끝난 영상은 아무것도 안 한다. `--rebuild` 는 저장된 판독으로 클립만 다시 만들고(설정의 `clip.*`·`filter.*` 를 바꾼 뒤), `--force` 는 판독까지 처음부터 다시 한다. 다시 만들 때 기존 클립은 `.trash` 로 옮겨진다.
- 스트리머 이름은 `--streamer` 또는 설정 `vod.streamers` 에 영상 id 로 넣는다. `vod.gameGapSec`(게임 안 끊김 허용, 기본 30초)·`vod.minGameSec`(기본 60초)로 게임 분할을 조절한다.
- 결과 화면(순위 등)에는 RapidOCR 가 필요하다(위 "개발 환경" 참고). 없거나 실패해도 클립은 만들어진다.

### 참고. 게임 기록 보관

자동 정리·완전 삭제로 클립이 다 사라져도 그 경기의 순위·전적·결과표는 `clips/.games/` 에 남아 목록에 "클립 삭제됨" 행으로 보인다(`retention.keepGameRecords`, 옵션 > 자동 정리의 "게임 기록은 유지"). 게임 행의 "기록 삭제"·게임 "완전 삭제"로 지운다. 프론트를 고쳤으면 `npm run build`.

### 9. 브라우저 디버깅 (개발용)

- **클라이언트 오류 로그**: 프론트가 `window.onerror` / `unhandledrejection` / `console.error` 를 `POST /api/client-log` 로 보내고, 서버가 `[client]` 접두로 로그 파일에 남긴다. 로그 파일은 `%LOCALAPPDATA%\LumiaBriefingRoom\logspp.log` (서버 로그와 같은 파일, 2MB 회전). Claude Code 에 "브라우저 오류 봐줘" 라고 하면 이 파일을 읽는다. 프론트를 고쳤으면 `npm run build`.
- **브라우저 자동 조작(Playwright MCP)**: 저장소 루트 `.mcp.json` 에 시스템 Chrome(`--browser chrome`)으로 붙는 설정이 들어 있다. Claude Code 를 이 폴더에서 다시 열면 프로젝트 MCP 승인을 물어본다. 대상은 `python -m lumia_briefing_room.cli.serve --port 8000` 로 띄운 `http://127.0.0.1:8000/`. (Chrome 재생·콘솔 읽기 실측은 아직 안 했다 — [plan-ui.md §6](docs/plan-ui.md))

## 개발 도구 (tools/)

`scripts/probe/` 와 달리 실사용하며 계속 돌리는 도구다.

| 도구 | 용도 |
|---|---|
| `tools/collect_frames.py` | 라벨링용 프레임 수집 |
| `tools/label_combat.py` | 검출기 결과로 라벨 초안 생성 |
| `tools/build_templates.py` | 라벨셋 → 숫자 본보기(npz) |
| `tools/build_regions.py` | 라벨셋 → 지역명 본보기(npz) |
| `tools/migrate_labels.py` | 클립을 새 경계로 다시 만들 때 옛 클립의 교전/사냥 라벨을 시간이 겹치는 새 클립으로 이관 |
| `tools/backfill_day.py` | 이미 만든 클립의 일차·제목을 재처리 없이 채움 (클립 영상의 HUD 에서 읽음) |
| `tools/rescore_clips.py` | 저장된 클립 메타데이터의 교전 점수를 재검출 없이 다시 계산 |
| `tools/eval_pvp.py` | UI 에서 찍은 교전/사냥 라벨로 점수를 평가 (가중치·임계 튜닝) |
| `tools/eval_detect.py` | 라벨셋 대비 검출 정확도 리포트 |

가상환경을 활성화한 상태에서 실행할 것.
