import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_contract", ROOT / "tools" / "sync_contract.py")
sync_contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_contract)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def test_sync_copies_new_and_changed_files_and_removes_stale_ones(tmp_path):
    source, dest = tmp_path / "src", tmp_path / "dst"
    _write(source, "a.json", "{}")
    _write(source, "fixtures/x/valid/b.json", "1")
    _write(dest, "a.json", "old")
    _write(dest, "stale.json", "x")

    changed = sync_contract.sync_contract(source, dest)

    assert sorted(changed) == ["a.json", "fixtures/x/valid/b.json", "stale.json"]
    assert (dest / "a.json").read_text(encoding="utf-8") == "{}"
    assert (dest / "fixtures" / "x" / "valid" / "b.json").exists()
    assert not (dest / "stale.json").exists()
    assert sync_contract.contract_diff(source, dest) == []


def test_diff_reports_missing_changed_and_extra_files_without_touching_dest(tmp_path):
    source, dest = tmp_path / "src", tmp_path / "dst"
    _write(source, "a.json", "{}")
    _write(source, "b.json", "1")
    _write(dest, "a.json", "different")
    _write(dest, "extra.json", "x")

    assert sync_contract.contract_diff(source, dest) == ["a.json", "b.json", "extra.json"]
    assert (dest / "a.json").read_text(encoding="utf-8") == "different"


def test_line_endings_are_not_a_difference(tmp_path):
    source, dest = tmp_path / "src", tmp_path / "dst"
    _write(source, "a.json", "{\n}\n")
    _write(dest, "a.json", "{\r\n}\r\n")
    assert sync_contract.contract_diff(source, dest) == []


def test_missing_source_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        sync_contract.contract_diff(tmp_path / "nope", tmp_path / "dst")


def test_bundled_copy_matches_the_infra_original_when_it_is_checked_out():
    source = sync_contract.DEFAULT_SOURCE
    if not source.is_dir():
        pytest.skip("infra 저장소가 이 PC 에 없다")
    assert sync_contract.contract_diff(source, sync_contract.DEFAULT_DEST) == [], (
        "계약 복사본이 원본과 다르다. `python tools/sync_contract.py` 로 갱신한다"
    )
