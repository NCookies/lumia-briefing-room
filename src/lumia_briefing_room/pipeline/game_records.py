"""클립을 다 지워도 남기는 게임 기록. 영상은 클립당 수십 MB 지만 경기 요약·결과표 이미지는 수백 KB 라 따로 보관한다. (SPEC §7.6)

클립을 영구 삭제하는 네 경로(수동 완전 삭제·휴지통 비우기·유예 만료·permanent 자동 삭제)에서 호출한다.
게임 하나(sessionDir+matchStartUtc)당 기록 하나이고, 결과표를 못 읽은 게임은 남길 요약이 없어 기록하지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.pipeline.clip_assets import resolve_result_image

RECORDS_DIRNAME = ".games"


def records_dir_for(clips_dir: Path) -> Path:
    return clips_dir / RECORDS_DIRNAME


def game_key(session_dir: str | None, match_start_utc: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", f"{session_dir or ''}__{match_start_utc or ''}")


def record_game(meta_path: Path, records_dir: Path | None) -> Path | None:
    if records_dir is None or not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    result = meta.get("matchResult")
    if not isinstance(result, dict) or not meta.get("matchStartUtc"):
        return None

    key = game_key(meta.get("sessionDir"), meta["matchStartUtc"])
    records_dir.mkdir(parents=True, exist_ok=True)
    kept_result = {k: v for k, v in result.items() if k != "imagePath"}
    source_image = resolve_result_image(meta_path, meta)
    target_image = records_dir / f"{key}.jpg"
    if source_image is not None and source_image.exists() and source_image.resolve() != target_image.resolve():
        shutil.copyfile(source_image, target_image)
    if target_image.exists():
        kept_result["imagePath"] = str(target_image)

    record = {
        "id": key,
        "sessionDir": meta.get("sessionDir"),
        "matchStartUtc": meta["matchStartUtc"],
        "gameMode": meta.get("gameMode"),
        "matchResult": kept_result,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    target = records_dir / f"{key}.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_records(records_dir: Path) -> list[dict]:
    if not records_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir.glob("*.json"))]


def delete_record(records_dir: Path, key: str) -> bool:
    target = records_dir / f"{key}.json"
    if not target.exists():
        return False
    target.unlink()
    (records_dir / f"{key}.jpg").unlink(missing_ok=True)
    return True


def clear_records(records_dir: Path) -> None:
    for record in load_records(records_dir):
        delete_record(records_dir, record["id"])
