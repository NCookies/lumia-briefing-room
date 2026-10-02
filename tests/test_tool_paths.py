import json
import re
from pathlib import Path

from lumia_briefing_room import tool_paths

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def _config(tmp_path, **paths):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"paths": paths}), encoding="utf-8")
    return path


def test_app_paths_follow_the_storage_root_from_the_app_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "vod_root"

    paths = tool_paths.app_paths(_config(tmp_path, root=str(root)))

    assert paths.games_steam == root / "full_video" / "steam_replay"
    assert paths.library_steam == tmp_path / "local" / "LumiaBriefingRoom" / "library" / "steam"
    assert paths.clip_roots == (root / "clips",)


def test_clip_meta_files_lists_the_json_files(tmp_path, capsys):
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")

    assert [p.name for p in tool_paths.clip_meta_files(tmp_path)] == ["a.json", "b.json"]
    assert capsys.readouterr().err == ""


def test_clip_meta_files_warns_when_the_folder_has_no_clip_info(tmp_path, capsys):
    assert tool_paths.clip_meta_files(tmp_path / "missing") == []
    assert "클립 정보" in capsys.readouterr().err


def test_clip_videos_finds_videos_under_the_clip_roots_and_beside_the_info(tmp_path):
    library, root = tmp_path / "library", tmp_path / "clips"
    library.mkdir()
    (root / "자동 보관").mkdir(parents=True)
    for clip_id in ("a", "b"):
        (library / f"{clip_id}.json").write_text("{}", encoding="utf-8")
    (root / "자동 보관" / "a.mp4").write_bytes(b"1")
    (library / "b.mp4").write_bytes(b"2")

    videos = tool_paths.clip_videos(library, ["a", "b", "missing"], [root])

    assert videos == {"a": root / "자동 보관" / "a.mp4", "b": library / "b.mp4"}


def test_tools_do_not_hard_code_storage_paths():
    """경로 기본값은 `tool_paths` 한 곳에서 앱 설정을 따른다 - 도구마다 박아 둔 `~/Videos/...` 가 저장 구조 변경(F7·F8)을 놓쳤다."""
    pattern = re.compile(r"Path\.home\(\)|Videos[/\\\"']|LumiaBriefingRoom[/\\]")
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(TOOLS_DIR.glob("*.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if pattern.search(line)
    ]
    assert offenders == []
