"""문서가 코드·규칙과 어긋났는지 기계적으로 검사한다. (CLAUDE.md "문서를 최신 상태로 유지한다")

- 끊긴 상대 링크 (SPEC·spec·plan·DEVELOPMENT·README·CLAUDE)
- plan 에 남은 완료 체크(`- [x]`) — 끝난 일은 spec 으로 옮기고 plan 에서 지운다
- spec 에 계획 표현("미구현", "구현 예정") — 계획은 plan 에만 둔다
- 설정 스키마(config.py)와 docs/spec/config.md 의 키 목록 차이

`tests/test_check_docs.py` 가 저장소 전체에 대해 돌리므로 pytest 에 함께 걸린다.
사용: python tools/check_docs.py
"""

from __future__ import annotations

import dataclasses
import re
import sys
import typing
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PLANNED_WORDS = ("미구현", "구현 예정")

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_CHECKED = re.compile(r"^\s*[-*] \[[xX]\]")
_CONFIG_KEY = re.compile(r"`([a-z][A-Za-z0-9]*(?:\.[a-z][A-Za-z0-9]*)+)`")


def _strip_code(text: str) -> str:
    return _INLINE_CODE.sub("", _CODE_FENCE.sub("", text))


def broken_links(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        for target in _LINK.findall(_strip_code(f.read_text(encoding="utf-8"))):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (f.parent / path).exists():
                problems.append(f"{f}: 끊긴 링크 {target}")
    return problems


def completed_items(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _CHECKED.match(line):
                problems.append(f"{f.name}:{i}: 완료 항목이 plan 에 남아 있다 — spec 으로 옮기고 지운다")
    return problems


def planned_wording(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(w in line for w in PLANNED_WORDS):
                problems.append(f"{f.name}:{i}: spec 에 계획 표현 — plan 으로 옮긴다: {line.strip()[:60]}")
    return problems


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


def config_keys(cls, prefix: str = "") -> set[str]:
    keys = set()
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        key = prefix + _camel(f.name)
        tp = hints[f.name]
        if dataclasses.is_dataclass(tp):
            keys |= config_keys(tp, key + ".")
        else:
            keys.add(key)
    return keys


def documented_config_keys(markdown: str) -> set[str]:
    keys = set()
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) > 2:
            keys |= set(_CONFIG_KEY.findall(cells[1]))
    return keys


def config_doc_mismatch(schema: set[str], documented: set[str]) -> list[str]:
    return [f"config.md: {k} 가 문서에 없음" for k in sorted(schema - documented)] + [
        f"config.md: {k} 가 스키마에 없음(config.py)" for k in sorted(documented - schema)
    ]


def run(repo: Path = REPO) -> list[str]:
    docs = repo / "docs"
    spec = [docs / "SPEC.md", *sorted((docs / "spec").glob("*.md"))]
    plans = sorted(docs.glob("plan*.md"))
    linked = [*spec, *plans, docs / "DEVELOPMENT.md", repo / "README.md", repo / "CLAUDE.md"]

    sys.path.insert(0, str(repo / "src"))
    from lumia_briefing_room.config import Config

    return (
        broken_links([f for f in linked if f.exists()])
        + completed_items(plans)
        + planned_wording(spec)
        + config_doc_mismatch(config_keys(Config), documented_config_keys((docs / "spec" / "config.md").read_text(encoding="utf-8")))
    )


def main() -> int:
    problems = run()
    for p in problems:
        print(p)
    print("문서 검사 통과" if not problems else f"문제 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
