"""클립에 딸린 썸네일·결과표 이미지의 경로를 저장하고 다시 찾는다.

메타데이터에 절대경로를 그대로 적어두면 클립 폴더를 옮기는 순간 옛 위치를 가리킨다.
그래서 클립 폴더 기준 상대경로로 저장하고, 예전에 절대경로로 저장된 값도 클립 폴더 안의
`.thumbs` 에서 파일 이름으로 다시 찾는다.
"""

from pathlib import Path

THUMBS_DIRNAME = ".thumbs"
TRASH_DIRNAME = ".trash"


def stored_asset_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def _resolve(raw: str, base: Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        return base / path
    local = base / THUMBS_DIRNAME / path.name
    if local.exists():
        return local
    if path.exists():
        return path
    return local


def clips_root_of(meta_path: Path) -> Path:
    parent = meta_path.parent
    return parent.parent if parent.name == TRASH_DIRNAME else parent


def resolve_thumbnail(meta_path: Path, meta: dict) -> Path | None:
    raw = meta.get("thumbnailPath")
    return _resolve(raw, meta_path.parent) if raw else None


def resolve_result_image(meta_path: Path, meta: dict) -> Path | None:
    raw = (meta.get("matchResult") or {}).get("imagePath")
    return _resolve(raw, clips_root_of(meta_path)) if raw else None
