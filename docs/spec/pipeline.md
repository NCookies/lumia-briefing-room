# 파이프라인 — 감시·처리·클립·보관

> 코드: `src/lumia_briefing_room/pipeline/`, `cli/`. 설정 키는 [config.md](config.md).

## 1. 전체 흐름

```
Player.log 폴링 ─ 경기 경계(GAME→LOBBY) ─▶ 녹화 세션 결정(폴더명·session.mpd)
  ─▶ 세그먼트 범위(존재 확인) ─▶ [여유 적으면 구출 복사] ─▶ 검출(detect_match)
  ─▶ 게임 전체 영상 컷(full.mp4) ─▶ 결과 화면·초상화 판독 ─▶ 생성 필터 ─▶ 클립 범위·병합
  ─▶ (saveMode=auto) -c copy 컷 + 썸네일 + 메타데이터 JSON ─▶ game.json
```

`pipeline/orchestrator.py::process_match(session, start, end, cfg, …)` 가 한 경기를 끝까지 처리한다. 경계만 받으면 나머지는 같으므로 로그 감시·다시 분석·과거 녹화 분석이 모두 이 함수를 부른다.

- 진행률: 검출(프레임 비율) 0~45% → 결과 화면 16% → 클립 컷(클립마다) 나머지. 실측 21분 경기 55초(24.8 / 8.8 / 21.6초).
- 클립 계획은 `_plan_clips(intervals, cfg, game_mode=…)`.

## 2. 감시 (`pipeline/watcher.py::run_polling`)

- **줄 단위 tail 이 아니라 주기적 폴링**이다. `watch.pollIntervalMs`(1초)마다 `Player.log`·`Player-prev.log` 를 통째로 다시 읽어, 끝난 지 `watch.delaySec`(5초, `.tmp` 확정 대기)이 지난 **처리 이력에 없는** 경기를 **오래된 것부터** 처리한다.
  - tail 방식은 두 번 경기를 놓쳤다: 처음 연 로그 핸들을 쥐고 있어 게임 재실행 뒤 새 로그를 못 봄, 밀린 경기 처리 중 시작된 경기의 시작 줄을 못 봄.
- 처리 이력(`processed_matches.json`, 임시 폴더)이 중복을 막는다. 세션이 없는 경기는 건너뛴다.
- 예외로 실패한 경기는 **3번까지** 재시도(메모리 카운터, 감시 스레드는 죽지 않음). 실패 사실과 원인은 `pipeline/watch_failures.py::WatchFailureTracker` 가 JSON 에 영속화해 화면 상단 빨간 배너로 보이고, "계속하기"(`POST /api/watch/failures/{key}/retry`)는 횟수 제한과 무관하게 다음 폴링에서 다시 시도한다. ffmpeg 디스크 부족은 `pipeline/ffmpeg_errors.py` 가 "저장 공간이 부족해…"로 번역한다(VOD 분석 오류 문구도 같은 판별기).
- 감시 정지/재개는 트레이 토글이 실제로 스레드를 멈추고 다시 띄운다(`cli/app.py::make_watch_controller`).
- 녹화 폴더를 못 찾으면 10초마다 재시도(첫 실행에서 감시 스레드가 죽던 문제).
- 녹화 폴더 결정 순서: `--recording-root` → `paths.steamRecording` → `localconfig.vdf` 자동 탐지.

## 3. 링버퍼 대응

```
매치 첫 세그먼트 나이 = (종료 후 경과) + (매치 길이)
남은 여유 = 버퍼 길이 - 첫 세그먼트 나이
```

- 앱이 떠 있으면 여유 약 100분이라 실시간성은 문제가 아니다. **앱이 2시간 넘게 꺼져 있으면 영구 소실** → `ui.autoStart` 기본 켬이 실질적 방어책.
- **구출**(`watch.rescueThresholdMin`, 20분): 여유가 임계 이하면 원본 세그먼트를 먼저 임시 폴더로 통째 복사한 뒤 분석한다(20분 매치 ≈ 3.5GB). 복사본 폴더 이름은 원본과 **똑같이 `bg_<appid>_…`** 여야 한다(`RecordingSession.load()` 가 폴더명에서 시각을 읽는다). 격리는 상위 폴더로 한다.
- **부분 소실**: 남은 구간만 분석하고 없는 구간은 기록한다. 메타데이터 `sourceIncomplete: true` + 실제 세그먼트 범위, UI 에 표시.

