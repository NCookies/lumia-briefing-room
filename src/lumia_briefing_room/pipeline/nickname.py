from __future__ import annotations

from pathlib import Path

from lumia_briefing_room.config import load_config, save_config


def learn_nickname(config_path: Path | None, nickname: str | None) -> bool:
    """결과 화면에서 읽은 닉네임을 설정이 비어 있을 때만 저장한다. 사용자가 직접 넣은 값은 덮어쓰지 않는다."""
    nickname = (nickname or "").strip()
    if not nickname:
        return False
    cfg = load_config(config_path)
    if cfg.player.nickname:
        return False
    cfg.player.nickname = nickname
    save_config(cfg, config_path)
    return True
