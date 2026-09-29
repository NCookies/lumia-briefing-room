import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_docs  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_broken_relative_link_is_reported(tmp_path):
    _write(tmp_path, "docs/a.md", "[b](b.md) [없음](gone.md#절) [밖](https://x.io/y.md) [앵커](#절)")
    _write(tmp_path, "docs/b.md", "")
    problems = check_docs.broken_links([tmp_path / "docs/a.md"])
    assert len(problems) == 1
    assert "gone.md" in problems[0]


def test_link_to_directory_is_fine(tmp_path):
    _write(tmp_path, "docs/a.md", "[spec](spec/)")
    (tmp_path / "docs/spec").mkdir()
    assert check_docs.broken_links([tmp_path / "docs/a.md"]) == []


def test_links_inside_code_blocks_are_ignored(tmp_path):
    _write(tmp_path, "docs/a.md", "```\n[x](nope.md)\n```\n`[y](nope2.md)`")
    assert check_docs.broken_links([tmp_path / "docs/a.md"]) == []


def test_completed_checkbox_left_in_plan_is_reported(tmp_path):
    p = _write(tmp_path, "docs/plan.md", "- [ ] 할 일\n- [x] 끝난 일\n  - [X] 끝난 하위\n")
    problems = check_docs.completed_items([p])
    assert len(problems) == 2
    assert "plan.md:2" in problems[0]


def test_planned_wording_in_spec_is_reported(tmp_path):
    p = _write(tmp_path, "docs/spec/x.md", "구현됨\n이 기능은 미구현이다\n구현 예정\n미사용 키\n")
    problems = check_docs.planned_wording([p])
    assert [pr.split(":")[1] for pr in problems] == ["2", "3"]


@dataclass
class _Inner:
    a_b: int = 1
    weights: dict = field(default_factory=dict)


@dataclass
class _Outer:
    inner: _Inner = field(default_factory=_Inner)
    top_level: str = ""


def test_config_keys_flatten_nested_dataclasses_in_camel_case():
    assert check_docs.config_keys(_Outer) == {"inner.aB", "inner.weights", "topLevel"}


def test_documented_keys_come_from_first_table_column():
    md = (
        "| 키 | 기본값 |\n|---|---|\n"
        "| `paths.clips` | `x` |\n"
        "| `vod.gameGapSec` / `vod.minGameSec` | 30 |\n"
        "본문의 `filter.preset` 은 세지 않는다\n"
    )
    assert check_docs.documented_config_keys(md) == {"paths.clips", "vod.gameGapSec", "vod.minGameSec"}


def test_config_doc_mismatch_both_directions():
    problems = check_docs.config_doc_mismatch({"a.b", "a.c"}, {"a.b", "a.gone"})
    assert any("a.c" in p and "문서에 없음" in p for p in problems)
    assert any("a.gone" in p and "스키마에 없음" in p for p in problems)


def test_repository_docs_are_consistent():
    problems = check_docs.run(REPO)
    assert problems == [], "\n".join(problems)