## 4. 클립 범위·컷 (`pipeline/clip.py`)

- 배틀로얄: `교전 시작 - clip.prerollSec(5) ~ 교전 끝 + clip.postrollSec(8)`. `team_combat_unreliable` 구간은 프리롤 `clip.fixedPrerollSec(30)` 을 쓰고 `prerollSource="fixed"`.
- 코발트: 프리롤·포스트롤 없이 구간 그대로.
- `clip.mergeGapSec(10)` 보다 가까운 범위는 병합. **길이 상한 없음**(90초 상한이 126초 교전의 추격 장면을 잘라 2026-09-24 폐지).
- 컷은 필요한 세그먼트만 병합해 `ffmpeg -c copy`. 3초 키프레임 격자에 붙어 앞뒤로 최대 3초 늘어나고, 메타데이터에는 실제 경계를 남긴다.
- 썸네일: 클립 길이의 35% 지점, 폭 480 JPEG, `<clips>/.thumbs/`.
- 모든 subprocess 는 `procs.py` 도우미로 부른다(콘솔 창 숨김, 낮은 우선순위, 앱 종료 시 작업 개체로 함께 종료).

## 5. 생성 필터 (`pipeline/filters.py`)

- 기본 **전부 통과**. 프리셋 `won`(kill|assist)·`lost`(death)은 태그 포함 조건으로 환원.
- `filter.minDurationSec(4)` 보다 짧은 교전은 버리되 **킬·어시·사망 태그가 있으면 길이와 무관하게 남긴다**(1~2초 배지로 킬이 난 교전이 버려져 클립이 교전 한복판에서 끊기던 문제).
- 필터는 생성 단계에만 적용된다. 이미 지나간 경기는 원본이 남아 있을 때 다시 분석으로 반영.

## 6. 과거 녹화 분석 (백필, `pipeline/backfill.py`)

`Player.log` 는 최근 게임 실행 2번 분량만 알아서, 앱을 늦게 설치하면 스팀에 녹화가 남아 있어도 그 경기를 모른다. 사용자가 버튼(또는 첫 실행 화면의 "과거 녹화도 분석하기", 기본 선택)으로 실행한다.

1. **세션 스캔**(`session_scan.py`): 이터널 리턴 세션의 키프레임을 판독(캐시에 이어 씀) → VOD 와 같은 `split_games` 로 게임 구간.
2. **중복 제외**: **풀영상이 있는(또는 자동 정리로 지운) 게임**과 `Player.log` 가 아는 경기(처리 전 포함)와 겹치면 건너뛴다 — 감시와 겹치지 않게. 시작 전에 이전 버전 클립을 게임 기록으로 옮긴다(§11 이전 버전 게임 통합). 클립만 있는 옛 게임은 원본이 링버퍼에 남았으면 **풀영상·후보·마커만 새로 만들고 기존 클립은 다시 자르지 않는다**(`process_match(existing_clip_ids=…)`: 같은 ID 후보는 저장됨으로 표시, 이 경우 `saveMode` 와 무관하게 클립을 새로 자르지 않는다). 게임 기록 없이 휴지통·게임 기록(`.games`)에만 남은 경기는 처리된 것으로 본다. 단 **처리 이력에만 있고 현재 클립 폴더에 클립이 없는 경기는 건너뛰지 않는다**(클립 폴더를 바꾼 경우 등).
3. **처리**: 오래된 것부터, 경기 단위 **스테이징 폴더**에 다 만든 뒤 mp4 → 썸네일 → json 순으로 옮긴다(중간에 꺼져도 깨진 클립이 목록에 안 뜬다). 결과 화면은 `process_match(result_search_from=…)` 로 끝 뒤에서 앞으로. 실패 3번까지.
4. **취소 = 이어하기**: 롤백이 아니다. 완성된 클립은 유효하고, 다시 누르면 판독 캐시 지점부터.
5. 경계 보정: 화면 기준 시작은 로그보다 ~25초 늦고 끝은 ~10초 이르다(로딩·결과 화면). 끝에 여유를 주되 다음 경기 시작을 넘지 않는다.
6. **앞부분이 잘린 경기는 건너뛴다**(시작 시각이 계속 밀려 다른 키로 중복될 위험).
7. 진행률(`backfill_progress.py`): 스캔 작업량 = 영상 길이 ÷ 배속, 처리 작업량 = 게임 수 × 게임당 평균(최근 5개 이동 평균, 기본 80초). 화면 값은 단조 증가(`MonotonicProgress`). 스캔 중 게임 수는 세션 길이 ÷ 20분으로 추정.
8. 실측: 28배속 스캔(병목은 디스크 112MB/s), 경기당 60~100초. CPU 를 많이 써서 확인 창이 게임을 끄라고 안내한다.

