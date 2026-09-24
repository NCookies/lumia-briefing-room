from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Allowlist(BaseModel):
    """허용 목록에 없는 필드는 검증 단계에서 조용히 버려진다."""

    model_config = ConfigDict(extra="ignore")


class Label(_Allowlist):
    userLabel: Literal["pvp", "hunt", "none"] | None = None
    labelSource: str | None = Field(default=None, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=32)
    pvpScore: float | None = Field(default=None, ge=0, le=1)
    pvpSignals: list[str] = Field(default_factory=list, max_length=64)
    teamWipe: str | None = Field(default=None, max_length=32)
    enemyRingMean: float | None = None
    region: str | None = Field(default=None, max_length=64)
    durationSec: float | None = Field(default=None, ge=0)
    killDelta: int | None = None
    assistDelta: int | None = None
    ultimateDelta: int | None = None
    died: bool | None = None
    gameDay: int | None = None
    dayNight: str | None = Field(default=None, max_length=16)
    phaseIndex: int | None = None
    detectorConfidence: float | None = None


class LabelBatch(_Allowlist):
    installId: UUID
    appVersion: str = Field(max_length=32)
    labels: list[Label] = Field(max_length=500)


class Environment(_Allowlist):
    appVersion: str = Field(max_length=32)
    os: str = Field(max_length=128)
    resolution: str | None = Field(default=None, max_length=32)
    codec: str | None = Field(default=None, max_length=32)
    readFailStats: dict[str, int] = Field(default_factory=dict, max_length=64)


class LogEntry(_Allowlist):
    ts: str = Field(max_length=40)
    level: str = Field(max_length=16)
    message: str = Field(max_length=2000)


class LogBatch(_Allowlist):
    installId: UUID
    env: Environment
    entries: list[LogEntry] = Field(max_length=2000)
