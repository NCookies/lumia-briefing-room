import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from envfile import load_env_file  # noqa: E402


def test_reads_key_value_lines_and_skips_comments(tmp_path: Path):
    text = '# 주석\nLUMIA_RECEIVER_URL="https://x.example"\n\nLUMIA_RECEIVER_TOKEN = tok\nbroken line\n'
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    env: dict = {}
    assert load_env_file(tmp_path / ".env", env) == ["LUMIA_RECEIVER_URL", "LUMIA_RECEIVER_TOKEN"]
    assert env == {"LUMIA_RECEIVER_URL": "https://x.example", "LUMIA_RECEIVER_TOKEN": "tok"}


def test_existing_environment_wins_and_a_missing_file_is_fine(tmp_path: Path):
    (tmp_path / ".env").write_text("A=file\n", encoding="utf-8")
    env = {"A": "real"}
    assert load_env_file(tmp_path / ".env", env) == [] and env == {"A": "real"}
    assert load_env_file(tmp_path / "none.env", env) == []


def test_env_file_is_gitignored():
    text = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".env" for line in text.splitlines())


def test_inline_comment_after_an_unquoted_value_is_dropped(tmp_path: Path):
    (tmp_path / ".env").write_text("A=abc123   # 값은 여기서 가져온다\nB=\"x # y\"  # 주석\nC=tok#en\n", encoding="utf-8")
    env: dict = {}
    load_env_file(tmp_path / ".env", env)
    assert env == {"A": "abc123", "B": "x # y", "C": "tok#en"}


def test_server_url_gets_https_when_only_a_host_is_given():
    from lumia_briefing_room.envfile import normalize_server_url

    assert normalize_server_url("r.example.com") == "https://r.example.com"
    assert normalize_server_url(" https://r.example.com/ ") == "https://r.example.com"
    assert normalize_server_url("http://localhost:9000") == "http://localhost:9000"
    assert normalize_server_url("") == ""
