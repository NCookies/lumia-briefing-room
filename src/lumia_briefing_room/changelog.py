"""CHANGELOG.md(사용자용 패치노트)를 앱 화면용 구조로 읽는다."""

from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_RELEASE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?(?:\s*-\s*(\S+))?\s*$")
_SECTION = re.compile(r"^###\s+(.+?)\s*$")
_ITEM = re.compile(r"^[-*]\s+(.+?)\s*$")


def parse_changelog(text: str) -> list[dict]:
    releases: list[dict] = []
    section: dict | None = None
    for line in _COMMENT.sub("", text).splitlines():
        line = line.strip()
        release = _RELEASE.match(line)
        if release:
            releases.append({"version": release.group(1), "date": release.group(2) or "", "sections": []})
            section = None
            continue
        if not releases:
            continue
        title = _SECTION.match(line)
        if title:
            section = {"title": title.group(1), "items": []}
            releases[-1]["sections"].append(section)
            continue
        item = _ITEM.match(line)
        if item:
            if section is None:
                section = {"title": "", "items": []}
                releases[-1]["sections"].append(section)
            section["items"].append(item.group(1))
    return releases
