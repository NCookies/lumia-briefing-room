# 파이프라인 자동화 구현 계획 (SPEC 2단계)

> 대상: [SPEC.md §6 2단계](SPEC.md) — `Player.log` 감시 → 매치 종료 감지 → (이미 만든) 검출기 실행 →
> 필터 적용 → ffmpeg 컷 → 메타데이터/썸네일 저장까지 자동으로 잇는다.
> 1단계(검출기)는 [plan.md](plan.md) 에서 완료했다. 이 문서는 그 다음이다.

## 0. 진행 상태 (세션이 끊겨도 여기부터 이어간다)

- [x] 계획 수립
- [x] `config.py` — SPEC §7 전체 스키마, 기본값, JSON 로드/저장
- [x] `pipeline/playerlog.py` — 로그 파싱, 매치 경계 추출, tail follow
- [x] `pipeline/filters.py` — 생성 필터 적용 (§7.3)
- [x] `pipeline/clip.py` — ffmpeg 컷 + 썸네일
- [x] `pipeline/metadata.py` — 클립 메타데이터 JSON (§3 스키마)
- [x] `pipeline/orchestrator.py` — 위 전부를 잇는 `process_match()`
- [x] `cli/process_match.py` — 매치 하나를 수동으로 돌리는 CLI

**✅ 실제 녹화본으로 전체 파이프라인 end-to-end 검증 완료** (research §4.7 사망 시퀀스 구간):
검출 → 필터 → 컷 → 썸네일 → 메타데이터 JSON 까지 전부 실행돼 실제 클립(mp4)과
썸네일(jpg), 메타데이터(json)가 만들어졌다. 메타데이터의 `tags:["death"]`,
`dayNight:"day"`, `matchKills:2` 모두 이미 확인된 실제 사실과 일치했다.

이 과정에서 실제 버그 하나를 잡았다: `clips_dir` 를 오버라이드해도 썸네일 경로가
`cfg.paths.clips`(설정 파일 기본 경로) 를 따라가 **지정하지 않은 `%USERPROFILE%\Videos\...`
에 썸네일이 생기는 버그**였다. `_resolve_clip_paths()` 로 분리하고 회귀 테스트를 추가했다.
- [x] `pipeline/watcher.py` (판단 로직만) — remaining_margin/should_rescue/백로그 탐지/
  세션 찾기. **아직 없는 것: 실제 무한루프(`run_forever`) — tail_follow() 소비하며
  process_match() 호출하는 배선.**
- [x] `pipeline/watcher.py` 의 `rescue_copy()`, `resolve_buffer_minutes()`,
  `run_once()`, `run_forever()` — 전부 `process`/`now`/`sleep` 을 주입받는
  순수 함수라 무한루프·실시간 지연 없이 테스트했다
- [x] `cli/watch.py` — 실제 배선(진짜 `tail_follow`, 진짜 `process_match`, 진짜
  `RecordingSession`). `python -m lumia_briefing_room.cli.watch --recording-root ...`
  로 실행하면 부팅 시 백로그 복구 → 실시간 감시가 Ctrl+C 전까지 계속 돈다
