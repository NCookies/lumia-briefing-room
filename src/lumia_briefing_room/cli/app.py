"""트레이 상주 + 백그라운드 감시를 한 프로세스로 묶는다. (SPEC §6 2단계)

트레이 아이콘은 메인 스레드에서, Player.log 감시는 백그라운드 데몬 스레드에서 돈다.
usage: python -m lumia_briefing_room.cli.app [watch.py 와 동일한 옵션]
"""

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

from lumia_briefing_room import autostart, paths, procs, selftest, startup
from lumia_briefing_room.cli import serve as serve_cli
from lumia_briefing_room.cli.watch import build_parser, run
from lumia_briefing_room.telemetry.sender import TelemetrySender
from lumia_briefing_room.updater import Updater, launch_installer
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


UPDATE_QUIT_DELAY_SEC = 3.0
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


def make_on_open(
    *,
    host="127.0.0.1",
    port=8000,
    config_path=None,
    open_browser=webbrowser.open,
    on_recording_root_changed=None,
    on_update_launched=None,
):
    """트레이 "열기": 서버를 (최초 1회만) 띄우고 브라우저로 연다.

    pystray 의 icon.run() 이 이미 메인 스레드를 쓰고 있어 pywebview 의
    webview.start() 를 여기서 같이 호출할 수 없다(둘 다 메인 스레드를 요구) —
    그래서 트레이 경로는 항상 기본 브라우저를 연다. 전용 창(pywebview)이 필요하면
    `python -m lumia_briefing_room.cli.serve` 를 독립 실행한다 (plan-ui.md §4-1).
    """
    state: dict = {}
    start_lock = threading.Lock()

    def ensure_server() -> None:
        with start_lock:
            if "server" not in state:
                cfg = load_config(config_path)
                app = serve_cli.build_app(cfg, config_path=config_path)
                if on_recording_root_changed is not None:
                    app.state.on_recording_root_changed = on_recording_root_changed
                if on_update_launched is not None:
                    app.state.on_update_launched = on_update_launched
                if paths.is_frozen():
                    app.state.update_launcher = deferred_installer.launcher
                server, thread = serve_cli.run_server_in_thread(app, host=host, port=port)
                serve_cli.wait_until_started(server)
                state["server"] = server
                state["thread"] = thread
                state["app"] = app

    def client_hits() -> int:
        app = state.get("app")
        return getattr(getattr(app, "state", None), "request_count", 0) if app is not None else 0

    def on_open() -> None:
        ensure_server()
        open_browser(access_url(port))

    on_open.ensure_server = ensure_server
    on_open.client_hits = client_hits
    return on_open


def open_after_update(on_open, *, wait_sec: float = 8.0, poll_sec: float = 0.5, sleep=time.sleep) -> None:
    """업데이트 뒤 서버를 띄우고, 열려 있던 탭이 스스로 돌아오지 않으면 브라우저 창을 직접 연다.

    옛 탭은 서버가 되살아나면 스스로 새로고침하므로 그 요청이 들어오면 창을 또 열지 않는다(중복 방지).
    """
    on_open.ensure_server()
    waited = 0.0
    while waited < wait_sec:
        if on_open.client_hits() > 0:
            return
        sleep(poll_sec)
        waited += poll_sec
    log.info("업데이트 뒤 열려 있던 화면이 없어 브라우저를 연다")
    on_open()


def make_watch_controller(args, *, auto_start: bool = True):
    """트레이 "감시 중" 토글의 실제 시작/정지 배선. (plan-pipeline.md §3-5 해결)

    `run()` 이 `should_stop` 으로 넘겨받는 `stop_event.is_set` 을 `run_polling()` 이
    폴링마다 확인하므로, 정지 요청은 다음 폴링 주기 안에 반영된다. 재개는
    새 스레드로 `run()` 을 처음부터 다시 부르는 것과 같다 — 이미 끝난 경기는
    `ProcessedState` 로 이미 처리한 매치를 다시 건드리지 않으니 안전하다.
    """
    state = {"thread": None, "stop_event": threading.Event(), "running": False}

    def _start() -> None:
        # 새 Event 를 쓴다 — 옛 스레드가 아직 끝나기 전에 같은 Event 를 clear 하면 옛 감시가 계속 돈다.
        state["stop_event"] = threading.Event()
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

    def restart() -> None:
        """감시는 시작 때 설정(녹화 폴더 등)을 한 번만 읽는다. 옵션에서 바꾸면 돌던 감시를 새 설정으로 다시 시작한다.

        사용자가 감시를 꺼 둔 상태였다면 켜지 않는다.
        """
        if not state["running"]:
            return
        state["stop_event"].set()
        old = state["thread"]
        if old is not None:
            old.join(timeout=RESTART_JOIN_SEC)
        _start()

    on_toggle_watch.restart = restart

    def watch_enabled() -> bool:
        return state["running"]

    if auto_start:
        _start()

    return on_toggle_watch, watch_enabled


def start_telemetry(config_path, *, sender=None):
    """동의한 라벨·오류 로그를 하루 한 번 서버로 보내는 스레드. 동의가 꺼져 있으면 네트워크를 쓰지 않는다. (plan-deploy.md D10)"""
    sender = sender or TelemetrySender(config_path=config_path)
    stop = threading.Event()
    thread = threading.Thread(target=sender.run_forever, args=(stop,), daemon=True, name="telemetry")
    thread.start()
    return thread, stop


