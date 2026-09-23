import io
import json
import zipfile
from pathlib import Path

from lumia_briefing_room.diagnostics import build_diagnostics_zip, scrub_config, scrub_text

USER = "홍길동PC"


def test_scrub_replaces_user_name_in_windows_paths():
    text = r"clips at C:\Users\홍길동PC\Videos\LumiaBriefingRoom and C:/Users/홍길동PC/AppData"
    out = scrub_text(text, usernames=[USER], nicknames=[])
    assert "홍길동PC" not in out
    assert r"C:\Users\<user>\Videos" in out
    assert "C:/Users/<user>/AppData" in out


def test_scrub_is_case_insensitive_for_user_paths():
    out = scrub_text(r"c:\users\tester\x", usernames=["tester"], nicknames=[])
    assert "tester" not in out and "tester" not in out.lower().replace("<user>", "")


def test_scrub_replaces_standalone_user_name_when_long_enough():
    out = scrub_text("owner=tester done", usernames=["tester"], nicknames=[])
    assert out == "owner=<user> done"


def test_scrub_leaves_short_names_outside_paths_alone():
    out = scrub_text(r"a is fine, path C:\Users\a\x", usernames=["a"], nicknames=[])
    assert out.startswith("a is fine")
    assert r"C:\Users\<user>\x" in out


def test_scrub_replaces_nickname_anywhere_including_korean():
    out = scrub_text("nick=테스트닉 result 테스트닉님", usernames=[], nicknames=["테스트닉"])
    assert "테스트닉" not in out
    assert out.count("<nickname>") == 2


def test_scrub_ignores_blank_names():
    text = "nothing to hide"
    assert scrub_text(text, usernames=["", " "], nicknames=["", None]) == text


def test_scrub_config_drops_nickname_and_ids_and_scrubs_paths():
    cfg = {
        "player": {"nickname": "테스트닉"},
        "telemetry": {"installId": "abc", "sendLogs": False},
        "paths": {"clips": r"C:\Users\tester\Videos\clips"},
        "vod": {"sources": [r"D:\vods\tester"], "streamers": {"id1": "테스트닉"}},
    }
    out = scrub_config(cfg, usernames=["tester"], nicknames=["테스트닉"])
    dumped = json.dumps(out, ensure_ascii=False)
    assert "테스트닉" not in dumped and "tester" not in dumped and "abc" not in dumped
    assert out["player"]["nickname"] == "<nickname>"


def _zip_names_and_text(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


def test_zip_contains_scrubbed_logs_info_and_config(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "app.log").write_text(r"2026 INFO 열었다 C:\Users\tester\Videos 테스트닉", encoding="utf-8")
    (log_dir / "app.log.1").write_text("older tester line", encoding="utf-8")
    (log_dir / "notes.txt").write_text("not a log", encoding="utf-8")

    data = build_diagnostics_zip(
        log_dir=log_dir,
        info={"version": "0.1.0", "resolution": {"width": 2560, "height": 1440}, "root": r"C:\Users\tester\v"},
        config={"player": {"nickname": "테스트닉"}},
        usernames=["tester"],
        nicknames=["테스트닉"],
    )
    files = _zip_names_and_text(data)

    assert set(files) == {"info.json", "config.json", "logs/app.log", "logs/app.log.1"}
    for name, text in files.items():
        assert "tester" not in text and "테스트닉" not in text, name
    assert json.loads(files["info.json"])["version"] == "0.1.0"
    assert "열었다" in files["logs/app.log"]


def test_zip_works_without_log_directory(tmp_path: Path):
    data = build_diagnostics_zip(log_dir=tmp_path / "missing", info={"version": "x"}, config={}, usernames=[], nicknames=[])
    assert set(_zip_names_and_text(data)) == {"info.json", "config.json"}
