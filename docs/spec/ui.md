# 열람 UI

> 코드: 백엔드 `src/lumia_briefing_room/api/`, 프론트 `frontend/src/`. **`frontend/src` 를 고치면 같은 작업에서 `npm run build` 로 `frontend/dist` 를 갱신한다**(`run.bat` 은 빌드된 정적 파일만 띄운다).

## 1. 스택과 실행 구조

- **React + TypeScript + Vite + Tailwind** → 정적 빌드 → FastAPI 가 서빙(`api/static.py`, 라우트를 먼저 등록하고 `Mount("/")` 를 나중에). 무거운 컴포넌트 라이브러리·상태 관리 라이브러리는 쓰지 않는다.
- 셸: 트레이 경로는 **기본 브라우저**(pystray 와 pywebview 가 메인 스레드를 다툰다). `cli.serve` 독립 실행만 pywebview(WebView2) 창을 시도하고 실패하면 브라우저. Electron 은 쓰지 않는다(RAM 150~300MB).
- 서버는 `127.0.0.1` 에만 바인드. 접속 주소 **`http://lumia-briefingroom.localhost`**(Chromium·Firefox 가 `*.localhost` 를 루프백으로 푼다, hosts 불필요). 포트 후보는 고정 순서 **80 → `ui.port`(8765) → +20** — 포트가 바뀌면 origin 이 바뀌어 localStorage(볼륨·탭·"다시 묻지 않기")가 초기화되기 때문이다. `ui.port=auto`(옛 값)는 8765 와 같다.
- 설정 API 는 매번 설정 파일을 다시 읽는다(감시가 학습한 닉네임을 메모리 사본이 덮어쓰지 않게).
- 앱 모드(`appmode.resolve_mode`, `app.mode`): 빌드본 = `release`, 소스 = `dev`. `release` 에서는 튜닝용 화면(클립 ID, 교전 점수 칩·슬라이더, 근거 상세)과 관리자 탭을 숨긴다. `GET /api/app-info` 로 모드·버전을 내려준다. 헤더 제목 옆에 버전(`v0.1.x`, dev 는 `(dev)`).
- 프론트 테스트: 순수 로직 모듈(`grouping.ts`·`timeline.ts`·`labeling.ts`·`cleanupPreview.ts`·`vodDates.ts` 등)만 Node 내장 러너로 TDD(`npm test`). 화면은 실제 브라우저로 확인한다.

## 2. 화면 구성

- 상단 탭 **`스팀 녹화` | `영상 파일`**(개발 모드는 `관리자` 탭 추가). 선택 탭은 localStorage, **탭마다 필터·정렬·펼침·보기 모드가 독립**이다. 플레이어의 이전/다음은 현재 탭 목록 안에서만.
- **날짜 머리줄**(`gameDays.ts`·`GameDayHeader`): 게임 목록을 **자정 기준** 로컬 날짜로 나누고 `9월 30일 (수) · 오늘` + 게임·클립 수·용량을 적는다. 스크롤해도 위에 붙어 있다(sticky). 정렬 순서를 그대로 따르고, 시각을 모르는 게임은 맨 뒤 `날짜 모름`. 밤샘 세션도 자정에서 나눈다(사용자 결정 — 새벽 5시 기준안은 채택 안 함). **영상 파일 탭**도 같은 머리줄을 쓴다(`vodDates.groupVodsByDate`): 영상 날짜(`videoDate`)로 영상 묶음을 나누고 `영상 N개 · 게임 · 클립 · 용량` 을 적는다. 날짜 순서는 정렬 방향을 따르고(영상 목록은 원래 이름순이라 날짜로 다시 묶는다), 한 날짜 안은 이름순, 날짜 없는 영상은 맨 뒤 `날짜 모름`.
  - **접기·바로가기**(`dayFold.ts`·`useDayFold.ts`·`DayShortcutBar`, 두 탭 공통): 머리줄을 누르면 그 날짜 목록이 접히고(머리줄 한 줄은 남음, `▼/▶`) 모두 펼치기/접기 버튼이 있다(영상 파일 탭은 `날짜 모두 펼치기/접기`). 접힌 날짜는 탭마다 localStorage(`lumia.collapsedDays.<탭>`, 접근은 try/catch)에 저장하고 저장된 적 없는 새 날짜는 펼쳐진다. 날짜 바로가기 줄(`9/30`·`9/29`…, 화면 순서 그대로, 가로 스크롤)은 **거르지 않고** 그 날짜 머리줄로 스크롤하며 접혀 있으면 펼친다. 옛 영상 파일 탭의 날짜 칩 거르기(`filter.dates`)는 없앴다. 한 번에 한 날짜만 보이는 이동기는 채택하지 않았다.