## 7. 다시 분석 (`pipeline/reprocess.py`, `POST /api/games/reprocess`)

- 원본 존재와 종료 시각(`matchEndUtc` 또는 로그)을 확인한 뒤 새 클립을 **스테이징 폴더(`.staging/<uuid>`)에 만들고, 성공해야** 기존 클립을 설정 삭제 방식으로 지우고 옮긴다. 새로 만든 게 0개면 기존을 보존하고 오류. (파일명이 결정적이라 기존을 먼저 지우면 충돌한다.)
- 라벨 이관(`pipeline/label_migrate.py`): 같은 세션에서 3초 이상 겹치는 옛 클립 중 하나라도 pvp 면 pvp, 섞이면 pvp + `labelConflict`. 사용자가 새 클립에 직접 찍은 라벨은 덮어쓰지 않는다. 이관이 실패해도 새 클립은 유지.
- 수동 보정 잠금(`matchResultSource="manual"`)은 새 클립에 그대로 옮긴다.
- 한 번에 하나(`409`). 진행 중엔 `activity.py` 레지스트리(`kind="reprocess"`)에 올라 공통 활동 배너에 보인다.

## 8. 클립 메타데이터

클립 하나 = `<id>.json` + `<id>.mp4` + `.thumbs/<id>.jpg`. 클립 ID = 파일 이름(`20260920_134809_03` = 경기 시작 시각 + 번호, VOD 는 `vod_<vodId>_g<게임>_<시작초>`, 분할 조각 `<원본>-pN`).

```json
{
  "title": "3일차 낮 묘지 교전",
  "sessionDir": "bg_1049590_20260919_130747", "sessionStartUtc": "…", "matchStartUtc": "…", "matchEndUtc": "…",
  "clipUid": "b1f6c7e2…", "gameMode": "battle_royale", "sourceWidth": 2560, "sourceHeight": 1440,
  "segmentStart": 2782, "segmentEnd": 2795, "videoOffsetSec": 8343.0, "durationSec": 39.0,
  "thumbnailPath": ".thumbs/<id>.jpg", "sourceIncomplete": false,
  "combatStartOffsetSec": 8351.0, "combatEndOffsetSec": 8378.5, "prerollSource": "combat",
  "tags": ["kill"], "killDelta": 1, "assistDelta": 0, "died": false,
  "pvpScore": 1.0, "pvpSignals": ["kill_delta"], "teamWipe": null, "enemyRingMean": 0.4, "ultimateDelta": 0.3,
  "gameDay": 3, "dayNight": "day", "cobaltPhase": null, "region": "묘지", "phaseIndex": 4, "reviveCost": "credit",
  "myCharacter": null, "teamCharacters": [],
  "myCharacterPortraitPath": ".thumbs/…_portrait_me.jpg", "teammatePortraitPaths": ["…", "…"],
  "pinned": false, "matchKills": 4, "matchAssists": 9, "matchTeamKills": 18, "detectorConfidence": 0.94,
  "matchResult": {"matchType": "rank", "matchLabel": "랭크", "placement": 4, "total": 7, "outcome": "실험 종료",
                  "nickname": "…", "tk": 13, "kills": 3, "deaths": 1, "assists": 6, "imagePath": ".thumbs/…_result.jpg"},
  "matchResultSource": null,
  "userLabel": null, "labelNote": null, "labeledAt": null, "labelConflict": false,
  "trimmed": false, "originalDurationSec": null, "splitFrom": null
}
```

