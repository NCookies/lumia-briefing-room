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
- 썸네일: 클립 길이의 35% 지점, 폭 480 JPEG, `library\steam\.thumbs\`(클립 정보 폴더).
- 모든 subprocess 는 `procs.py` 도우미로 부른다(콘솔 창 숨김, 낮은 우선순위, 앱 종료 시 작업 개체로 함께 종료).

## 5. 생성 필터 (`pipeline/filters.py`)

- 기본 **전부 통과**. 프리셋 `won`(kill|assist)·`lost`(death)은 태그 포함 조건으로 환원.
- `filter.minDurationSec(4)` 보다 짧은 교전은 버리되 **킬·어시·사망 태그가 있으면 길이와 무관하게 남긴다**(1~2초 배지로 킬이 난 교전이 버려져 클립이 교전 한복판에서 끊기던 문제).
- 필터는 생성 단계에만 적용된다. 이미 지나간 경기는 원본이 남아 있을 때 다시 분석으로 반영.

## 6. 과거 녹화 분석 (백필, `pipeline/backfill.py`)

`Player.log` 는 최근 게임 실행 2번 분량만 알아서, 앱을 늦게 설치하면 스팀에 녹화가 남아 있어도 그 경기를 모른다. 사용자가 버튼(또는 첫 실행 화면의 "과거 녹화도 분석하기", 기본 선택)으로 실행한다.

1. **세션 스캔**(`session_scan.py`): 이터널 리턴 세션의 키프레임을 판독(캐시에 이어 씀) → VOD 와 같은 `split_games` 로 게임 구간.
2. **중복 제외**: **풀영상이 있는(또는 자동 정리로 지운) 게임**과 `Player.log` 가 아는 경기(처리 전 포함)와 겹치면 건너뛴다 — 감시와 겹치지 않게. 시작 전에 이전 버전 클립을 게임 기록으로 옮긴다(§11 이전 버전 게임 통합). 클립만 있는 옛 게임은 원본이 링버퍼에 남았으면 **풀영상·후보·마커만 새로 만들고 기존 클립은 다시 자르지 않는다**(`process_match(existing_clip_ids=…)`: 같은 ID 후보는 저장됨으로 표시, 이 경우 `saveMode` 와 무관하게 클립을 새로 자르지 않는다). 게임 기록 없이 휴지통·게임 기록(`.games`)에만 남은 경기는 처리된 것으로 본다. 풀영상을 새로 만든 게임의 시작이 옛 게임과 다르면(캐릭터 선택 확장으로 ~1분 앞당겨짐 - 실측) 키가 다른 새 게임이 되므로, **겹치는 옛 클립을 새 후보에 저장됨으로 이어 붙이고**(세션 기준 전투 구간이 겹치는 후보 하나에 클립 하나, `adopt_legacy_clips`) 옛 게임 기록에는 `supersededBy` 를 적어 목록에서 뺀다(지우지 않아 옛 클립에서 다시 만들어지지 않는다). 단 **처리 이력에만 있고 현재 클립 폴더에 클립이 없는 경기는 건너뛰지 않는다**(클립 폴더를 바꾼 경우 등).
3. **처리**: 오래된 것부터, 경기 단위 **스테이징 폴더**에 다 만든 뒤 mp4 → 썸네일 → json 순으로 옮긴다(중간에 꺼져도 깨진 클립이 목록에 안 뜬다). 결과 화면은 `process_match(result_search_from=…)` 로 끝 뒤에서 앞으로. 실패 3번까지.
4. **취소 = 이어하기**: 롤백이 아니다. 완성된 클립은 유효하고, 다시 누르면 판독 캐시 지점부터.
5. 경계 보정: 화면 기준 시작은 로그보다 ~25초 늦고 끝은 ~10초 이르다(로딩·결과 화면). 끝에 여유를 주되 다음 경기 시작을 넘지 않는다.
6. **앞부분이 잘린 경기는 건너뛴다**(시작 시각이 계속 밀려 다른 키로 중복될 위험).
7. 진행률(`backfill_progress.py`): 스캔 작업량 = 영상 길이 ÷ 배속, 처리 작업량 = 게임 수 × 게임당 평균(최근 5개 이동 평균, 기본 80초). 화면 값은 단조 증가(`MonotonicProgress`). 스캔 중 게임 수는 세션 길이 ÷ 20분으로 추정.
8. 실측: 28배속 스캔(병목은 디스크 112MB/s), 경기당 60~100초. CPU 를 많이 써서 확인 창이 게임을 끄라고 안내한다.

## 7. 다시 분석 (`pipeline/reprocess.py`, `POST /api/games/reprocess`)

- 원본 존재와 종료 시각(`matchEndUtc` 또는 로그)을 확인한 뒤 새 클립을 **스테이징 폴더(`<작업 폴더>/<uuid>` — 영상이 놓일 드라이브의 `.staging`, 정보와 영상이 함께 만들어진다)에 만들고, 성공해야** 기존 클립을 설정 삭제 방식으로 지우고 옮긴다. 새로 만든 게 0개면 기존을 보존하고 오류. (파일명이 결정적이라 기존을 먼저 지우면 충돌한다.)
- 라벨 이관(`pipeline/label_migrate.py`): 같은 세션에서 3초 이상 겹치는 옛 클립 중 하나라도 pvp 면 pvp, 섞이면 pvp + `labelConflict`. 사용자가 새 클립에 직접 찍은 라벨은 덮어쓰지 않는다. 이관이 실패해도 새 클립은 유지.
- 수동 보정 잠금(`matchResultSource="manual"`)은 새 클립에 그대로 옮긴다.
- 분석 대기열(§11)에서 한 번에 하나. 이 경로(옛 화면)도 **사용자가 보관한 클립은 지우지 않는다**(§9) - 그 게임의 `자동 보관` 클립만 새 클립으로 바꾼다(성공했을 때만). 새 클립이 보관한 클립과 3초 이상 겹치거나 ID 가 같으면 스테이징에서 지우고 만들지 않으며(`on_dropped` 로 받아 `game.json` 의 저장됨 표시를 뗀다 - 없는 클립을 가리키지 않게), 옛 경로 모드는 기존 클립이 전부 남는다. **ID 가 같으면 안 되는 이유**: 클립 ID 는 순번(`<시작 시각>_<NN>`)이라 검출이 달라지면 같은 ID 가 다른 구간을 가리키고, 그대로 옮기면 보관한 클립 파일을 덮어쓴다. 진행 중엔 `activity.py` 레지스트리(`kind="reprocess"`)에 올라 공통 활동 배너에 보인다.

## 8. 클립 메타데이터

클립 하나 = 정보 `<id>.json` + `.thumbs/<id>.jpg`(앱 데이터 `library\steam`·`libraryod`) + 영상 `<id>.mp4`(저장 폴더의 클립 영상 자리, 하위 폴더 어디든 - 탐색기에서 이름을 바꾸거나 옮겨도 이어진다, `pipeline/clip_files.py::link_all`). **이음 순서**: ① 영상 안 `clipUid` 태그(새 클립) ② 태그 없는 영상의 파일 이름 줄기 ③ 태그 없는 영상의 내용 지문 - 태그 없는 옛 클립은 앱이 켜질 때 (크기, 앞·뒤 1MiB 해시)를 정보의 `videoSizeBytes`·`videoFingerprint` 로 한 번 기록해 두고(`pipeline/clip_fingerprint.py`, 영상 읽기는 락 밖), 크기가 같은 영상만 읽어 대조한다. **앱이 만들지 않은 영상**(태그도 지문도 이어지는 정보도 없는 OBS 녹화 등)은 `source="other"` 클립으로 `GET /api/clips?source=all|other` 에 나온다(`api/unknown_clips.py`): ID `x_<내용 지문>`(옮겨도 같음, 같은 내용의 복사본은 `~<해시>`), 제목 = 파일 이름, 길이 = ffprobe(캐시), 썸네일 = 처음 볼 때 만들어 `library\steam\.thumbs` 에 캐시, 게임 정보·태그 없음. 제목·라벨을 고치면 그때 `x_<지문>.json` 이 생기고 그 뒤엔 지문으로 이어진다. 자르기·분할은 막고(409) 재생·내보내기·삭제(영상 파일만)는 된다. 같은 ID 태그의 복사본은 모두 보이되 경로순 첫째가 원래 ID, 나머지는 `<ID>~<경로 해시 6자>` 이고 정보(제목·태그·라벨)는 같은 json 을 같이 쓴다. 정보 폴더와 영상 폴더가 같은 작업 폴더·옛 테스트 구조에서는 정보 파일 옆 영상을 먼저 찾는다. 클립 ID = 파일 이름(`ClipSummary.video` 가 영상 경로)(`20260920_134809_03` = 경기 시작 시각 + 번호, VOD 는 `vod_<vodId>_g<게임>_<시작초>`, 분할 조각 `<원본>-pN`).

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
  "userLabel": null, "labelNote": null, "labeledAt": null, "labelConflict": false, "memo": null,
  "trimmed": false, "originalDurationSec": null, "splitFrom": null
}
```