- **게임 행**(`GameSection`, dak.gg 식 접이식): 순위(1위 초록 막대)·모드·시작 시각/경과·초상화 3장(`PortraitRow`, 코발트는 그리지 않음)·TK/K/A·클립 수·총 용량. 코발트는 `#N위` 대신 `승리`/`패배`, 그 아래 회색 `코발트`. ▾ 로 펼치면 첫 칸 결과표 썸네일(`ResultCard` → 확대 뷰어, ←/→ 로 이전/다음 게임 결과표) + 클립.
- 게임 묶음은 `sessionDir + matchStartUtc`(VOD 는 영상 → 게임). **정렬은 게임 순서에만** 적용(최신 순 기본 / 오래된 순 / 교전 가능성 = 게임의 최고 `pvpScore`), 게임 안 클립은 항상 오름차순. 정렬은 프론트에서 하며 API `sort` 는 쓰지 않는다.
- 클립이 다 지워진 게임은 게임 기록(`GET /api/games/records`)으로 "클립 삭제됨" 행이 된다(필터가 켜지면 숨김).
- **보기 모드** `카드 | 일자 타임라인`(라벨 `보기`). 타임라인은 `phaseIndex` 칸(1일차 낮·밤…)을 가로로 놓고 무료 부활/크레딧 경계를 표시, 교전 없는 페이즈도 칸을 그린다.
  - `phaseIndex` 가 없는 클립은 게임 경과 시간 ÷ `PHASE_LENGTH_SEC`(165초)로 칸을 추정해 **점선 테두리 + 툴팁**으로 구분. 그것도 못 하면 맨 끝 `시점 미상`. VOD 는 `combatStartOffsetSec − gameStartOffsetSec`.
  - 코발트 게임은 `cobaltPhase` 칸(`buildCobaltPhaseColumns`).
- **필터 바**: 태그(서버에서 **OR**), 게임 모드, 라벨 상태, 교전 가능성 하한(맨 왼쪽 `전체`), 고정만, 제목 검색(`q`, 대소문자·공백 무시 부분 일치, 0.3초 디바운스, 메모는 대상 아님), `삭제 예정만 보기`, VOD 날짜 칩, 영상 파일 탭 새로고침.
- **빈 화면**(`emptyState.ts`): 가운데 문구 + 스팀 탭 "과거 녹화 분석", 영상 파일 탭 "영상 경로 추가". 목록을 아직 못 받았으면 빈 문구를 띄우지 않는다. 비활성 버튼은 `title` 로 이유를 말한다.
- **활동 표시**: `GET /api/activity` 를 3초마다 읽어 헤더 아래 막대(감시의 게임 분석, 과거 녹화 분석, 다시 분석). 작업 중엔 5초마다, 끝나는 순간 한 번 목록을 깜빡임 없이 다시 읽는다. 다시 분석 중인 게임 행은 파란 테두리·불확정 막대. 감시 실패는 상단 빨간 배너 + "계속하기". 저장 공간 부족·풀영상 저장 실패는 그 아래 노란 배너(`NoticeBanner`, `GET /api/notices` 를 10초마다, "닫기" = dismiss).
- **첫 실행 화면 저장 공간 안내**: 설정 단계에서 "게임 하나에 2~5GB 가 저장됩니다. 50~100GB 여유 공간을 확보하고 사용하세요." 를 큰 글씨 경고 상자로 두고, 저장 폴더 드라이브의 현재 여유 공간(`disk`)을 보여 준다(50GB 미만이면 빨강). **"확인했습니다"를 켜야 `시작하기` 가 눌린다**(동의 항목만 다시 묻는 경우는 제외).
- **삭제 예정 표시**: 자동 정리가 켜져 있으면 대상 클립·게임 행(전부 대상일 때)·타임라인 블록에 빨간 테두리 + "N일 후 삭제 예정"/"한도 초과로 삭제 예정" 배지(툴팁 "현재 기준 예상"). 고정하면 사라진다. 스팀 탭만.

