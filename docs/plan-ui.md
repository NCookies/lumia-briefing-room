# 열람 UI 구현 계획 (SPEC 3단계)

> 대상: [SPEC.md §6 3단계](SPEC.md), [§3 클립 목록/타임라인](SPEC.md), [§4 UI 스택](SPEC.md).
> 1단계(검출기)는 [plan.md](plan.md), 2단계(파이프라인 자동화)는 [plan-pipeline.md](plan-pipeline.md) 에서 완료했다.
> 이 문서는 그 위에 얹는 열람/관리 화면이다.

## 0. 진행 상태 (세션이 끊겨도 여기부터 이어간다)

- [x] 계획 수립 (이 문서)
- [x] `api/clips.py` — 클립 스캔 (scan_clips/find_clip/to_summary_dict)
- [x] `api/filters.py` — 저장된 메타데이터 위에서 도는 UI 필터
- [x] FastAPI 라우트 (`api/app.py`) — 클립 목록/조회/수정/삭제/복구/영구삭제,
  Range 지원 비디오 스트리밍, 썸네일, 설정 조회/저장. TestClient 로 전부 테스트
  (실제 서버 안 띄우고 ASGI 로 직접 호출 — 빠르고 결정적)

**✅ 진짜 uvicorn 서버 + 진짜 클립으로도 확인했다.** `process_match()` 로 만든
실제 클립(78MB HEVC mp4)을 서빙하는 실제 서버에 curl 로 요청했다:
`GET /api/clips` 가 실제 메타데이터를 정확히 반환, `Range: bytes=0-1023` 요청에
`206 Partial Content` + `Content-Range: bytes 0-1023/78557811` 정상 응답,
썸네일도 28KB 그대로 서빙됐다. TestClient(ASGI 직접호출)와 실제 TCP 서버
양쪽에서 Range 구현이 큰 파일에도 정확히 동작함을 확인했다.
- [x] React 프론트엔드 스캐폴딩 (Vite + TS + Tailwind, `frontend/`)
- [x] 클립 목록 뷰 (카드 그리드, `ClipCard.tsx`) — 썸네일/제목(더블클릭 수정)/태그뱃지/
  재생시간/`sourceIncomplete` 뱃지