- `sessionDir` + `segmentStart/End` 가 있어야 원본을 다시 찾는다.
- `thumbnailPath`·`imagePath`·초상화 경로는 **클립 정보 폴더(library) 기준 상대경로**(`pipeline/clip_assets.py` 가 메타 위치 기준으로 찾고, 옛 절대경로도 그 폴더의 `.thumbs` 에서 파일명으로 찾는다) → 폴더를 옮겨도 안 깨진다.
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
- **영상 안에도 넣는다**(`pipeline/mp4_tags.py`): 새 클립을 자를 때 `ffmpeg -c copy -metadata comment=lumia:clipUid=<ID>` 로 mp4 표준 `comment` 태그에 쓴다(스팀 컷·영상 클립 컷·풀영상에서 저장·교체 저장은 기존 ID 유지·분할 조각은 조각 자기 ID). `-movflags use_metadata_tags` 없이 들어가고 자르기(`-map 0 -c copy`)·복사·이름 바꾸기 뒤에도 남는다. 사용자 정의 키(`-metadata lumia_clip_uid=…`)는 그 옵션 없이는 조용히 버려지고 켜면 `major_brand` 가 중복되므로 쓰지 않는다. 읽기는 ffprobe(70ms)가 아니라 파이썬으로 mp4 상위 박스를 훑어 `moov/udta/meta/ilst/©cmt` 만 읽는다(1ms, 경로·크기·수정 시각으로 메모리 캐시). 옛 클립 mp4 는 다시 쓰지 않는다.
- **서버 전송에는 아직 쓰지 않는다**(서버 계약이 `clipUid`·`legacyClipId` 를 받기 전) — [plan.md](../plan.md).

## 9. 삭제·보관·자동 정리