## 3. 플레이어 (`PlayerModal`)

- 좌우 큰 이전/다음 버튼(끝에서 비활성), 삭제(후 다음 클립으로), 저장(내보내기), 자르기. **닫기는 닫기 버튼·ESC 만** — 배경 클릭으로 닫으면 자르기 작업이 날아간다(결과표 뷰어도 같음).
- 방향키 ←/→ = **재생 위치 ∓5초**(클립 이동 아님). 저장 창이 떠 있는 동안 단축키 정지.
- 볼륨·음소거는 localStorage(영상마다 `<video>` 가 새로 만들어진다).
- 영상/썸네일 URL 에 `?v=길이` 를 붙여 자르기 뒤 캐시를 깬다.
- 창이 넘치면 잘리지 않고 스크롤(`playerLayout.ts` 가 라벨 컨트롤 높이를 반영).
- **재생 폴백**: 시작 시 `canPlayType`(`hvc1`·`hev1` 둘 다) + 첫 재생 `videoWidth === 0`/오류면 HEVC 불가로 보고 클립별 **H.264 프록시**로 자동 전환(`POST/GET /api/clips/{id}/proxy`, 진행률 표시). 프록시 모드면 현재 클립이 준비되면 다음 클립 1개를 미리 만든다(`?prefetch=1`, 서버 `PriorityGate` 는 직접 요청을 먼저, 실행 중 작업은 끊지 않음, `encode.proxy.prefetch`). 대기 화면에 선택적 코덱 설치 안내(유료 스토어 링크, 무료 제조사판은 검색 안내, 자동 설치 안 함). 프론트가 판별 결과를 `POST /api/client-capabilities` 로 알린다(환경 정보용).
- **라벨링**: `교전`/`그 외` 버튼, 키 `1`/`2`/`0`(해제). 라벨을 붙여도 **다음 클립으로 자동 이동하지 않는다**(메모를 쓰려면 머물러야 한다). 메모(`labelNote`, 500자, 텍스트만, 라벨 해제 시 함께 지움) — 라벨링을 켜면 라벨 전에도 보이되 비활성. `(?)` 도움말(무엇을 보내고 안 보내는지). 배포 모드에서는 `telemetry.sendLabels` 가 켜져 있을 때만 라벨링 UI 가 보인다(개발 모드는 항상). 이미 라벨한 카드는 선택된 버튼만.

### 자르기·분할 (`pipeline/trim.py`, `TrimPanel`)

- 구간 1개: `POST /api/clips/{id}/trim` — `ffmpeg -ss S -to E -i clip.mp4 -map 0 -c copy` 로 임시 파일 → `os.replace`(실패 시 원본 유지). MP4 편집 리스트로 시작 프레임이 정확하다. `durationSec`/`videoOffsetSec` 갱신, `trimmed`·`originalDurationSec`. 보이지 않는 프리롤(최대 3초)이 파일에 남는 게 무재인코딩의 대가.
- 구간 2개 이상: `POST /api/clips/{id}/split` — 구간마다 새 클립(`<원본>-pN`, `splitFrom`, 라벨은 비우고 자동 근거는 복사), 원본은 설정 삭제 방식으로. 구간은 겹칠 수 없고(서버도 400) 최소 1초. 하나라도 실패하면 만든 조각을 지우고 원본 유지.
- 자르기 시작 위치 = 현재 재생 위치.

### 내보내기

- 서버가 Windows 탐색기 선택 창을 띄운다(`POST /api/fs/pick-folder`, VOD 파일은 `pick-videos`, `native_dialog.py`, 전경 창 소유). 브라우저가 로컬 경로를 못 다루기 때문. 옛 `/api/fs/dirs`·`mkdir`·`videos` 는 남아 있지만 프론트는 안 쓴다.
- `POST /api/clips/{id}/export`: 같은 이름이면 `(2)`, 고른 폴더를 `paths.exportDefault` 로 기억.
- 디스코드 10MB 용 재인코딩은 실험 후 접었다(720p 이하로 뭉개져 닉네임이 안 읽힘). 다시 하려면 인코딩 말고 다른 방법부터. 외부 호스팅 자동 업로드는 "영상은 밖으로 보내지 않는다" 원칙과 충돌.