- `sessionDir` + `segmentStart/End` 가 있어야 원본을 다시 찾는다.
- `thumbnailPath`·`imagePath`·초상화 경로는 **클립 폴더 기준 상대경로**(`pipeline/clip_assets.py` 가 메타 위치 기준으로 찾고, 옛 절대경로도 그 폴더의 `.thumbs` 에서 파일명으로 찾는다) → 폴더를 옮겨도 안 깨진다.
- `myCharacter`/`teamCharacters` 는 캐릭터 OCR 폐기 후 항상 `null`/`[]`(옛 클립·전송 계약 호환용으로만 남김). 코발트는 초상화 경로가 비어 있다.
- `gameDay`/`dayNight` 와 `cobaltPhase` 는 모드별로 한쪽만 채워진다.
- `deletedAt` 은 없다(앱 휴지통 폐지).
- VOD 클립은 세션 필드 대신 VOD 필드를 쓴다 → [vod.md §3](vod.md). `source` 가 없으면 `steam`.
- 여러 구간이 한 클립으로 합쳐지면: 태그 합집합, 궁 델타는 최댓값, `team_combat_unreliable` 은 하나라도 있으면 유지, 코발트 페이즈·일차는 알려진 값 유지.

### 제목 (`orchestrator.default_title`, `pipeline/titles.py`)

- 배틀로얄 `N일차 낮/밤 <지역> 교전`, 코발트 `Phase N 교전 - k`(k 는 **페이즈별로 1부터**, `next_phase_clip_index`). 코발트는 우연히 읽힌 낮/밤을 절대 붙이지 않는다. 판독 실패 항목은 빠진다. 캐릭터 이름은 넣지 않는다.
- 자동 제목만 다시 만들고 사용자가 고친 제목은 건드리지 않는다.

### `clipUid` (`pipeline/clip_uid.py`)

- 여러 사용자의 라벨을 서버에서 합칠 전역 키. 새 클립은 `uuid4().hex`(하이픈 없음), 분할 조각은 `<부모>-<번호>`(조각의 조각 `…-1-3`, 기존 조각 최댓값 다음 번호). 계보가 값에 들어 있어 원본 필드를 따로 두지 않는다. 파일 이름은 바꾸지 않는다.
- 앱 시작 시 백그라운드로 스팀·VOD 클립과 라벨 보관소 사본에 없는 것만 채운다(임시 파일 → `os.replace`, 서버와 같은 락). `GET /api/clips` 도 안전망으로 채운다.
- **서버 전송에는 아직 쓰지 않는다**(서버 계약이 `clipUid`·`legacyClipId` 를 받기 전) — [plan.md](../plan.md).

## 9. 삭제·보관·자동 정리

- **삭제는 한 번에 끝난다**: Windows 휴지통(`Send2Trash`, pywin32 없이 동작) 또는 영구 삭제. 앱 자체 휴지통·유예 기간·복구 버튼은 없다(2026-09-28). 모든 삭제 경로(수동·게임 단위·자동 정리·다시 분석·분할 원본·VOD)가 `pipeline/delete_helper.py` 를 거친다. 휴지통을 못 쓰는 드라이브는 앱이 따로 처리하지 않는다.
- 옛 버전의 `clips/.trash` 는 첫 실행에 `pipeline/legacy_trash.py` 가 복구/Windows 휴지통/나중에 로 묻는다(비면 더 안 묻는다).
- **라벨 보관소**: 지우기 직전(방식 무관) `userLabel` 이 있는 클립은 경로 필드를 뺀 메타 사본을 `clips/.labels/<id>.json` 에 남긴다. 평가·전송의 자료다. `scan_clips` 는 하위 폴더를 안 보므로 목록에 안 뜬다.
- **게임 기록**(`pipeline/game_records.py`, `retention.keepGameRecords` 기본 켬): 클립이 다 지워져도 경기 요약(순위·모드·TK/K/A·결과표 이미지)을 `clips/.games/<경기키>.json` 에 남겨 "클립 삭제됨" 게임 행으로 보인다. 결과표를 못 읽은 경기는 요약하지 않는다. 기록만 지우려면 `DELETE /api/games/records/{id}`.
- **자동 정리**(`pipeline/game_cleanup.py`, 스팀 게임): 1시간마다 설정을 다시 읽어 **풀영상(`games/<경기키>/full.mp4`)** 에 나이(`matchStartUtc` 기준)·총 용량·개수 한도를 오래된 것부터 적용한다(선정 규칙은 `retention.select_for_auto_clean` 공용). **저장한 클립은 대상이 아니다.** 풀영상만 지우고 `game.json`(후보·마커·결과)과 결과·초상화 이미지는 남기며 `fullVideo:null`·`fullVideoDeletedAt` 을 기록한다. 고정(`game.json` 의 `pinned`)·보호 태그(후보 태그 합집합)는 제외. 방식 기본은 **영구 삭제**. 기본값은 자동 정리 **켬 + 총 용량 40GB**(새 설치만 — 저장된 설정은 그대로). `POST /api/cleanup {dryRun}` 로 미리보기·즉시 실행. 옛 클립 정리 함수(`cleanup.py::run_cleanup` 등)는 F5 까지 코드에 남아 있으나 아무도 부르지 않는다.
- **삭제 예정 미리 계산**(`pipeline/cleanup_registry.py`): 게임 기록 생성·정리 실행·설정 변경·앱 시작 때 `notify_clips_changed()` → 1.5초 디바운스로 실제 정리와 **같은 함수**로 재계산해 메모리에 캐시, `GET /api/cleanup/preview` 는 읽기만 한다. **키는 경기 키**(`YYYYMMDD_HHMMSS`)이고 나이 기준은 예정 시각을 같이 준다. 옛 클립 카드의 "삭제 예정" 배지는 이 키와 맞지 않아 더 뜨지 않는다(새 게임 목록이 대신한다, F4).
- **클립 폴더 이동**(`pipeline/move_clips.py`, `POST /api/clips-dir/move`, 202 + 진행률): mp4·json·썸네일·`.proxy`·`.games`·`.labels` 를 옮긴 뒤 설정을 바꾼다. 같은 이름 파일이 있거나 폴더가 겹치면 409 로 아무것도 안 옮긴다.