class DeferredInstaller:
    """설치기 실행을 앱이 완전히 종료된 뒤로 미룬다.

    설치기는 시작할 때 실행 중인 앱(`AppMutex`)을 발견하면 조용한 모드에서 곧바로 중단한다(종료 코드 1). 그래서 설치기를 먼저 띄우고
    앱을 나중에 닫으면 설치가 절대 진행되지 않는다. 앱이 단일 실행 잠금까지 놓은 뒤(`main` 의 끝)에 실행해야 한다. (plan-deploy.md D9)
    """

    def __init__(self, launch=launch_installer):
        self._launch = launch
        self._path = None

    def launcher(self, path) -> None:
        self._path = path

    def run_pending(self) -> None:
        path, self._path = self._path, None
        if path is None:
            return
        try:
            self._launch(path)
        except Exception:
            log.exception("종료 뒤 설치기를 실행하지 못했다: %s", path)


deferred_installer = DeferredInstaller()


def update_notice(release: dict) -> tuple[str, str]:
    return f"새 버전 {release['version']} 이 나왔습니다. 앱 옵션의 '정보·진단' 탭에서 업데이트할 수 있습니다.", "루미아 브리핑룸"


def first_run_notice() -> tuple[str, str]:
    return (
        "루미아 브리핑룸이 실행됐습니다. 곧 브라우저에 첫 화면이 열립니다. 열리지 않으면 작업표시줄 오른쪽 아래(∧ 안)의 아이콘을 눌러 주세요.",
        "루미아 브리핑룸",
    )


def announce_first_run(cfg, notify) -> bool:
    """첫 실행 화면이 아직 필요하면 알림을 띄운다. 설치 직후 아무 반응이 없다고 오해하지 않게 한다."""
    if not needs_first_run(cfg.consent.version):
        return False
    try:
        notify(*first_run_notice())
    except Exception:
        log.info("첫 실행 알림을 띄우지 못했다", exc_info=False)
    return True


def start_update_checks(config_path, *, notify, updater=None):
    """`update.check` 가 켜져 있으면 시작 시와 하루 1회 새 버전을 확인해 알리는 스레드. 꺼져 있으면 네트워크를 쓰지 않는다. (plan-deploy.md D9)"""
    updater = updater or Updater(config_path=config_path, notify=notify)
    stop = threading.Event()
    thread = threading.Thread(target=updater.run_forever, args=(stop,), daemon=True, name="update-check")
    thread.start()
    return thread, stop


def quit_after_update_launch(on_quit, *, delay: float = UPDATE_QUIT_DELAY_SEC, timer=threading.Timer):
    """설치기가 뜬 뒤 앱을 종료한다. 화면이 "설치기를 실행했습니다" 를 받아 볼 시간을 잠깐 둔다."""
    def quit_soon() -> None:
        timer(delay, on_quit).start()

    return quit_soon


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
    elif sys.platform == "win32" and not getattr(args, "quiet", False):
        os.startfile(path)
    return ok


def build_app_parser():
    parser = build_parser()
    parser.add_argument("--open-ui", action="store_true", help="시작하자마자 열람 UI 를 연다")
    parser.add_argument(
        "--start-server",
        action="store_true",
        help="브라우저는 열지 않고 열람 서버만 먼저 띄운다(업데이트 뒤 재시작에서 열려 있던 탭이 되살아나게 한다)",
    )
    parser.add_argument("--selftest", action="store_true", help="번들 리소스를 점검하고 보고서를 남긴다")
    parser.add_argument("--quiet", action="store_true", help="--selftest 보고서를 자동으로 열지 않는다")
    return parser


def main(argv: list[str] | None = None) -> None:
    startup.setup_logging()
    startup.install_excepthooks()
    parser = build_app_parser()
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
        deferred_installer.run_pending()


def _run_app(args, instance: SingleInstance) -> None:
    cfg = load_config(args.config)
    procs.kill_children_on_exit()
    if cfg.app.low_priority:
        procs.lower_current_process_priority()
    autostart.apply_setting(cfg)

    on_toggle_watch, watch_enabled = make_watch_controller(args)
    threading.Thread(
        target=cleanup_loop, args=(make_cleanup_runner(args.config), threading.Event()), daemon=True
    ).start()
    start_telemetry(resolve_config_path(args.config))

    on_open = make_on_open(
        host="127.0.0.1",
        port=resolve_port(cfg.ui.port),
        config_path=resolve_config_path(args.config),
        on_recording_root_changed=on_toggle_watch.restart,
        on_update_launched=quit_after_update_launch(lambda: _on_quit()),
    )

    instance.listen(on_open)
    notice = Updater(config_path=resolve_config_path(args.config)).just_updated()
    if notice or args.start_server:
        if should_open_ui_on_start(cfg, open_ui=args.open_ui):
            threading.Thread(target=on_open.ensure_server, daemon=True).start()
        elif notice:
            threading.Thread(target=open_after_update, args=(on_open,), daemon=True).start()
        else:
            threading.Thread(target=on_open.ensure_server, daemon=True).start()
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

    def on_tray_ready(tray_icon) -> None:
        tray_icon.visible = True
        announce_first_run(cfg, tray_icon.notify)
        start_update_checks(
            resolve_config_path(args.config),
            notify=lambda release: tray_icon.notify(*update_notice(release)),
        )

    icon.run(setup=on_tray_ready)


_icon_ref: dict = {}


WATCH_RETRY_SEC = 10.0
RESTART_JOIN_SEC = 15.0


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
