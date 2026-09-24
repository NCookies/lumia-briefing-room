import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_tokens: tuple[str, ...]
    max_body_bytes: int
    retention_days: int = 90
    purge_interval_sec: int = 24 * 3600


def _tokens(*raw: str) -> tuple[str, ...]:
    found: list[str] = []
    for value in raw:
        for token in value.split(","):
            token = token.strip()
            if token and token not in found:
                found.append(token)
    return tuple(found)


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        api_tokens=_tokens(os.environ.get("API_TOKENS", ""), os.environ.get("API_TOKEN", "")),
        max_body_bytes=int(os.environ.get("MAX_BODY_BYTES", 20 * 1024 * 1024)),
        retention_days=int(os.environ.get("RETENTION_DAYS", 90)),
    )
