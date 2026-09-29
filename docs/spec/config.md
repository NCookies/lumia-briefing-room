# 설정

> 원본은 `src/lumia_briefing_room/config.py`. 파일은 `%APPDATA%\LumiaBriefingRoom\config.json`(camelCase 점 표기, 파이썬 필드는 snake_case). 전부 기본값이 있어 아무것도 안 건드려도 동작한다. UI 에서 편집하고 직접 고쳐도 된다.
>
> **"미사용"** 표시 키는 스키마에만 있고 읽는 코드가 없다. 기능을 만들 때 쓰거나 지운다.

## 경로 `paths.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `paths.clips` | `%USERPROFILE%\Videos\LumiaBriefingRoom\clips` | 스팀 클립. 썸네일 `.thumbs`, 프록시 `.proxy`, 라벨 보관소 `.labels`, 게임 기록 `.games` 가 그 아래 |
| `paths.vodClips` | `…\LumiaBriefingRoom\vod` | 영상 파일 클립(스팀과 섞지 않는다). `.thumbs`·`.vods` |
| `paths.temp` | `%LOCALAPPDATA%\Temp\LumiaBriefingRoom` | 구출 복사·병합 중간물·처리 이력. 클립 폴더와 드라이브가 다르면 최종 이동이 복사가 된다 |
| `paths.exportDefault` | `%USERPROFILE%\Videos` | 저장 창 시작 위치. 저장할 때마다 갱신 |
| `paths.steamRecording` | 자동 탐지 | 탐지 실패 시 수동 |
| `paths.thumbnails` | `<clips>\.thumbs` | |
| `paths.proxies` | `<clips>\.proxy` | 미사용 — 프록시는 항상 `<클립 폴더>\.proxy` |
| `paths.minFreeGB` | 20 | 미사용 — 풀영상 부족 알림에서 쓸 예정([plan-fullvideo.md](../plan-fullvideo.md)) |

## 감시 `watch.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `watch.playerLog` | 자동 탐지 | |
| `watch.pollIntervalMs` | 1000 | 로그 폴링 간격 |
| `watch.delaySec` | 5 | 경기 종료 후 대기(`.tmp` 확정) |
| `watch.bufferMinutes` | `auto` | 링버퍼 길이([game.md §6](game.md)) |
| `watch.processBacklog` | `true` | 앱이 꺼져 있던 동안 끝난 경기도 처리 |
| `watch.rescueThresholdMin` | 20 | 남은 여유가 이 이하면 원본을 먼저 복사 |
| `watch.triggerOn` | `lobby_return` | 미사용 |
| `watch.retryCount` | 3 | 미사용 — 재시도 횟수는 코드 상수 3 |

## 생성 필터 `filter.*` (기본 전부 통과)

| 키 | 기본값 | 설명 |
|---|---|---|
| `filter.preset` | `all` | `all`/`won`(kill\|assist)/`lost`(death)/`custom` |
| `filter.tags.include` / `.exclude` | `[]` | |
| `filter.phaseMin` / `phaseMax` | `null` | `phaseIndex` 범위 |
| `filter.dayNight` | `any` | |
| `filter.reviveCost` | `any` | `free`(≤3)/`credit`(≥4) |
| `filter.minPvpScore` | 0.0 | 이 점수 미만은 만들지 않는다. **라벨로 검증되기 전까지 0**(생성에서 버리면 영구 손실) |
| `filter.pvpWeights` | `{enemyRings: 0, death: 0.9, teammateDeath: 0.8, teammateDeathSplit: 0.5, ultimateUsed: 0.75}` | 킬/어시는 항상 1.0. 고친 뒤 `tools/rescore_clips.py` |
| `filter.minDurationSec` | 4 | 킬·어시·사망 태그가 있으면 무시 |
| `filter.maxDurationSec` | `null` | |
| `filter.gameMode` | `any` | `battle_royale`/`cobalt` |
| `filter.myCharacter` | `[]` | 폐기(캐릭터 이름 인식 안 함) |

영상 파일 분석도 같은 필터·클립 설정을 쓴다.

## 클립 구간 `clip.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `clip.mode` | `combat` | `combat`/`fixed` |
| `clip.prerollSec` / `postrollSec` | 5 / 8 | 코발트는 적용 안 함 |
| `clip.fixedPrerollSec` | 30 | `fixed` 모드, 팀 전투 신호 포화 구간 |
| `clip.mergeGapSec` | 10 | |
| `clip.includeAudio` | `true` | |
| `clip.snapToKeyframe` | `true` | 미사용 — 항상 `-c copy` |

