"""전송 계약(`contract/receiver.schema.json`)의 서버 쪽 구현. 필드 이름·제약을 바꾸면 계약 파일도 같이 고친다.

허용 목록에 없는 필드는 검증 단계에서 버려지고, 버려진 필드 이름은 `context["dropped"]` 에 모인다(집계용, 값은 남기지 않는다).
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, model_validator

Mode = Literal["dev", "release"]
HexKey = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
ShortName = Annotated[str, StringConstraints(max_length=64)]
SchemaVersion = Annotated[int, Field(ge=1, le=1000)]


class _Allowlist(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _record_dropped(cls, data, info: ValidationInfo):
        if isinstance(info.context, dict) and isinstance(data, dict):
            info.context.setdefault("dropped", set()).update(data.keys() - cls.model_fields.keys())
        return data


class Label(_Allowlist):
    userLabel: Literal["combat", "other"]
    labelSource: Literal["user", "migrated"] | None = None
    labelNote: str | None = Field(default=None, max_length=500)
    labelConflict: bool | None = None
    labeledAt: str | None = Field(default=None, max_length=40)
    matchKey: HexKey
    clipKey: HexKey
    source: Literal["recording", "vod"] | None = None

    gameMode: str | None = Field(default=None, max_length=32)
    sourceWidth: int | None = Field(default=None, ge=1, le=20000)
    sourceHeight: int | None = Field(default=None, ge=1, le=20000)
    sourceIncomplete: bool | None = None
    prerollSource: str | None = Field(default=None, max_length=32)
    audioStatus: str | None = Field(default=None, max_length=32)

    durationSec: float | None = Field(default=None, ge=0)
    combatStartOffsetSec: float | None = Field(default=None, ge=0)
    combatEndOffsetSec: float | None = Field(default=None, ge=0)

    tags: list[Annotated[str, StringConstraints(max_length=64)]] = Field(default_factory=list, max_length=32)
    pvpScore: float | None = Field(default=None, ge=0, le=1)
    pvpSignals: list[ShortName] = Field(default_factory=list, max_length=64)
    pvpSignalValues: dict[ShortName, float] | None = Field(default=None, max_length=64)
    teamWipe: str | None = Field(default=None, max_length=32)
    enemyRingMean: float | None = None
    ultimateDelta: float | None = None
    killDelta: int | None = None
    assistDelta: int | None = None
    died: bool | None = None
    detectorConfidence: float | None = None

    region: str | None = Field(default=None, max_length=64)
    gameDay: int | None = None
    dayNight: str | None = Field(default=None, max_length=16)
    phaseIndex: int | None = None
    reviveCost: str | None = Field(default=None, max_length=16)

    myCharacter: str | None = Field(default=None, max_length=64)
    matchKills: int | None = Field(default=None, ge=0)
    matchAssists: int | None = Field(default=None, ge=0)
    matchTeamKills: int | None = Field(default=None, ge=0)


class LabelBatch(_Allowlist):
    installId: UUID
    appVersion: str = Field(max_length=32)
    schemaVersion: SchemaVersion
    mode: Mode
    labels: list[Label] = Field(max_length=500)


class Environment(_Allowlist):
    appVersion: str = Field(max_length=32)
    os: str = Field(max_length=128)
    resolution: str | None = Field(default=None, max_length=32)
    displayScale: float | None = Field(default=None, ge=0)
    aspectRatio: str | None = Field(default=None, max_length=16)
    codec: str | None = Field(default=None, max_length=32)
    cpuModel: str | None = Field(default=None, max_length=128)
    cpuCores: int | None = Field(default=None, ge=1)
    gpuName: str | None = Field(default=None, max_length=128)
    memoryMb: int | None = Field(default=None, ge=1)
    hwaccel: bool | None = None
    hevcPlayable: bool | None = None
    ffmpegBuild: str | None = Field(default=None, max_length=64)
    proxyEncoder: str | None = Field(default=None, max_length=32)
    steamBufferMinutes: int | None = Field(default=None, ge=0)
    locale: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    analysisTimeRatio: float | None = Field(default=None, ge=0)
    proxyBuildSec: float | None = Field(default=None, ge=0)
    readFailStats: dict[ShortName, int] = Field(default_factory=dict, max_length=64)


class LogEntry(_Allowlist):
    ts: str = Field(max_length=40)
    level: str = Field(max_length=16)
    logger: str | None = Field(default=None, max_length=128)
    message: str = Field(max_length=2000)
    exceptionType: str | None = Field(default=None, max_length=128)
    stack: str | None = Field(default=None, max_length=8000)
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{16,64}$")


class LogBatch(_Allowlist):
    installId: UUID
    schemaVersion: SchemaVersion
    mode: Mode
    env: Environment
    entries: list[LogEntry] = Field(max_length=2000)


class DiagnosticBundle(LogBatch):
    displayId: str = Field(pattern=r"^LUMIA-[0-9A-Z]{4}-[0-9A-Z]{4}$")