## 4. 게임 단위 동작

- 게임 단위 삭제(클립 삭제와 같은 확인 창), 게임 기록은 `retention.keepGameRecords` 대로 서버가 남긴다.
- **다시 분석**(`POST /api/games/reprocess`, 한 번에 하나 — 동시 요청은 지금 409).
- **수동 보정**: 순위 배지 옆 `✎` → 순위·결과 문구 입력 → 그 게임의 모든 클립에 `PATCH /api/clips/{id}`(`matchResult` 의 `placement`/`outcome` 만, `matchResultSource="manual"`). 잠금 해제는 `matchResultSource: null`(값은 유지). 캐릭터 보정은 후보 목록이 없어 만들지 않았다.
- 제목 수정: 카드·플레이어 `✎`/더블클릭.

## 5. 삭제 확인 창 (`DeleteConfirmDialog`)

- "정말 삭제하시겠습니까?" + 체크박스 `다시 묻지 않기`(`ui.confirmDelete`) · `휴지통으로 보내지 않고 영구 삭제하기`(`ui.deleteMode`). 옵션 화면과 같은 값이다.
- 휴지통으로 보낼 때: "Windows 휴지통에서 되살릴 때는 클립의 파일(영상·정보·썸네일)을 모두 복원해야 이 앱에서 다시 볼 수 있다"고 안내(클립 = 여러 파일).
- 영구 삭제 + 다시 묻지 않기 조합은 저장 전에 한 번 더 경고.

## 6. 옵션 모달 (`SettingsModal`)

탭: 일반(닉네임, 자동 시작, 재생 — 프록시 미리 만들기, 삭제 확인) / 영상 저장(저장 기본 폴더, 클립 폴더 — 바꿀 때 "기존 클립도 옮길까요?") / 자동 정리 / 영상 파일 / 정보·진단.

- **자동 정리**: 켜기 + 기준별 체크박스(N일 지난 / N개 초과 / N GB 초과, 체크 해제 = `null`), 삭제 방식, 보호(고정·태그), 미리보기·즉시 실행. 끄면 기준들이 비활성. "게임 기록 유지"는 수동 삭제에도 적용돼 별도 구역. **켤 때마다 경고 창**(방식에 따라 "영구 삭제됩니다"/"휴지통으로 보내집니다").
- **영상 파일**: 경로 추가(파일/폴더), 하위 폴더, 클립 저장 폴더, 원본 삭제(`매번 묻기`/`항상`/`안 함`, 방식, 항상+영구는 경고). 지원 확장자 `(?)` — `.mp4` `.mkv` `.ts` `.webm` `.mov`, 확인된 것은 `.mp4` 뿐이라고 적는다. 목록은 `video_formats.py` 한 곳 → `GET /api/app-info` `videoFormats` 로 내려준다.
- **정보·진단**: 버전·패치노트(`GET /api/changelog`)·업데이트, 선택 기능(동의 항목), 전송 상태·미리보기·삭제 요청, 진단 정보 보내기/zip, 표시용 ID, 개인정보 처리 안내([deploy.md](deploy.md)).

## 7. REST API 개요

모든 경로의 정확한 동작은 코드(`api/*.py`)와 테스트가 기준이다.