- [ ] 매치 타임라인 뷰 (v1.1 로 미룸)
- [ ] **판독값 수동 보정** (설계만, 미구현 — [SPEC §2.13 수동 보정](SPEC.md)) — 게임 행에서 내 캐릭터·팀원 캐릭터·순위를 직접 고치고, 고친 값은 `manual` 로 잠가 자동 판독·backfill·제목 재생성이 덮어쓰지 않게 한다
- [x] 필터 UI (`FilterBar.tsx`) — 태그/낮밤/게임모드/고정만/클립·휴지통 탭
- [x] 정리 UI (삭제/복구/고정/이름변경) — 내보내기는 v1.1 로 미룸
- [x] **교전 라벨링 UI** (SPEC 4단계, [plan-pvp.md §2.6](plan-pvp.md)) — 카드 라벨 버튼, 모달 키보드 라벨링(1/2/0, 자동 다음), 교전 가능성 칩·정렬·점수 슬라이더·라벨 필터
- [x] **게임 섹션 첫 칸에 결과표 이미지** — 결과 화면 프레임을 경기당 1장(1280px JPEG)으로 저장(`matchResult.imagePath`), `GET /api/clips/{id}/result-image`, `ResultCard`(썸네일 + 순위 배지, 클릭하면 `ResultViewer` 로 확대)
- [x] **게임 결과 배지에 캐릭터 이름** — `마커스 · 랭크 · 1위 / 8팀 · 최종 생존`
- [x] **게임 결과 표시 · 닉네임 설정** — 게임 섹션 제목에 `랭크 · 4위 / 7팀 · 실험 종료`(1위는 금색), 옵션 모달에서 닉네임 수정. 판독은 SPEC §2.13
- [x] **게임 목록을 dak.gg 식 접이식 행으로** — `GameSection`: 접힌 한 줄(순위·모드·시작 시각/경과·캐릭터·TK/K/A·클립 수, 1위는 초록 막대)과 ▾ 펼침(결과표 썸네일 + 클립 카드). 모두 펼치기/접기. 제목에서 팀 수·`실험 종료` 제거(탈출만 표시). 결과 화면의 `TK K D A` 스탯도 열 위치로 읽어 `matchResult` 에 저장
- [x] **간단한 영상 자르기** — 플레이어 `TrimPanel`(이중 손잡이·현재 위치로 지정·구간 미리보기·삭제량 표시), `POST /api/clips/{id}/trim`(`pipeline/trim.py`, `-c copy`). 원본을 잘린 것으로 교체(복구 불가, 확인창). 실측: 636MB HEVC 클립을 1초에 29.5초로, 시작 프레임 픽셀 차이 0.0. 영상/썸네일 URL 에 `?v=길이` 를 붙여 캐시를 깬다
- [x] **게임 단위 삭제·복구·완전 삭제, 게임 행에 클립 총 용량** — API 클립에 `sizeBytes`, 게임 행에 합계(`totalSize`)와 삭제/복구 버튼(확인창). 마지막 클립을 완전 삭제하면 결과표 이미지도 정리
- [x] **게임 '다시 분석' 버튼** — `POST /api/games/reprocess`(백그라운드 작업 1개, `GET /api/games/reprocess/{key}` 진행 상태), `pipeline/reprocess.py`: 원본 존재·종료 시각(`matchEndUtc` 또는 Player.log)을 확인한 뒤 기존 클립을 휴지통으로 옮기고 `process_match` 를 다시 돌리며, 실패하면 새로 만든 파일을 지우고 되돌린다. 화면은 3초마다 상태를 보고 끝나면 목록을 갱신
- [x] **팀원 캐릭터 표시(게임 행), 클립 이름 수정 버튼(카드·플레이어 ✎), 휴지통 비우기 버튼** — `POST /api/trash/empty`(한 번에 삭제, 결과표 이미지 정리), 항상 확인창
- [x] **결과표 뷰어에서 ←/→ 와 좌우 버튼으로 이전/다음 게임의 결과표로 이동** — 화면에 보이는 게임 순서를 따르고 `게임 N · 결과 · i/n` 을 표시
- [x] **버그 수정: 휴지통 썸네일 엑박 · 동시 삭제 후 목록 미갱신** — 썸네일/영상 API 가 휴지통 클립을 못 찾던 것, 게임 완전 삭제(동시 요청)가 서로 부딪혀 500 이 나고 화면이 목록을 다시 안 불러오던 것(서버 락·스캔 예외 처리·삭제 재시도, 화면은 항상 목록 갱신하고 실패는 표시)
- [x] **삭제 확인 창(자체 모달) + "다시 확인하지 않기" + 옵션 `ui.confirmDelete`, 자르기 모드 시작 위치=현재 재생 위치, 자르기 모드에서 하단 버튼이 잘리던 레이아웃 수정**
- [x] **기본 정렬을 최신 순으로, `asc`/`desc` 표기 제거, UI 문구 전수 검수** — 화면에 보이는 모든 문장(확인창·오류·안내·툴팁)과 API 오류 문구를 합니다체로 통일(`~한다`→`~합니다`, `계속할까?`→`계속하시겠습니까?`), `이관`·`옛` 같은 어색한 단어를 `옮겨 온 라벨` 등으로 정리
- [x] **자동 정리 + 옵션 모달 좌측 탭 개편** — 탭: 일반(닉네임) / 영상 저장 / 자동 정리. 자동 정리 화면: 켜기, 한도(경기 후 N일·N개·N GB, 비우면 제한 없음), 지우는 방식(휴지통/즉시)·휴지통 보관 일수, 보호(고정·태그), 미리보기·즉시 실행. 백엔드 `pipeline/cleanup.py` + `POST /api/cleanup`
- [x] **정렬은 게임에만 적용, 게임 안 클립은 항상 오름차순** — desc 는 게임만 최신순, 교전 가능성순은 게임의 최고 `pvpScore` 순(동점은 오래된 게임 먼저)
- [x] **영상 저장 폴더 선택 · 옵션 모달** — 서버 쪽 폴더 탐색/생성/복사 API(`api/export.py`), 저장 대화상자, 마지막 저장 폴더 기억(`paths.exportDefault`), 헤더 ⚙ 옵션에서 기본 폴더 설정
- [x] **게임 단위 목록 · 정렬 asc/desc · 볼륨 유지** — `grouping.ts` 로 `sessionDir+matchStartUtc` 기준 섹션 묶음(기본 오름차순), 플레이어 볼륨/음소거를 localStorage 에 저장. 게임 섹션은 색 테두리+헤더로 구분, 플레이어에 좌우 큰 이동 버튼과 삭제 버튼(삭제 후 다음 영상으로 이동)
- [x] pywebview 셸 배선 (`cli/serve.py::open_ui`) — §4-1 해결, 아래 참고
- [x] 빌드 산출물을 FastAPI 정적 서빙에 연결 (`api/static.py`, `cli/serve.py`)

