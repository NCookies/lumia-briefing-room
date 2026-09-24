import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_token: str
    max_body_bytes: int


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        api_token=os.environ.get("API_TOKEN", ""),
        max_body_bytes=int(os.environ.get("MAX_BODY_BYTES", 20 * 1024 * 1024)),
    )
