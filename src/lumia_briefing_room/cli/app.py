"""트레이 상주 + 백그라운드 감시를 한 프로세스로 묶는다. (SPEC §6 2단계)

트레이 아이콘은 메인 스레드에서, Player.log 감시는 백그라운드 데몬 스레드에서 돈다.
usage: python -m lumia_briefing_room.cli.app [watch.py 와 동일한 옵션]
"""

import logging
import sys
import threading

from lumia_briefing_room import autostart
from lumia_briefing_room.cli.watch import build_parser, run
from lumia_briefing_room.config import load_config
from lumia_briefing_room.tray import build_icon

log = logging.getLogger("lumia_briefing_room.app")


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

    apply_autostart_setting(load_config(args.config))

    watch_thread = threading.Thread(target=_run_watch_safely, args=(args,), daemon=True)
    watch_thread.start()

    icon = build_icon(
        on_open=_on_open,
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


def _on_open() -> None:
    # SPEC 3단계(열람 UI)가 아직 없다 — 만들어지면 여기서 로컬 서버 주소를 연다.
    log.info("열람 UI 는 아직 없다 (SPEC 3단계 대기)")


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
