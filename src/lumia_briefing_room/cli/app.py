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
from lumia_briefing_room.config import load_config
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


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)
    apply_autostart_setting(cfg)

    watch_thread = threading.Thread(target=_run_watch_safely, args=(args,), daemon=True)
    watch_thread.start()

    on_open = make_on_open(
        host="127.0.0.1", port=resolve_port(cfg.ui.port), config_path=args.config
    )

    icon = build_icon(
        on_open=on_open,
        on_toggle_watch=_on_toggle_watch,
        watch_enabled=lambda: True,  # TODO: 실제 정지/재개 배선 - 확인 필요(plan-pipeline.md §3)
        on_quit=lambda: _on_quit(),
    )
    _icon_ref["icon"] = icon
    icon.run()


_icon_ref: dict = {}


def _run_watch_safely(args) -> None:
    try:
        run(args)
    except SystemExit as exc:
        log.error("감시 스레드 종료: %s", exc)
    except Exception:
        log.exception("감시 스레드에서 처리되지 않은 예외")


def _on_toggle_watch() -> None:
    # TODO: run_forever 루프에 정지 신호를 보내는 배선이 없다. 지금은 표시만
    # 바뀌지 않는다 - plan-pipeline.md §3 확인 필요.
    log.warning("감시 정지/재개는 아직 구현되지 않았다")


def _on_quit() -> None:
    icon = _icon_ref.get("icon")
    if icon is not None:
        icon.stop()


if __name__ == "__main__":
    main()
