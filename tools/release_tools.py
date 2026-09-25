"""릴리스 파이프라인의 보조 도구. (plan-deploy.md D13, .github/workflows/release.yml 이 부른다)

usage:
  python tools/release_tools.py check-tag <태그> [--changelog CHANGELOG.md]
  python tools/release_tools.py prepare <태그> [--changelog CHANGELOG.md] [--notes-out dist/release-notes.md]
  python tools/release_tools.py virustotal [--file 설치기.exe]      (환경변수 VT_API_KEY)
  python tools/release_tools.py finalize <태그> [--virustotal-url URL]

순수 로직(태그·버전 검증, 파일 이름, 체크섬, 패치노트 추출, 본문 조립)은 tests/test_release_tools.py 가 확인한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_installer import installer_name  # noqa: E402
from lumia_briefing_room import __version__  # noqa: E402

_TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_SHA256_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
VT_API = "https://www.virustotal.com/api/v3"


class ReleaseError(Exception):
    pass


def parse_tag(tag: str) -> str:
    if not _TAG.fullmatch(tag):
        raise ReleaseError(f"태그 형식이 vMAJOR.MINOR.PATCH 가 아니다: {tag!r}")
    return tag[1:]


def verify_tag(tag: str, version: str) -> str:
    tag_version = parse_tag(tag)
    if tag_version != version:
        raise ReleaseError(
            f"태그({tag_version})와 코드의 __version__({version})이 다르다 — "
            "src/lumia_briefing_room/__init__.py 의 버전을 올린 커밋에 태그를 달았는지 확인할 것"
        )
    return tag_version


def asset_names(version: str) -> tuple[str, str]:
    installer = installer_name(version)
    return installer, f"{installer}.sha256"


def extract_notes(changelog: str, version: str) -> str:
    heading = re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s|$)")
    any_heading = re.compile(r"^##\s")
    section: list[str] | None = None
    for line in changelog.splitlines():
        if section is None:
            if heading.match(line):
                section = []
        elif any_heading.match(line):
            break
        else:
            section.append(line)
    if section is None:
        raise ReleaseError(f"CHANGELOG.md 에 {version} 절이 없다 — 릴리스 전에 이 버전의 패치노트를 써야 한다")
    notes = "\n".join(section).strip()
    if not notes:
        raise ReleaseError(f"CHANGELOG.md 의 {version} 절이 비어 있다")
    return notes


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_line(digest: str, filename: str) -> str:
    return f"{digest} *{filename}\n"


def parse_checksum(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        match = _SHA256_LINE.match(line.strip())
        if match:
            return match.group(1).lower(), match.group(2)
    raise ReleaseError("SHA-256 줄을 읽을 수 없다")


def write_checksum_file(installer: Path) -> tuple[str, Path]:
    digest = sha256_of(installer)
    target = installer.with_name(installer.name + ".sha256")
    target.write_text(checksum_line(digest, installer.name), encoding="utf-8", newline="\n")
    return digest, target


def virustotal_file_url(sha256: str) -> str:
    return f"https://www.virustotal.com/gui/file/{sha256}"


def release_body(notes: str, *, installer: str, sha256: str, virustotal_url: str | None = None) -> str:
    parts = [notes.strip(), "---", f"**{installer}** 의 SHA-256: `{sha256}`"]
    if virustotal_url:
        parts.append(
            f"바이러스 검사 결과: [VirusTotal]({virustotal_url})  \n"
            "코드 서명이 없는 프로그램이라 일부 엔진이 잘못 의심(오탐)할 수 있습니다. "
            "설치 중 Windows 경고가 뜨면 \"추가 정보 → 실행\" 을 누르세요."
        )
    return "\n\n".join(parts) + "\n"


def multipart_file(filename: str, data: bytes, *, boundary: str | None = None) -> tuple[bytes, str]:
    boundary = boundary or uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("ascii")
    return head + data + tail, f"multipart/form-data; boundary={boundary}"


def prepare(*, tag: str, version: str, changelog: Path, dist: Path, notes_out: Path) -> str:
    verify_tag(tag, version)
    notes = extract_notes(changelog.read_text(encoding="utf-8"), version)
    installer_file, _ = asset_names(version)
    installer = dist / installer_file
    if not installer.is_file():
        raise ReleaseError(f"설치기가 없다: {installer} — tools/build_installer.py 를 먼저 돌려야 한다")
    digest, _ = write_checksum_file(installer)
    notes_out.parent.mkdir(parents=True, exist_ok=True)
    notes_out.write_text(release_body(notes, installer=installer.name, sha256=digest), encoding="utf-8", newline="\n")
    return digest


def virustotal_upload(installer: Path, api_key: str) -> str:
    headers = {"x-apikey": api_key, "accept": "application/json"}
    request = urllib.request.Request(f"{VT_API}/files/upload_url", headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        upload_url = json.load(response)["data"]
    body, content_type = multipart_file(installer.name, installer.read_bytes())
    upload = urllib.request.Request(
        upload_url, data=body, headers={**headers, "content-type": content_type}, method="POST"
    )
    with urllib.request.urlopen(upload, timeout=600) as response:
        json.load(response)
    return virustotal_file_url(sha256_of(installer))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="릴리스 보조 도구")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check-tag", "prepare", "finalize"):
        cmd = sub.add_parser(name)
        cmd.add_argument("tag")
        cmd.add_argument("--changelog", default=str(ROOT / "CHANGELOG.md"))
        cmd.add_argument("--dist", default=str(ROOT / "dist"))
        cmd.add_argument("--notes-out", default=str(ROOT / "dist" / "release-notes.md"))
        if name == "finalize":
            cmd.add_argument("--virustotal-url", default="")
    vt = sub.add_parser("virustotal")
    vt.add_argument("--file")
    args = parser.parse_args(argv)

    try:
        if args.command == "check-tag":
            version = verify_tag(args.tag, __version__)
            extract_notes(Path(args.changelog).read_text(encoding="utf-8"), version)
            print(f"태그 {args.tag} 와 버전·패치노트가 맞다")
        elif args.command == "prepare":
            digest = prepare(
                tag=args.tag,
                version=__version__,
                changelog=Path(args.changelog),
                dist=Path(args.dist),
                notes_out=Path(args.notes_out),
            )
            print(f"SHA-256 {digest}\n본문: {args.notes_out}")
        elif args.command == "finalize":
            version = verify_tag(args.tag, __version__)
            installer_file, checksum_file = asset_names(version)
            digest, _ = parse_checksum((Path(args.dist) / checksum_file).read_text(encoding="utf-8"))
            notes = extract_notes(Path(args.changelog).read_text(encoding="utf-8"), version)
            Path(args.notes_out).write_text(
                release_body(notes, installer=installer_file, sha256=digest, virustotal_url=args.virustotal_url or None),
                encoding="utf-8",
                newline="\n",
            )
            print(f"본문: {args.notes_out}")
        else:
            api_key = os.environ.get("VT_API_KEY", "").strip()
            if not api_key:
                raise ReleaseError("환경변수 VT_API_KEY 가 없다 (GitHub Secrets 에 등록할 것)")
            installer = Path(args.file) if args.file else ROOT / "dist" / asset_names(__version__)[0]
            print(virustotal_upload(installer, api_key))
    except (ReleaseError, OSError) as exc:
        print(f"릴리스 도구 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
