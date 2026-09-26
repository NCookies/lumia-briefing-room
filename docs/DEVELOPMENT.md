# 개발자 문서 (루미아 브리핑룸)

사용자용 안내(설치·사용법)는 저장소 루트의 [README.md](../README.md) 에 있다. 이 문서는 소스에서 실행·빌드·테스트하는 개발자용이다. 설계 문서는 이 폴더에 있다.

- [docs/SPEC.md](SPEC.md) — 설계 결정과 근거
- [docs/research.md](research.md) — 0단계 조사 결과(실측)
- [docs/plan.md](plan.md) — 검출기 구현 계획 및 진행 상태
- [docs/plan-pipeline.md](plan-pipeline.md) — 파이프라인 자동화(SPEC 2단계) 구현 계획 및 진행 상태
- [docs/plan-ui.md](plan-ui.md) — 열람 UI(SPEC 3단계) 구현 계획 및 진행 상태
- [docs/plan-pvp.md](plan-pvp.md) — PvP 판별(SPEC 4단계) 구현 계획 및 진행 상태
- [docs/plan-deploy.md](plan-deploy.md) — 공개 배포 계획. D1~D6·D10·D14 구현 완료, D7 은 파일 정리 완료·git 이력 정리 대기. D13 배포 자동화는 완료(v0.1.3 태그 릴리스까지 자동으로 성공). D9 자동 업데이트는 구현·자동 테스트 완료, 남은 것은 덮어쓰기 설치 실측(수동 절차는 plan-deploy D9)
- [docs/friend-guide.md](friend-guide.md) — **친구에게 설치기와 같이 주는 안내문**(설치·확인 항목·진단 파일 보내는 법)
- [docs/plan-vod.md](plan-vod.md) — 다시보기(VOD) 클립(SPEC 5단계) 설계 및 진행 상태. 분석·클립 생성, API, UI 탭("다시보기")까지 구현됐다(아래 "실행 방법 8")

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

서버와 공유하는 **전송 계약 테스트**(`tests/test_contract.py`)는 `tests/contract/`(infra 저장소 `contract/` 의 복사본)를 쓴다. infra 저장소가 인프라 저장소 처럼 이 저장소 옆에 있으면 복사본이 원본과 같은지도 검사하고, 없으면 그 검사만 건너뛴다. 서버 쪽 계약이 바뀌었으면 `python tools/sync_contract.py` 로 복사본을 갱신하고(`--check` 는 차이만 확인) 테스트를 다시 돌린다. 앱의 클립 메타데이터에 필드를 추가하면 `tests/contract/app-metadata-fields.json` 에 전송/제외 분류가 없어 이 테스트가 깨진다 — 분류는 infra 저장소 원본에서 고치고 다시 복사한다.

**서버 통합 테스트**(`-m integration`)는 기본 `pytest` 에서 빠진다. 도커가 켜져 있고 infra 저장소가 이 저장소 옆(인프라 저장소)에 있으면 `pytest -m integration tests/test_integration_receiver.py` 로 receiver 컨테이너를 임시 토큰으로 띄워 앱의 전송 클라이언트(라벨·오류 로그 전송, 재전송 덮어쓰기, 삭제 요청, `pull_labels.py`, 개발 모드 분리)를 실제 서버 코드에 붙여 본다. 운영 서버에는 접속하지 않는다.

ffmpeg 를 찾을 수 없으면 ffmpeg 통합 테스트는 자동으로 skip 된다(제품 코드 실행에는 ffmpeg 가 필수지만, 순수 로직 테스트는 ffmpeg 없이도 전부 돈다). ffmpeg 위치를 지정하려면:

```bash
export LUMIA_FFMPEG=/path/to/ffmpeg.exe   # git bash
$env:LUMIA_FFMPEG = "C:\path\to\ffmpeg.exe"   # PowerShell
```

## 실행 방법

> 코드가 바뀌어 아래 내용이 실제와 달라지면 그때그때 이 섹션을 같이 고친다
> ([CLAUDE.md](../CLAUDE.md) 참고).

### 0. 가장 간편한 방법 — `run.bat` 더블클릭

가상환경 활성화 없이 [run.bat](../run.bat) 을 더블클릭(또는 PowerShell 에서 `.\run.bat`)하면
1번(트레이 상주)이 `--open-ui` 로 실행돼 열람 UI 도 바로 브라우저로 열린다.
UI 를 보려면 먼저 `cd frontend && npm install && npm run build` 를 한 번 해둘 것.
프로그램은 트레이 아이콘(작업표시줄 우측 `^` 숨겨진 아이콘 안일 수 있음)으로 상주하며,
터미널 창은 로그용이라 닫으면 프로그램도 종료된다.

접속 주소는 `http://lumia-briefingroom.localhost` 다(주소창에 직접 쳐도 된다). 서버는 80번 포트를 먼저 잡아 포트가 안 붙고, 80번이 쓰이고 있으면 `ui.port`(기본 8765) → 그 뒤 +20 순으로 잡아 `http://lumia-briefingroom.localhost:8765` 처럼 포트가 붙는다. 서버는 `127.0.0.1` 에만 바인드한다. 주소가 바뀌었으므로 예전 `127.0.0.1:8765` 에 저장됐던 볼륨·선택 탭 등은 새 주소에서 한 번 비어 있다. `cli.serve` 독립 실행은 기존 `--host/--port` 그대로다.