**✅ 실제 Playwright + 실제 설치된 Edge 로 프론트엔드까지 검증했다.** 실제
`uvicorn`(백엔드) + 실제 `vite`(프론트, `/api` 를 백엔드로 프록시) 를 동시에 띄우고,
`process_match()` 로 만든 실제 클립(78MB HEVC mp4 + 실제 썸네일)을 그리드에서
확인: 썸네일/제목/태그가 정확히 렌더링됨. 재생 모달을 열어 실제 설치된
`msedge.exe` 로 재생한 결과 `videoWidth: 2560, videoHeight: 1440` 로 정상 디코딩되고
실제 게임 화면(인게임 HUD `TK 9 K 2 A 5`)이 그대로 보였다 — **§4-2 확정, 아래 참고**.
고정(pin)→휴지통 이동(trash)→복구(restore) 라운드트립은 실제 API(curl)로 직접
검증: `PATCH pinned:true` → `POST trash`(목록에서 사라지고 `?trashed=true` 로 보임)
→ `POST restore`(`pinned:true` 그대로 유지된 채 기본 목록에 복귀) 정상 동작 확인.
(참고: `trash`/`restore` 응답 바디는 `{id, trashed}` 만 반환하고 전체 메타데이터를
안 돌려준다 — 프론트는 응답을 안 쓰고 재조회하므로 문제 없지만, API 단독으로 확인할
땐 헷갈릴 수 있어 기록해둔다.)

**범위 판단**: SPEC §3 3단계가 요구하는 전체(타임라인 뷰 + 그리드 뷰 + 모든 필터 +
정리 도구 + 재생)를 한 번에 다 만들지 않는다. **백엔드 API를 먼저 완결하고
(TDD로, 이미 검증된 파이프라인처럼), 프론트는 동작하는 최소 버전(그리드 뷰 +
기본 필터 + 재생 + 삭제/복구)부터 만들어 실제로 열어볼 수 있게 한 뒤 넓힌다.**
타임라인 뷰·고급 필터·내보내기는 v1.1 후보로 미룬다 — SPEC 자체도 "타임라인
중심"이라고 못박았지만, 그리드 뷰가 먼저 있어야 API를 검증하며 반복할 수 있다.

## 1. 왜 이 순서인가

| 후보 | 장점 | 단점 |
|---|---|---|
| **백엔드 API 먼저** | 지금까지와 같은 파이썬 TDD로 계속 검증 가능. pipeline/retention.py 를 그대로 노출하면 됨 | 눈에 보이는 화면이 늦게 나옴 |
| 프론트 먼저(목업 데이터) | 화면을 빨리 봄 | API 계약이 나중에 바뀌면 다시 작업. 실제 클립 데이터 검증이 늦어짐 |

**백엔드 먼저로 정한다.** 이 프로젝트 전체가 "실제 데이터로 검증"을 반복해온 방식과
일치하고, API가 먼저 안정되면 프론트는 그 위에서 빠르게 만들 수 있다.

## 2. FastAPI 백엔드 설계

### 2.1 파일 구조

실제로는 계획했던 routes_*.py 분할 대신 `app.py` 하나에 모든 라우트를 모았다
(라우트 수가 적어 분할할 이유가 없었다) — 최종 구조:

