from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room import __version__
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.changelog import parse_changelog

TEXT = """# 패치노트

소개 문장

<!--
- 이건 쓰는 법 안내라서 무시된다
## [9.9.9] - 2000-01-01
-->

## [0.2.0] - 2026-10-01

### 새로 생겼어요
- 첫째 **굵게**
- 둘째

### 고쳤어요
- 셋째

## [0.1.3] - 2026-09-25

### 좋아졌어요
- 넷째
"""


def test_releases_come_out_newest_first_as_written():
    releases = parse_changelog(TEXT)
    assert [r["version"] for r in releases] == ["0.2.0", "0.1.3"]
    assert releases[0]["date"] == "2026-10-01"


def test_sections_keep_their_titles_and_items():
    first = parse_changelog(TEXT)[0]
    assert first["sections"] == [
        {"title": "새로 생겼어요", "items": ["첫째 **굵게**", "둘째"]},
        {"title": "고쳤어요", "items": ["셋째"]},
    ]


def test_html_comments_are_not_content():
    assert "9.9.9" not in [r["version"] for r in parse_changelog(TEXT)]


def test_heading_without_a_date_is_still_a_release():
    assert parse_changelog("## [1.0.0]\n### 좋아졌어요\n- a\n")[0]["date"] == ""


def test_empty_or_unstructured_text_gives_no_releases():
    assert parse_changelog("") == []
    assert parse_changelog("# 제목만 있다\n") == []


def test_items_before_any_section_title_go_into_an_untitled_section():
    releases = parse_changelog("## [1.0.0] - 2026-01-01\n- 바로 나온 항목\n")
    assert releases[0]["sections"] == [{"title": "", "items": ["바로 나온 항목"]}]


def test_the_shipped_changelog_documents_the_current_version():
    text = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    releases = parse_changelog(text)
    assert releases and releases[0]["version"] == __version__
    assert all(section["items"] for release in releases for section in release["sections"])


@pytest.fixture
def client(tmp_path: Path):
    from lumia_briefing_room.config import Config

    return TestClient(create_app(Config(), config_path=tmp_path / "config.json"))


def test_changelog_endpoint_serves_the_parsed_releases(client, monkeypatch, tmp_path):
    file = tmp_path / "CHANGELOG.md"
    file.write_text(TEXT, encoding="utf-8")
    monkeypatch.setattr("lumia_briefing_room.api.app_info_routes.changelog_path", lambda: file)
    body = client.get("/api/changelog").json()
    assert [r["version"] for r in body["releases"]] == ["0.2.0", "0.1.3"]


def test_changelog_endpoint_is_a_404_when_the_file_is_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr("lumia_briefing_room.api.app_info_routes.changelog_path", lambda: tmp_path / "none.md")
    assert client.get("/api/changelog").status_code == 404