| 묶음 | 경로 |
|---|---|
| 클립 | `GET /api/clips`(`source`=steam 기본/vod, `vodId`, 태그·모드·라벨·`minPvpScore`·`q`…), `GET·PATCH·DELETE /api/clips/{id}`, `…/video`(**Range 필수** — 탐색바), `…/thumbnail`, `…/result-image`, `…/character-portrait/{me\|teammate1\|teammate2}`, `…/trim`, `…/split`, `…/export`, `…/proxy` |
| 게임 | `GET /api/games/records`, `DELETE /api/games/records/{id}`, `…/result-image`, `POST /api/games/reprocess`, `GET /api/games/reprocess/{key}`, 풀영상 게임 API 는 [pipeline.md §11](pipeline.md) (`GET /api/games?source=steam\|vod\|all`, 기본 steam) |
| 영상 파일 | `GET /api/vods`, `PATCH·DELETE /api/vods/{vid}`, `POST·GET /api/vods/{vid}/analyze`(`resume`/`rebuild`/`force`/`deleteSource`), `…/analyze/cancel`, `POST /api/vods/{vid}/full-videos`(이미 분석한 옛 영상의 풀영상 만들기), `DELETE /api/vods/{vid}/clips`, `DELETE /api/vods/{vid}/games/{i}`, `…/games/{i}/result-image` |
| 정리 | `POST /api/cleanup`, `GET /api/cleanup/preview`, `GET·POST /api/clips-dir/move`, `GET /api/legacy-trash`, `POST /api/legacy-trash/migrate` |
| 작업 | `GET /api/activity`, `GET /api/backfill`, `GET /api/backfill/preview`, `POST /api/backfill/start·cancel`, `GET /api/watch/failures`, `POST /api/watch/failures/{key}/retry` |
| 파일 선택 | `POST /api/fs/pick-folder`, `POST /api/fs/pick-videos` |
| 앱 | `GET·PUT /api/config`(`ui.autoStart` 는 저장 즉시 레지스트리 반영), `GET /api/app-info`, `GET /api/changelog`, `GET /api/privacy`, `GET /api/first-run`, `POST /api/first-run/complete`, `POST /api/client-log`, `POST /api/client-capabilities`, `GET /api/diagnostics` |
| 업데이트·전송 | `/api/update/*`, `/api/telemetry/*` → [deploy.md](deploy.md) |
| 관리자(dev) | `/api/admin/*` → [deploy.md §6](deploy.md) |

## 8. 개발용 디버깅

- 프론트 전역 오류(`window.onerror`·`unhandledrejection`·`console.error`)를 `POST /api/client-log` 로 보내(중복 억제, 재전송 없음) `%LOCALAPPDATA%\LumiaBriefingRoom\logs\app.log` 에 `[client]` 로 남긴다. 두 모드 모두 켜져 있다(로컬 파일, 진단 재료).
- Playwright MCP(시스템 Chrome) 연결 방법은 [DEVELOPMENT.md](../DEVELOPMENT.md). HEVC 는 번들 Chromium 에서 검게 나온다.

## 스팀 녹화 탭 = 게임 목록 → 풀영상 (F4·F4-b, 새 컴포넌트 `GameList`·`GameViewer`·`ViewerBar`·`ViewerCandidates`)

"스팀 녹화" 탭은 게임 목록이고 게임을 열면 풀영상 화면(← 게임 목록)이 뜬다. 별도 "게임(풀영상)" 탭은 없다. 옛 카드 뷰(`ClipBrowser` steam·`GameSection`·`ClipCard`)와 첫 구현 `GamePlayer` 는 F5 제거 전까지 코드로만 남아 있다 — `App.tsx` 의 전환 커밋 하나를 되돌리면 옛 화면이 돌아온다.

