"""트레이 상주 + 백그라운드 감시를 한 프로세스로 묶는다. (SPEC §6 2단계)

트레이 아이콘은 메인 스레드에서, Player.log 감시는 백그라운드 데몬 스레드에서 돈다.
usage: python -m lumia_briefing_room.cli.app [watch.py 와 동일한 옵션]
"""

import logging
import socket
import sys
import threading
import webbrowser

from lumia_briefing_room import autostart
from lumia_briefing_room.cli import serve as serve_cli
from lumia_briefing_room.cli.watch import build_parser, run
from lumia_briefing_room.config import load_config, resolve_config_path
from lumia_briefing_room.pipeline.cleanup import cleanup_loop, make_cleanup_runner
from lumia_briefing_room.tray import build_icon

log = logging.getLogger("lumia_briefing_room.app")


def resolve_port(port_setting) -> int:
    """SPEC §7.7 ui.port: "auto" 면 빈 포트를 하나 골라온다."""
    if port_setting == "auto":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    return int(port_setting)


def make_on_open(*, host="127.0.0.1", port=8000, config_path=None, open_browser=webbrowser.open):
    """트레이 "열기": 서버를 (최초 1회만) 띄우고 브라우저로 연다.

    pystray 의 icon.run() 이 이미 메인 스레드를 쓰고 있어 pywebview 의
    webview.start() 를 여기서 같이 호출할 수 없다(둘 다 메인 스레드를 요구) —
    그래서 트레이 경로는 항상 기본 브라우저를 연다. 전용 창(pywebview)이 필요하면
    `python -m lumia_briefing_room.cli.serve` 를 독립 실행한다 (plan-ui.md §4-1).
    """
    state: dict = {}

    def on_open() -> None:
        if "server" not in state:
            cfg = load_config(config_path)
            app = serve_cli.build_app(cfg, config_path=config_path)
            server, thread = serve_cli.run_server_in_thread(app, host=host, port=port)
            serve_cli.wait_until_started(server)
            state["server"] = server
            state["thread"] = thread
        open_browser(f"http://{host}:{port}/")

    return on_open


def autostart_command() -> str:
    """레지스트리에 등록할 명령. --onedir 배포 시 실행 파일 경로로 교체될 자리다."""
    return f'"{sys.executable}" -m lumia_briefing_room.cli.app'


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
    return open_ui or not cfg.ui.start_minimized


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    parser.add_argument("--open-ui", action="store_true", help="시작하자마자 열람 UI 를 연다")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    apply_autostart_setting(cfg)

    on_toggle_watch, watch_enabled = make_watch_controller(args)
    threading.Thread(
        target=cleanup_loop, args=(make_cleanup_runner(args.config), threading.Event()), daemon=True
    ).start()

    on_open = make_on_open(
        host="127.0.0.1", port=resolve_port(cfg.ui.port), config_path=resolve_config_path(args.config)
    )

    if should_open_ui_on_start(cfg, open_ui=args.open_ui):
        threading.Thread(target=on_open, daemon=True).start()

    icon = build_icon(
        on_open=on_open,
        on_toggle_watch=on_toggle_watch,
        watch_enabled=watch_enabled,
        on_quit=lambda: _on_quit(),
    )
    _icon_ref["icon"] = icon
    icon.run()


_icon_ref: dict = {}


def _run_watch_safely(args, stop_event: threading.Event) -> None:
    try:
        run(args, should_stop=stop_event.is_set)
    except SystemExit as exc:
        log.error("감시를 시작하지 못했다 - %s", exc)
    except Exception:
        log.exception("감시 중 처리되지 않은 예외가 발생했다")


def _on_quit() -> None:
    icon = _icon_ref.get("icon")
    if icon is not None:
        icon.stop()


if __name__ == "__main__":
    main()