- [x] **버그: 앱을 켠 뒤 게임을 (재)실행하면 그 게임의 경기를 하나도 못 뽑던 문제 (2026-09-22)** — `tail_follow` 가 처음 연 `Player.log` 핸들을 계속 쥐고 있었다. 게임이 다시 실행되면 로그가 새 파일로 바뀌거나 비워지는데, 핸들은 옛 파일 끝만 봐서 새 경기가 아무리 끝나도 로그에 새 줄이 안 보였다(23:41 앱 시작, 23:43 게임 실행, 23:48~00:02 경기 → 클립 없음, 앱 CPU 12시간 동안 4초). 이제 읽을 때만 파일을 열고 바이트 위치를 기억하며, 파일 ID 가 바뀌거나 크기가 줄면 처음부터 다시 읽는다(부분 줄은 줄바꿈이 올 때까지 보류, 파일이 잠깐 없어도 계속). 테스트 5건. 앱 재시작 시 백로그 복구(`discover_backlog`)가 놓친 경기를 처리한다
- [x] **버그: 결과 화면 찾기가 20분 넘게 걸려 클립이 안 생기던 문제 (2026-09-22)** — 클립은 결과 화면 판독이 끝나야 만들어지는데, 순위표가 보이면 `read_scoreboard` 가 캐릭터 이름을 못 읽은 **모든 행**(적 팀 포함)을 행마다 OCR 최대 54번씩 재시도했다(py-spy 로 `recover_character` 에서 도는 것 확인, 게임과 함께 돌면 행 하나에 수 분). 필요한 건 내 팀원 행뿐이라, 순위표는 재시도 없이 읽고(`recover=False`) 내 닉네임으로 팀이 정해진 뒤 `attach_board(recover=…)` 가 캐릭터가 빈 팀원만 다시 읽는다. 실제 경기(26분)로 결과 화면 찾기 14초, 테스트 3건
- [x] `pipeline/retention.py` — 휴지통 이동/복구/자동정리 (§7.6)
- [x] `autostart.py` — 레지스트리 Run 키 (실제 HKCU 레지스트리로 테스트, 정리까지 확인)
- [x] `tray.py` — 메뉴 구조(순수 테스트) + `pystray.Icon` 배선. 실제 이벤트루프
  (`icon.run()`)는 GUI라 테스트 불가 — 수동 확인 필요 (§3 확인 필요 참고)
- [x] `cli/app.py` — tray(메인 스레드) + watch(백그라운드 데몬 스레드)를 한 프로세스로,
  부팅 시 `ui.autoStart` 설정을 레지스트리에 반영. 감시 정지/재개 토글도 실제로
  멈추고 다시 시작한다(`make_watch_controller`) — §3-5 해결, 아래 참고
- [x] 열람 UI (SPEC 3단계) — FastAPI + React 로 완성. 자세한 내용은 [plan-ui.md](plan-ui.md) 참고

**SPEC §6 2단계(파이프라인 자동화)가 여기서 사실상 완료됐다.** `python -m
lumia_briefing_room.cli.app --recording-root ...` 하나로 트레이 상주 + 자동 시작 +
백로그 복구 + 실시간 감시 + 검출 + 컷 + 메타데이터까지 전부 돈다. 남은 건 SPEC
3단계(열람 UI)뿐이다.

**다음에 이어서 할 일 순서**: `pipeline/retention.py` (삭제/복구) → 트레이 앱 → UI.

**✅ `cli/watch.py` 도 실제 데이터로 end-to-end 검증했다.** 실제 `Player.log`(매치 23개)
+ 실제 녹화본으로 `discover_backlog → run_once → make_processor → (구출 복사) →
process_match` 를 통째로 돌렸다. 대상 매치는 남은 여유가 임계 이하라 **구출 복사가
실제로 트리거됐고**(`resolve_buffer_minutes` 가 120분으로 정확히 판단), 20분짜리
실제 매치에서 **클립 7개**(각 27~174초, 73MB~524MB)가 정상적으로 만들어졌다.
`died`/`dayNight` 값도 전부 그럴듯했다. 백로그 복구 경로 전체가 실제로 동작한다.

### `run_forever` 의 "직전 MATCH_START 기억" 문제 — 해소됨

우려했던 지점(앱 재시작 시 진행 중이던 매치를 놓치는 문제)은 `discover_backlog()` 의
기존 동작으로 그냥 풀렸다: `extract_matches()` 가 마지막 미완료 매치를 `end_utc=None`
으로 이미 돌려주므로, `cli/watch.py::run()` 이 그 값을 `initial_start_utc` 로
`run_forever()` 에 그대로 넘긴다. 앱이 매치 도중에 시작해도, 그 매치가 끝나면
실시간 감시가 정상적으로 잡는다. 별도 영속 상태가 필요 없었다.

## 1. 이번 회차에서 만든 것