- **게임 목록**(`GET /api/games`): 날짜 머리줄(`GameDayHeader`, 게임 수·저장한 클립 수·풀영상 합계) 아래 게임 행 — **왼쪽**: 초상화 3장, 순위(`#1`, `#7`; 코발트 프로토콜은 `승리`/`패배`만, 결과를 모르면 `결과 미확인`)와 `일반`/`랭크` 배지(`matchResult.matchType`, 판독하지 못했으면 배지 없음), 시작 시각, TK/K/A. **오른쪽 정렬**(게임마다 있을 수도 없을 수도 있는 배지 — 빨간 `편집 N개 저장 안 됨`·고정·삭제 예정·풀영상 오류 — 는 이 묶음의 가장 왼쪽에 두어 나머지 열이 행마다 같은 자리에 오게 한다): 저장한 클립 수, 풀영상 크기(또는 "풀영상 삭제됨/없음"), 고정 배지, **자동 정리 삭제 예정 배지**(경기 키로 `GET /api/cleanup/preview` 와 맞춤), **저장 안 된 편집이 있으면 빨간 `편집 N개 저장 안 됨` 배지**(`unsavedEditCount` — 범위를 저장 당시/검출값과 다르게 고친 후보 수, 무시한 후보 제외), 고정/해제 버튼. **행 어디를 눌러도 풀영상이 열린다**(열기 버튼 없음, 고정 버튼은 열지 않는다). 위쪽에 "게임 N개 · 풀영상 합계".
- **풀영상 화면 배치**: 왼쪽에 영상(창 높이에서 머리줄을 뺀 만큼 최대) + 컨트롤 + 재생 막대 + 편집 줄, 오른쪽에 고정 폭(320px) 후보 패널. 기본 `<video controls>` 는 쓰지 않고 재생 막대는 하나뿐이다.
- **컨트롤**(아이콘은 전부 흰색 SVG — 이모지는 플랫폼 색이 섞여 쓰지 않는다): 재생/일시정지(영상 클릭도 같음), 10초 뒤로/앞으로, 이전 클립/다음 클립(이전·다음 후보 시작으로 이동), 시각/길이, 볼륨·음소거(`volume.ts` 로 기억), 전체화면(영상+막대 영역 `viewer-shell` 만 전체화면 — 후보 패널은 안 보임).
- **재생 막대**(`ViewerBar`, 스팀 편집기 모양): 파란 트랙 위 노란 후보 구간(확실 = 진하게, 나머지 = 옅게, 무시 = 회색, 양 끝 노란 점선), 킬(초록)·어시(파랑)·사망(빨강)·팀원 사망(주황) 눈금은 트랙 아래, 재생 위치는 흰 핀, 마우스를 올리면 시각·후보 제목.
  - **막대 어디를 누르거나 끌어도 재생 위치만 움직인다(노란 구간 안 포함).** 눌린 자리에 후보가 있으면 선택(목록 강조)되고, 빈 곳을 눌러도 선택은 풀리지 않는다(선택한 구간의 끝점을 찾으러 이동하는 흐름).
  - **편집은 손잡이·버튼으로만**: 선택된 후보의 양 끝 손잡이(구간 바깥 양옆, 끌 때만 범위 변경 → 놓으면 `PATCH`), **되돌리기**(범위 변경·구간 추가·무시), **돋보기 +/−**(보이는 범위를 절반/두 배로, 최소 10초, 재생 위치 기준; 전체가 다 보이면 전체 보기. 확대 중에는 막대 아래 **스크롤 띠**를 끌거나 눌러서, 또는 그 위에서 휠로 좌우로 옮긴다), **+ 여기서 구간 추가**(현재 위치 앞뒤 10초). 편집 줄의 버튼은 오른쪽에 모여 있다. `시작점=현재`/`끝점=현재`·`구간 확대`/`전체 보기` 버튼은 없다(단축키 I/O 만 남았다). 구간 통째 옮기기·빈 곳 끌어 만들기는 없다(이동과 부딪힌다).
  - **범위 편집은 초안이다.** 손잡이를 놓으면 `game.json` 의 후보 범위만 바뀌고(되돌리기 = 버튼 또는 Ctrl+Z) 클립은 그대로다. 범위를 저장 당시(저장한 적 없으면 검출값)와 다르게 고친 후보는 막대에서 주황색, 목록에서 주황 테두리 + `수정됨`(저장한 클립이면 `수정됨 · 저장 전`) 배지로 표시한다. 클립에 반영하려면 후보의 `저장`(저장한 클립은 `다시 저장` → 같은 클립을 새 범위로 교체).
  - 짧은 구간(20초 = 25분 영상의 1.7%)에서 두 손잡이가 겹치지 않도록 손잡이를 구간 안쪽이 아니라 바깥쪽에 둔다.
