"""트레이 상주 + 백그라운드 감시를 한 프로세스로 묶는다. (SPEC §6 2단계)

트레이 아이콘은 메인 스레드에서, Player.log 감시는 백그라운드 데몬 스레드에서 돈다.
usage: python -m lumia_briefing_room.cli.app [watch.py 와 동일한 옵션]
"""

import logging
import os
import socket
import sys
import threading
import webbrowser

from lumia_briefing_room import autostart, paths, procs, selftest, startup
from lumia_briefing_room.cli import serve as serve_cli
from lumia_briefing_room.cli.watch import build_parser, run
from lumia_briefing_room.consent import needs_first_run
from lumia_briefing_room.logsetup import default_log_path
from lumia_briefing_room.single_instance import SingleInstance
from lumia_briefing_room.config import load_config, resolve_config_path
from lumia_briefing_room.pipeline.cleanup import cleanup_loop, make_cleanup_runner
from lumia_briefing_room.tray import build_icon

log = logging.getLogger("lumia_briefing_room.app")


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


HOSTNAME = "lumia-briefingroom.localhost"
HTTP_PORT = 80
DEFAULT_PORT = 8765


def port_candidates(port_setting, *, fallback_range: int = 20) -> list[int]:
    """SPEC §7.7 ui.port: 80번(주소에서 포트 생략) → 설정 포트 → 그 뒤 +20 순.

    "auto" 는 예전 기본값이라 설정 파일에 남아 있을 수 있어, 기본 포트(8765)와 같은 뜻으로 취급한다.

    순서를 고정해 두는 이유: 포트가 바뀌면 브라우저 origin 이 달라져 localStorage 가 초기화된다.
    """
    base = DEFAULT_PORT if port_setting == "auto" else int(port_setting)
    ports = [HTTP_PORT, *range(base, base + fallback_range + 1)]
    return list(dict.fromkeys(ports))


def resolve_port(port_setting, *, fallback_range: int = 20, is_free=_is_free) -> int:
    for port in port_candidates(port_setting, fallback_range=fallback_range):
        if is_free(port):
            return port
    return _free_port()


def access_url(port: int, *, hostname: str = HOSTNAME) -> str:
    """사용자에게 보이는 주소. 서버는 127.0.0.1 에만 바인드하고, *.localhost 는 브라우저가 스스로 루프백으로 푼다."""
    suffix = "" if port == HTTP_PORT else f":{port}"
    return f"http://{hostname}{suffix}/"


def make_on_open(*, host="127.0.0.1", port=8000, config_path=None, open_browser=webbrowser.open):
    """트레이 "열기": 서버를 (최초 1회만) 띄우고 브라우저로 연다.

    pystray 의 icon.run() 이 이미 메인 스레드를 쓰고 있어 pywebview 의
    webview.start() 를 여기서 같이 호출할 수 없다(둘 다 메인 스레드를 요구) —
    그래서 트레이 경로는 항상 기본 브라우저를 연다. 전용 창(pywebview)이 필요하면
    `python -m lumia_briefing_room.cli.serve` 를 독립 실행한다 (plan-ui.md §4-1).
    """
    state: dict = {}
    start_lock = threading.Lock()

    def on_open() -> None:
        with start_lock:
            if "server" not in state:
                cfg = load_config(config_path)
                app = serve_cli.build_app(cfg, config_path=config_path)
                server, thread = serve_cli.run_server_in_thread(app, host=host, port=port)
                serve_cli.wait_until_started(server)
                state["server"] = server
                state["thread"] = thread
        open_browser(access_url(port))

    return on_open


def build_autostart_command(*, frozen: bool, executable: str) -> str:
    """빌드본에서 sys.executable 은 앱 exe 라 `-m` 인자가 의미 없다."""
    if frozen:
        return f'"{executable}"'
    return f'"{executable}" -m lumia_briefing_room.cli.app'


def autostart_command() -> str:
    """레지스트리에 등록할 명령. 시작할 때마다 덮어쓰므로 개발 PC 에서 등록한 옛 명령도 바뀐다."""
    return build_autostart_command(frozen=paths.is_frozen(), executable=sys.executable)


def apply_autostart_setting(cfg, *, app_name: str | None = None) -> None:
    """SPEC §7.7 ui.autoStart 를 실제 레지스트리 상태에 반영한다."""
    if not autostart.is_supported():
        return
    name = app_name or autostart.APP_NAME
    if cfg.ui.auto_start:
        autostart.enable(autostart_command(), app_name=name)
    else:
        autostart.disable(app_name=name)


