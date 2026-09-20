# 파이프라인 자동화 구현 계획 (SPEC 2단계)

> 대상: [SPEC.md §6 2단계](SPEC.md) — `Player.log` 감시 → 매치 종료 감지 → (이미 만든) 검출기 실행 →
> 필터 적용 → ffmpeg 컷 → 메타데이터/썸네일 저장까지 자동으로 잇는다.
> 1단계(검출기)는 [plan.md](plan.md) 에서 완료했다. 이 문서는 그 다음이다.

## 0. 진행 상태 (세션이 끊겨도 여기부터 이어간다)

- [x] 계획 수립
- [x] `config.py` — SPEC §7 전체 스키마, 기본값, JSON 로드/저장
- [ ] `pipeline/playerlog.py` — 로그 파싱, 매치 경계 추출, tail follow
- [ ] `pipeline/filters.py` — 생성 필터 적용 (§7.3)
- [ ] `pipeline/clip.py` — ffmpeg 컷 + 썸네일
- [ ] `pipeline/metadata.py` — 클립 메타데이터 JSON (§3 스키마)
- [ ] `pipeline/orchestrator.py` — 위 전부를 잇는 `process_match()`
- [ ] `cli/process_match.py` — 매치 하나를 수동으로 돌리는 CLI
- [ ] `pipeline/watcher.py` — 실시간 tail 감시 + 트리거 (§7.2, §7.2.1 백로그/구출)
- [ ] `pipeline/retention.py` — 휴지통 이동/복구/자동정리 (§7.6)
- [ ] 트레이 상주 + 자동 시작 (§6 2단계, `ui.autoStart`) — Windows 전용, `pystray`+레지스트리
- [ ] 열람 UI (SPEC 3단계) — 아직 손 안 댐. FastAPI + React, SPEC §4 참조

**다음에 이어서 할 일 순서**: `pipeline/watcher.py` (실시간 감시 루프) → `pipeline/retention.py` (삭제/복구) → 트레이 앱 → UI. 아래 각 절에 파일별 설계가 이미 있으니 순서대로 만들면 된다.

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

## 3. 확인 필요 (추측으로 메우지 않은 것)

### 3-1. `[LOADING][GAME]` 이 로그 시작 직후라 이전 매치 시작을 못 찾는 경우

`Player.log` 는 **현재 세션 것만** 들고 있고 `Player-prev.log` 가 그 이전 것이다(research §3.1). 두 파일을 모두 읽어야 백로그를 놓치지 않는데, **둘의 시각 순서를 어떻게 잇는지는 파일 자체에 나와 있지 않다**(파일 mtime 비교로 순서를 정해야 함). `extract_matches` 는 지금 파일 하나만 받는다 — 여러 파일을 이어붙이는 건 `pipeline/watcher.py` 단계에서 다룬다.

### 3-2. 매치 종료 후 다음 세션의 `session.mpd` 가 어떤 상태인가

매치가 끝난 시점에 `session.mpd` 가 아직 `type="dynamic"`인지, 트리거 지연(`watch.delaySec`) 동안 바뀌는지 실측하지 않았다. `RecordingSession.load()` 는 이미 두 경우(dynamic/static) 를 다 처리하므로 **막지는 않지만**, 트리거 직후 바로 로드했을 때 세그먼트가 아직 `.tmp` 상태일 위험은 `watch.delaySec` 로 완화하는 것 외에 검증한 바 없다.

이 둘 다 `pipeline/watcher.py`(다음 작업)에서 실측하며 확정한다.