**첫 실행 화면**: 설정의 `consent.version` 이 현재 화면 버전보다 낮으면(처음 실행하는 PC, 개발 PC 도 한 번) 앱이 시작할 때 `ui.startMinimized` 와 무관하게 UI 를 열고 첫 실행 화면을 보여 준다 — 스팀 녹화 폴더(자동 탐지 결과, 못 찾으면 직접 선택), 클립 저장 폴더, 가장 최근 녹화의 해상도 지원 여부, 선택 기능 세 가지(업데이트 알림·라벨 전송·오류 로그 전송 — 모두 꺼진 채로 시작, 옵션 → 정보·진단에서 변경). 배포본에서는 라벨 전송을 켜야 클립의 라벨링(교전 / 그 외, 메모) 기능이 보인다(개발 모드는 항상 보임). "시작하기" 를 눌러야 저장되고, 창을 그냥 닫으면 다음 실행 때 다시 뜬다. 녹화 폴더를 아직 못 찾은 상태에서도 앱은 10초마다 감시 시작을 다시 시도하므로 화면에서 폴더를 고르면 재시작 없이 시작된다.

**스팀 녹화 폴더**: 자동 탐지는 스팀 설정의 `BackgroundRecordPath`(폴더를 바꿨을 때만 저장되는 값)를 먼저 보고, 없으면 기본 위치 `스팀 설치 폴더\userdata\<숫자>\gamerecordings\video` 를 본다(녹화가 든 계정·가장 최근 세션 우선). 직접 고른 폴더가 `gamerecordings` 처럼 한 단계 위여도 `video` 로 바로잡는다. **옵션 → 일반 → "스팀 녹화 폴더"** 에서 언제든 바꾸거나 자동 탐지로 되돌릴 수 있고, 바꾸면 돌던 감시가 새 폴더로 **다시 시작된다**(감시는 시작 때 폴더를 한 번만 읽기 때문). 감시를 꺼 둔 상태라면 켜지 않는다.

**과거 녹화 전체 분석**: 헤더의 **"과거 녹화 분석"** 버튼. 게임 로그(`Player.log`)에는 최근 게임 실행 2번 분량의 경기만 남아서, 앱을 늦게 설치했거나 한동안 안 켰다면 스팀에 녹화가 남아 있어도 그 경기는 자동으로 클립이 안 만들어진다. 이 버튼은 스팀 녹화 세션을 **화면으로 직접 훑어**(인게임 HUD·일차로 경기를 나눈다) 로그에 없는 경기를 찾아 클립으로 만든다. 만드는 부분(검출·컷·썸네일·결과 화면 OCR)은 평소 경로와 같다. 확인 창에 대상(녹화 개수·길이·용량)과 **예상 시간**이 나오고(약 25배속으로 어림한 값), 시간이 걸리고 컴퓨터가 느려질 수 있다는 안내가 뜬다. **게임을 끄고 실행하는 것을 권한다.**

- **취소·이어하기**: 언제든 취소할 수 있다(프레임 사이에서 바로 멈춘다). 이미 끝낸 경기의 클립은 그대로 남고, 다시 시작하면 훑은 곳부터 이어서 한다(판독은 `%LOCALAPPDATA%\Temp\LumiaBriefingRoom\backfill` 에 캐시). 경기 하나는 임시 폴더에 다 만든 뒤 클립 폴더로 옮기므로 도중에 멈추거나 컴퓨터가 꺼져도 깨진 클립이 목록에 뜨지 않는다(json 을 마지막에 옮긴다).
- **건너뛰는 경기**: 이미 클립이 있거나 게임 기록·휴지통에 있는 경기, `Player.log` 로 아는 경기(아직 처리 전인 것도 — 곧 감시가 만든다), 앞부분이 스팀 링버퍼에 지워진 경기, 아직 진행 중인 경기. 끝난 뒤 요약에 개수가 나온다.
- **이터널 리턴 세션만**(폴더 이름의 앱 ID 1049590) 오래된 것부터 본다. 창을 닫아도 분석은 계속되고 헤더 버튼에 진행률이 표시된다.
- 명령줄은 없다(앱 안에서만).

**자동 시작**: 옵션 → 일반 → "윈도우에 로그인할 때 자동으로 실행" 으로 켜고 끈다(`ui.autoStart`, 기본 켬). 끄면 레지스트리 값(`HKCU\...\Run\LumiaBriefingRoom`)이 **그 자리에서** 지워진다 — 설정 파일만 고치면 다음 로그인에 한 번 더 뜬다. 앱이 시작할 때도 설정대로 다시 맞춘다.

**중복 실행 방지**: 앱이 이미 떠 있는데 또 실행하면(바로가기, 자동 시작과 겹침) 새로 띄우지 않고 떠 있는 앱의 UI 를 연 뒤 종료한다. 트레이 메뉴에 "로그 폴더 열기" 가 있고, 옵션 → "정보·진단" 에서 진단 정보 zip(로그·버전·해상도·설정, 닉네임·사용자 이름 제거)을 받는다.