## 10. 트레이 앱 (`cli/app.py`)

- 트레이(메인 스레드) + 감시(데몬 스레드) + 열람 서버(첫 "열기" 때 기동, 이후 재사용)를 한 프로세스로.
- 트레이 "열기"는 **항상 기본 브라우저**를 연다(pystray 가 메인 스레드를 점유해 pywebview 와 충돌). 전용 창은 `cli.serve` 독립 실행에서만.
- 로그인 자동 시작(`autostart.py`, `HKCU\…\Run\LumiaBriefingRoom`): 빌드본이면 exe 경로, 소스면 `python -m lumia_briefing_room.cli.app`. 시작할 때마다 현재 명령으로 덮어쓴다.
- 중복 실행 방지(`single_instance.py`, 뮤텍스): 두 번째 실행은 기존 앱의 UI 를 열고 종료. 개발 앱과 빌드본이 뮤텍스를 공유한다(동시 실행은 `LUMIA_PROFILE` 로 분리 — `run-parallel.bat`).
- `app.lowPriority`: 앱 전체와 자식 ffmpeg 를 BELOW_NORMAL 로 돌려 게임 프레임 저하를 줄인다.

## 11. 게임 폴더·풀영상 (`pipeline/game_store.py`, `full_video.py`)

게임 하나 = `paths.games\<경기키>\`(경기키 = 게임 시작 시각 `YYYYMMDD_HHMMSS`, 클립 ID 앞부분과 같다).

```
full.mp4      게임 전체(-c copy, 원본 화질, 4GB/24분 실측)
game.json     결과·초상화·후보·마커·사용자 수정 자리(마지막에 원자적으로 씀 - 있어야 게임으로 본다)
result.jpg / portrait_{me,teammate1,teammate2}.jpg   클립 쪽 썸네일 폴더 사본
```

- **순서**(`process_match`): 검출 → **풀영상 컷(클립 컷보다 먼저 - 링버퍼가 원본을 지우기 전)** → 결과 화면·초상화 → 후보 이름 붙이기 → `clip.saveMode` 에 따라 클립 컷 → `game.json`. 후보가 0개인 게임도 풀영상과 `game.json` 은 남는다.
- **풀영상이 실패해도(디스크 부족·세그먼트 없음·ffmpeg 오류) 후보 기록과 클립 저장은 계속한다.** 컷 전에 원본 청크 크기로 필요 용량을 어림해 여유(+512MB)가 없으면 건너뛰고 `fullVideoError` 에 이유를 남기며 `on_full_video_error` 로 알린다. 이때는 `saveMode` 와 무관하게 **확실한 후보(킬·어시·사망 태그)만** 클립으로 저장한다.
- `clip.saveMode`: `auto`(기본, 후보 전부 클립으로 - 기존 방식) / `manual`(클립을 안 자름 - 수동 저장 UI 는 아직 없다).
- `game.json` 필드: `fullVideo{path,sizeBytes,durationSec,offsetSec,segmentStart/End,sourceIncomplete,audioStatus}`, `candidates[]`(시각은 풀영상 기준 초 - 후보 범위 `start/end`, 교전 `combatStart/End`, `certain`, 태그·pvp·지역·일차, `user{savedClipId}`), `userCandidates[]`(비어 있음), `markers[]{t,kind}`(kill/assist/death/teammate_death - 검출이 이미 읽는 값), 결과표·초상화 파일명. 풀영상 0초 = 세션 기준 `offsetSec`(첫 세그먼트 시작)라 후보 시각 = 세션 기준 시각 - `offsetSec`.
- 스테이징(다시 분석·백필)으로 클립만 옮기는 경우에도 `games/` 는 스테이징을 거치지 않고 바로 쓴다(같은 경기키를 덮어쓴다).
- 실측(2026-09-30, 스팀 녹화 24분 게임): 검출 + 풀영상 컷 + 클립 12개 전체 81초, 풀영상 4.02GB.

### 이전 버전 게임 통합 (`pipeline/legacy_games.py`)

풀영상 전환 전에 만든 클립(`clips/*.json`)과 게임 기록(`clips/.games/*.json`)을 `games/<경기키>/game.json` 으로 옮긴다. 경기키는 `matchStartUtc` 로 만든다.

- **언제**: 앱을 켠 뒤 `GET /api/games` 를 처음 부를 때(클립·게임 폴더 경로 조합마다 한 번). 시작 시 자동보다 옵션에서 경로를 바꾼 뒤에도 따라가고, 서버가 뜨는 동안 파일을 건드리지 않아서 이쪽이 안전하다. 몇 번 돌려도 같다.
- 한 게임(`sessionDir`+`matchStartUtc`)의 클립들 → 후보(저장됨, `user.savedClipId` = 클립 ID, 태그·점수·제목 그대로). 후보 시각은 세션 기준 오프셋에서 게임 시작을 뺀 값(풀영상이 없어 표시용). 결과·초상화·결과표 이미지는 게임 폴더로 복사한다(`result.jpg`, `portrait_*.jpg`).
- `legacy: true`, `fullVideo: null`, `fullVideoError` = "이전 버전에서 분석한 게임이라 풀영상이 없습니다". 자동 정리는 풀영상이 없는 폴더를 건너뛰므로 지워지지 않는다.
- **원본이 남은 옛 게임의 풀영상 만들기**(`pipeline/rebuild_full_video.py`): 과거 녹화 분석과 같은 처리(`process_match(existing_clip_ids=…)`)를 그 게임 하나에만 돌린다. `GET /api/games/{key}` 의 `canRebuildFullVideo`(풀영상이 없고 자동 정리로 지운 게임이 아니며, 시작 지점 세그먼트가 링버퍼에 남음) 가 참일 때 `POST /api/games/{key}/full-video`(202) 로 시작하고 `GET /api/games/{key}/full-video/status`(`state`: idle/running/done/error, `message`)로 본다. 한 번에 하나만. 저장한 클립은 그대로이고, 결과가 안 나오면 기존 게임 기록을 둔다. 다시 만든 `game.json` 은 새 후보·마커·결과로 덮이며 `pinned` 만 이어 간다(후보 ID 가 클립 ID 와 같으면 저장됨으로 이어진다).
- 이미 `game.json` 이 있는 경기, `full.mp4` 만 있는(자르는 중일 수 있는) 폴더는 건드리지 않는다. 옛 파일은 지우지 않는다. 클립이 모두 지워지고 게임 기록만 남은 경기는 후보 없는 게임이 된다.

### 게임 API (`api/game_routes.py`, F4 백엔드)

기존 클립 API 는 그대로 두고 새 경로만 둔다. `{key}` 는 경기 키(`YYYYMMDD_HHMMSS`, 형식이 아니면 404).

| 경로 | 동작 |
|---|---|
| `GET /api/games` | 최신순 요약: 결과, 초상화 파일명, `hasFullVideo`, 풀영상 크기·길이, 후보 수(무시 제외)·확실한 후보 수·저장한 클립 수·저장 안 된 범위 수정 수(`unsavedEditCount`), `pinned` |
| `GET /api/games/{key}` | `game.json` 전체 + `hasFullVideo` |
| `GET /api/games/{key}/video` | 풀영상 스트리밍(Range 지원, `FileResponse`). 없으면 404 |
| `GET /api/games/{key}/asset/{name}` | `result.jpg`, `portrait_{me,teammate1,teammate2}.jpg` 만 |
| `PATCH /api/games/{key}` | `{pinned}` (자동 정리에서 제외) |
| `PATCH /api/games/{key}/candidates/{id}` | 사용자 수정 → `candidates[].user`: `start`/`end`(영상 안, 1초 이상), `dismissed`, `label`(`combat`/`hunt`/null), `title`(클립 이름, 100자 이하, 빈 값 = 검출 이름으로 복귀; 이미 저장한 후보면 클립 json 의 title 도 바로 바꾼다 — 다시 자르지 않음). 자동 검출 값은 그대로 |
| `POST /api/games/{key}/candidates` | 직접 추가한 구간(`userCandidates`, ID `<키>_uN`) |
| `DELETE /api/games/{key}/candidates/{id}` | 직접 추가한 구간만 삭제(자동 후보는 "무시") |
| `POST /api/games/{key}/candidates/{id}/save` | 후보(조정한 범위)를 풀영상에서 `-c copy` 로 잘라 클립 저장 → `{clipId}`. 이미 저장했고 범위가 저장 당시와 같으면 다시 자르지 않고 기존 ID, **범위를 고쳤으면 같은 클립(파일·ID·제목·라벨·고정·`clipUid` 유지)을 새 범위로 다시 잘라 교체**. 풀영상이 없으면 409 |
| `POST /api/games/{key}/save` | 일괄 저장 `{mode: all\|certain\|ids, ids}` → `{saved[], failed[]}` (무시·저장된 후보 제외) |

- 클립 저장(`pipeline/clip_from_full.py`): 시작은 키프레임 격자 때문에 앞으로 최대 3초 당겨진다. 클립 메타데이터는 기존 클립과 같은 형식이라(세션 기준 오프셋 포함) 기존 화면·API 가 그대로 읽는다. 결과·초상화는 클립이 읽는 `.thumbs` 로 복사. 저장 후 `user.savedClipId` 와 저장에 쓴 범위 `user.savedStart/savedEnd` 를 남긴다(기록이 없는 옛 클립은 검출 범위로 만든 것으로 본다). 교체는 임시 파일에 잘라 `os.replace` 로 바꾼다.
- 실측(스팀 녹화 63초 풀영상 → 21초 구간 `-c copy`): HEVC + AAC 가 그대로 나오고 길이 21.02초.

## 12. 저장 공간 알림 (`pipeline/disk_space.py`, `disk_alert.py`, `notices.py`, `api/disk_routes.py`)

- **예상 게임 용량** = 최근 풀영상 5개(`game.json` 의 `fullVideo.sizeBytes`)의 평균, 기록이 없으면 분당 190MB × 15분.
- **부족 기준** = 여유 공간 < `max(예상 × 5, paths.minFreeGb)`. 문구는 남은 GB 와 해결책(풀영상 자동 정리 한도, 오래된 풀영상, 저장한 클립 정리)을 같이 준다.
- **재는 때**: 앱 시작(트레이 준비 뒤 백그라운드)과 게임 하나를 처리하기 직전(`cli/watch.py::make_processor`). 부족하면 `NoticeCenter`(메모리)에 `disk_low` 를 올리고 **트레이 알림**을 띄운다(같은 내용은 한 번만, 남은 GB 가 바뀌면 다시). 충분해지면 알림을 거둔다.
- 풀영상 컷이 실패하면 `full_video_failed` 알림(원인 문구 포함)을 올린다.
- API: `GET /api/disk`(여유 GB·경고 여부·권장 50~100GB 미만 여부, 잴 수 없으면 `available:false`), `GET /api/notices`, `POST /api/notices/{kind}/dismiss`, `GET /api/first-run` 에 `disk` 포함.

