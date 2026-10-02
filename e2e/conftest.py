"""화면 E2E 공통 fixture. 실행: `pytest e2e -m e2e` (기본 pytest 에는 안 돌아간다 — docs/DEVELOPMENT.md "화면 E2E").

- `world`/`server`: 테스트마다 새 임시 세계 + 새 서버 프로세스(서로 영향 없음).
- `shot("이름")`: 스크린샷을 build/e2e-report/shots 에 남기고 보고서(index.html)에 모은다(릴리스 체크 H4).
- 처리되지 않은 JS 예외(pageerror)가 나면 그 테스트는 실패한다.
- 실패하면 마지막 화면을 자동으로 찍는다.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from e2e.world import Server, World, make_sample_video

REPORT_DIR = Path(__file__).resolve().parents[1] / "build" / "e2e-report"
_results: list[dict] = []
_shots: dict[str, list[str]] = {}


def pytest_collection_modifyitems(items):
    for item in items:
        if "e2e" in Path(str(item.fspath)).parts or item.fspath.dirname.endswith("e2e"):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def ffmpeg_path() -> str:
    """합성 영상을 만들려면 libx264 가 있는 ffmpeg 가 필요하다(배포용 vendor 빌드엔 없다). 앱도 같은 걸 쓴다."""
    candidates = [os.environ.get("LUMIA_FFMPEG"), shutil.which("ffmpeg")]
    for found in filter(None, candidates):
        encoders = subprocess.run([found, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if "libx264" in encoders:
            return found
    pytest.skip("libx264 가 있는 ffmpeg 를 찾을 수 없다(PATH 또는 LUMIA_FFMPEG)")


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory, ffmpeg_path) -> Path:
    return make_sample_video(ffmpeg_path, tmp_path_factory.mktemp("sample") / "sample.mp4")


@pytest.fixture
def world(tmp_path, sample_video, ffmpeg_path) -> World:
    home = tmp_path / "home"
    (home / "Local").mkdir(parents=True)
    (home / "Roaming").mkdir()
    return World(home=home, root=tmp_path / "storage", sample_video=sample_video, ffmpeg=ffmpeg_path)


@pytest.fixture
def launch(world):
    """`launch()` 로 서버를 띄운다. 시드를 넣고 싶으면 띄우기 전에 world 를 채운다."""
    servers: list[Server] = []

    def _launch(*, consented: bool = True, extra_config: dict | None = None) -> Server:
        world.write_config(consented=consented, extra=extra_config)
        server = Server(world).start()
        servers.append(server)
        return server

    yield _launch
    for server in servers:
        server.stop()


@pytest.fixture
def server(world, launch) -> Server:
    """기본 세계(게임 4개)로 서버를 띄운다."""
    world.seed_default_games()
    return launch()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}, "locale": "ko-KR"}


@pytest.fixture
def page(page, request):
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    request.node._page = page
    yield page
    if errors:
        pytest.fail("처리되지 않은 JS 예외:\n" + "\n".join(errors))


@pytest.fixture
def go(page, server):
    """`go("#/steam")` — 서버 주소를 붙여 연다."""

    def _go(path: str = "/") -> None:
        page.goto(server.url + path)
        page.wait_for_load_state("networkidle")

    return _go


@pytest.fixture
def shot(page, request):
    name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", request.node.name)

    def _shot(label: str) -> Path:
        REPORT_DIR.joinpath("shots").mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / "shots" / f"{name}__{label}.png"
        page.screenshot(path=str(path))
        _shots.setdefault(request.node.nodeid, []).append(path.name)
        return path

    return _shot


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    page = getattr(item, "_page", None)
    if report.failed and page is not None:
        REPORT_DIR.joinpath("shots").mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", item.name)
        path = REPORT_DIR / "shots" / f"{name}__FAIL.png"
        try:
            page.screenshot(path=str(path))
            _shots.setdefault(item.nodeid, []).append(path.name)
        except Exception:
            pass
    _results.append({
        "id": item.nodeid, "outcome": report.outcome, "seconds": round(report.duration, 2),
        "error": _short(report.longreprtext) if report.failed else "",
    })


def _short(text: str) -> str:
    return text if len(text) < 2000 else text[:1200] + "\n...\n" + text[-600:]


def pytest_sessionstart(session):
    shutil.rmtree(REPORT_DIR, ignore_errors=True)


def pytest_sessionfinish(session):
    if not _results:
        return
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "report.json").write_text(
        json.dumps({"results": _results, "shots": _shots}, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for r in _results:
        shots = "".join(
            f'<a href="shots/{s}"><img src="shots/{s}" width="320" loading="lazy"></a> ' for s in _shots.get(r["id"], []))
        err = f"<pre>{html.escape(r['error'])}</pre>" if r["error"] else ""
        rows.append(f'<section class="{r["outcome"]}"><h3>{html.escape(r["id"])} — {r["outcome"]} ({r["seconds"]}s)</h3>{err}{shots}</section>')
    (REPORT_DIR / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>E2E 보고서</title>"
        "<style>body{font:14px sans-serif;margin:24px}section{border-left:6px solid #3a3;padding:4px 12px;margin:12px 0}"
        "section.failed{border-color:#c33}img{border:1px solid #888;margin:4px}pre{background:#fee;padding:8px;overflow:auto}</style>"
        "<h1>E2E 보고서</h1>" + "".join(rows), encoding="utf-8")