**HEVC 재생 폴백**: 브라우저가 스팀 녹화(HEVC)를 재생하지 못하면(검게 나오거나 오류) 플레이어가 그 클립의 H.264 재생용 사본을 `<클립 폴더>/.proxy/` 에 처음 한 번 만들고(진행률 표시, 90초 클립에 약 30초) 그걸 재생한다. 원본은 그대로다. 클립을 완전 삭제하거나 자르면 사본도 정리·무효화된다. ffmpeg 는 `LUMIA_FFMPEG` 환경변수 → 번들(`vendor/ffmpeg/ffmpeg.exe`) → PATH 순으로 찾는다. 이 PC 처럼 HEVC 가 재생되면 폴백은 일어나지 않는다(강제로 보려면 브라우저 콘솔에서 `sessionStorage['lumia.playback']='proxy'` 후 새로고침).

**개발/배포 모드**: 소스로 실행하면 개발 모드, 빌드본이면 배포 모드다(`app.mode` 설정으로 `dev`/`release` 강제 가능). 배포 모드에서는 클립 ID·교전 점수 칩·점수 슬라이더를 숨긴다(라벨링 UI 는 라벨 전송을 켠 경우에만 보인다).

**설치판과 개발판을 동시에 실행** (서버 전송이 실제로 되는지 실시간으로 볼 때): [run-parallel.bat](../run-parallel.bat) 은 환경변수 `LUMIA_PROFILE=dev` 를 주고 앱을 띄운다. 프로필이 있으면 설정(`%APPDATA%\LumiaBriefingRoom-dev\config.json`)·로그·전송 기록·outbox·업데이트 상태(`%LOCALAPPDATA%\LumiaBriefingRoom-dev`)·클립 기본 폴더(`Videos\LumiaBriefingRoom-dev`)·중복 실행 뮤텍스·트레이 이름이 기본과 따로라서 둘이 서로를 막거나 덮어쓰지 않고, 자동 시작 레지스트리는 건드리지 않는다. 처음 한 번은 첫 실행 화면이 뜨는 새 앱처럼 시작한다(기존 `run.bat` 의 설정·클립은 기본 폴더에 그대로 있고 설치판이 그걸 이어 쓴다). 웹 주소는 80번 포트를 먼저 잡은 쪽이 쓰고 다른 쪽은 8765 부터 잡는다. 이름은 영문·숫자·`_`·`-` 20자까지만 받고, 다른 이름을 쓰려면 `set LUMIA_PROFILE=이름` 뒤 `dev.bat` 등을 실행한다. 두 앱이 **같은 Player.log 를 보므로 같은 게임을 각자 클립으로 만든다**(폴더는 달라서 충돌하지 않는다) — 개발판에서 감시를 끄려면 트레이 메뉴의 "감시 중"을 끈다.

### 0-1. 개발용 — 코드 저장 시 자동 재시작 (`dev.bat`)

[dev.bat](../dev.bat) (= `python tools/dev_run.py [cli.app 옵션]`)은 `src/` 아래 `.py` 를 저장할 때마다 앱(트레이 + 서버)을 껐다가 다시 띄운다.
브라우저는 첫 기동에만 열리고, 재시작 뒤에는 열려 있는 탭을 새로고침하면 된다(포트가 고정이라 origin 이 그대로다).
트레이 "종료"로 앱을 끄면 `dev.bat` 도 끝나고, 앱이 오류로 죽으면 다음 저장까지 기다린다.
`watchfiles` 가 필요하다(`pip install -e ".[dev]"`). `frontend/src` 를 저장하면 `npm run build` 도 자동으로 돌려 `frontend/dist` 를 갱신한다(서버 재시작 없음) — 빌드가 끝났다는 메시지가 나오면 브라우저를 새로고침한다. 평소 실사용은 그대로 `run.bat`.

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
`--start-server` 는 브라우저는 열지 않고 열람 서버만 먼저 띄운다 — 앱 안 업데이트 뒤 설치기가 앱을 다시 실행할 때 쓰며(`installer/lumia.iss` 의 `/RELAUNCH=1` 항목), 열려 있던 탭이 자동으로 새로고침돼 되살아나게 한다.

