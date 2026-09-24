"""서버와 공유하는 전송 계약을 infra 저장소에서 tests/contract 로 복사한다. (docs/plan-infra.md §3, roadmap §7)

usage:
    python tools/sync_contract.py                 # 복사(원본과 같게 맞춤, 없어진 파일은 지움)
    python tools/sync_contract.py --check         # 다르면 목록을 보이고 종료 코드 1
    python tools/sync_contract.py --source P:\\infra\\contract

계약의 원본은 infra 저장소의 contract/ 이다. 앱 쪽에서 계약을 고치지 않고, 여기로 복사한 것으로 테스트한다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "infra" / "contract"
DEFAULT_DEST = ROOT / "tests" / "contract"


def _files(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*")) if p.is_file()}


def _same(a: Path, b: Path) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def contract_diff(source: Path, dest: Path) -> list[str]:
    if not source.is_dir():
        raise FileNotFoundError(f"계약 원본 폴더가 없다: {source}")
    src = _files(source)
    dst = _files(dest) if dest.is_dir() else {}
    changed = [rel for rel, path in src.items() if rel not in dst or not _same(path, dst[rel])]
    changed += [rel for rel in dst if rel not in src]
    return sorted(changed)


def sync_contract(source: Path, dest: Path) -> list[str]:
    changed = contract_diff(source, dest)
    for rel in changed:
        origin, target = source / rel, dest / rel
        if origin.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
        else:
            target.unlink()
    for folder in sorted((p for p in dest.rglob("*") if p.is_dir()), reverse=True) if dest.is_dir() else []:
        if not any(folder.iterdir()):
            folder.rmdir()
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--check", action="store_true", help="복사하지 않고 차이만 확인한다")
    args = parser.parse_args(argv)
    try:
        changed = contract_diff(args.source, args.dest) if args.check else sync_contract(args.source, args.dest)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    verb = "다른 파일" if args.check else "갱신한 파일"
    print(f"{verb} {len(changed)}개" + ("" if not changed else ": " + ", ".join(changed)))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