```
src/lumia_briefing_room/
├── api/
│   ├── __init__.py
│   ├── app.py              FastAPI 앱 팩토리 (create_app(cfg) -> FastAPI).
│   │                       클립 목록/조회/수정/trash/restore/영구삭제,
│   │                       Range 지원 video/thumbnail, config 조회/저장 라우트 전부.
│   ├── clips.py            클립 스캔 + 조회 (scan_clips/find_clip/to_summary_dict)
│   ├── filters.py          저장된 메타데이터 위에서 도는 UI 필터
│   └── static.py           frontend/dist 를 찾아 FastAPI 에 정적으로 얹는다
│                           (find_frontend_dist/mount_static)
└── cli/
    └── serve.py            uvicorn(백그라운드 스레드) + pywebview(또는 기본
                             브라우저, 메인 스레드)로 API+정적 프론트를 띄우는 CLI
                             (build_app/run_server_in_thread/wait_until_started/open_ui)

frontend/                    Vite + React + TypeScript + Tailwind, `npm run build`
                             결과가 frontend/dist 에 생기면 static.py 가 자동으로 찾는다
```

### 2.2 클립 스캔 — `api/clips.py`

`clips_dir` 아래 `*.json` 을 전부 읽어 `ClipSummary` 목록을 만든다. 매번 디스크를
훑는 게 단순하고, 클립이 수천 개 수준이면(§7.9: 매치당 0.4~0.8GB, 하루 5매치) 파일
I/O 도 수 ms~수십 ms 라 캐싱 없이 시작한다 — 느려지면 그때 mtime 기반 캐시를 더한다.

```python
@dataclass(frozen=True)
class ClipSummary:
    id: str                 # 파일명(확장자 제외) — meta_path.stem
    meta_path: Path
    meta: dict               # 메타데이터 JSON 그대로
    size_bytes: int          # mp4 파일 크기
    created_at: datetime     # meta_path 의 mtime (매치 시각이 아니라 "생성된 시각" —
                              # retention 정렬 기준은 이거다)


def scan_clips(clips_dir: Path) -> list[ClipSummary]: ...
def find_clip(clips_dir: Path, clip_id: str) -> ClipSummary | None: ...
```

`select_for_auto_clean()` 이 요구하는 `_created_at`/`_size_bytes` 키는 여기서
`ClipSummary` 를 dict 로 펼 때 채운다 (`{**meta, "_created_at": ..., "_size_bytes": ...}`).

### 2.3 필터 재사용

`pipeline/filters.py::apply_filter()` 는 `CombatInterval` 리스트에 대해 동작한다.
UI 필터는 **이미 저장된 메타데이터 dict** 위에서 동작해야 하므로 별도의 얇은
`filter_clip_summaries(clips, query) -> list[ClipSummary]` 를 만든다 — 태그/낮밤/
일차범위/기간/캐릭터를 메타데이터 필드 그대로 비교하는 수준이라 apply_filter 보다
단순하다. 로직 중복처럼 보이지만 **입력 타입이 다르다**(CombatInterval vs 저장된 dict)
는 걸 명확히 하기 위해 이름과 파일을 분리한다.

### 2.4 REST API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/clips` | 목록. 쿼리파라미터로 필터(`tags`, `dayNight`, `gameMode`, `pinned`, `trashed`, `minPvpScore`, `label`=pvp/pve/unlabeled) 와 정렬(`sort`=pvp/recent — 웹 UI 는 이걸 안 쓰고 받은 목록을 게임 단위로 묶어 프론트에서 정렬한다) |
| GET | `/api/clips/{id}` | 메타데이터 하나 |
| PATCH | `/api/clips/{id}` | 제목 수정, pin 토글, 교전/사냥 라벨(`userLabel`: pvp/pve/null, 그 외 400) |
| POST | `/api/clips/{id}/export` | 영상을 `dir` 폴더에 `filename`(기본 제목)으로 복사(중복 시 `(2)`), 그 폴더를 `paths.exportDefault` 에 저장. 폴더 없음 404 |
| GET | `/api/fs/dirs?path=` | 하위 폴더 목록(path 비면 드라이브 목록). 저장 폴더 선택기용 |
| POST | `/api/fs/mkdir` | `path` 아래 `name` 폴더 생성(구분자 포함 이름 400) |
| POST | `/api/clips/{id}/trash` | 휴지통으로 |
| POST | `/api/clips/{id}/restore` | 복구 |
| DELETE | `/api/clips/{id}` | 휴지통에서 완전 삭제 (유예기간 무시하고 수동) |
| GET | `/api/clips/{id}/video` | 클립 mp4 스트리밍 (Range 헤더 지원 — 탐색바 이동에 필수) |
| GET | `/api/clips/{id}/thumbnail` | 썸네일 |
| GET | `/api/config` / PUT `/api/config` | 설정 조회/저장 (config.py 재사용) |