**업데이트(D9)**: 트레이가 뜨면 `update.check` 가 켜진 경우에만 업데이트 확인 스레드가 시작 후·하루 1회 GitHub Releases 를 조회해 새 버전을 트레이 알림과 UI 배너로 알린다(꺼져 있으면 네트워크 0회). 꺼져 있어도 UI 옵션 → 정보·진단의 "업데이트 확인"·"업데이트"로 수동 확인·설치한다. 설치기 실행은 exe 로 빌드한 앱에서만 되고(개발 모드는 거부), 테스트는 `pytest tests/test_updater.py tests/test_update_routes.py`(로컬 HTTP 서버가 GitHub 를 흉내 내므로 인터넷 불필요). 상태 파일은 `%LOCALAPPDATA%\LumiaBriefingRoom\update_state.json`, 받은 설치기는 같은 폴더의 `updates\`.

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

**보기 모드**: 필터 바 왼쪽의 `카드 | 일자 타임라인` 토글. 타임라인은 게임 행을 펼쳤을 때 1일차 낮·밤, 2일차 낮·밤… 칸을 가로로 늘어놓고 칸마다 그 시간대 교전 클립을 보여 준다(무료 부활/크레딧 구간 경계 표시, 교전 없는 칸도 표시). 선택은 탭별로 브라우저에 기억된다. 프론트만 바꿨으니 `cd frontend && npm run build`.

**영상 자르기**: 플레이어 하단 "✂ 자르기" → **시작 위치는 자르기를 켠 순간의 재생 위치**로 잡히고(끝 근처면 처음부터), 두 손잡이(또는 "현재 위치를 시작/끝으로")로 남길 구간을 고르고 "▶ 구간 미리보기" 로 확인한 뒤 "구간만 남기고 나머지 삭제" 를 누르면 그 클립 파일이 잘린 것으로 **교체되고 나머지는 삭제된다(되돌릴 수 없다, 확인창이 뜬다)**. `ffmpeg -c copy` 라 재인코딩이 없어 636MB 클립도 1초 남짓 걸리고 화질 손실이 없다. 최소 1초. **"+ 구간 추가" 로 겹치지 않는 구간을 여러 개 고르면 구간마다 별도 클립(`<원본ID>-p1`, `-p2`…)으로 나뉘고 원본은 휴지통으로 가서(유예기간 안에 복구 가능) 확인창이 그렇게 안내한다.** 라벨은 조각에 복사하지 않는다. 잘린 클립은 메타데이터에 `trimmed`/`originalDurationSec` 가 남고 썸네일이 다시 만들어진다. 시작 앞 키프레임까지(최대 3초)는 화면에 안 보이는 채 파일에 남는다.

**게임 다시 분석**: 게임 행의 "다시 분석" 버튼이 그 게임을 스팀 원본 녹화에서 처음부터 다시 분석해 클립을 새로 만든다(검출 규칙이 고쳐졌을 때나 결과가 이상할 때). 기존 클립은 **휴지통으로 이동**되고(클립 이름 수정 등 편집 내용은 새 클립에 이어지지 않는다), 분석이 실패하면 자동으로 되돌린다. **교전/사냥 라벨은 시간이 겹치는 새 클립으로 자동 이관**된다(`labelSource=migrated`; 겹치는 옛 클립 중 하나라도 교전이면 교전, 교전·사냥이 섞이면 교전으로 옮기고 `labelConflict` 로 확인 표시, 사용자가 직접 찍은 옛 라벨이 있으면 그것만 따르고, 옮겨 온 교전 라벨을 훨씬 큰 옛 통짜 클립에서 검출 신호(점수 0)가 없는 짧은 조각이 물려받지는 않고(라벨 없음으로 남는다), 이관이 실패해도 새 클립은 라벨 없이 유지). 옛 클립 폴더끼리 옮기는 수동 도구는 `python tools/migrate_labels.py <옛> <새>`. 원본이 링버퍼에서 이미 지워졌으면 이유를 알려 주고 아무것도 바꾸지 않는다(스팀은 새 녹화가 쌓이면 옛 세그먼트를 지우므로 가능한 한 빨리 해야 한다). 분석은 백그라운드로 돌고(경기 길이에 따라 2~6분) 끝나면 목록이 자동 갱신된다. 다음부터 클립 메타데이터에 `matchEndUtc` 가 남아 로그 없이도 가능하다.

**라벨 보관소**: 영상을 완전히 지워도(휴지통 비우기·완전 삭제·보관 기간이 지난 자동 삭제·즉시 삭제 모드) **교전/사냥 라벨이 붙은 클립의 근거·라벨은 `clips/.labels/<클립ID>.json` 에 남는다**(영상·썸네일·결과 이미지 경로는 빼고 수 KB). 라벨이 없는 클립은 남기지 않는다. `tools/eval_pvp.py` 가 보관소도 같이 읽어(같은 ID 의 지금 클립이 있으면 그쪽이 우선) 용량 때문에 영상을 정리해도 라벨링이 쌓인다.

**게임 단위 삭제**: 게임 행 오른쪽 "게임 삭제" 로 그 게임의 클립을 한꺼번에 휴지통으로 보낸다(휴지통 탭에서는 "게임 복구"/"게임 완전 삭제"). 접힌 게임 행에는 클립 수와 **총 용량**이 같이 표시된다. 휴지통에서 게임의 마지막 클립을 완전 삭제하면 결과표 이미지도 함께 지워진다.

**자동 정리**: 헤더 "⚙ 옵션" → "자동 정리" 탭에서 켠다(기본 꺼짐). 앱(트레이)이 1시간마다 설정 파일을 다시 읽어, 경기한 지 N일 지난 클립 / 클립 N개 초과 / 총 N GB 초과분을 오래된 것부터 휴지통으로(또는 즉시 삭제) 옮기고, 휴지통에서 N일(기본 30)이 지난 것을 영구 삭제한다. 고정한 클립과 선택한 태그(기본 사망)는 보호된다. "저장하고 정리될 항목 확인" 으로 미리보고 "지금 정리 실행" 으로 바로 돌릴 수 있다. 꺼져 있으면 클립도 휴지통도 영원히 남는다.

**클립 저장 폴더 바꾸기**: 옵션 → 일반 → "내 녹화 클립 저장 폴더"(다시보기는 옵션 → 다시보기)에서 "바꾸기" 로 새 폴더를 고르면 "기존 클립도 새 폴더로 옮길까요?" 를 묻는다. "예" 는 클립·썸네일·휴지통·프록시·게임 기록·라벨 보관함을 새 폴더로 옮긴 뒤 폴더를 바꾸고(`POST /api/clips-dir/move` 가 백그라운드로 시작하고 `GET /api/clips-dir/move` 가 옮긴 바이트/전체 바이트를 알려줘 화면에 진행률(%)과 막대가 뜬다. 파일 하나를 옮길 때마다 갱신된다), "아니오" 는 폴더만 바꾼다 — 이때 기존 클립은 이전 폴더에 남고 목록에서는 안 보이며, 이전 폴더로 되돌리면 다시 보인다. 새 폴더에 같은 이름의 파일이 있거나 이전 폴더의 안팎이면 아무것도 옮기지 않고 거부한다. 클립 폴더가 아닌 파일은 건드리지 않는다. 썸네일·결과표 이미지 경로는 클립 폴더 기준 상대경로(`.thumbs/…`)로 저장되므로 폴더를 직접 통째로 옮겨도 그대로 인식된다(예전에 절대경로로 저장된 클립도 그 폴더의 `.thumbs` 에서 파일 이름으로 찾는다). 프론트를 고쳤으면 `cd frontend && npm run build`.

**영상 저장(내보내기)**: 카드/플레이어의 "저장" 버튼 → "폴더 선택…" 으로 윈도우 탐색기 창을 띄워 폴더를 골라(새 폴더 만들기도 그 창에서) 파일 이름과 함께 복사한다. 같은 이름이 있으면 `(2)` 를 붙여 덮어쓰지 않는다. 마지막에 저장한 폴더가 `paths.exportDefault` 로 기억돼 다음 저장 창의 시작 위치가 된다. 헤더의 "⚙ 옵션" 에서 이 기본 폴더를 직접 바꿀 수 있다. 실행 방법은 그대로다(프론트를 고쳤으면 `npm run build`).

**게임 결과(순위·랭크 여부)**: 경기가 끝날 때 나오는 결과 화면(`4/7 실험 종료`)을 OCR 로 읽어 클립 메타데이터의 `matchResult`(`matchType` rank/normal, `placement`, `total`, `outcome`, `nickname`)에 넣고, 게임 행에 `#4 랭크 … 13 / 3 / 6` 으로 표시한다. 원본 녹화가 남아 있는 새 경기부터 채워진다. 이미 저장된 클립은 영상에 결과 화면이 없어서, 원본이 아직 남은 경기만 `python tools/backfill_result.py [clips_dir] [--recording-root DIR] [--force]` 로 채운다(게임별로 마지막 클립 뒤에서 원본을 훑어 첫 결과 화면을 읽는다. 링버퍼가 지운 경기는 건너뛴다). 결과 화면은 1280px JPEG 로 `clips/.thumbs/<경기시작>_result.jpg` 에 저장돼 게임 섹션의 첫 칸에 썸네일처럼 보이고(클릭하면 크게), 이미 저장된 경기는 `backfill_result.py` 가 같이 만든다. 내 캐릭터는 결과 화면 오른쪽 세로 영문 이름을 읽어 `data/characters.json`(영문→한글, 없는 이름은 여기에 추가)으로 한글 이름을 찾는다. 닉네임은 첫 결과 화면에서 자동으로 읽어 설정에 저장하고(비어 있을 때만), 헤더 "⚙ 옵션" 에서 직접 고칠 수 있다.