```
src/lumia_briefing_room/
├── config.py                       (기존 discover_ffmpeg 유지) + Config 스키마 전체
├── pipeline/
│   ├── __init__.py
│   ├── playerlog.py                로그 라인 파싱 + 매치 경계 추출 + tail follow
│   ├── filters.py                  CombatInterval 목록에 filter.* 적용
│   ├── clip.py                     세그먼트 -> ffmpeg 컷 + 썸네일
│   ├── metadata.py                 CombatInterval -> 메타데이터 dict/JSON
│   └── orchestrator.py             process_match() — 위 전부 통합
└── cli/
    └── process_match.py            매치 하나를 수동 실행하는 CLI

tests/
├── test_config.py
├── test_playerlog.py
├── test_filters.py
├── test_clip.py
├── test_metadata.py
└── test_orchestrator.py
```

## 2. 설계 결정

### 2.1 config.py — camelCase JSON ↔ snake_case 파이썬

SPEC §7은 `paths.temp`, `watch.pollIntervalMs` 같은 **camelCase 점 표기**를 설정 파일 스키마로 못박아뒀다(사용자가 직접 열어 고칠 수도 있다고 명시). 파이썬 필드는 관례대로 snake_case 로 두고, JSON 파일만 camelCase 로 내보낸다.

```python
@dataclass
class PathsConfig:
    temp: Path | None = None            # None = 기본 위치 사용
    clips: Path | None = None
    ...

@dataclass
class Config:
    paths: PathsConfig = field(default_factory=PathsConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    clip: ClipConfig = field(default_factory=ClipConfig)
    encode: EncodeConfig = field(default_factory=EncodeConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    ui: UiConfig = field(default_factory=UiConfig)
```

`to_json_dict()` / `from_json_dict()` 가 camelCase 변환을 맡는다. **필드 전부를 선언하되, 이번 회차 파이프라인이 실제로 쓰는 건 일부다**(경로 해석, 필터, 클립 구간, 썸네일, 삭제 모드). `watch.pollIntervalMs`(실시간 감시), `retention.autoClean*`(자동 정리 스케줄), `ui.*`(UI 자체) 는 스키마만 있고 아직 소비하는 코드가 없다 — §0 체크리스트의 다음 항목들이 채운다.

**경로 해석**: `paths.temp` 등이 `None`(미지정)이면 SPEC §7.1의 기본 위치(`%LOCALAPPDATA%\Temp\LumiaBriefingRoom` 등)를 쓴다. `resolved_paths()` 가 `None`→기본값 치환과 `<clips>\.thumbs` 같은 상대 참조를 해석한다.

### 2.2 pipeline/playerlog.py

research.md §3.3 / SPEC §2.3 이 이미 정확한 라인 포맷을 확정해뒀다. 순수 파싱 함수와 실시간 tail 을 분리한다.

```python
@dataclass(frozen=True)
class MatchBoundary:
    start_utc: datetime
    end_utc: datetime | None   # None = 아직 진행 중(로그에 종료가 안 찍힘)

def parse_line(line: str) -> LogEvent | None: ...
def extract_matches(lines: Iterable[str], *, local_tz) -> list[MatchBoundary]: ...
def tail_follow(path: Path, *, poll_interval_sec: float) -> Iterator[str]: ...
```

- `parse_line` 은 SPEC §2.3 표의 정규식 매칭만 한다. `[LOADING][GAME]` → 매치 시작, `[LOADING][LOBBY]` → 매치 종료.
- **시각은 로그가 로컬 타임존이고 세션은 UTC다**(research §2.5). `extract_matches` 가 로컬→UTC 변환까지 맡아 이후 단계가 전부 UTC 만 다루게 한다.
- 첫 `[LOADING][GAME]` 앞에 끝나지 않은 매치가 있으면(로그 파일이 매치 도중에 시작함) 무시한다 — 시작을 모르는 매치는 처리할 수 없다.
- `tail_follow` 는 나중에 `pipeline/watcher.py` 가 쓴다. 이번 회차에서는 함수만 만들고 실시간 루프에 엮지 않는다(§0 체크리스트).

### 2.3 pipeline/filters.py — SPEC §7.3

`CombatInterval` 목록 + `FilterConfig` → 통과한 것만 남긴다. 순수 함수라 가장 테스트하기 쉽다.