- **후보 패널**: 저장 대기 개수, 행의 연필 아이콘으로 **클립 이름 수정**(Enter 확정·Esc 취소·포커스를 잃으면 확정, 빈 값 = 검출 이름 복귀; 저장한 클립은 이름만 즉시 바뀐다), **전부 저장 (N)**(범위를 고친 후보 N개를 저장/교체 — 고친 후보가 없으면 비활성), 행 = 제목(누르면 시작으로 이동·선택)·구간·확실/태그·**저장/다시 저장**·**무시**(목록에서 숨긴다, 되살리기는 Ctrl+Z 뿐; 직접 구간은 삭제, 저장한 후보에는 없다). 재생 위치가 든 후보는 노란 테두리로 강조하고 목록이 따라 스크롤한다.
- **단축키**: Space 재생/일시정지, ←/→ 5초, N/P 다음/이전 클립, S 선택 후보 저장, D 선택 후보 무시(직접 구간은 삭제), I/O 시작·끝점, Ctrl+Z 되돌리기. 입력칸에 포커스가 있으면 무시.
- 순수 계산은 `frontend/src/games.ts`(`dragRange`·`neighborCandidate` 등)와 `frontend/src/playerBar.ts`(막대 좌표↔시각·확대 범위·확대 이동·누른 위치의 후보·I/O 규칙·눈금 간격), node 테스트. 화면은 Playwright 로 확인한다.
- **과거 녹화 분석 버튼**은 스팀 녹화 탭의 도구 줄("게임 N개 · 풀영상 용량" 줄 오른쪽 끝)에 있다. 진행 중에는 버튼과 활동 막대에 `과거 녹화 분석 중 N%`. 영상 파일 탭에는 없다(헤더에도 없다).
- 풀영상이 없으면(정리됨·저장 실패) 이유 안내와 함께 후보 패널만 보이고 저장 버튼은 꺼진다. HEVC 를 못 그리면 안내 문구.
- **이전 버전 게임**(`legacy`, `LegacyGamePanel`, `legacyGame.ts`): 풀영상 전환 전에 분석한 게임은 목록 행에 "풀영상 없음(이전 버전)" 배지가 붙고, 열면 "이전 버전에서 분석한 게임이라 풀영상이 없습니다. 저장된 클립으로 볼 수 있습니다" 안내 + 예전 방식의 클립 목록(오른쪽)·클립 재생(`ClipVideo` 재사용 - HEVC 프록시 폴백 포함)이 뜬다. 클립은 `GET /api/clips` 에서 `matchStartUtc`+`sessionDir` 이 같은 것만 고른다(후보 패널은 안 보인다). 원본이 링버퍼에 남아 있으면(`canRebuildFullVideo`) "원본이 남아 있습니다 — 풀영상 만들기" 버튼: 진행률을 1.5초마다 읽고, 끝나면 풀영상 화면으로 바뀐다(저장한 클립은 그대로). 백엔드는 [pipeline.md §11](pipeline.md).
- 후보 라벨(교전/사냥)·태그 필터는 API 만 있고 화면은 아직 없다.

## 영상 파일 탭 = 날짜 > 영상 묶음 > 게임 행 → 풀영상 (F6, `VodGameList`)

스팀 녹화 탭과 같은 문법이다. 날짜 머리줄(영상 날짜 `videoDate` 기준, 접기·바로가기) 아래 **영상 묶음**(`VodSection`), 그 안에 **게임 행**(`GameRow` - 스팀 녹화 탭과 같은 컴포넌트, 시간 칸만 `게임 N` + 원본 안 위치), 게임을 누르면 같은 `GameViewer`(← 영상 목록, 제목 `스트리머 · 게임 N`)가 열린다. 옛 카드 화면(`ClipBrowser` vod)은 F5 전까지 코드로만 남고 `App.tsx` 의 전환 커밋 하나를 되돌리면 돌아온다.

- 영상 묶음 머리 기능은 그대로: 분석 시작·취소·진행률(`풀영상 만들기` 단계 추가), 날짜·이름 고치기, 다시 분석, 전체 삭제(확인 문구가 게임 풀영상까지 지운다고 알린다), 목록에서 삭제.
- **필터 바는 없다** - 스팀 녹화 탭이 새 화면에서 필터 바를 없애고 도구 줄(게임 수·풀영상 용량·날짜 모두 펼치기/접기·바로가기)만 둔 기준을 따른다. 도구 줄에 새로고침·영상 형식 도움말. 날짜는 최신순, 한 날짜 안은 영상 이름순, 영상 안은 게임 번호순.
- 옛 영상: 원본·캐시가 남았으면 영상 머리에 `풀영상 만들기 (N)`(확인 창에 최대 용량). 원본이 지워졌으면 게임 행이 `풀영상 없음(이전 버전)` 이고 열면 저장된 클립으로 본다(`LegacyGamePanel`, 클립은 후보 기록에서).