def make_watch_controller(args, *, auto_start: bool = True):
    """트레이 "감시 중" 토글의 실제 시작/정지 배선. (plan-pipeline.md §3-5 해결)

    `run()` 이 `should_stop` 으로 넘겨받는 `stop_event.is_set` 을 `run_polling()` 이
    폴링마다 확인하므로, 정지 요청은 다음 폴링 주기 안에 반영된다. 재개는
    새 스레드로 `run()` 을 처음부터 다시 부르는 것과 같다 — 이미 끝난 경기는
    `ProcessedState` 로 이미 처리한 매치를 다시 건드리지 않으니 안전하다.
    """
    state = {"thread": None, "stop_event": threading.Event(), "running": False}

    def _start() -> None:
        state["stop_event"].clear()
        thread = threading.Thread(
            target=_run_watch_safely, args=(args, state["stop_event"]), daemon=True
        )
        state["thread"] = thread
        state["running"] = True
        thread.start()

    def _stop() -> None:
        state["stop_event"].set()
        state["running"] = False

    def on_toggle_watch() -> None:
        if state["running"]:
            _stop()
        else:
            _start()

    def watch_enabled() -> bool:
        return state["running"]

    if auto_start:
        _start()

    return on_toggle_watch, watch_enabled


def should_open_ui_on_start(cfg, *, open_ui: bool) -> bool:
    """첫 실행 화면이 필요하면 ui.startMinimized 와 무관하게 UI 를 연다(plan-deploy.md D3)."""
    return open_ui or not cfg.ui.start_minimized or needs_first_run(cfg.consent.version)


def open_logs_folder() -> None:
    folder = default_log_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    os.startfile(folder)


def run_selftest_command(args) -> bool:
    """번들 점검 보고서를 로그 폴더에 남긴다. 콘솔이 없는 빌드본에서는 파일을 열어서 보여 준다."""
    results, ok = selftest.run_all()
    report = selftest.format_report(results, header="루미아 브리핑룸 자체 점검")
    path = default_log_path().parent / "selftest.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    log.info("자체 점검 보고서를 남겼다: %s (%s)", path, "모두 통과" if ok else "실패 있음")

    if startup.console_logging_wanted():
        print(report)
    elif sys.platform == "win32":
        os.startfile(path)
    return ok


def main(argv: list[str] | None = None) -> None:
    startup.setup_logging()
    startup.install_excepthooks()
    parser = build_parser()
    parser.add_argument("--open-ui", action="store_true", help="시작하자마자 열람 UI 를 연다")
    parser.add_argument("--selftest", action="store_true", help="번들 리소스를 점검하고 보고서를 남긴다")
    args = parser.parse_args(argv)

    if args.selftest:
        run_selftest_command(args)
        return

    instance = SingleInstance()
    if not instance.acquire():
        log.info("이미 실행 중이다 - 떠 있는 앱의 UI 를 열고 종료한다")
        instance.signal_existing()
        return
    try:
        _run_app(args, instance)
    except Exception as exc:
        startup.report_fatal(f"시작하지 못했습니다: {exc}")
        raise
    finally:
        instance.close()


def _run_app(args, instance: SingleInstance) -> None:
    cfg = load_config(args.config)
    procs.kill_children_on_exit()
    if cfg.app.low_priority:
        procs.lower_current_process_priority()
    apply_autostart_setting(cfg)

    on_toggle_watch, watch_enabled = make_watch_controller(args)
    threading.Thread(
        target=cleanup_loop, args=(make_cleanup_runner(args.config), threading.Event()), daemon=True
    ).start()

    on_open = make_on_open(
        host="127.0.0.1", port=resolve_port(cfg.ui.port), config_path=resolve_config_path(args.config)
    )

    instance.listen(on_open)
    if should_open_ui_on_start(cfg, open_ui=args.open_ui):
        threading.Thread(target=on_open, daemon=True).start()

    icon = build_icon(
        on_open=on_open,
        on_toggle_watch=on_toggle_watch,
        watch_enabled=watch_enabled,
        on_quit=lambda: _on_quit(),
        on_open_logs=open_logs_folder,
    )
    _icon_ref["icon"] = icon
    icon.run()


_icon_ref: dict = {}


WATCH_RETRY_SEC = 10.0


def _run_watch_safely(args, stop_event: threading.Event, *, run_fn=None, retry_sec: float = WATCH_RETRY_SEC) -> None:
    """녹화 폴더가 아직 없는 첫 실행처럼 시작 조건이 안 맞으면, 첫 실행 화면에서 설정을 고칠 때까지 기다렸다 다시 시도한다."""
    run_fn = run_fn or run
    last_error = None
    while not stop_event.is_set():
        try:
            run_fn(args, should_stop=stop_event.is_set)
            return
        except SystemExit as exc:
            if str(exc) != last_error:
                log.error("감시를 시작하지 못했다 - %s (%d초마다 다시 시도한다)", exc, retry_sec)
                last_error = str(exc)
            if stop_event.wait(retry_sec):
                return
        except Exception:
            log.exception("감시 중 처리되지 않은 예외가 발생했다")
            return


def _on_quit() -> None:
    icon = _icon_ref.get("icon")
    if icon is not None:
        icon.stop()


if __name__ == "__main__":
    main()