```python
def apply_filter(intervals: list[CombatInterval], cfg: FilterConfig, *,
                  game_mode: str, phase_index: int | None) -> list[CombatInterval]:
```

프리셋(`all`/`won`/`lost`/`custom`)은 `custom` 의 개별 키 조합으로 환원해서 처리한다 — `won`은 `tags.include=["kill","assist"]`(OR), `lost`는 `tags.include=["death"]` 와 동일하게 내부적으로 변환.

### 2.4 pipeline/clip.py — 컷 + 썸네일

SPEC §3의 `[구간 확정]` ~ `[클립+썸네일+메타데이터 저장]` 박스.

```python
def resolve_clip_range(interval: CombatInterval, cfg: ClipConfig) -> tuple[float, float]:
    """교전 구간 -> 실제 컷 구간(초). §3 클립 구간 규칙 그대로."""

def merge_overlapping(ranges: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    """겹치거나 mergeGapSec 이내로 가까운 구간을 하나로 합친다."""

def cut_clip(session, seg_range: SegmentRange, out_path: Path, *, ffmpeg_path, include_audio) -> None:
    """필요한 세그먼트만 병합해 -c copy 로 자른다."""

def make_thumbnail(clip_path: Path, out_path: Path, *, offset_ratio: float, width: int, ffmpeg_path) -> None:
```

- `resolve_clip_range`: `prerollSec`/`postrollSec` 적용, `prerollSource` 결정(교전구간 있으면 `"combat"`, 없으면 `fixedPrerollSec` 로 `"fixed"`), `maxDurationSec` 상한.
- 컷 경계는 **3초 키프레임 격자에 맞춰 세그먼트 단위로 스냅**한다(SPEC §2.2/§3) — `segment_time_range()` 로 세그먼트 범위를 구하고 그 세그먼트들만 병합 후 `-c copy`.
- `cut_clip`/`make_thumbnail` 은 ffmpeg 서브프로세스라 `requires_ffmpeg` 통합 테스트, `resolve_clip_range`/`merge_overlapping` 은 순수 함수라 일반 테스트.

### 2.5 pipeline/metadata.py

SPEC §3 클립 메타데이터 스키마를 그대로 dict 로 만든다. `dayNight`/`gameDay`→`phaseIndex`→`reviveCost` 계산(§2.0 공식)도 여기서 한다.

```python
def phase_index(game_day: int, day_night: str) -> int:
    return (game_day - 1) * 2 + (0 if day_night == "day" else 1)

def revive_cost(phase: int) -> str:
    return "free" if phase <= 3 else "credit"

def build_metadata(...) -> dict: ...
def write_metadata(meta: dict, path: Path) -> None: ...
```

### 2.6 pipeline/orchestrator.py — `process_match()`

SPEC §3 다이어그램 전체를 하나로 잇는다. 지금까지 만든 걸 순서대로 호출만 한다 — 새 로직은 거의 없다.

```python
def process_match(
    session: RecordingSession,
    match_start: datetime,
    match_end: datetime,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    k_templates=None,
    a_templates=None,
) -> list[Path]:
    """매치 하나를 끝까지 처리해 만들어진 클립 메타데이터 경로 목록을 반환한다."""
```

1. `segment_time_range` 로 세그먼트 범위
2. `detect_match()` (1단계에서 완성) 로 `MatchDetection`
3. `apply_filter()` 로 생성 대상 추리기
4. 남은 교전마다 `resolve_clip_range` → `merge_overlapping` → `cut_clip` + `make_thumbnail`
5. `build_metadata` + `write_metadata`

### 2.7 pipeline/watcher.py — 실시간 감시 + 백로그

당초 스케치대로 `process`/`now`/`sleep` 을 주입받는 순수 함수로 짰다(§0 참고).
`rescue_copy()` 의 목적지 폴더명은 **원본과 똑같이** `bg_<appid>_...` 를 유지해야
한다 — `RecordingSession.load()` 가 폴더명 자체에서 appid/시작시각을 파싱하기
때문에, 구분을 위해 접두사/접미사를 붙이면 다시 못 읽는다(실제로 이 실수를
했다가 테스트로 잡았다). 격리는 `dest_root`(호출자가 고르는 상위 폴더)로 한다.