**기준: 클립에 사람과의 교전이 *포함*되어 있으면 "교전".** 사냥하다 교전하거나, 교전 뒤에 야생동물·오브젝트(알파/오메가/위클라인)를 잡는 클립도 교전이다.
야생동물·보스만 상대했으면 "사냥", 판단이 안 되면 안 찍고 넘어간다. 자세한 표는 [plan-pvp.md §4-0](plan-pvp.md).

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

### 10. 배포본 빌드 (`build.bat`)

친구 PC(파이썬·node·ffmpeg 없음)에서 돌아가는 배포본을 만든다. 순서가 중요해서 한 스크립트로 묶었다 —
`npm run build` → PyInstaller `--onedir --windowed` → 번들 ffmpeg 복사 → 리소스 검증 → zip.

```bash
python tools/fetch_ffmpeg.py      # 최초 1회: LGPL ffmpeg 를 vendor/ffmpeg 로 (약 150MB, git 에 안 들어간다)
.\build.bat                       # = python tools/build_release.py
```

- 결과: `dist\LumiaBriefingRoom\`(약 400MB)와 `dist\LumiaBriefingRoom-<버전>-win64.zip`(약 180MB).
- 옵션: `--skip-frontend`(프론트를 다시 안 빌드), `--skip-zip`, `--skip-checks`.
- **ffmpeg 는 반드시 LGPL 빌드**만 동봉한다. `fetch_ffmpeg.py` 가 받은 빌드의 `configuration` 에
  `--enable-gpl`/`--enable-nonfree` 가 없는지, H.264 프록시 인코더가 있는지 실행해서 확인한 뒤에만 자리를 잡는다.
  개발 PC 에 winget 으로 깔린 ffmpeg 는 GPL 풀 빌드라 그대로 쓰면 안 된다.
- 버전은 `lumia_briefing_room.__version__` 하나에서 나온다(폴더 이름·zip 이름·`GET /api/app-info`).
- `vendor/ffmpeg` 가 생기면 **개발 환경의 `discover_ffmpeg()` 도 그 LGPL 빌드를 먼저 고른다.**
  테스트만은 `tests/conftest.py` 가 PATH 의 전체 빌드를 쓰도록 되돌린다(합성 녹화 픽스처에 libx264 가 필요하다).

**빌드본 점검**: 빌드가 끝나면 아래로 번들이 제대로 묶였는지 확인한다(본보기 npz·characters.json·프론트 dist·
ffmpeg/ffprobe·H.264 인코더·OCR 엔진 로드). 콘솔이 없는 빌드라 보고서는
`%LOCALAPPDATA%\LumiaBriefingRoom\logs\selftest.txt` 에 남고 자동으로 열린다(`--quiet` 면 안 연다).

```bash
dist\LumiaBriefingRoom\LumiaBriefingRoom.exe --selftest
```

### 11. 설치기 만들기 (친구·공개 배포용)

```bash
.\build.bat                              # 먼저 dist\LumiaBriefingRoom 을 만든다
python tools/build_installer.py          # → dist\LumiaBriefingRoom-<버전>-setup.exe (약 134MB)
```

- [Inno Setup 6](https://jrsoftware.org/isinfo.php) 이 필요하다(`winget install JRSoftware.InnoSetup`).
  `installer/lumia.iss` 를 직접 컴파일하지 말고 이 스크립트로 만든다 — 버전·경로를 `/D` 정의로 넘긴다.
- **관리자 권한 없이** `%LOCALAPPDATA%\Programs\LumiaBriefingRoom` 에 설치된다(실측 확인).
- 설치기는 자동 시작 레지스트리 값을 쓰지 않는다. 앱이 `ui.autoStart` 설정에 따라 스스로 등록한다.
  **제거할 때는 그 값을 지운다**(안 지우면 로그인마다 없는 exe 를 실행하려 한다).
- 제거해도 **클립 폴더는 건드리지 않는다.** 설정·로그(`%LOCALAPPDATA%\LumiaBriefingRoom`)는 지울지 물어본다
  (무인 제거 `/VERYSILENT` 에서는 묻지 않고 남긴다).
- 실행 중이면 설치기가 닫아 달라고 알린다(`AppMutex` 가 앱의 중복 실행 방지 뮤텍스와 같은 이름이다).
- `THIRD_PARTY_NOTICES.md` 가 설치 폴더에 같이 들어간다. ffmpeg LGPL 고지와 소스 링크가 여기 있다.
- **코드 서명을 하지 않으므로 SmartScreen 경고가 뜬다.** 사용자에게 "추가 정보 → 실행" 을 안내한다
  ([docs/friend-guide.md](friend-guide.md)).

### 12. 라벨·오류 로그 전송 (동의 기반, D10)

전송은 **사용자가 켠 항목만** 한다. 첫 실행 화면이나 옵션 "정보·진단" 탭의 "선택 기능"에서 라벨 전송·오류 로그 전송을 켜고 끈다(기본은 둘 다 꺼짐, 꺼져 있으면 네트워크를 전혀 쓰지 않는다). 보내는 항목·보관 기간·삭제 방법은 [개인정보 처리 안내](privacy.md)(앱 안에서는 동의 항목 아래 링크)에 있다.

- **보내는 때**: 앱이 떠 있는 동안 종류별로 하루 한 번 묶어서 보낸다. 서버가 안 받으면 15분부터 두 배씩(최대 6시간) 늦춰 다시 시도하고, 앱은 멈추지 않는다.
- **라벨**: 스팀 녹화·다시보기 클립의 교전/그 외 라벨과 근거 수치, 해상도·게임 모드, 결과 화면의 최종 킬·어시스트, 내 캐릭터, 라벨 메모(`labelNote`). 로컬 `pvp`/`pve` 는 `combat`/`other` 로 바뀌어 나간다. 라벨이나 메모를 고치면 같은 클립 키로 다시 보내 서버가 덮어쓴다. 제목·경로·닉네임·팀원·시각 원문은 나가지 않는다.
- **오류 로그**: ERROR 이상 기록이 `%LOCALAPPDATA%\LumiaBriefingRoom\outbox\errors.jsonl` 에 쌓이고(20MB 상한), 보낼 때 닉네임·사용자 이름·경로 속 폴더 이름을 지운다. 환경 정보(OS·CPU·GPU·메모리·화면 배율·해상도·코덱·스팀 버퍼 길이·HEVC 재생 가능 여부·재생용 영상 인코더와 생성 시간·게임 분석 시간 비율·하드웨어 디코딩 사용 여부·판독 실패 통계)가 같이 간다. 재생·분석 값은 앱이 돌면서 `%LOCALAPPDATA%\LumiaBriefingRoom\runtime_stats.json` 에 스스로 재 둔 것이다.
- **진단 정보 보내기**(D14): 옵션 "정보·진단" 탭 맨 아래. 개인정보를 지운 로그 발췌(최근 오류 기록 100건, 정기 전송과 별개인 로컬 링 `%LOCALAPPDATA%\LumiaBriefingRoom\outbox\errors_recent.jsonl` 1MB)·환경 정보·판독 실패 통계를 미리보기로 보여 주고, 확인하면 **한 번만** 서버로 보내 접수 번호를 알려 준다(`telemetry.sendLogs` 와 무관, 자동 전송을 켜지 않음). 짧은 표시용 ID(`LUMIA-XXXX-XXXX`)를 복사할 수 있고 재설치하면 새로 만들어진다. 서버로 안 보내지면 같은 탭의 "진단 정보 zip 받기"로 파일로 저장해 보낸다(zip 은 대안으로 유지, `info.json` 에 표시용 ID 포함).
- **미리보기·삭제**: 옵션 "정보·진단" 탭의 "보낼 내용 미리보기"(전송이 꺼져 있어도 볼 수 있고 네트워크를 쓰지 않는다), "보낸 데이터 삭제 요청"(서버의 내 데이터를 지우고 전송을 끈다).
- **개발 모드**(소스 실행)는 기본적으로 서버에 보내지 않는다. 시험할 때만 설정 `telemetry.allowDevSend` 를 켜면 `mode=dev` 로 보내 서버가 운영 데이터와 다른 곳에 둔다. 서버 주소·토큰은 설정(`telemetry.serverUrl`·`apiToken`)이나 환경변수 `LUMIA_RECEIVER_URL`·`LUMIA_RECEIVER_TOKEN` 으로 줄 수 있다.
- **서버 주소와 토큰은 git 에 없다(코드에 기본 주소도 없다).** 저장소 루트에 `.env`(gitignore) 를 만들어 `LUMIA_RECEIVER_URL=https://…` 와 `LUMIA_RECEIVER_TOKEN=…`(값은 infra 저장소 `terraform.tfvars` 의 `receiver_api_token`)를 적거나 같은 이름의 환경변수를 주고 `build.bat` 을 돌리면 번들에 들어간다(`data/telemetry_endpoint.json`, 빌드 뒤 자동 삭제, gitignore). 이미 있는 환경변수가 `.env` 보다 우선한다. 둘 중 하나라도 없이 빌드하면 "서버 전송이 꺼진 빌드"라고 경고하고 전송 기능은 동작하지 않는다. `--selftest` 가 httpx·인증서·개인정보 안내 파일·토큰 유무를 점검한다.
- **서버에 쌓인 라벨 가져오기** (분류기 튜닝용): 서버 관리자 토큰을 환경변수로 주고 실행한다.