전부 `127.0.0.1` 에만 바인드한다 (SPEC §7.7 `ui.port`, 이미 로컬 전용 원칙 §3).

### 2.5 비디오 스트리밍은 Range 를 지원해야 한다

브라우저의 `<video>` 탐색바(seek)가 동작하려면 `Accept-Ranges`/`Content-Range` 를
직접 구현해야 한다 — FastAPI 의 기본 `FileResponse` 는 Range 를 지원하지 않는다.
`starlette.responses` 의 저수준 스트리밍으로 직접 구현하거나, 검증된 서드파티
(`fastapi-range` 류)를 쓴다. 이건 실제 재생 UX 를 좌우하는 지점이라 **테스트에
Range 요청(`Range: bytes=100-199`)을 반드시 포함시킨다.**

## 3. 프론트엔드 — 최소 버전

SPEC §4 가 정한 스택 그대로: **Vite + React + TypeScript + Tailwind**, 셸은
**pywebview**. 화면 전체를 테스트하지는 않는다 — 백엔드만큼의 TDD 를 프론트 컴포넌트에
요구하면 화면이 안 나온다. 대신 **타입(TypeScript)과 백엔드 계약 일치**를 기본 안전망으로 삼고,
**라벨링 흐름의 순수 로직**(다음 안 한 클립 찾기·키 매핑·낙관적 갱신, `src/labeling.ts`)만
Node 내장 테스트 러너로 TDD 한다(`npm test`, 의존성 추가 없음). 화면은 실제 Edge 로 확인한다.

### 최소 화면

- 클립 카드 그리드 (썸네일 + 제목 + 태그 뱃지)
- 상단 필터 바 (태그, 낮/밤, 게임모드)
- 클릭하면 재생 모달 (`<video>` + Range 지원 확인)
- 카드 우클릭/버튼: 고정, 삭제(휴지통), 복구(휴지통 뷰에서)
- 제목 인라인 편집

### v1.1 로 미루는 것

- 매치 타임라인 뷰(SPEC 이 원래 강조한 뷰)
- 가상 스크롤(`@tanstack/react-virtual`) — 클립이 정말 수천 개가 되면
- 내보내기, 일괄 작업
- phaseIndex/부활구간 필터 (game_day 판독이 아직 없어 필터할 데이터 자체가 없음)
- 설정 화면 — 네임플레이트 색 스크린샷 인식 (§5)

## 4. 확인 필요

### 4-1. pywebview 와 FastAPI(uvicorn)를 한 프로세스에서 같이 띄우는 법 — ✅ 해결됨

`cli/serve.py` 로 구현: uvicorn 을 백그라운드 스레드(`run_server_in_thread`)로
띄우고, 메인 스레드에서 `open_ui()` 가 pywebview 를 시도한다(없거나 실패하면
`webbrowser.open()` 으로 대체). 실제로 만들어 `npm run build` 산출물(`frontend/
dist`)을 `api/static.py::mount_static()` 으로 같은 FastAPI 앱에 얹고, 실제
uvicorn 서버를 띄워 curl 로 확인: `GET /` 가 프론트 `index.html`(정적 자산 포함)을
정상 서빙하면서 `GET /api/clips` 도 그대로 실제 클립 메타데이터를 반환함 — 정적
마운트가 API 라우트를 가리지 않는다(FastAPI 라우트를 먼저 등록하고 `Mount("/")`
를 나중에 추가하면 Starlette 가 등록 순서대로 매칭하기 때문).

트레이 상주 프로세스(`cli/app.py`)의 "열기" 메뉴는 pystray 의 `icon.run()` 이 이미
메인 스레드를 점유하고 있어 같은 스레드에서 `webview.start()` 를 또 요구하는
pywebview 와 충돌한다 — 그래서 트레이 경로(`make_on_open`)는 **항상 기본
브라우저**를 연다(서버는 최초 1회만 기동, 이후엔 재사용). 전용 창이 필요하면
`python -m lumia_briefing_room.cli.serve` 를 독립 실행하면 되고, 그 경로에서는
pywebview 창을 그대로 시도한다.