## 인코딩 `encode.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `encode.proxy.prefetch` | `true` | 프록시 모드에서 다음 클립 프록시를 미리 |
| `encode.proxy.height` | 1080 | 원본보다 키우지 않는다 |
| `encode.proxy.crf` | 23 | `libx264` 일 때만. `h264_mf` 는 비트레이트(1080p 8000k, 면적 비례, 최소 1500) |
| `encode.proxy.enabled` | `false` | 미사용 — 프록시는 재생 불가 판별 시 자동 |
| `encode.thumbnail.enabled` / `offsetRatio` / `width` | `true` / 0.35 / 480 | |
| `encode.reencode` | `false` | 미사용 |

## 보관·자동 정리 `retention.*` (스팀 클립만)

| 키 | 기본값 | 설명 |
|---|---|---|
| `retention.autoCleanEnabled` | `false` | |
| `retention.maxAgeDays` / `maxTotalGB` / `maxCount` | `null` | 기준별, `null` = 미적용 |
| `retention.deleteMode` | `permanent` | 자동 정리 전용(`recycle`/`permanent`) |
| `retention.protectPinned` | `true` | |
| `retention.protectTags` | `[]` | 기본은 고정만 보호(2026-09-25 변경, 기존 설정은 유지) |
| `retention.keepGameRecords` | `true` | 클립이 다 지워진 경기 요약·결과표를 `.games` 에 남김 |

## 내보내기 `export.*` — 전부 미사용

`copyMetadata`(true), `copyThumbnail`(true), `mode`(`copy`), `nameTemplate`(`{date}_{title}`). 지금 저장은 mp4 만 복사한다.

## UI `ui.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `ui.port` | 8765 | 80 을 먼저 시도하고, 점유 시 이 값 → +20. `auto` 는 8765 와 같다 |
| `ui.startMinimized` | `true` | 트레이로 시작 |
| `ui.autoStart` | `true` | 레지스트리 Run 키. 저장 즉시 반영 |
| `ui.deleteMode` | `recycle` | 수동 삭제 방식 |
| `ui.confirmDelete` | `true` | 삭제 확인 창 |
| `ui.shell` | `webview` | `cli.serve` 독립 실행에서만 의미 |
| `ui.defaultView`, `ui.titleTemplate`, `ui.language`, `ui.theme` | | 미사용 |

## 앱 `app.*`, 플레이어 `player.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `app.mode` | `auto` | `dev`/`release` 강제 |
| `app.lowPriority` | `true` | 앱·ffmpeg BELOW_NORMAL |
| `player.nickname` | `""` | 비면 감시가 첫 결과 화면에서 채운다(사용자 입력은 덮어쓰지 않음, VOD 는 채우지 않음) |

## 영상 파일 `vod.*`

| 키 | 기본값 | 설명 |
|---|---|---|
| `vod.sources` | `[]` | 파일·폴더 경로 |
| `vod.recursive` | `false` | |
| `vod.gameGapSec` / `minGameSec` | 30 / 60 | 게임 분할 |
| `vod.hwaccel` | `null` | 디코딩 가속(과거 녹화 분석도 이 값) |
| `vod.streamers` / `videoDates` | `{}` | 영상별 스트리머 표시명 / 사용자가 고친 날짜 |
| `vod.deleteSourceAfter` | `ask` | `ask`/`always`/`never` |
| `vod.deleteSourceMode` | `trash` | `trash`/`permanent` |
| `vod.autoAnalyze` | `false` | 미사용 |

## 업데이트·전송·동의

| 키 | 기본값 | 설명 |
|---|---|---|
| `consent.version` | 0 | 답한 동의 화면 버전(현재 3) |
| `update.check` | `false` | 자동 업데이트 확인 |
| `telemetry.sendLabels` / `sendLogs` | `false` | |
| `telemetry.installId` | 무작위 UUID | 익명 설치 ID |
| `telemetry.serverUrl` / `apiToken` | `""` | 개발·시험용 덮어쓰기(진단 zip 에서 토큰 제외) |
| `telemetry.allowDevSend` | `false` | 개발 모드 전송 허용(`mode=dev`) |

## 디스크 감각

- 스팀 버퍼 2시간 ≈ 17~23GB(스팀이 점유).
- 클립 60~80MB/개, 매치당 0.4~0.8GB(분당 약 190MB). `retention.maxTotalGB` 를 권한다.
- 프록시는 원본의 대략 1/4~1/5.