```bash
set LUMIA_ADMIN_TOKEN=...; set LUMIA_RECEIVER_URL=...                    # 값은 infra 저장소 terraform.tfvars 의 admin_token. PowerShell: $env:LUMIA_ADMIN_TOKEN = "..."
python tools/pull_labels.py --out pulled_labels          # → pulled_labels/.labels/<clipKey>.json (pvp/pve 로 되돌림)
python tools/eval_pvp.py pulled_labels                   # 가져온 라벨로 점수 평가
```

  다음 실행부터는 새로 온·고쳐서 다시 온 라벨만 받는다(`--full` 은 처음부터, `--mode dev` 는 개발 모드 데이터).
- **관리자 화면** (개발 모드 전용 "관리자" 탭, 별도 프로그램 없음): `run.bat`/`dev.bat` 으로 소스 실행하면 클립 탭 옆에 "관리자" 탭이 보인다(배포 빌드에는 탭도 API `/api/admin/*` 도 없다 — 서버가 요청마다 개발 모드인지 확인해 404). 저장소 루트 `.env` 의 `LUMIA_ADMIN_TOKEN`·`LUMIA_RECEIVER_URL`(또는 같은 이름의 환경변수)을 앱 프로세스가 읽어 서버의 관리자 읽기 API 를 대신 호출한다(토큰은 브라우저에 넘기지 않는다). 하위 탭: **서버 상태**(모드별 설치·라벨·로그·진단 수와 종류별 "마지막 수신 N분 전", 오늘 받은/거부한 요청, 디스크·차단 IP 수), **진단 번들**(접수 번호·표시용 ID `LUMIA-XXXX-XXXX`·installId 앞부분 검색, 행을 눌러 환경 정보와 로그 발췌 전문), **오류 로그**(같은 오류 묶음 집계 + 최신순 목록, 수준·문구 필터), **라벨**(집계와 `installId`/`clipKey` 검색). "5초마다 자동 새로고침"을 켜면 상태·진단·오류 로그가 실시간으로 갱신된다(라벨은 전량을 받아 오므로 수동). release/dev 선택이 서버의 `mode` 다. `.env` 는 요청 때마다 읽으므로 고친 뒤 앱을 다시 띄울 필요는 없지만 앱 코드가 바뀌면 다시 띄운다. 값 뒤 ` # 설명` 은 주석으로 잘라내고, 서버 주소에 `https://` 가 없으면 붙인다(앱의 라벨·오류 로그 전송도 같다). 토큰에 한글·공백이 섞이면 500 이 아니라 안내 문구가 든 503 이다. **서버(`P:\infra`)에 읽기 API 가 배포돼 있어야 한다**(라벨 외 탭은 서버가 옛 버전이면 "아직 서버에 배포되지 않았습니다" 오류).