### 2.8 pipeline/retention.py — 휴지통

SPEC §7.6 그대로 "삭제 = 휴지통 이동"이다.

```python
def trash_clip(meta_path: Path, trash_dir: Path, *, now=...) -> Path: ...
def restore_clip(trashed_meta_path: Path, clips_dir: Path) -> Path: ...
def purge_expired(trash_dir: Path, *, trash_days: int, now=...) -> list[Path]: ...
def is_protected(meta: dict, cfg: RetentionConfig) -> bool: ...
def select_for_auto_clean(metas: list[dict], cfg: RetentionConfig, *, now=...) -> list[dict]: ...
```

- 클립 하나는 `<id>.json` + `<id>.mp4` + (있으면) `.thumbs/<id>.jpg` 세 파일이다.
  `trash_clip`/`restore_clip` 은 메타데이터의 `thumbnailPath` 를 보고 같이 옮기며,
  clips_dir 기준 상대 경로 구조(`.thumbs/...`)를 휴지통 안에서도 그대로 유지한다.
- `select_for_auto_clean` 은 실제 파일 스캔을 하지 않는다 — 호출 규약으로
  `meta["_created_at"]`(datetime), `meta["_size_bytes"]`(int) 를 요구한다.
  **실제 클립 목록을 스캔해서 이 두 필드를 채우는 계층은 아직 없다** — UI/CLI
  단계에서 만들 것 (§3 확인 필요에 추가하지 않은 이유: 순수 로직은 이미 완결돼
  있고 남은 건 "파일 mtime/크기 읽기"라는 뻔한 I/O 뿐이라 막는 게 아니다).
- 세 한도(maxAgeDays/maxTotalGB/maxCount)가 동시에 걸리면 순서대로 적용되고,
  같은 클립이 여러 조건에 걸려도 중복 선택되지 않는다. 최종 반환 순서는
  원래(오래된 것부터) 순서를 유지한다.

## 3. 확인 필요 (추측으로 메우지 않은 것)

### 3-1. `[LOADING][GAME]` 이 로그 시작 직후라 이전 매치 시작을 못 찾는 경우 — ✅ 해소됨

`discover_backlog()` 가 `Player-prev.log` 를 먼저, `Player.log` 를 그다음에 읽는다.
mtime 비교가 필요할 걱정을 했었는데 — **애초에 필요 없었다.** `Player-prev.log` 는
"그 이전 실행 전체", `Player.log` 는 "이번 실행 전체"라 파일 자체가 이미 시간순이다.
실제 로그로도 확인했다(§0 참고, 매치 23개 정상 추출).

### 3-2. 매치 종료 후 다음 세션의 `session.mpd` 가 어떤 상태인가

매치가 끝난 시점에 `session.mpd` 가 아직 `type="dynamic"`인지, 트리거 지연(`watch.delaySec`) 동안 바뀌는지 실측하지 않았다. `RecordingSession.load()` 는 이미 두 경우(dynamic/static) 를 다 처리하므로 **막지는 않지만**, 트리거 직후 바로 로드했을 때 세그먼트가 아직 `.tmp` 상태일 위험은 `watch.delaySec` 로 완화하는 것 외에 검증한 바 없다. 실제 `cli/watch.py` 를 며칠 실사용하며 확인할 것.

### 3-4. `localconfig.vdf` 파싱 — ✅ 해결됨 (덤으로 녹화 경로 자동탐지도 됨)

`src/lumia_briefing_room/steam_paths.py` 를 새로 만들었다:

- `find_steam_install_path()` — 레지스트리(`HKCU\Software\Valve\Steam\SteamPath`,
  실패 시 `HKLM\...\Valve\Steam\InstallPath`)에서 스팀 설치 위치를 찾는다.
  **이 PC 의 실제 레지스트리로 테스트함** (`c:\program files (x86)\steam`).
- `parse_vdf()` — 중첩 중괄호 기반 VDF 텍스트를 파싱하는 최소 재귀 파서.
  **이 PC 의 실제 `localconfig.vdf` 원문 조각을 그대로 테스트 픽스처로 씀**
  (tab 구분자, `\\` 이스케이프 포함).
