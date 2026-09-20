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
- [ ] React 프론트엔드 스캐폴딩 (Vite + TS + Tailwind)
- [ ] 클립 목록 뷰 (카드 그리드)
- [ ] 매치 타임라인 뷰
- [ ] 필터 UI
- [ ] 정리 UI (삭제/복구/고정/내보내기)
- [ ] pywebview 셸 배선
- [ ] 빌드 산출물을 FastAPI 정적 서빙에 연결

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

```
src/lumia_briefing_room/
└── api/
    ├── __init__.py
    ├── app.py              FastAPI 앱 팩토리 (create_app(cfg) -> FastAPI)
    ├── clips.py            클립 스캔 + 조회/필터 (pipeline/retention.py 의
    │                       select_for_auto_clean 이 요구하는 _created_at/_size_bytes 를
    │                       실제로 채우는 계층 — plan-pipeline.md §2.8 에서 남겨둔 자리)
    ├── routes_clips.py     GET /api/clips, GET /api/clips/{id}
    ├── routes_actions.py   POST /api/clips/{id}/trash|restore|pin|unpin
    ├── routes_media.py     GET /api/clips/{id}/video, /thumbnail
    └── routes_config.py    GET/PUT /api/config

cli/
└── serve.py                uvicorn 으로 API(+정적 프론트 빌드)를 띄우는 CLI
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
| GET | `/api/clips` | 목록. 쿼리파라미터로 필터(`tags`, `dayNight`, `gameMode`, `pinned`, `trashed`) |
| GET | `/api/clips/{id}` | 메타데이터 하나 |
| PATCH | `/api/clips/{id}` | 제목 수정, pin 토글 (SPEC: "제목은 수동 편집 가능") |
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
**pywebview**. React 자체 테스트(Vitest 등)는 이번 1차 범위에서는 만들지 않는다 —
백엔드만큼의 TDD 를 프론트에도 요구하면 이번 회차 안에 화면이 안 나온다. 대신
**타입(TypeScript)과 백엔드 계약 일치**로 최소한의 안전망을 삼는다.

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

## 4. 확인 필요

### 4-1. pywebview 와 FastAPI(uvicorn)를 한 프로세스에서 같이 띄우는 법

uvicorn 은 보통 자체 이벤트루프(asyncio)를 블로킹으로 돈다. pywebview 의
`webview.start()` 도 메인 스레드를 요구하는 경우가 많다(플랫폼別). Windows 에서는
pywebview 가 별도 스레드에서도 대체로 동작한다고 알려져 있지만, **이 환경에서
직접 확인하지 않았다.** 계획: uvicorn 을 백그라운드 스레드로 띄우고 `webview.start()`
를 메인 스레드에서 호출 — 안 되면 `ui.shell=browser`(기본 브라우저로 열기) 를
사실상의 기본 경로로 삼는다. `cli/app.py` 의 트레이 "열기"가 이미 그 폴백 자리를
잡아뒀다(§_on_open, plan-pipeline.md).

### 4-2. 대용량 HEVC 클립의 브라우저 재생 (research §4.10 의 연장)

research §4.10 에서 **OS 코덱은 있음을 확인**했지만, `<video>` 태그로 로컬 서버발
HEVC 스트림을 재생하는 것까지는 확인하지 않았다(Chromium 계열은 라이선스 문제로
HEVC `<video>` 재생을 기본적으로 막아둔 빌드가 흔하다 — pywebview 의 백엔드가
Edge WebView2 라면 OS 코덱을 타므로 될 가능성이 높지만 **실측 전이다**). 안 되면
SPEC §7.5 의 H.264 프록시 생성(`encode.proxy.enabled`)을 UI 쪽에서 기본으로
켜는 결정이 필요해진다 — 이건 이번 계획 §2 백엔드 완성 직후 가장 먼저 실측할 것.