### 13. 릴리스 (GitHub Actions, D13)

태그를 푸시하면 `.github/workflows/release.yml` 이 설치기를 만들어 GitHub Release 로 올린다. 사람이 하는 일은 아래뿐이다.

```bash
# 1) src/lumia_briefing_room/__init__.py 의 __version__ 을 올리고, CHANGELOG.md 에 그 버전 절을 쓴다 → 커밋·푸시
# 2) 태그를 달아 푸시한다 (태그 = v + __version__)
git tag v0.1.4
git push origin v0.1.4
```

- 태그와 `__version__` 이 다르거나 CHANGELOG 에 그 버전 절이 없으면 **워크플로 첫 단계에서 실패**한다. 로컬 확인: `python tools/release_tools.py check-tag v0.1.4`.
- 태그 없이 파이프라인만 시험하려면 Actions 탭 → release → **Run workflow**. 빌드·설치기·SHA-256 까지만 하고 Release 는 만들지 않으며, 설치기는 아티팩트(3일)로 남는다.
- 결과 Release: 설치기(`LumiaBriefingRoom-<버전>-setup.exe`), `<설치기>.sha256`, 본문(CHANGELOG 절 + SHA-256 + VirusTotal 링크). 초안으로 만들었다가 마지막에 공개한다. VirusTotal 이 실패하면 링크만 빠진 채 공개되므로 Actions 로그를 확인한다.
- 패치노트는 루트 `CHANGELOG.md` 하나가 원본이다. 앱 옵션의 "패치노트 보기"(`GET /api/changelog`, 빌드에 `CHANGELOG.md` 동봉)와 Release 본문이 모두 이 파일에서 나오므로 릴리스 전에 그 버전 절을 쓴다.
- 필요한 Secrets 는 README "릴리스 만들기" 참고. 로컬에서 흉내: `python tools/release_tools.py prepare v0.1.4` (설치기가 `dist/` 에 있어야 한다).
- 러너 실측: Inno Setup 6.7.1 이 이미 설치돼 있고 전체 약 4분 반이다([plan-deploy §7-19](plan-deploy.md)).