- `read_buffer_minutes_override(steam_path, app_id)` — `GameRecording.
  PerGameSettings.<appid>.minutes` 를 찾는다. `resolve_buffer_minutes()` 에 배선:
  활성 세션이 없어도 **남아있는 세션 폴더 이름에서 appid 만은 뽑아** VDF 조회에
  쓴다 — session.mpd 가 없어도(오래돼서 지워졌어도) 폴더명(`bg_<appid>_...`)만
  있으면 이 폴백이 동작한다. 정말 세션 폴더가 하나도 없을 때만 120분 기본값으로
  떨어진다(이 경우는 원래 코멘트보다도 더 드물어졌다).
- `read_background_record_path()` / `discover_recording_root()` — 덤으로,
  `GameRecording.BackgroundRecordPath` 를 읽어 **녹화 폴더 자체도 자동으로
  찾게** 했다(원래 계획엔 없던 확장 — 사용자 요청: 다른 사람도 쓸 수 있게
  `--recording-root` 를 안 넣어도 되게). `cli/watch.py::run()` 이
  `--recording-root` → `paths.steamRecording` → `discover_recording_root()`
  순으로 폴백한다. **이 PC 에서 실제로 `H:\steam video\video` 를 정확히 찾아냄.**

여러 스팀 계정이 있으면(이 PC 는 2개) 값이 실제로 설정된 계정을 찾을 때까지
전부 훑는다 — research.md §1.1 에서 확인한 대로 계정마다 설정 여부가 다르다.

### 3-5. 트레이의 "감시 중" 토글이 실제로 감시를 멈추지 않는다 — ✅ 해결됨

`pipeline/playerlog.py::tail_follow()`/`_follow()` 에 `should_stop: Callable[[],
bool]` 을 추가했다 — 유휴 폴링(새 줄이 없을 때) 중에 `should_stop()` 이 참이면
제너레이터가 끝난다(이미 남아있는 줄은 멈추기 전에 마저 낸다). `run_forever()` 는
`for line in lines:` 가 자연히 끝나는 것으로 빠져나오므로 별도 수정이 필요 없었다.
`cli/watch.py::run()` 이 `should_stop` 을 받아 `tail_follow()` 에 그대로 넘기고,
`cli/app.py::make_watch_controller()` 가 `threading.Event` 를 만들어 tray 콜백
(정지→`event.set()`, 재개→새 감시 스레드 시작 + `event.clear()`)과 감시 스레드가
공유하게 배선했다. TDD로 확인: `tail_follow` 의 정지 동작(2건) +
`make_watch_controller` 의 시작/정지/자동시작(2건) 전부 테스트.

### 3-3. `cut_clip()` 의 오디오 먹싱 경로 — ✅ 실제 녹화본으로 검증됨

`tests/conftest.py` 의 합성 세션 픽스처는 비디오 트랙만 있어(오디오까지 만들려면
픽스처가 상당히 복잡해진다) 오디오 먹싱 분기가 합성 테스트로는 커버되지 않았다.

대신 **실제 녹화본으로 직접 확인했다.** research §4.7의 그 사망 시퀀스 구간을
`cut_clip()` 으로 잘라(`ClipRange(11450, 11495)`, 48초) 결과 파일을 열어봤다:

- HEVC 비디오 + AAC 오디오 둘 다 포함, 전체 디코딩 오류 없음(2875/2880 프레임)
- 중간 프레임을 뽑아 보니 **실제로 "팀원이 사망하였습니다" 장면, `K 2 A 5`** — research 가 기록한 바로 그 순간이 정확히 잘렸다
- `CutResult(segment_start=3817, segment_end=3832, duration_sec=48.0, source_incomplete=False)`

오디오 먹싱 경로가 실제 데이터로 동작함을 확인했다. 합성 테스트로 회귀를 못 잡는다는
한계는 남아있지만(§0 향후 과제로 오디오 있는 합성 픽스처를 만들면 해소된다), 기능 자체는 검증됐다.