### 4-2. 대용량 HEVC 클립의 브라우저 재생 (research §4.10 의 연장) — ✅ 해결됨

**실측 완료.** Playwright 로 두 가지를 비교했다:
- Playwright 번들 `chromium-headless-shell`: `<video>` 가 `readyState:4`/길이/
  `currentTime` 진행은 정상이지만 `videoWidth`/`videoHeight` 가 계속 0 — HEVC
  디코더가 없어 화면은 검은색(오디오/탐색바만 동작).
- **실제 설치된 Microsoft Edge**(`executablePath: 'C:/Program Files (x86)/Microsoft/
  Edge/Application/msedge.exe'`, Playwright 로 직접 실행): `videoWidth: 2560,
  videoHeight: 1440` 로 재생 전/후 모두 정상, 스크린샷에 실제 게임 화면이 보임.

pywebview 의 Windows 백엔드가 Edge WebView2(=이 Edge 와 같은 엔진)이므로 **프록시
생성(`encode.proxy.enabled`) 없이 원본 HEVC mp4 를 그대로 재생해도 된다** —
Chromium 번들(headless-shell)에서만 안 되는 것이지, 실제 배포 환경(WebView2)에서는
문제 없음을 확인했다. H.264 프록시는 계획대로 v1.1 이후 "필요해지면" 검토.

## 5. 추후 구현 옵션 — 설정 화면 스크린샷으로 네임플레이트 색 읽기

**아직 만들지 않는다.** 근거: 네임플레이트 신호 자체가 쓸 만한지 아직 증명되지 않았다([plan-pvp.md §5-3](plan-pvp.md)). 신호를 채택하기로 결정하면 그때 같이 만든다.

**왜 필요한가.** 머리 위 체력바 색(자신/아군/몬스터/팀1~8)은 게임 내 `설정 → 색약 간단 설정` 에서 사용자가 바꿀 수 있다([SPEC §2.12-8](SPEC.md)). 코드에 기본 RGB 를 박으면 색약 설정을 쓰는 사용자에게는 검출기가 조용히 고장 난다.

**스크린샷 범위는 하나로 통일한다.** `색약 간단 설정` 화면의 **오른쪽 미리보기 패널만** 잘라서 첨부한다 — 왼쪽 드롭다운 목록은 넣지 않는다. 범위: `자신 색상` 행부터 `팀8 색상` 행까지 **12행**(이름 + 레벨 상자 + 체력바 견본), 위 4행(자신/아군/환경 오브젝트/몬스터)과 아래 8행(팀1~8) 사이에 빈 간격이 있는 그대로.
왜 오른쪽인가: 견본이 실제 게임 속 체력바 모양(눈금·레벨 상자) 그대로라 색을 뽑는 곳이 곧 검출할 모양이다. 왼쪽 막대는 색만 있고 모양이 없다.
(예시 이미지 `docs/img/` 는 미디어라 커밋하지 않는다 — CLAUDE.md.)

**형태.** UI 에 설정 화면을 만들고 거기에 위 범위의 스크린샷을 드래그해 넣으면:

1. 업로드 → `POST /api/profile/nameplate-colors` (이미지 바이트)
2. 서버가 12개 행을 찾아 각 체력바 견본의 대표 RGB 를 뽑는다. 행 순서는 고정이므로 세로 위치(4행 + 간격 + 8행)로 역할을 안다 — 이름 글자를 읽을 필요가 없다. 이미지 크기가 달라도 비율로 잡는다.
3. 결과를 역할→RGB 표로 화면에 보여주고(사용자가 눈으로 확인), 저장하면 해상도 프로필 옆에 사용자 오버라이드로 기록한다.
4. 저장된 색이 없으면 기본값 표를 쓴다.

**주의.** 스크린샷 해상도가 녹화 해상도와 다를 수 있으므로 좌표는 비율로 잡는다. 행 개수가 안 맞으면(게임 업데이트로 항목 추가) 조용히 틀린 색을 저장하지 말고 **거부하고 알린다.**