### 9. 브라우저 디버깅 (개발용)

- **클라이언트 오류 로그**: 프론트가 `window.onerror` / `unhandledrejection` / `console.error` 를 `POST /api/client-log` 로 보내고, 서버가 `[client]` 접두로 로그 파일에 남긴다. 로그 파일은 `%LOCALAPPDATA%\LumiaBriefingRoom\logs\app.log` (서버 로그와 같은 파일, 2MB 회전). Claude Code 에 "브라우저 오류 봐줘" 라고 하면 이 파일을 읽는다. 프론트를 고쳤으면 `npm run build`.
- **브라우저 자동 조작(Playwright MCP)**: 저장소 루트 `.mcp.json` 에 시스템 Chrome(`--browser chrome`)으로 붙는 설정이 들어 있다. Claude Code 를 이 폴더에서 다시 열면 프로젝트 MCP 승인을 물어본다. 대상은 `python -m lumia_briefing_room.cli.serve --port 8000` 로 띄운 `http://127.0.0.1:8000/`. (Chrome 재생·콘솔 읽기 실측은 아직 안 했다 — [plan-ui.md §6](plan-ui.md))

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
| `tools/pull_labels.py` | 서버에 쌓인 라벨을 로컬로 받아 `eval_pvp.py` 가 읽는 `.labels/` 형태로 저장 (관리자 토큰은 환경변수 `LUMIA_ADMIN_TOKEN`, 증분 수집, `--full`·`--mode dev`) |
| `tools/release_tools.py` | 릴리스 파이프라인 보조(태그·버전·패치노트 확인, SHA-256 파일, 릴리스 본문, VirusTotal 업로드). 워크플로가 부른다 — 아래 "13" |
| `tools/sync_contract.py` | 서버와 공유하는 전송 계약을 infra 저장소(infra 저장소의 `contract/`)에서 `tests/contract` 로 복사 (`--check` 는 차이만 확인, `--source` 로 경로 지정) |

가상환경을 활성화한 상태에서 실행할 것.
