"""개발용 자동 재시작: src 아래 .py 가 바뀌면 앱(트레이 상주 + 서버)을 껐다가 다시 띄운다.

usage: python tools/dev_run.py [cli.app 과 동일한 옵션]

브라우저는 첫 기동에만 자동으로 열고(--open-ui), 재시작 때는 열지 않는다(열려 있는 탭을 새로고침).
앱이 정상 종료(트레이 "종료")하면 이 스크립트도 끝나고, 오류로 죽으면 다음 변경까지 기다린다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"
FRONTEND_SRC = FRONTEND / "src"
FRONTEND_EXTS = (".ts", ".tsx", ".css", ".html", ".svg")
DEBOUNCE_MS = 500
STOP_TIMEOUT = 5.0


def is_source_change(changes) -> bool:
    return any(str(p).endswith(".py") and "__pycache__" not in str(p) for _, p in changes)


def is_frontend_change(changes) -> bool:
    return any(Path(p).is_relative_to(FRONTEND_SRC) and str(p).endswith(FRONTEND_EXTS) for _, p in changes)


def build_command(app_args: list[str], *, first_start: bool) -> list[str]:
    args = [a for a in app_args if a != "--open-ui"]
    if first_start:
        args.append("--open-ui")
    return [sys.executable, "-m", "lumia_briefing_room.cli.app", *args]


def stop(proc, *, timeout: float = STOP_TIMEOUT) -> None:
    if proc.poll() is not None:
        return
    pid = getattr(proc, "pid", None)
    if sys.platform == "win32" and pid:
        # venv 의 python.exe 는 실제 인터프리터를 자식으로 띄우는 런처라 terminate() 만으로는 자식이 남는다.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _spawn(cmd):
    return subprocess.Popen(cmd, cwd=ROOT)


def _build_frontend() -> None:
    result = subprocess.run("npm run build", cwd=FRONTEND, shell=True)
    print("[dev] 프론트 빌드 " + ("완료 - 브라우저를 새로고침하세요." if result.returncode == 0 else "실패"), flush=True)


def _default_watch():
    from watchfiles import watch

    return watch(SRC, FRONTEND_SRC, debounce=DEBOUNCE_MS, yield_on_timeout=True, rust_timeout=1000)


def run(app_args: list[str], *, watch=None, spawn=_spawn, build_frontend=_build_frontend) -> None:
    proc = spawn(build_command(app_args, first_start=True))
    for changes in watch if watch is not None else _default_watch():
        if is_frontend_change(changes):
            print("[dev] 프론트 변경을 감지해 빌드합니다.", flush=True)
            build_frontend()
        if not is_source_change(changes):
            if proc is not None and proc.poll() == 0:
                print("[dev] 앱이 종료되어 개발 실행도 끝냅니다.", flush=True)
                return
            continue
        print("[dev] 코드 변경을 감지해 재시작합니다.", flush=True)
        if proc is not None:
            stop(proc)
        proc = spawn(build_command(app_args, first_start=False))
    if proc is not None:
        stop(proc)


def main() -> None:
    try:
        run(sys.argv[1:])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
