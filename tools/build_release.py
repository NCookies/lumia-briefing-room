"""배포본(PyInstaller --onedir)과 zip 을 한 번에 만든다. (plan-deploy.md D5)

usage: python tools/build_release.py [--skip-frontend] [--skip-checks] [--skip-zip]

순서가 중요하다: 프론트 빌드 → PyInstaller → 검증 → zip. `frontend/dist` 는 저장소에 없고
`npm run build` 로 그때그때 만들어지므로, 빌드 전에 반드시 새로 만들어야 옛 화면이 섞이지 않는다.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from envfile import load_env_file  # noqa: E402
from lumia_briefing_room import __version__  # noqa: E402
from lumia_briefing_room.icon import save_ico  # noqa: E402

APP_NAME = "LumiaBriefingRoom"
SEP = ";" if sys.platform == "win32" else ":"
MEASURED_NPZ = "2560x1440.npz"
HIDDEN_IMPORTS = (
    "pystray._win32",
    "PIL._tkinter_finder",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "onnxruntime",
    "rapidocr",
    "httpx",
    "httpcore",
    "h11",
)
COLLECT_DATA = ("rapidocr", "certifi")
COLLECT_SUBMODULES = ("uvicorn", "rapidocr")
EXCLUDES = ("torch", "torchvision", "tensorrt", "paddle", "matplotlib", "tkinter", "pytest")
REQUIRED_IN_BUNDLE = (
    "data/characters.json",
    f"data/templates/digits/{MEASURED_NPZ}",
    f"data/templates/regions/{MEASURED_NPZ}",
    f"data/templates/days/{MEASURED_NPZ}",
    "lumia_briefing_room/profiles/builtin/2560x1440.json",
    "frontend/dist/index.html",
    "docs/privacy.md",
    "CHANGELOG.md",
    "vendor/ffmpeg/ffmpeg.exe",
    "vendor/ffmpeg/ffprobe.exe",
    "pystray/__init__.py",
)
FORBIDDEN_IN_BUNDLE = ("data/templates/**/_samples", "data/templates/**/*_samples", "data/**/*_labels.jsonl")
HOOKS_DIR = Path(__file__).resolve().parent / "pyi_hooks"


class BuildError(Exception):
    pass


def release_name(version: str) -> str:
    return f"{APP_NAME}-{version}"


def zip_name(version: str) -> str:
    return f"{release_name(version)}-win64.zip"


def data_specs(root: Path) -> list[tuple[str, str]]:
    """PyInstaller `--add-data` 목록. 목적지는 `paths.resource_dir()`(=sys._MEIPASS) 기준 상대 경로다.

    ffmpeg 는 여기 넣지 않는다 — PyInstaller 가 datas 안의 .dll 을 바이너리로도 분류해
    `_internal` 루트에 한 벌 더 복사하는 바람에 149MB 가 통째로 중복됐다(실측). 빌드 뒤에 직접 복사한다.

    특히 `data/` 를 통째로 넣지 않는다 — 개발 PC 에 있는 본보기 라벨셋 원본(`_samples`, 게임 화면 조각)과 `*_labels.jsonl` 이
    설치본에 딸려 들어가기 때문이다(공개 저장소에서 뺀 것을 설치기로 다시 배포하게 된다).
    """
    templates = [
        (str(npz), f"data/templates/{npz.parent.name}")
        for npz in sorted((root / "data" / "templates").glob("*/*.npz"))
    ]
    endpoint = root / "data" / "telemetry_endpoint.json"
    return [
        (str(root / "data" / "characters.json"), "data"),
        *([(str(endpoint), "data")] if endpoint.exists() else []),
        *templates,
        (str(root / "src" / "lumia_briefing_room" / "profiles" / "builtin"), "lumia_briefing_room/profiles/builtin"),
        (str(root / "frontend" / "dist"), "frontend/dist"),
        (str(root / "docs" / "privacy.md"), "docs"),
        (str(root / "CHANGELOG.md"), "."),
    ]


PRUNE = (
    # 우리 설정은 PPOCRV5 + KOREAN/CH 로 고정이라 v6 인식 모델은 열리지 않는다(실측: 실제로 쓰는 모델 4개 확인).
    "rapidocr/models/PP-OCRv6_rec_small.onnx",
    # 영상은 전부 ffmpeg 를 따로 띄워 다루고 cv2 는 이미지 연산에만 쓴다.
    "cv2/opencv_videoio_ffmpeg500_64.dll",
)


def prune_unused(out_dir: Path, names: tuple[str, ...] = PRUNE) -> list[tuple[str, float]]:
    """쓰지 않는 큰 파일을 덜어낸다. 지운 뒤에는 반드시 `--selftest` 로 확인한다."""
    internal = out_dir / "_internal"
    base = internal if internal.is_dir() else out_dir
    removed = []
    for name in names:
        path = base / name
        if path.exists():
            size_mb = path.stat().st_size / 1e6
            path.unlink()
            removed.append((name, size_mb))
    return removed


def copy_vendor(root: Path, out_dir: Path) -> Path:
    """번들 ffmpeg 를 리소스 폴더(`_internal`) 아래로 그대로 복사한다."""
    internal = out_dir / "_internal"
    dest = (internal if internal.is_dir() else out_dir) / "vendor" / "ffmpeg"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(root / "vendor" / "ffmpeg", dest)
    return dest


def missing_prerequisites(root: Path) -> list[str]:
    """빌드를 시작하기 전에 갖춰져 있어야 하는 것(프론트 dist 는 이 스크립트가 만든다)."""
    problems = []
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        if not (root / "vendor" / "ffmpeg" / name).exists():
            problems.append(f"번들 ffmpeg 가 없다: vendor/ffmpeg/{name} — python tools/fetch_ffmpeg.py 를 먼저 돌릴 것")
            break
    for kind in ("digits", "regions", "days"):
        if not (root / "data" / "templates" / kind / MEASURED_NPZ).exists():
            problems.append(f"{kind} 본보기가 없다: data/templates/{kind}/{MEASURED_NPZ}")
    if not (root / "data" / "characters.json").exists():
        problems.append("data/characters.json 이 없다")
    return problems


def pyinstaller_args(root: Path, *, version: str, icon: Path, work_dir: Path | None = None) -> list[str]:
    work_dir = work_dir or root / "build" / "pyinstaller"
    args = [
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", APP_NAME,
        "--icon", str(icon),
        "--distpath", str(root / "dist"),
        "--workpath", str(work_dir),
        "--specpath", str(work_dir),
        "--paths", str(root / "src"),
    ]
    for source, dest in data_specs(root):
        args += ["--add-data", f"{source}{SEP}{dest}"]
    args += ["--additional-hooks-dir", str(HOOKS_DIR)]
    for name in HIDDEN_IMPORTS:
        args += ["--hidden-import", name]
    for name in COLLECT_DATA:
        args += ["--collect-data", name]
    for name in COLLECT_SUBMODULES:
        args += ["--collect-submodules", name]
    for name in EXCLUDES:
        args += ["--exclude-module", name]
    args.append(str(root / "src" / "lumia_briefing_room" / "cli" / "app.py"))
    return args


ENDPOINT_FILE = "data/telemetry_endpoint.json"


def write_endpoint_file(root: Path, environ=None) -> Path | None:
    """서버 주소·토큰을 번들에 넣는다(저장소가 공개라 둘 다 git 에 없다). 환경변수(또는 `.env`)의
    LUMIA_RECEIVER_URL·LUMIA_RECEIVER_TOKEN 에서 읽고, 하나라도 없으면 파일을 만들지 않으며 남아 있던 옛 파일도 지운다
    — 이 빌드는 서버 전송이 꺼진 채로 나간다."""
    import json
    import os

    environ = os.environ if environ is None else environ
    path = root / ENDPOINT_FILE
    token = (environ.get("LUMIA_RECEIVER_TOKEN") or "").strip()
    url = (environ.get("LUMIA_RECEIVER_URL") or "").strip()
    if not token or not url:
        path.unlink(missing_ok=True)
        return None
    data = {"token": token, "url": url}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def verify_bundle(out_dir: Path, *, expect_endpoint: bool = False) -> list[str]:
    """PyInstaller 가 조용히 빠뜨린 리소스를 잡는다 — 빌드본에서만 나는 고장의 대부분이 이것이다."""
    problems = []
    exe = out_dir / f"{APP_NAME}.exe"
    if not exe.exists():
        problems.append(f"실행 파일이 없다: {exe}")
    internal = out_dir / "_internal"
    base = internal if internal.is_dir() else out_dir
    for rel in REQUIRED_IN_BUNDLE:
        if not (base / rel).exists():
            problems.append(f"번들에 빠졌다: {rel}")
    for pattern in FORBIDDEN_IN_BUNDLE:
        for found in sorted(base.glob(pattern)):
            problems.append(f"번들에 있으면 안 된다(공개 배포 대상이 아님): {found.relative_to(base).as_posix()}")
    if expect_endpoint and not (base / ENDPOINT_FILE).exists():
        problems.append(f"번들에 빠졌다: {ENDPOINT_FILE} (토큰을 넣는 빌드인데 파일이 없다)")
    return problems


def build_frontend(root: Path) -> None:
    frontend = root / "frontend"
    if not (frontend / "node_modules").is_dir():
        _run(["npm", "install"], cwd=frontend, what="npm install")
    _run(["npm", "run", "build"], cwd=frontend, what="npm run build")
    if not (frontend / "dist" / "index.html").exists():
        raise BuildError("npm run build 뒤에도 frontend/dist/index.html 이 없다")


def run_pyinstaller(root: Path, *, version: str, icon: Path) -> Path:
    _run(
        [sys.executable, "-m", "PyInstaller", *pyinstaller_args(root, version=version, icon=icon)],
        cwd=root,
        what="PyInstaller",
    )
    return root / "dist" / APP_NAME


def make_zip(out_dir: Path, archive: Path) -> Path:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, f"{out_dir.name}/{path.relative_to(out_dir).as_posix()}")
    return archive


def _run(cmd: list[str], *, cwd: Path, what: str) -> None:
    print(f"\n=== {what} ===")
    result = subprocess.run(cmd, cwd=cwd, shell=sys.platform == "win32" and cmd[0] == "npm")
    if result.returncode != 0:
        raise BuildError(f"{what} 이(가) 실패했다 (종료 코드 {result.returncode})")


def _folder_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배포본 빌드")
    parser.add_argument("--skip-frontend", action="store_true", help="frontend/dist 를 그대로 쓴다")
    parser.add_argument("--skip-checks", action="store_true", help="사전 점검을 건너뛴다")
    parser.add_argument("--skip-zip", action="store_true", help="zip 을 만들지 않는다")
    args = parser.parse_args(argv)

    started = time.monotonic()
    version = __version__
    print(f"루미아 브리핑룸 {version} 배포본을 만든다")

    try:
        if not args.skip_checks:
            problems = missing_prerequisites(ROOT)
            if problems:
                for problem in problems:
                    print(f"  - {problem}", file=sys.stderr)
                raise BuildError("사전 점검 실패")

        if not args.skip_frontend:
            build_frontend(ROOT)

        icon = save_ico(ROOT / "build" / "icon.ico")
        load_env_file(ROOT / ".env")
        endpoint_file = write_endpoint_file(ROOT)
        if endpoint_file is None:
            print("  경고: LUMIA_RECEIVER_URL·LUMIA_RECEIVER_TOKEN 이 없어 서버 전송이 꺼진 빌드다 (라벨·오류 로그 전송은 동작하지 않는다)")
        else:
            print("  서버 주소·토큰을 번들에 넣는다")
        try:
            out_dir = run_pyinstaller(ROOT, version=version, icon=icon)
        finally:
            if endpoint_file is not None:
                endpoint_file.unlink(missing_ok=True)
        copy_vendor(ROOT, out_dir)
        for name, size_mb in prune_unused(out_dir):
            print(f"  뺐다: {name} ({size_mb:.0f} MB)")

        problems = verify_bundle(out_dir, expect_endpoint=endpoint_file is not None)
        if problems:
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            raise BuildError("번들 검증 실패")

        print(f"\n빌드 완료: {out_dir} ({_folder_size_mb(out_dir):.0f} MB)")
        if not args.skip_zip:
            archive = make_zip(out_dir, ROOT / "dist" / zip_name(version))
            print(f"zip: {archive} ({archive.stat().st_size / 1e6:.0f} MB)")
    except BuildError as exc:
        print(f"\n빌드 실패: {exc}", file=sys.stderr)
        return 1

    print(f"{time.monotonic() - started:.0f}초 걸렸다")
    print(f"확인: \"{out_dir / (APP_NAME + '.exe')}\" --selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