- **사용자가 보관한 클립은 사용자가 직접 지우기 전에는 어떤 경로로도 지워지지 않는다**(2026-10-02). 직접 지우는 곳은 클립 탭의 삭제(폴더 삭제·나누기 포함)와 풀영상 화면의 보관 해제·클립 삭제(`unsave`)뿐이다. **판정은 `categories.is_user_archived(cfg, video)` 한 곳**: `자동 보관`(`AUTO_ARCHIVE_FOLDER`)이 아닌 카테고리의 클립이 사용자가 보관한 것이다(후보의 `archived`·게임 행 `savedClipCount` 도 같은 함수). **카테고리가 없는 옛 경로 모드는 구분할 수 없어 전부 보관한 것**으로 본다. 영상이 없는 클립 정보나 `clips\` 바로 밑의 클립은 보관한 것이 아니다(찌꺼기라 지운다). 이 판정을 쓰는 곳: 게임 행 `자동 보관 클립 삭제`·`게임 전체 삭제`(`delete_game_files`), 영상 파일 `전체 삭제`·`목록에서 완전히 삭제`·게임 삭제(`vods.split_by_archive`), 영상 파일 다시 분석(`vod_analyze._kept_clip_ids`), 스팀 다시 분석(`reanalyze_clips`), 옛 게임 다시 분석(`reprocess_game`, §7). 자동 정리는 처음부터 풀영상만 지운다. 일괄 삭제 응답은 `keptClips`(남긴 수)를 담고 게임 요약은 `autoClipCount`(지워질 `자동 보관` 클립 수)를 담아 확인 창이 "자동 보관 클립 N개를 삭제합니다. 보관한 클립 M개는 남습니다"를 적는다. **함정**: ① 지운 클립의 저장됨 표시만 뗀다(`_clear_saved_marks(keep=…)`) - 남긴 클립은 후보 연결을 유지한다. ② 게임 전체 삭제 뒤 남은 클립은 게임 기록 없이도 클립 탭에서 보이고 재생·삭제된다(정보는 library, 영상은 카테고리 폴더라 게임 폴더에 의존하지 않는다). ③ `게임 전체 삭제` 한 키는 `games\.deleted_games.txt`(`pipeline/deleted_games.py`)에 적어 두고 `migrate_legacy_games`·`migrate_legacy_vod_games` 가 건너뛴다 - 안 그러면 앱을 다시 켤 때 남은 클립(영상 게임은 색인)으로 게임 행이 되살아난다(2026-10-02 실측). ④ 테스트의 기본 `client`(`test_api_games`)는 옛 경로 모드라 "지워진다"를 보려면 카테고리 저장소(`test_api_categories.client`·`test_api_vods.cat_env`·`test_vod_analyze.make_cat_cfg`)에 `자동 보관` 클립을 만들어야 한다.
- **삭제는 한 번에 끝난다**: Windows 휴지통(`Send2Trash`, pywin32 없이 동작) 또는 영구 삭제. 앱 자체 휴지통·유예 기간·복구 버튼은 없다(2026-09-28). 모든 삭제 경로(수동·게임 단위·자동 정리·다시 분석·분할 원본·VOD)가 `pipeline/delete_helper.py` 를 거친다. 휴지통을 못 쓰는 드라이브는 앱이 따로 처리하지 않는다.
- 옛 버전의 `<클립 영상 폴더>/.trash` 는 첫 실행에 `pipeline/legacy_trash.py` 가 복구/Windows 휴지통/나중에 로 묻는다(비면 더 안 묻는다).
- **라벨 보관소**: 지우기 직전(방식 무관) `userLabel` 이 있는 클립은 경로 필드를 뺀 메타 사본을 `library\steam\.labels\<id>.json` 에 남긴다(영상 파일 클립은 `libraryod`). 평가·전송의 자료다. `scan_clips` 는 하위 폴더를 안 보므로 목록에 안 뜬다.
- **게임 기록**(`pipeline/game_records.py`, `retention.keepGameRecords` 기본 켬): 클립이 다 지워져도 경기 요약(순위·모드·TK/K/A·결과표 이미지)을 `library\steam\.games\<경기키>.json` 에 남겨 "클립 삭제됨" 게임 행으로 보인다. 결과표를 못 읽은 경기는 요약하지 않는다. 기록만 지우려면 `DELETE /api/games/records/{id}`.
- **자동 정리**(`pipeline/game_cleanup.py`, 스팀 게임): 1시간마다 설정을 다시 읽어 **풀영상(`games/<경기키>/full.mp4`)** 에 나이(`matchStartUtc` 기준)·총 용량·개수 한도를 오래된 것부터 적용한다(선정 규칙은 `retention.select_for_auto_clean` 공용). **저장한 클립은 대상이 아니다.** 풀영상만 지우고 `game.json`(후보·마커·결과)과 결과·초상화 이미지는 남기며 `fullVideo:null`·`fullVideoDeletedAt` 을 기록한다. 고정(`game.json` 의 `pinned`)·보호 태그(후보 태그 합집합)는 제외. 방식 기본은 **영구 삭제**. 기본값은 자동 정리 **켬 + 총 용량 40GB**(새 설치만 — 저장된 설정은 그대로). **삭제 직전 보존**(`retention.preserveBeforeDelete`, 기본 꺼짐, `pipeline/preserve_before_delete.py`): 켜면 지우기 직전 그 게임의 확실한(`certain`) 후보 중 무시하지 않았고 아직 저장 안 된 것을 게임 API 와 같은 `game_clip_save.save_and_mark` 로 클립 저장하고 `savedClipId` 를 남긴다(영상 게임은 영상 클립 폴더). **하나라도 실패하면 그 풀영상은 지우지 않고**(`GameCleanupPlan.held_back`) 다음 정리 때 다시 시도하며, 보존이 켜졌는데 보존 함수가 없어도 지우지 않는다. 미리보기 항목의 `preserveCount`·dry-run 의 `preserveClips` 는 남길 클립 수. `POST /api/cleanup {dryRun}` 로 미리보기·즉시 실행(`preserveClips`·`heldBack` 도 돌려준다). 옛 클립 정리 함수(`cleanup.py::run_cleanup` 등)는 F5 까지 코드에 남아 있으나 아무도 부르지 않는다.
- **삭제 예정 미리 계산**(`pipeline/cleanup_registry.py`): 게임 기록 생성·정리 실행·설정 변경·앱 시작 때 `notify_clips_changed()` → 1.5초 디바운스로 실제 정리와 **같은 함수**로 재계산해 메모리에 캐시, `GET /api/cleanup/preview` 는 읽기만 한다. **키는 경기 키**(`YYYYMMDD_HHMMSS`)이고 나이 기준은 예정 시각을 같이 준다. 옛 클립 카드의 "삭제 예정" 배지는 이 키와 맞지 않아 더 뜨지 않는다(새 게임 목록이 대신한다, F4).
- **클립 폴더 이동**(`pipeline/move_clips.py`, `POST /api/clips-dir/move`, 202 + 진행률): 영상 파일(하위 폴더 구조 그대로)과 재생용 변환 영상 `.proxy` 만 옮긴 뒤 설정을 바꾼다(정보는 앱 데이터 library 라 따라 옮기지 않는다). 같은 이름 파일이 있거나 폴더가 겹치면 409 로 아무것도 안 옮긴다.
- **저장 위치 바꾸기**(`pipeline/storage_migrate.py`, `api/storage_routes.py`): `GET /api/storage`(구조·저장 폴더·풀영상 위치·남은 공간·되돌리기 가능 여부·`recordingSameDisk{clips,fullVideos}` — 스팀 녹화 폴더와 같은 물리 디스크인지(`disk_identity.same_disk`), 참이면 옵션 저장 폴더 절에 "녹화와 다른 디스크로 옮기기"를 권하는 경고를 띄운다), `POST /api/storage/migrate {root, fullVideos?}`(202 + `GET /api/storage/migrate` 진행 바이트)가 옛 경로(또는 다른 저장 폴더)의 영상을 새 구조로 옮긴다: 클립 영상은 하위 폴더 구조 그대로, 풀영상은 게임 폴더째(`game.json` 은 폴더 안 마지막에), 재생용 변환 영상 포함. 영상 아닌 파일·작업 폴더는 안 옮기고 클립 정보(library)는 그대로다. 클립 영상 자리의 하위 폴더는 사용자가 만든 빈 폴더까지 구조 그대로 새 위치에 만들고(`.` 으로 시작하는 폴더 제외), 다 옮긴 뒤 비게 된 옛 폴더(옛 경로 모드의 `clips`·`vod`·`games`, 새 구조끼리 옮길 때의 `클립`·`풀영상`·`.cache`, 빈 작업 폴더)는 치운다. 사용자 파일이 남은 폴더와 저장 폴더 자체는 남긴다. 되돌리기는 빈 폴더도 되살린다. 같은 드라이브면 이름 바꾸기, 다르면 `.part` 로 복사 뒤 이름 바꾸기. 파일마다 `library\storage_migration.jsonl` 에 기록해 두 번 돌려도 같고 꺼져도 이어 한다. 목적지에 같은 이름이 있거나 새 폴더가 옛 폴더 안쪽이면 409 로 아무것도 안 옮기고, 게임 분석 같은 활동이 있으면 409. 끝나면 설정을 원자적으로 바꾼다(`root`·`fullVideos` 설정, 옛 `clips`·`vodClips`·`games` 비움). `POST /api/storage/undo` 는 기록을 거꾸로 돌려 파일과 옛 설정을 되돌리고, 원래 자리에 다른 파일이 생겼으면 거부한다. 새로 설치한 사용자는 시작할 때 기본 저장 폴더를 자동으로 잡는다(`adopt_default_root`).
- **정보 파일 이전**(`pipeline/library_migrate.py`, `cli/library_migrate.py`): 옛 클립 폴더의 `*.json`·`.thumbs`·`.labels`·`.games`·`.vods` 를 앱 데이터 `library\{steam,vod}` 로 옮긴다(영상·`.proxy` 제외). 파일마다 임시 복사 → 크기 확인 → `os.replace` → 원본 삭제 → `migration.jsonl` 기록이라 두 번 돌려도 같고 중간에 꺼져도 이어 한다. 내용이 다른 같은 이름이 있으면 `MigrationConflict` 로 아무것도 안 옮기고, 옛 `.trash`(옛 휴지통)는 건드리지 않는다 - 복원하면 정보 파일이 옛 자리로 돌아오므로 그 API 끝에서 다시 옮긴다. 비지 않은 `.staging` 은 그대로 둔다(중간 작업물이라 지우지 않는다). `undo_migration` 이 기록을 거꾸로 돌리되 원래 자리에 다른 파일이 생겼으면 거부한다. `create_app` 이 시작할 때 `library_startup.migrate_legacy_layout` 으로 옛 경로 모드의 두 폴더(스팀·영상 파일)를 옮기고, 실패하면 알림(`library_migration_failed`)을 올린다(앱은 켜진다). 읽는 코드는 전부 library(정보)와 영상 자리를 따로 본다.

## 10. 트레이 앱 (`cli/app.py`)

- 트레이(메인 스레드) + 감시(데몬 스레드) + 열람 서버(첫 "열기" 때 기동, 이후 재사용)를 한 프로세스로.
- 트레이 "열기"는 **항상 기본 브라우저**를 연다(pystray 가 메인 스레드를 점유해 pywebview 와 충돌). 전용 창은 `cli.serve` 독립 실행에서만.
- 로그인 자동 시작(`autostart.py`, `HKCU\…\Run\LumiaBriefingRoom`): 빌드본이면 exe 경로, 소스면 `python -m lumia_briefing_room.cli.app`. 시작할 때마다 현재 명령으로 덮어쓴다.
- 중복 실행 방지(`single_instance.py`, 뮤텍스): 두 번째 실행은 기존 앱의 UI 를 열고 종료. 개발 앱과 빌드본이 뮤텍스를 공유한다(동시 실행은 `LUMIA_PROFILE` 로 분리 — `run-parallel.bat`).
- `app.lowPriority`: 앱 전체와 자식 ffmpeg 를 BELOW_NORMAL 로 돌려 게임 프레임 저하를 줄인다.

## 11. 게임 폴더·풀영상 (`pipeline/game_store.py`, `full_video.py`)

게임 하나 = 풀영상 폴더(`games_steam`·`games_vod`, 옛 경로 모드는 `paths.games` 하나)의 `<경기키>\`(경기키 = 게임 시작 시각 `YYYYMMDD_HHMMSS`, 클립 ID 앞부분과 같다).

```
full.mp4      게임 전체(-c copy, 원본 화질, 4GB/24분 실측)
game.json     결과·초상화·후보·마커·사용자 수정 자리(마지막에 원자적으로 씀 - 있어야 게임으로 본다)
result.jpg / portrait_{me,teammate1,teammate2}.jpg   클립 쪽 썸네일 폴더 사본
```

- **순서**(`process_match`): 검출 → **풀영상 컷(클립 컷보다 먼저 - 링버퍼가 원본을 지우기 전)** → 결과 화면·초상화 → 후보 이름 붙이기 → `clip.saveMode` 에 따라 클립 컷 → `game.json`. 후보가 0개인 게임도 풀영상과 `game.json` 은 남는다.
- **풀영상이 실패해도(디스크 부족·세그먼트 없음·ffmpeg 오류) 후보 기록과 클립 저장은 계속한다.** 컷 전에 원본 청크 크기로 필요 용량을 어림해 여유(+512MB)가 없으면 건너뛰고 `fullVideoError` 에 이유를 남기며 `on_full_video_error` 로 알린다. 이때는 `saveMode` 와 무관하게 **확실한 후보(킬·어시·사망 태그)만** 클립으로 저장한다.
- **스팀 녹화가 멈춘 게임 표시**(`pipeline/recording_stop.py`): 스팀은 녹화가 밀리면 세션을 오류로 끝내고 게임을 다시 켤 때까지 녹화하지 않아, 그 뒤 게임은 끝난 세션 기준으로 처리된다. 세션의 마지막 조각이 게임 첫 조각보다 앞이면 `before`(녹화 없음), 게임 끝 조각보다 3개 넘게 모자라면 `during`(일부만 녹화)으로 보고 `game.json` 의 `recordingStopped` 에 남긴다. `before` 는 `fullVideoError` 를 "스팀 녹화가 이 게임 전에 멈춰…"로 쓰고, 둘 다 `on_recording_stopped` 로 "스팀 녹화가 멈췄습니다" 알림을 올리며(풀영상 실패 알림 대신) ERROR 로그로 남긴다. 표시가 없는 옛 기록은 API(`stopped_of_record`)가 오류 문구(`세그먼트를 찾을 수 없다`)·풀영상 끝 조각으로 어림한다. 게임 목록 행은 `스팀 녹화 오류로 녹화 없음`/`일부만 녹화` 배지, 결과가 없으면 제목 `녹화 없음`.
- **스팀이 녹화 중이면 복사 속도를 제한한다**(`pipeline/clip.py::copy_rate_for`, `video/throttle.py`): 녹화 폴더의 세션 폴더 중 하나라도 60초 안에 바뀌었으면 녹화 중으로 보고(`video/session.py::recording_in_progress` — `session.mpd` 의 `type="dynamic"` 은 스팀이 죽으면 남을 수 있어 안 본다) 풀영상·클립 컷이 세그먼트를 읽는 속도를 초당 32MB 로 묶고, 결과가 녹화와 **같은 물리 디스크**(`disk_identity.same_disk` — 드라이브 문자가 달라도 같은 HDD 파티션이면 같다)면 임시 폴더에 만든 뒤 같은 속도로 옮긴다. 제한 없이 몰아서 복사하면 스팀이 프레임을 버리다 2초 넘게 밀려 녹화 세션을 오류로 끝내고, 게임을 다시 켤 때까지 새로 녹화하지 않는다(스팀 `logs\streaming_log.txt` 의 `Ending game recording session due to error`). 검출(키프레임 디코딩)의 읽기는 아직 제한하지 않는다.
- `clip.saveMode`: `auto`(기본, 후보 전부 클립으로 - 기존 방식) / `manual`(클립을 안 자름 - 풀영상 화면에서 후보를 골라 저장).
- `game.json` 필드: `fullVideo{path,sizeBytes,durationSec,offsetSec,segmentStart/End,sourceIncomplete,audioStatus}`, `candidates[]`(시각은 풀영상 기준 초 - 후보 범위 `start/end`, 교전 `combatStart/End`, `certain`, 태그·pvp·지역·일차, `user{savedClipId}`), `userCandidates[]`(비어 있음), `markers[]{t,kind}`(kill/assist/death/teammate_death - 검출이 이미 읽는 값), 결과표·초상화 파일명. 풀영상 0초 = 세션 기준 `offsetSec`(첫 세그먼트 시작)라 후보 시각 = 세션 기준 시각 - `offsetSec`.
- 스테이징(다시 분석·백필)으로 클립만 옮기는 경우에도 `games/` 는 스테이징을 거치지 않고 바로 쓴다(같은 경기키를 덮어쓴다).
- 실측(2026-09-30, 스팀 녹화 24분 게임): 검출 + 풀영상 컷 + 클립 12개 전체 81초, 풀영상 4.02GB.

### 이전 버전 게임 통합 (`pipeline/legacy_games.py`)

풀영상 전환 전에 만든 클립 정보(`library\steam\*.json`)와 게임 기록(`library\steam\.games\*.json`)을 `games/<경기키>/game.json` 으로 옮긴다. 경기키는 `matchStartUtc` 로 만든다.

- **언제**: 앱을 켠 뒤 `GET /api/games` 를 처음 부를 때(클립·게임 폴더 경로 조합마다 한 번). 시작 시 자동보다 옵션에서 경로를 바꾼 뒤에도 따라가고, 서버가 뜨는 동안 파일을 건드리지 않아서 이쪽이 안전하다. 몇 번 돌려도 같다.
- 한 게임(`sessionDir`+`matchStartUtc`)의 클립들 → 후보(저장됨, `user.savedClipId` = 클립 ID, 태그·점수·제목 그대로). 후보 시각은 세션 기준 오프셋에서 게임 시작을 뺀 값(풀영상이 없어 표시용). 결과·초상화·결과표 이미지는 게임 폴더로 복사한다(`result.jpg`, `portrait_*.jpg`).
- `legacy: true`, `fullVideo: null`, `fullVideoError` = "이전 버전에서 분석한 게임이라 풀영상이 없습니다". 자동 정리는 풀영상이 없는 폴더를 건너뛰므로 지워지지 않는다.
- **분석 대기열**(`api/analysis_queue.py`, `app.state.analysis_queue`): 스팀 게임 `다시 분석`·`풀영상 만들기`, 옛 reprocess, 영상 파일 `분석`·`다시 분석`·`풀영상 만들기` 가 **앞 작업이 돌고 있어도 거부(409)하지 않고 줄을 선다**. 워커 하나가 요청 순서대로 한 번에 하나씩만 돌린다(동시 실행 없음). 응답·상태에 `state=queued` 와 `position`(1 = 지금 도는 작업 다음 차례)이 붙고, 시작할 때 `running` 이 된다. 같은 대상(스팀 `rebuild:<게임키>`·`reanalyze:<게임키>`, 영상 파일 `analyze:<vodId>`·`full:<vodId>:<게임 번호들>`)을 또 누르면 대기 중인 요청을 최신 것으로 바꾸고(자리 유지) 실행 중이면 줄 세우지 않고 202 로 그대로 둔다. **취소는 대기 중인 것만**: 영상 파일은 `POST /api/vods/{vid}/analyze/cancel`(실행 중이면 멈추고 아니면 줄에서 뺀다), 스팀은 `DELETE /api/games/{key}/queue`(실행 중이면 409). **실시간 감시와의 관계**: 감시는 줄에 들어오지 않고 자기 스레드에서 바로 돈다. 대기열은 감시가 게임을 처리하는 동안(`activity` 의 `watch`, 링버퍼가 원본을 지우기 전에 끝내야 한다) **다음 작업을 시작하지 않는다**(1초마다 확인). 이미 돌고 있는 작업은 멈추지 못해 CPU 경쟁은 남는다. 과거 녹화 분석(`/api/backfill`)은 따로 돌며 줄에 넣지 않는다(원래 이 작업들과 상호 배제가 아니었다). 대기 중인 영상은 목록에서 지울 수 없고(409), 저장 위치 이동·클립 폴더 이동은 대기열이 비어야 한다. 스팀 `다시 분석`은 원본도 풀영상도 없으면 줄에 넣지 않고 409. **줄이 길어지면 원본 녹화가 링버퍼에서 지워질 수 있다**: 대기 중에 `full` 이었던 게 실행 때 `candidates` 로 바뀌거나 실패할 수 있다(`mode` 는 실행 뒤 갱신된다).
- **원본이 남은 옛 게임의 풀영상 만들기**(`pipeline/rebuild_full_video.py`): 과거 녹화 분석과 같은 처리(`process_match(existing_clip_ids=…)`)를 그 게임 하나에만 돌린다. `GET /api/games/{key}` 의 `canRebuildFullVideo`(풀영상이 없고 자동 정리로 지운 게임이 아니며, 시작 지점 세그먼트가 링버퍼에 남음) 가 참일 때 `POST /api/games/{key}/full-video`(202) 로 시작하고 `GET /api/games/{key}/full-video/status`(`state`: idle/queued/running/done/error, `message`, 대기 중이면 `position`)로 본다. 분석 대기열에서 한 번에 하나. 저장한 클립은 그대로이고, 결과가 안 나오면 기존 게임 기록을 둔다. 다시 만든 `game.json` 은 새 후보·마커·결과로 덮이며 `pinned` 만 이어 간다(후보 ID 가 클립 ID 와 같으면 저장됨으로 이어진다).
- 이미 `game.json` 이 있는 경기, `full.mp4` 만 있는(자르는 중일 수 있는) 폴더는 건드리지 않는다. 옛 파일은 지우지 않는다. 클립이 모두 지워지고 게임 기록만 남은 경기는 후보 없는 게임이 된다.

### 영상 파일 게임

같은 `games/` 폴더에 `vod_<vodId>_g<번호>` 폴더로 들어가고 같은 게임 API·화면을 쓴다([vod.md §4](vod.md)). 구분: `game.json` 의 `source:"vod"`. `GET /api/games?source=steam|vod|all`(기본 steam)로 탭마다 따로 본다. 후보 저장은 풀영상에서 잘라 **영상 클립 폴더**(`paths.vodClips`)에 영상 클립 형식으로 만든다(`clip_from_full._vod_clip_metadata`). 영상 전체 삭제·목록에서 삭제·게임 삭제는 그 게임 폴더도 지운다(풀영상은 설정한 삭제 방식). 과거 결과 채우기 도구는 영상 게임을 건너뛴다.

### 게임 API (`api/game_routes.py`, F4 백엔드)

기존 클립 API 는 그대로 두고 새 경로만 둔다. `{key}` 는 경기 키(`YYYYMMDD_HHMMSS`, 형식이 아니면 404).

| 경로 | 동작 |
|---|---|
| `GET /api/games` | 최신순 요약(옛 스팀 게임은 `canRebuildFullVideo` 도): 결과, 초상화 파일명, `hasFullVideo`, 풀영상 크기·길이, 후보 수(무시 제외)·확실한 후보 수·보관한 클립 수(`savedClipCount`)·보관한 클립 중 범위를 고치고 아직 저장(반영)하지 않은 수(`unsavedEditCount` - 보관하지 않은 후보의 수정은 바로 기억되므로 세지 않는다), `pinned` |
| `GET /api/games/{key}` | `game.json` 전체(게임 폴더에 `portrait_<칸>.jpg` 가 남아 있는데 `game.json` 이 이름을 잃었으면 목록·상세 모두 그 이름을 채워 보여 준다) + `hasFullVideo`(+ 클립이 있는 후보마다 계산 값 `user.savedCategory`·**`user.archived`**(자동 보관이 아닌 카테고리에 있을 때만 true - `자동 보관` 의 클립은 파일은 있어도 어디에도 속하지 않은 것으로 본다, 옛 경로 모드는 클립이 있으면 true)·`user.savedMemo`) |
| `GET /api/games/{key}/video` | 풀영상 스트리밍(Range 지원, `FileResponse`). 없으면 404 |
| `GET /api/games/{key}/asset/{name}` | `result.jpg`, `portrait_{me,teammate1,teammate2}.jpg` 만 |
| `PATCH /api/games/{key}` | `{pinned}`(자동 정리에서 제외) · `{title}`(사용자 제목, 60자 이하, 빈 값 = 제목 없음 → `null`) · `{matchResult}`(**게임 정보 고치기**: `placement` 1~99·`outcome`·`matchType`(`rank`/`normal`/`unknown`)·`tk`/`kills`/`assists` 0~999 중 보낸 것만, 빈 값 = `null`; 코발트는 `outcome` 이 승리/패배만). 검증 실패는 400 이고 아무것도 바꾸지 않는다. 응답은 요약(`title`·`matchResultSource` 포함) |
| `PATCH /api/games/{key}/candidates/{id}` | 사용자 수정 → `candidates[].user`: `start`/`end`(영상 안, 1초 이상), `dismissed`, `label`(`combat`/`hunt`/null), `title`(클립 이름, 100자 이하, 빈 값 = 검출 이름으로 복귀; 이미 저장한 후보면 클립 json 의 title 도 바로 바꾼다 — 다시 자르지 않음). 자동 검출 값은 그대로 |
| `POST /api/games/{key}/candidates` | 직접 추가한 구간(`userCandidates`, ID `<키>_uN`) |
| `DELETE /api/games/{key}/candidates/{id}` | 직접 추가한 구간만 삭제(자동 후보는 "무시") |
| `POST /api/games/{key}/candidates/{id}/save` | 후보(조정한 범위)를 풀영상에서 `-c copy` 로 잘라 클립 저장(직접 보관) → `{clipId, category}`. 본문 `{category}` 로 카테고리를 고르고(없으면 `보관함`, 없는 이름이면 만든다) 옛 경로 모드는 카테고리 없이 `category: null`. 이미 저장했고 범위가 저장 당시와 같으면 다시 자르지 않고 기존 ID, **범위를 고쳤으면 같은 클립(파일·ID·제목·라벨·고정·`clipUid` 유지)을 새 범위로 다시 잘라 교체**. 풀영상이 없으면 409 |
| `POST /api/games/{key}/save` | 일괄 저장 `{mode: all\|certain\|ids, ids, category}` → `{saved[], failed[]}` (무시·저장된 후보 제외) |
| `PATCH /api/clips/{id}` `{memo}` | **클립 메모**(`memo`, `normalize_memo` - 최대 5,000자, 줄바꿈 유지, 빈 값 = 지움, 문자열이 아니면 400): 좋았던·아쉬웠던 점을 적는 개인 메모. 라벨 메모(`labelNote`, 500자, 전송 대상)와 **별개 필드**이며 서버로 보내지 않는다(`contract/app-metadata-fields.json` `excluded`, `test_local_clip_memo_is_never_sent`). 라벨을 해제해도 지워지지 않고, 범위를 고쳐 다시 저장(`_KEPT_ON_REPLACE`)해도 유지된다. 정보 파일(library)에 있어 영상을 옮기거나 이름을 바꿔도 `clipUid` 로 이어진다. 게임 상세는 보관한 후보마다 계산 값 `user.savedMemo` 를 붙인다 |
| `POST /api/games/{key}/candidates/{id}/unsave` | 클립 삭제(화면의 `클립 삭제`): 클립 영상을 `clipUid`/`savedClipId` 로 찾아 지우고(클립 탭 삭제와 같은 처리 - 라벨 보관·게임 기록 유지, 휴지통/영구는 `ui.deleteMode`) **그 구간(후보)도 목록에서 없앤다**(자동 후보는 `candidates`, 직접 추가한 구간은 `userCandidates` 에서 제거 - 되돌릴 수 없다, 2026-10-01 사용자 결정). 풀영상·다른 후보는 그대로. 클립이 없는 후보면 409. 응답 `{id, deleted:true}` |
| `GET /api/categories` | 클립 카테고리(= `clips\` 바로 아래 폴더) 목록 `{enabled, categories[{name, auto, default, clipCount, thumbnailClipId}]}`. `보관함`이 맨 앞, 사용자 카테고리(이름순), `자동 보관`(`auto`)이 맨 뒤이며 앞뒤 두 칸은 폴더가 없어도 항상 있고 목록을 읽을 때 폴더를 만들어 둔다(클립 탭이 열 수 있게). `thumbnailClipId` 는 그 카테고리에서 가장 최근에 만든 클립(썸네일은 `GET /api/clips/{id}/thumbnail`). 옛 경로 모드는 `enabled:false` |
| `POST /api/categories` | `{name}` 카테고리(폴더) 만들기 → 201. 이름 규칙은 클립 정리 탭 폴더와 같고(`.` 시작·경로 문자 400), 이미 있으면(기본 두 칸 포함) 409 |
| `POST /api/categories/move` | `{clipIds[], category}` 클립 영상을 그 카테고리로 옮긴다(없으면 만듦, 같은 이름이 있으면 ` (2)` 를 붙여 둘 다 둔다) → `{moved, category}`. 정보·라벨은 영상 태그·지문으로 이어져 그대로다 |
| `GET /api/games/{key}/reanalyze` | 다시 분석이 무엇을 하는지 `{mode: full\|candidates\|null}`: `full`(원본 스팀 녹화가 링버퍼에 남음 → 풀영상·후보·마커·결과표·초상화를 전부 새로 만든다), `candidates`(원본은 없지만 저장한 풀영상이 있음 → 풀영상에서 후보·마커·결과표·초상화만 다시 찾는다), `null`(둘 다 없음). 영상 파일 게임은 `null` |
| `POST /api/games/{key}/reanalyze` · `GET …/reanalyze/status` | 위를 분석 대기열로 실행(202, `{state: queued\|running\|done\|error\|idle, message, fraction, mode, position}`, 풀영상 만들기와 같은 줄 - 거부하지 않고 대기). `pipeline/reanalyze_game.py`: 새 결과는 작업 폴더(`full_video\.staging`)에 다 만든 뒤에만 영상 → 이미지 → `game.json` 순으로 바꿔치기해(브라우저가 읽는 중이면 재시도) 실패하면 기존 게임이 그대로다. **이어 붙이는 것**: 고정, 수동으로 고친 결과(`matchResultSource=manual`), 새로 못 읽은 결과·초상화는 이전 값, 직접 추가한 구간(새 풀영상의 시작이 달라졌으면 세션 시각 기준으로 옮김), **보관한 클립**(저장 범위가 겹치는 새 후보에 `savedClipId`·`savedStart/End` 와 사용자 범위로 이음 - 고친 것으로 보이지 않게, 겹치는 후보가 없는 클립은 직접 추가한 구간이 되어 목록에 남음). **초기화되는 것**: 자동 후보의 무시·이름·범위 수정. **자동 저장 클립 정리**(`pipeline/reanalyze_clips.py`, `reanalyze_one`): 사용자가 보관한 클립(`자동 보관` 카테고리가 아닌 곳)만 새 후보에 이어 붙이고, `자동 보관` 클립은 새 결과가 확정된 뒤 지운 다음 `clip.saveMode=auto` 면 보관되지 않은 후보를 새 풀영상에서 다시 자른다(`save_and_mark(manual=False)`). 카테고리가 없는 옛 경로 모드는 구분할 수 없어 지우지 않는다. 실패하면 기존 클립은 그대로이고, 못 만든 클립 수는 상태 `clipsFailed` 로 알린다. 원본이 없어 `candidates` 로 한 경우 화면이 "원본 녹화가 없어 저장된 풀영상에서 클립만 다시 추출했습니다"를 보인다. **영상 파일 게임도 같은 함수**(`reanalyze_game` 은 영상 게임의 원본을 찾지 않고 풀영상으로만 한다)로 다시 추출한다. `candidates` 방식은 영상 파일 분석과 같은 판독(`split_games`·`detect_games`·결과 화면·초상화 판독)을 풀영상 한 편에 돌리며 게임 화면을 못 찾으면 기존 후보를 그대로 둔다 |
| `POST /api/games/{key}/delete` | `{target: fullVideo\|clips\|both\|all}` → `{deletedFullVideo, deletedClips, keptClips, freedBytes}`. **`all` = 게임 전체 삭제**: 풀영상·`자동 보관` 클립에 더해 게임 폴더(`game.json`·결과표·초상화)와 `.games` 기록(`delete_record`)까지 지워 목록에서 사라진다 - 기록이 남으면 앱을 다시 켤 때 `migrate_legacy_games` 가 "풀영상 없음(이전 버전)" 게임으로 되살린다(연습 모드 게임 정리용). `fullVideo` 는 풀영상만(`delete_full_video` - 행은 "풀영상 삭제됨", 없으면 409), `clips` 는 **`자동 보관` 클립만**(사용자가 보관한 클립은 남기고 응답 `keptClips` 에 센다 - 아래 §9, 영상이 이미 없으면 지운 것으로 세지 않고 표시만 지운다), `both` 는 둘 다. `all` 이 아니면 게임 기록(결과·후보)은 남는다. 고정한 게임이어도 서버는 막지 않는다(경고는 화면이 한다) |

- **게임 정보·제목 직접 고치기**(`pipeline/game_edit.py`): 고친 결과는 `game.json` 의 `matchResultSource="manual"` 로 **게임 단위**에서 잠근다(옛 카드 뷰의 클립 단위 잠금과 같은 규칙). **잠금을 푸는 수단은 없다** - 사용자가 고친 값이 항상 이긴다(되돌리려면 다시 고친다). 소급 채우기(`game_backfill`)는 게임·클립 어느 쪽이든 `manual` 이면 `--force` 여도 건너뛰고, 다시 분석·풀영상 다시 만들기·영상 파일 다시 분석/업그레이드는 `carry_user_fields` 로 **고정·제목·잠근 결과**를 새 게임 기록에 이어 붙인다. 고칠 때 그 게임에서 만든 클립(후보에 연결된 클립 + 같은 경기의 옛 스팀 클립)의 `matchResult`·`matchResultSource` 도 같은 값으로 쓰고(클립 탭 결과가 어긋나지 않는다, 클립이 가진 결과 이미지 경로는 그대로), 고친 뒤 새로 보관하는 클립도 게임의 잠금을 이어받는다. 이전 버전 클립 통합(`legacy_games`)은 클립에 `manual` 이 있으면 게임도 잠근다. **제목**은 `game.json` 의 `title`(없으면 null) — 클립·후보 이름과 별개이고 영상 파일 게임의 `스트리머 · 게임 N`(`streamer`·`vodGameIndex`)도 건드리지 않는다. 화면은 사용자 제목이 있으면 그것을, 없으면 그 자동 제목을 머리줄에 보인다.
- 클립 저장(`pipeline/clip_from_full.py`): 시작은 키프레임 격자 때문에 앞으로 최대 3초 당겨진다. 클립 메타데이터는 기존 클립과 같은 형식이라(세션 기준 오프셋 포함) 기존 화면·API 가 그대로 읽는다. 결과·초상화는 클립이 읽는 `.thumbs` 로 복사. 저장 후 `user.savedClipId` 와 저장에 쓴 범위 `user.savedStart/savedEnd` 를 남긴다(기록이 없는 옛 클립은 검출 범위로 만든 것으로 본다). 교체는 임시 파일에 잘라 `os.replace` 로 바꾼다.
- 실측(스팀 녹화 63초 풀영상 → 21초 구간 `-c copy`): HEVC + AAC 가 그대로 나오고 길이 21.02초.

## 12. 저장 공간 알림 (`pipeline/disk_space.py`, `disk_alert.py`, `notices.py`, `api/disk_routes.py`)

- **예상 게임 용량** = 최근 풀영상 5개(`game.json` 의 `fullVideo.sizeBytes`)의 평균, 기록이 없으면 분당 190MB × 15분.
- **부족 기준** = 여유 공간 < `max(예상 × 5, paths.minFreeGb)`. 문구는 남은 GB 와 해결책(풀영상 자동 정리 한도, 오래된 풀영상, 저장한 클립 정리)을 같이 준다.
- **재는 때**: 앱 시작(트레이 준비 뒤 백그라운드)과 게임 하나를 처리하기 직전(`cli/watch.py::make_processor`). 부족하면 `NoticeCenter`(메모리)에 `disk_low` 를 올리고 **트레이 알림**을 띄운다(같은 내용은 한 번만, 남은 GB 가 바뀌면 다시). 충분해지면 알림을 거둔다.
- 풀영상 컷이 실패하면 `full_video_failed` 알림(원인 문구 포함)을 올린다.
- API: `GET /api/disk`(여유 GB·경고 여부·권장 50~100GB 미만 여부, 잴 수 없으면 `available:false`), `GET /api/notices`, `POST /api/notices/{kind}/dismiss`, `GET /api/first-run` 에 `disk` 포함.

